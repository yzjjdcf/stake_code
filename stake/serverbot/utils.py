import time
import json
import urllib.parse
from pathlib import Path
import shutil
from django.utils import timezone
from DrissionPage import ChromiumPage, ChromiumOptions
import os


# 1. 代理插件生成逻辑（完全保留你的逻辑）
def get_proxy_ext(proxy_url, t_id):
    """解决 DrissionPage 报错的关键补丁：生成临时扩展处理账号密码"""
    try:
        auth, addr = proxy_url.replace('http://', '').split('@')
        user, pwd = auth.split(':')
        host, port = addr.split(':')
    except Exception:
        return None

    manifest_json = '{"version":"1.0.0","manifest_version":2,"name":"Proxy","permissions":["proxy","tabs","unlimitedStorage","storage","<all_urls>","webRequest","webRequestBlocking"],"background":{"scripts":["background.js"]}}'
    background_js = f'var config={{mode:"fixed_servers",rules:{{singleProxy:{{scheme:"http",host:"{host}",port:parseInt({port})}},bypassList:["localhost"]}}}};chrome.proxy.settings.set({{value:config,scope:"regular"}},function(){{}});chrome.webRequest.onAuthRequired.addListener(function(details){{return{{authCredentials:{{username:"{user}",password:"{pwd}"}}}};}},{{urls:["<all_urls>"]}},["blocking"]);'

    ext_dir = os.path.abspath(f'./proxy_ext_{t_id}')
    if not os.path.exists(ext_dir): os.makedirs(ext_dir)
    with open(os.path.join(ext_dir, 'manifest.json'), 'w') as f:
        f.write(manifest_json)
    with open(os.path.join(ext_dir, 'background.js'), 'w') as f:
        f.write(background_js)
    return ext_dir


# 2. 适配后的主采集逻辑
def run_pre_logic(account):
    """
    将你原来的 collect 逻辑应用到单个 StakeAccount 对象上
    """
    # 记录触发时间
    account.bypass_trigger_time = timezone.now()
    account.save()

    # 获取当前账号的代理地址
    proxy_address = account.proxy.address if account.proxy else None

    if not proxy_address:
        print(f"[-] 账号 {account.username} 没有绑定代理，取消任务")
        return

    print(f"\n[*] 正在为账号 {account.username} (ID: {account.id}) 启动过盾环境...")

    # 生成代理插件
    ext_path = get_proxy_ext(proxy_address, account.id)

    co = ChromiumOptions()
    # 为每个账号指定独立的 profile 文件夹，防止多开冲突
    co.set_user_data_path(os.path.abspath(f'./profiles/p_{account.id}'))
    if ext_path:
        co.add_extension(ext_path)

    page = ChromiumPage(co)
    try:
        page.get('https://stake.com/')
        print(f"[!] 请在弹出的浏览器中处理 {account.username} 的 CF 盾...")

        # 循环检测逻辑（保留你的 while True）
        start_time = time.time()
        while True:
            # 设置一个总超时（比如5分钟），防止线程死掉
            if time.time() - start_time > 300:
                print(f"[×] {account.username} 过盾超时")
                break

            cookies = page.cookies()
            cookies_dict = {c['name']: c['value'] for c in cookies}

            if 'cf_clearance' in cookies_dict:
                print(f"[✔] 账号 {account.username} 过盾成功！正在保存数据...")

                # 直接更新 Django 模型
                account.cookies_json = json.dumps(cookies)  # 存入完整 cookie 列表
                account.user_agent = page.user_agent
                account.bypass_success_time = timezone.now()
                account.save()
                break

            time.sleep(2)
    except Exception as e:
        print(f"[!] 运行中出错: {e}")
    finally:
        page.quit()
        # 清理临时的代理插件目录
        if ext_path and os.path.exists(ext_path):
            shutil.rmtree(ext_path)


def create_proxy_auth_extension(p_info, aid):
    """保持你原本 pre.py 的插件逻辑不动"""
    folder = Path(f'./profiles/{aid}_ext')
    folder.mkdir(parents=True, exist_ok=True)
    js = f'var config={{mode:"fixed_servers",rules:{{singleProxy:{{scheme:"http",host:"{p_info["host"]}",port:parseInt({p_info["port"]})}}}}}};chrome.proxy.settings.set({{value:config,scope:"regular"}},function(){{}});chrome.webRequest.onAuthRequired.addListener(function(d){{return{{authCredentials:{{username:"{p_info["user"]}",password:"{p_info["pass"]}"}}}}}},{{urls:["<all_urls>"]}},["blocking"]);'
    with open(folder / "manifest.json", "w") as f: json.dump(
        {"version": "1.0.0", "manifest_version": 2, "name": "Proxy Auth",
         "permissions": ["proxy", "tabs", "unlimitedStorage", "storage", "<all_urls>", "webRequest",
                         "webRequestBlocking"], "background": {"scripts": ["background.js"]}}, f)
    with open(folder / "background.js", "w") as f: f.write(js)
    return str(folder)


def parse_proxy(raw_url):
    """保持你原本 pre.py 的解析逻辑"""
    p = urllib.parse.urlparse(raw_url)
    return {'user': p.username, 'pass': p.password, 'host': p.hostname, 'port': p.port}

#
# def run_pre_logic(account_obj):
#     """
#         完全参照 pre.py 流程实现
#         只负责：1. 记录触发时间 2. 存入 Cookies/UA 3. 记录成功时间
#         """
#     # --- [触发阶段] 对应 pre.py 开始 ---
#     # 记录触发时间并立即入库 (防止脚本崩溃导致没记录)
#     account_obj.bypass_trigger_time = timezone.now()
#     account_obj.save(update_fields=['bypass_trigger_time'])
#
#     # 1. 代理准备 (这部分保持你原来的，不改动)
#     if not account_obj.proxy:
#         return False
#
#     aid = f"acc_{account_obj.id}"
#     p_info = parse_proxy(account_obj.proxy.address)
#     port = 9600 + account_obj.id
#
#     # 2. 浏览器初始化 (保持 pre.py 风格)
#     co = ChromiumOptions().add_extension(create_proxy_auth_extension(p_info, aid))
#     co.set_local_port(port).set_user_data_path(f'./profiles/{aid}_browser')
#
#     page = WebPage(mode='d', chromium_options=co)
#
#     try:
#         # 3. 访问并轮询 (完全按照 pre.py 的 30秒 逻辑)
#         page.get('https://stake.com')
#
#         success = False
#         final_cookies = None
#
#         for _ in range(30):  # 对应 pre.py 的 range(30)
#             c_list = page.cookies()
#             if any(c.get('name') == 'cf_clearance' for c in c_list):
#                 success = True
#                 final_cookies = c_list
#                 break
#             time.sleep(1)
#
#         if success:
#             # --- [成功阶段] 对应 pre.py 的 save_to_db ---
#             # 获取实时 UA 和数据
#             real_ua = page.user_agent
#             now = timezone.now()
#
#             account_obj.cookies_json = json.dumps(list(final_cookies))
#             account_obj.user_agent = real_ua
#             account_obj.bypass_success_time = now  # 写入过盾成功时间
#
#             # 严格执行保存，只更新这几个物理字段
#             account_obj.save(update_fields=[
#                 'cookies_json',
#                 'user_agent',
#                 'bypass_success_time'
#             ])
#
#             print(f"[{account_obj.username}] --- 成功！CF Cookie 与 UA 已存入数据库 ---")
#             return True
#         else:
#             print(f"[{account_obj.username}] 警告：未检测到 cf_clearance，过盾失败。")
#             return False
#
#     except Exception as e:
#         print(f"[{account_obj.username}] 预热异常: {e}")
#         return False
#     finally:
#         page.quit()  # 确保关闭浏览器

