import time
import json
import urllib.parse
import shutil
import os
import logging
from pathlib import Path
from datetime import datetime

from django.utils import timezone
from DrissionPage import ChromiumPage, ChromiumOptions
from .models import StakeAccount, ProxyPool

# 导入配置
import sys
import importlib.util
current_dir = os.path.dirname(os.path.abspath(__file__))
core_dir = os.path.dirname(current_dir)  # core/ 目录
project_root = os.path.dirname(core_dir)  # 项目根目录（包含 config/ 目录）
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 导入 config 模块
config_path = os.path.join(project_root, 'config', 'config.py')
if os.path.exists(config_path):
    spec = importlib.util.spec_from_file_location("config_module", config_path)
    config_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config_module)
    
    PROXY_EXT_DIR = config_module.PROXY_EXT_DIR
    PROFILES_DIR = config_module.PROFILES_DIR
    BROWSER_PATH = config_module.BROWSER_PATH
    BROWSER_HEADLESS = config_module.BROWSER_HEADLESS
    BROWSER_PORT_START = config_module.BROWSER_PORT_START
    BROWSER_PORT_RANGE = config_module.BROWSER_PORT_RANGE
    BYPASS_TIMEOUT = config_module.BYPASS_TIMEOUT
    IS_WINDOWS = config_module.IS_WINDOWS
    LOG_LEVEL = config_module.LOG_LEVEL
else:
    raise ImportError(f"无法找到配置文件: {config_path}")

# 配置过盾日志
log_dir = os.path.join(project_root, 'db', 'logs')
os.makedirs(log_dir, exist_ok=True)
bypass_log_file = os.path.join(log_dir, 'bypass.log')

# 创建过盾专用 logger
bypass_logger = logging.getLogger('bypass')
bypass_logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

# 避免重复添加 handler
if not bypass_logger.handlers:
    file_handler = logging.FileHandler(bypass_log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # 详细格式
    detailed_formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(detailed_formatter)
    console_handler.setFormatter(detailed_formatter)
    
    bypass_logger.addHandler(file_handler)
    bypass_logger.addHandler(console_handler)


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

    # 使用配置的目录，确保跨平台兼容
    ext_dir = os.path.join(PROXY_EXT_DIR, f'proxy_ext_{t_id}')
    if not os.path.exists(ext_dir):
        os.makedirs(ext_dir, exist_ok=True)

    with open(os.path.join(ext_dir, 'manifest.json'), 'w') as f:
        json.dump(manifest_json, f)
    with open(os.path.join(ext_dir, 'background.js'), 'w') as f:
        f.write(background_js)
    return ext_dir


def run_pre_logic(account):
    """
    针对中文版 Stake 优化的过盾逻辑 - 简化版本，确保浏览器能启动
    """
    start_time = time.time()
    bypass_logger.info(f"========== 开始过盾流程 ==========")
    bypass_logger.info(f"账号: {account.username} (ID: {account.id})")
    
    account.bypass_trigger_time = timezone.now()
    account.save()

    # 1. 代理分配逻辑
    if not account.proxy:
        bypass_logger.info(f"账号 {account.username} 未绑定代理，正在分配...")
        proxy = ProxyPool.objects.filter(is_active=True, stakeaccount__isnull=True).first()
        if not proxy:
            proxy = ProxyPool.objects.filter(is_active=True).order_by('?').first()
        if proxy:
            StakeAccount.objects.filter(pk=account.id).update(proxy=proxy)
            account.proxy = proxy
        else:
            bypass_logger.error(f"错误：账号 {account.username} 无可用代理")
            return

    # 获取代理归属地
    if not getattr(account.proxy, 'location', None):
        location = fetch_ip_location(account.proxy.address)
        ProxyPool.objects.filter(pk=account.proxy.pk).update(location=location)
        account.proxy.location = location

    bypass_logger.info(f"账号: {account.username} | 代理: {account.proxy.address.split('@')[-1] if '@' in account.proxy.address else account.proxy.address}")

    # 2. 生成代理扩展
    ext_path = get_proxy_ext(account.proxy.address, account.id)
    
    # 3. 配置浏览器 - 最简单的方式（按照示例代码）
    unique_port = BROWSER_PORT_START + (account.id % BROWSER_PORT_RANGE)
    profile_path = os.path.join(PROFILES_DIR, f'p_{account.id}')
    
    bypass_logger.info(f"配置浏览器 - 端口: {unique_port}")
    
    # 创建 ChromiumOptions
    co = ChromiumOptions()
    
    # 设置浏览器路径
    if BROWSER_PATH:
        co.set_browser_path(BROWSER_PATH)
    
    # 设置端口
    co.set_local_port(unique_port)
    
    # 设置用户数据目录
    co.set_user_data_path(profile_path)
    
    # 添加扩展
    if ext_path:
        co.add_extension(ext_path)
    
    # Linux 添加启动参数（按照示例代码）
    if not IS_WINDOWS:
        co._arguments.extend([
            '--headless=new',
            '--no-sandbox',
            '--disable-dev-shm-usage',
            '--disable-gpu',
        ])
    
    # 启动浏览器
    bypass_logger.info(f"正在启动浏览器...")
    page = ChromiumPage(co)
    bypass_logger.info(f"✅ 浏览器启动成功")

    try:
        bypass_logger.info(f"[步骤8] 访问 Stake 主页: https://stake.com/")
        page_start_time = time.time()
        page.get('https://stake.com/')
        page_load_duration = time.time() - page_start_time
        bypass_logger.info(f"页面加载完成 (耗时: {page_load_duration:.2f}秒)")
        
        bypass_logger.info(f"[步骤9] 开始过盾检测循环...")
        loop_count = 0
        start_time = time.time()
        
        while True:
            loop_count += 1
            elapsed_time = time.time() - start_time
            remaining_time = BYPASS_TIMEOUT - elapsed_time
            
            if elapsed_time > BYPASS_TIMEOUT:
                bypass_logger.warning(f"过盾超时 (已等待: {elapsed_time:.1f}秒, 超时限制: {BYPASS_TIMEOUT}秒)")
                break

            try:
                curr_url = page.url
                curr_title = page.title
                bypass_logger.debug(f"[循环 #{loop_count}] 当前URL: {curr_url} | 标题: {curr_title} | 剩余时间: {remaining_time:.1f}秒")
            except Exception as e:
                bypass_logger.warning(f"获取页面信息失败: {e}")
                time.sleep(2)
                continue

            # --- [判定逻辑：是否已经成功进入 Stake] ---
            try:
                is_in_stake = (
                                      ("Stake" in curr_title and "赌场" in curr_title) or
                                      ("stake.com" in curr_url and "challenges" not in curr_url)
                              ) and (
                                      page.ele('@data-testid=search-button', timeout=0.5) or
                                      page.ele('text=娱乐场', timeout=0.5) or
                                      page.ele('text=体育', timeout=0.5) or
                                      page.ele('text=Casino', timeout=0.5)
                              )
            except Exception as e:
                bypass_logger.debug(f"检测页面元素时出错: {e}")
                is_in_stake = False

            if is_in_stake:
                bypass_logger.info(f"✅ 识别到 Stake 中文主站！")
                bypass_logger.info(f"URL: {curr_url}")
                bypass_logger.info(f"标题: {curr_title}")
                bypass_logger.info(f"等待 10 秒以确保 Cookie 完全写入...")
                time.sleep(10)

                bypass_logger.info(f"[步骤10] 获取 Cookie...")
                cookies = page.cookies()
                cookies_dict = {c['name']: c['value'] for c in cookies}
                bypass_logger.debug(f"获取到 {len(cookies)} 个 Cookie")

                if 'cf_clearance' in cookies_dict:
                    bypass_logger.info(f"✅ 找到 cf_clearance Cookie!")
                    bypass_logger.debug(f"cf_clearance 值: {cookies_dict['cf_clearance'][:50]}...")
                    
                    bypass_logger.info(f"[步骤11] 保存 Cookie 到数据库...")
                    StakeAccount.objects.filter(pk=account.pk).update(
                        cookies_json=json.dumps(cookies),
                        user_agent=page.user_agent,
                        bypass_success_time=timezone.now()
                    )
                    total_duration = time.time() - start_time
                    bypass_logger.info(f"🎉 账号 {account.username} 过盾成功！")
                    bypass_logger.info(f"总耗时: {total_duration:.2f}秒 | 循环次数: {loop_count}")
                    bypass_logger.info(f"User-Agent: {page.user_agent}")
                    break
                else:
                    bypass_logger.warning(f"⚠️  已进入主站但 cf_clearance 尚未写入，继续轮询...")
                    bypass_logger.debug(f"当前 Cookie 列表: {list(cookies_dict.keys())[:10]}")

            # --- [判定逻辑：识别是否还在盾里] ---
            try:
                is_cf = (
                        "challenges" in curr_url or
                        page.ele('text=Verifying you are human', timeout=0.1) or
                        page.ele('text=确认您是真人', timeout=0.1)
                )
            except:
                is_cf = False

            if is_cf:
                bypass_logger.debug(f"仍处于 Cloudflare 验证页面... (URL: {curr_url})")
            else:
                bypass_logger.debug(f"等待组件渲染... 当前标题: {curr_title}")

            time.sleep(4)

    except Exception as e:
        total_duration = time.time() - start_time
        bypass_logger.error(f"❌ 账号 {account.username} 运行异常 (耗时: {total_duration:.2f}秒)", exc_info=True)
    finally:
        bypass_logger.info(f"[步骤12] 关闭浏览器...")
        cleanup_start = time.time()
        try:
            page.quit()
            bypass_logger.debug(f"浏览器已关闭 (耗时: {time.time() - cleanup_start:.2f}秒)")
        except Exception as e:
            bypass_logger.warning(f"关闭浏览器时出错: {e}")
        
        if ext_path and os.path.exists(ext_path):
            try:
                shutil.rmtree(ext_path)
                bypass_logger.debug(f"已清理代理扩展目录: {ext_path}")
            except Exception as e:
                bypass_logger.warning(f"清理代理扩展目录失败: {e}")
        
        total_duration = time.time() - start_time
        bypass_logger.info(f"========== 过盾流程结束 (总耗时: {total_duration:.2f}秒) ==========")

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