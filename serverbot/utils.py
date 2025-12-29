import time
import json
import urllib.parse
import shutil
import os
from pathlib import Path

from django.utils import timezone
from DrissionPage import ChromiumPage, ChromiumOptions
from .models import StakeAccount, ProxyPool


# 1. 代理插件生成逻辑 (处理带账号密码的代理)
def get_proxy_ext(proxy_url, t_id):
    """解决 DrissionPage 报错的关键补丁：生成临时扩展处理账号密码"""
    try:
        # 兼容处理数据库存储的完整 URI
        p = urllib.parse.urlparse(proxy_url)
        user = p.username
        pwd = p.password
        host = p.hostname
        port = p.port

        if not all([user, pwd, host, port]):
            return None
    except Exception:
        return None

    manifest_json = {
        "version": "1.0.0",
        "manifest_version": 2,
        "name": "Proxy",
        "permissions": ["proxy", "tabs", "unlimitedStorage", "storage", "<all_urls>", "webRequest",
                        "webRequestBlocking"],
        "background": {"scripts": ["background.js"]}
    }

    background_js = f'''
    var config = {{
        mode: "fixed_servers",
        rules: {{
            singleProxy: {{
                scheme: "http",
                host: "{host}",
                port: parseInt({port})
            }},
            bypassList: ["localhost"]
        }}
    }};
    chrome.proxy.settings.set({{value: config, scope: "regular"}}, function() {{}});
    chrome.webRequest.onAuthRequired.addListener(
        function(details) {{
            return {{
                authCredentials: {{
                    username: "{user}",
                    password: "{pwd}"
                }}
            }};
        }},
        {{urls: ["<all_urls>"]}},
        ["blocking"]
    );
    '''

    ext_dir = os.path.abspath(f'./proxy_ext_{t_id}')
    if not os.path.exists(ext_dir):
        os.makedirs(ext_dir)

    with open(os.path.join(ext_dir, 'manifest.json'), 'w') as f:
        json.dump(manifest_json, f)
    with open(os.path.join(ext_dir, 'background.js'), 'w') as f:
        f.write(background_js)
    return ext_dir


def run_pre_logic(account):
    """
    针对中文版 Stake 优化的过盾逻辑 - 已修复多开冲突
    """
    account.bypass_trigger_time = timezone.now()
    account.save()

    # 1. 代理分配逻辑
    if not account.proxy:
        print(f"[*] 账号 {account.username} 未绑定代理，正在分配...")
        proxy = ProxyPool.objects.filter(is_active=True, stakeaccount__isnull=True).first()
        if not proxy:
            proxy = ProxyPool.objects.filter(is_active=True).order_by('?').first()

        if proxy:
            StakeAccount.objects.filter(pk=account.id).update(proxy=proxy)
            account.proxy = proxy
        else:
            print(f"[!] 错误：账号 {account.username} 无可用代理")
            return

    # --- 获取并更新代理归属地 ---
    if not getattr(account.proxy, 'location', None):
        print(f"[*] 正在识别代理归属地: {account.proxy.address.split('@')[-1]}...")
        location = fetch_ip_location(account.proxy.address)
        ProxyPool.objects.filter(pk=account.proxy.pk).update(location=location)
        account.proxy.location = location

    print(
        f"[+] 账号: {account.username} | 代理: {account.proxy.address.split(':')[-1]} | 地区: {account.proxy.location}")

    # 2. 启动环境
    ext_path = get_proxy_ext(account.proxy.address, account.id)
    co = ChromiumOptions()

    # --- 【关键修复：解决多开浏览器冲突】 ---
    # 为每个账号分配一个独立端口（9000 + ID），防止多个浏览器挤在同一个端口导致失效
    unique_port = 9000 + (account.id % 1000)
    co.set_address(f'127.0.0.1:{unique_port}')

    co.set_load_mode('none')
    co.set_user_data_path(os.path.abspath(f'./profiles/p_{account.id}'))
    if ext_path:
        co.add_extension(ext_path)

    # 每个线程现在会启动完全独立的浏览器进程
    page = ChromiumPage(co)

    try:
        print(f"[*] {account.username} 正在发起请求 (端口: {unique_port})...")
        page.get('https://stake.com/')

        start_time = time.time()
        while True:
            if time.time() - start_time > 300:
                print(f"[×] {account.username} 过盾超时")
                break

            curr_url = page.url
            curr_title = page.title

            # --- [判定逻辑：是否已经成功进入 Stake] ---
            is_in_stake = (
                                  ("Stake" in curr_title and "赌场" in curr_title) or
                                  ("manager.com" in curr_url and "challenges" not in curr_url)
                          ) and (
                                  page.ele('@data-testid=search-button', timeout=0.5) or
                                  page.ele('text=娱乐场', timeout=0.5) or
                                  page.ele('text=体育', timeout=0.5) or
                                  page.ele('text=Casino', timeout=0.5)
                          )

            if is_in_stake:
                print(f"[!] {account.username}: 识别到 Stake 中文主站！准备收割 Cookie...")
                time.sleep(10)

                cookies = page.cookies()
                cookies_dict = {c['name']: c['value'] for c in cookies}

                if 'cf_clearance' in cookies_dict:
                    print(f"[✔] 账号 {account.username} 过盾成功，Cookie 已保存。")
                    # 仅更新必要的字段，极大减少锁定时间
                    StakeAccount.objects.filter(pk=account.pk).update(
                        cookies_json=json.dumps(cookies),
                        user_agent=page.user_agent,
                        bypass_success_time=timezone.now()
                    )
                    break
                else:
                    print(f"[?] 已进入主站但 cf_clearance 尚未写入，继续轮询...")

            # --- [判定逻辑：识别是否还在盾里] ---
            is_cf = (
                    "challenges" in curr_url or
                    page.ele('text=Verifying you are human', timeout=0.1) or
                    page.ele('text=确认您是真人', timeout=0.1)
            )

            if is_cf:
                print(f"[.] {account.username}: 仍处于验证页面...")
            else:
                print(f"[.] {account.username}: 正在等待组件渲染... 当前标题: {curr_title}")

            time.sleep(4)

    except Exception as e:
        print(f"[!] {account.username} 运行异常: {e}")
    finally:
        print(f"[*] 正在关闭账号 {account.username} 的浏览器...")
        # 注意：多开环境下必须使用 quit() 彻底杀掉进程，释放端口
        page.quit()
        if ext_path and os.path.exists(ext_path):
            try:
                shutil.rmtree(ext_path)
            except:
                pass

def parse_proxy(raw_url):
    """解析工具函数"""
    p = urllib.parse.urlparse(raw_url)
    return {'user': p.username, 'pass': p.password, 'host': p.hostname, 'port': p.port}


def fetch_ip_location(proxy_addr):
    """通过代理获取其归属地"""
    proxies = {"http": proxy_addr, "https": proxy_addr}
    try:
        # 使用 ip-api.com，无需 Key，直接返回 JSON
        # 注意：这里也用 curl_cffi 防止被反爬
        from curl_cffi import requests as curl_requests
        resp = curl_requests.get(
            "http://ip-api.com/json/?lang=zh-CN",
            proxies=proxies,
            timeout=5,
            impersonate="chrome110"
        )
        data = resp.json()
        if data.get('status') == 'success':
            # 返回 格式如：香港、德国、美国
            return data.get('country')
    except:
        pass
    return "未知"