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
    针对中文版 Stake 优化的过盾逻辑
    """
    account.bypass_trigger_time = timezone.now()
    account.save()

    # 1. 代理分配 (保持原样)
    if not account.proxy:
        proxy = ProxyPool.objects.filter(is_active=True, stakeaccount__isnull=True).first()
        if not proxy:
            proxy = ProxyPool.objects.filter(is_active=True).order_by('?').first()
        if proxy:
            StakeAccount.objects.filter(pk=account.id).update(proxy=proxy)
            account.proxy = proxy

    # 2. 启动环境
    ext_path = get_proxy_ext(account.proxy.address, account.id)
    co = ChromiumOptions()
    co.set_load_mode('none')
    co.set_user_data_path(os.path.abspath(f'./profiles/p_{account.id}'))
    if ext_path:
        co.add_extension(ext_path)

    page = ChromiumPage(co)

    try:
        print(f"[*] {account.username} 正在发起请求...")
        page.get('https://stake.com/')

        start_time = time.time()
        while True:
            if time.time() - start_time > 300:
                print(f"[×] {account.username} 过盾超时")
                break

            curr_url = page.url
            curr_title = page.title

            # --- [判定逻辑：是否已经成功进入 Stake] ---
            # 1. 检查你提供的 Log 中的中文标题
            # 2. 检查中文界面下的常用按钮文字
            is_in_stake = (
                                  ("Stake" in curr_title and "赌场" in curr_title) or
                                  ("stake.com" in curr_url and "challenges" not in curr_url)
                          ) and (
                                  page.ele('@data-testid=search-button', timeout=0.5) or
                                  page.ele('text=娱乐场', timeout=0.5) or  # 中文版关键词
                                  page.ele('text=体育', timeout=0.5) or  # 中文版关键词
                                  page.ele('text=Casino', timeout=0.5)  # 英文版兜底
                          )

            if is_in_stake:
                print(f"[!] {account.username}: 识别到 Stake 中文主站！准备收割 Cookie...")
                # 📢 既然已经进去了，说明盾肯定没了，等 10 秒让 Cookie 刷新
                time.sleep(10)

                cookies = page.cookies()
                cookies_dict = {c['name']: c['value'] for c in cookies}

                # 检查是否拿到了关键的 cf_clearance
                if 'cf_clearance' in cookies_dict:
                    print(f"[✔] 账号 {account.username} 过盾成功，Cookie 已保存。")
                    account.cookies_json = json.dumps(cookies)
                    account.user_agent = page.user_agent
                    account.bypass_success_time = timezone.now()
                    account.save()
                    break  # 成功跳出循环
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
                # 打印标题，方便观察状态转换
                print(f"[.] {account.username}: 正在等待组件渲染... 当前标题: {curr_title}")

            time.sleep(4)

    except Exception as e:
        print(f"[!] {account.username} 运行异常: {e}")
    finally:
        print(f"[*] 正在关闭账号 {account.username} 的浏览器...")
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