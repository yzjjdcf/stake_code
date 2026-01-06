"""
过盾相关功能模块（使用 Capsolver API，不使用浏览器）
"""
import time
import json
import urllib.parse
import os
import logging
import requests
from django.utils import timezone
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
else:
    raise ImportError(f"无法找到配置文件: {config_path}")

# 配置过盾日志（属于 Django 服务）
log_dir = os.path.join(project_root, 'db', 'logs', 'django')
os.makedirs(log_dir, exist_ok=True)
bypass_log_file = os.path.join(log_dir, 'bypass.log')

# 创建过盾专用 logger
# 统一在这里配置 handler，避免在其他模块重复配置导致日志重复输出
bypass_logger = logging.getLogger('bypass')
bypass_logger.setLevel(getattr(logging, config_module.LOG_LEVEL, logging.INFO))

# 避免重复添加 handler（使用线程锁确保只配置一次）
import threading
_handler_lock = threading.Lock()

if not bypass_logger.handlers:
    with _handler_lock:
        # 双重检查，防止多线程环境下重复添加
        if not bypass_logger.handlers:
            # 使用 TimedRotatingFileHandler 实现每日轮转
            # when='midnight' 表示每天午夜轮转
            # backupCount=30 表示保留30天的备份
            file_handler = logging.handlers.TimedRotatingFileHandler(
                bypass_log_file,
                when='midnight',
                interval=1,
                backupCount=30,
                encoding='utf-8'
            )
            file_handler.setLevel(logging.DEBUG)
            
            # 统一的时间戳格式（与其他模块保持一致）
            detailed_formatter = logging.Formatter(
                '[%(asctime)s] %(levelname)s: %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(detailed_formatter)
            
            bypass_logger.addHandler(file_handler)
            
            # 添加控制台 handler
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(detailed_formatter)
            bypass_logger.addHandler(console_handler)
            
            # 禁用传播，避免日志重复
            bypass_logger.propagate = False


def parse_proxy_to_capsolver_format(proxy_address: str, use_format_2: bool = False) -> dict:
    """
    将代理地址转换为 Capsolver API 需要的格式
    
    Args:
        proxy_address: 代理地址，新格式：host:port:username:password
        例如：isp.decodo.com:10001:spoigpsfuo:xkp5JeXPk3Ly+tn92h
        use_format_2: 是否使用格式2（字符串格式），否则使用格式1（分离字段）
    
    Returns:
        dict: Capsolver 代理配置
    """
    try:
        # 使用统一的代理解析函数
        from .utils import parse_proxy_address
        proxy_info = parse_proxy_address(proxy_address)
        
        if not proxy_info:
            bypass_logger.error(f"❌ 无法解析代理地址: {proxy_address}")
            return None
        
        host = proxy_info['host']
        port = proxy_info['port']
        username = proxy_info.get('username') or ''
        password = proxy_info.get('password') or ''
        proxy_type = proxy_info.get('scheme', 'http')
        
        # 确保代理类型有效
        if proxy_type not in ['http', 'https', 'socks4', 'socks5']:
            proxy_type = 'http'
        
        if use_format_2:
            # 格式2: "proxy": "socks5:192.191.100.10:4780:user:pwd"
            if username and password:
                proxy_str = f"{proxy_type}:{host}:{port}:{username}:{password}"
            else:
                proxy_str = f"{host}:{port}"
            return {"proxy": proxy_str}
        else:
            # 格式1: 分离字段
            capsolver_proxy = {
                "proxyType": proxy_type,
                "proxyAddress": host,
                "proxyPort": port
            }
            
            if username:
                capsolver_proxy["proxyLogin"] = username
            if password:
                capsolver_proxy["proxyPassword"] = password
            
            return capsolver_proxy
            
    except Exception as e:
        bypass_logger.error(f"❌ 解析代理地址失败: {e}")
        bypass_logger.error(f"   代理地址: {proxy_address}")
        import traceback
        bypass_logger.error(traceback.format_exc())
        return None


def get_turnstile_token(account, site_key=None, site_url=None, max_wait=60):
    """
    通过 Capsolver API 获取 Turnstile token
    
    Args:
        account: 账号对象（用于日志记录）
        site_key: Turnstile site key（如果为 None，使用默认值）
        site_url: 目标网站 URL（如果为 None，使用默认值）
        max_wait: 最大等待时间（秒）
    
    Returns:
        str: Turnstile token，如果获取失败则返回 None
    """
    # 记录开始时间
    start_time = time.time()
    
    try:
        # 获取 Capsolver API Key
        capsolver_api_key = os.getenv('CAPSOLVER_API_KEY', 'CAP-5B4B10EB54FE9A54BF32F113839720F39D1F6EC069121A3E25D5B205BDF076E7')
        if not capsolver_api_key:
            bypass_logger.error(f"❌ [{account.username}] 未设置 CAPSOLVER_API_KEY 环境变量")
            return None
        
        capsolver_api_url = 'https://api.capsolver.com'
        
        # 默认值（如果未提供）
        if not site_key:
            # 从配置文件中读取
            site_key = getattr(config_module, 'TURNSTILE_SITE_KEY', '')
            if not site_key:
                bypass_logger.error(f"❌ [{account.username}] 未配置 TURNSTILE_SITE_KEY，无法获取 Turnstile token")
                bypass_logger.error(f"   请在 config/config.py 中设置 TURNSTILE_SITE_KEY，或设置环境变量 TURNSTILE_SITE_KEY")
                return None
        
        if not site_url:
            site_url = getattr(config_module, 'TURNSTILE_SITE_URL', 'https://stake.com/')
        
        bypass_logger.info(f"🔐 [{account.username}] 开始获取 Turnstile token...")
        bypass_logger.info(f"   Site Key: {site_key[:20]}...")
        bypass_logger.info(f"   Site URL: {site_url}")
        
        # 创建任务
        payload = {
            "clientKey": capsolver_api_key,
            "task": {
                "type": "AntiTurnstileTaskProxyLess",
                "websiteKey": site_key,
                "websiteURL": site_url,
                "metadata": {
                    "action": ""  # optional
                }
            }
        }
        
        # 发送创建任务请求
        session = requests.Session()
        session.headers.update({'Content-Type': 'application/json'})
        session.proxies = {}  # 确保不使用代理访问 Capsolver API
        
        bypass_logger.info(f"📤 [{account.username}] 创建 Turnstile 任务...")
        res = session.post(f"{capsolver_api_url}/createTask", json=payload, timeout=30)
        res.raise_for_status()
        resp = res.json()
        
        task_id = resp.get("taskId")
        if not task_id:
            elapsed = time.time() - start_time
            error_msg = resp.get("errorDescription", "未知错误")
            bypass_logger.error(f"❌ [{account.username}] 创建 Turnstile 任务失败: {error_msg}")
            bypass_logger.error(f"   ⏱️  耗时: {elapsed:.2f} 秒（从发起请求到创建任务失败）")
            bypass_logger.error(f"   响应: {res.text}")
            return None
        
        bypass_logger.info(f"✅ [{account.username}] 任务创建成功，任务 ID: {task_id}")
        bypass_logger.info(f"⏳ [{account.username}] 等待任务完成（最大等待 {max_wait} 秒）...")
        
        # 轮询获取结果
        wait_start = time.time()
        check_count = 0
        
        while True:
            time.sleep(1)  # 延迟 1 秒
            check_count += 1
            
            payload = {"clientKey": capsolver_api_key, "taskId": task_id}
            res = session.post(f"{capsolver_api_url}/getTaskResult", json=payload, timeout=30)
            res.raise_for_status()
            resp = res.json()
            
            status = resp.get("status")
            
            if status == "ready":
                token = resp.get("solution", {}).get('token')
                if token:
                    # 计算总耗时（从函数开始到获取到 token）
                    total_elapsed = time.time() - start_time
                    # 计算等待耗时（从开始轮询到获取到 token）
                    wait_elapsed = time.time() - wait_start
                    bypass_logger.info(f"✅ [{account.username}] Turnstile token 获取成功")
                    bypass_logger.info(f"   ⏱️  总耗时: {total_elapsed:.2f} 秒（从发起请求到获取到 token）")
                    bypass_logger.info(f"   ⏱️  等待耗时: {wait_elapsed:.2f} 秒（从开始轮询到获取到 token）")
                    bypass_logger.debug(f"   Token: {token[:50]}...")
                    return token
                else:
                    total_elapsed = time.time() - start_time
                    bypass_logger.error(f"❌ [{account.username}] 任务完成但未获取到 token")
                    bypass_logger.error(f"   ⏱️  总耗时: {total_elapsed:.2f} 秒（从发起请求到任务完成但无 token）")
                    bypass_logger.error(f"   响应: {res.text}")
                    return None
            
            if status == "failed" or resp.get("errorId"):
                total_elapsed = time.time() - start_time
                error_msg = resp.get("errorDescription", "未知错误")
                bypass_logger.error(f"❌ [{account.username}] Turnstile 任务失败: {error_msg}")
                bypass_logger.error(f"   ⏱️  总耗时: {total_elapsed:.2f} 秒（从发起请求到任务失败）")
                bypass_logger.error(f"   响应: {res.text}")
                return None
            
            # 检查超时
            elapsed = time.time() - wait_start
            if elapsed > max_wait:
                total_elapsed = time.time() - start_time
                bypass_logger.error(f"❌ [{account.username}] Turnstile 任务超时（超过 {max_wait} 秒）")
                bypass_logger.error(f"   ⏱️  总耗时: {total_elapsed:.2f} 秒（从发起请求到超时）")
                return None
            
            # 每 5 次检查输出一次日志
            if check_count % 5 == 0:
                bypass_logger.info(f"⏳ [{account.username}] 等待中... ({int(elapsed)}/{max_wait} 秒)")
        
    except Exception as e:
        total_elapsed = time.time() - start_time
        bypass_logger.error(f"❌ [{account.username}] 获取 Turnstile token 时发生异常: {e}", exc_info=True)
        bypass_logger.error(f"   ⏱️  总耗时: {total_elapsed:.2f} 秒（从发起请求到异常）")
        return None


def run_pre_logic_capsolver(account, target_code=None):
    """
    使用 Capsolver API 处理过盾逻辑（不使用浏览器）
    账号和代理绑定，一旦分配不改变
    
    Args:
        account: 账号对象
        target_code: 可选，触发过盾的目标代码。如果提供，过盾完成后会自动复抢该码
    """
    start_time = time.time()
    bypass_logger.info(f"========== 开始 Capsolver 过盾流程 ==========")
    bypass_logger.info(f"账号: {account.username} (ID: {account.id})")
    
    # 更新触发时间
    account.bypass_trigger_time = timezone.now()
    account.save()
    
    try:
        # 1. 获取 Capsolver API Key
        capsolver_api_key = os.getenv('CAPSOLVER_API_KEY', 'CAP-5B4B10EB54FE9A54BF32F113839720F39D1F6EC069121A3E25D5B205BDF076E7')
        if not capsolver_api_key:
            bypass_logger.error("❌ 未设置 CAPSOLVER_API_KEY 环境变量")
            return
        
        capsolver_api_url = 'https://api.capsolver.com'
        target_url = 'https://stake.com'
        
        # 2. 代理分配逻辑（账号和代理绑定）
        if not account.proxy:
            bypass_logger.info(f"账号 {account.username} 未绑定代理，正在分配...")
            proxy = ProxyPool.objects.filter(is_active=True, stakeaccount__isnull=True).first()
            if not proxy:
                proxy = ProxyPool.objects.filter(is_active=True).order_by('?').first()
            if proxy:
                StakeAccount.objects.filter(pk=account.id).update(proxy=proxy)
                account.proxy = proxy
                bypass_logger.info(f"✅ 已将代理 {proxy.address} 分配给账号 {account.username}")
            else:
                bypass_logger.error(f"❌ 账号 {account.username} 无可用代理")
                return
        else:
            bypass_logger.info(f"✅ 使用账号 {account.username} 已绑定的代理: {account.proxy.address}")
        
        # 3. 解析代理地址为 Capsolver 格式
        proxy_config = parse_proxy_to_capsolver_format(account.proxy.address)
        if not proxy_config:
            bypass_logger.error(f"❌ 解析代理地址失败: {account.proxy.address}")
            return
        
        # 4. 创建 Capsolver 客户端
        session = requests.Session()
        session.headers.update({'Content-Type': 'application/json'})
        session.proxies = {}  # 确保不使用代理访问 Capsolver API
        
        # 5. 创建任务
        task_config = {
            "type": "AntiCloudflareTask",
            "websiteURL": target_url,
        }
        
        # 添加代理配置
        if isinstance(proxy_config, dict):
            for key, value in proxy_config.items():
                task_config[key] = value
        
        payload = {
            "clientKey": capsolver_api_key,
            "task": task_config
        }
        
        bypass_logger.info(f"📤 创建 Capsolver 任务...")
        response = session.post(f"{capsolver_api_url}/createTask", json=payload, timeout=30)
        response.raise_for_status()
        create_result = response.json()
        
        if create_result.get('errorId') != 0:
            error_code = create_result.get('errorCode') or create_result.get('errorId')
            error_desc = create_result.get('errorDescription', '未知错误')
            bypass_logger.error(f"❌ 任务创建失败: {error_code} - {error_desc}")
            return
        
        task_id = create_result.get('taskId')
        if not task_id:
            bypass_logger.error("❌ 未获取到任务 ID")
            return
        
        bypass_logger.info(f"✅ 任务创建成功，任务 ID: {task_id}")
        
        # 6. 等待任务完成
        bypass_logger.info(f"⏳ 等待任务完成（最大等待 300 秒）...")
        max_wait = 300
        wait_start = time.time()
        check_count = 0
        
        while True:
            check_count += 1
            elapsed = time.time() - wait_start
            
            if elapsed > max_wait:
                bypass_logger.warning(f"⏰ 等待超时（已等待: {elapsed:.1f}秒）")
                return
            
            try:
                get_payload = {"clientKey": capsolver_api_key, "taskId": task_id}
                get_response = session.post(f"{capsolver_api_url}/getTaskResult", json=get_payload, timeout=30)
                get_response.raise_for_status()
                result = get_response.json()
                
                status = result.get('status')
                
                if status == 'ready':
                    bypass_logger.info(f"✅ 任务完成！")
                    solution = result.get('solution', {})
                    
                    # 7. 保存数据到数据库
                    cookies_dict = solution.get('cookies', {})
                    user_agent = solution.get('userAgent', '')
                    
                    # 转换 cookies 格式
                    cookies_list = []
                    for cookie_name, cookie_value in cookies_dict.items():
                        cookies_list.append({
                            "name": cookie_name,
                            "value": cookie_value
                        })
                    
                    update_data = {
                        "cookies_json": json.dumps(cookies_list),
                        "bypass_success_time": timezone.now()
                    }
                    
                    if user_agent:
                        update_data["user_agent"] = user_agent
                    
                    StakeAccount.objects.filter(pk=account.pk).update(**update_data)
                    
                    total_duration = time.time() - start_time
                    bypass_logger.info(f"🎉 账号 {account.username} 过盾成功！")
                    bypass_logger.info(f"总耗时: {total_duration:.2f}秒")
                    bypass_logger.info(f"Cookies 数量: {len(cookies_list)}")
                    if user_agent:
                        bypass_logger.info(f"User-Agent: {user_agent}")
                    
                    # 8. 如果提供了目标代码，过盾完成后自动复抢
                    if target_code:
                        bypass_logger.info(f"🔄 过盾完成，账号 {account.username} 将重新抢码: {target_code}")
                        try:
                            # 导入 worker 模块的函数（避免循环导入）
                            # 注意：os 和 sys 已在文件开头导入，这里不需要重复导入
                            current_dir = os.path.dirname(os.path.abspath(__file__))
                            core_dir = os.path.dirname(current_dir)
                            if core_dir not in sys.path:
                                sys.path.insert(0, core_dir)
                            
                            from worker import request_single_account
                            from .models import CodeRecord
                            
                            # 查找或创建 CodeRecord（使用最近的推送记录）
                            code_record = CodeRecord.objects.filter(code=target_code).order_by('-created_at').first()
                            if not code_record:
                                # 如果没有找到，创建新的记录
                                code_record = CodeRecord.objects.create(
                                    code=target_code,
                                    status='unknown'
                                )
                            
                            # 重新抢码（在新线程中执行，避免阻塞）
                            import threading
                            threading.Thread(
                                target=request_single_account,
                                args=(account, target_code, code_record),
                                daemon=True
                            ).start()
                            bypass_logger.info(f"✅ 已启动复抢任务: {account.username} -> {target_code}")
                        except Exception as e:
                            bypass_logger.error(f"❌ 启动复抢任务失败: {e}", exc_info=True)
                    
                    break
                elif status == 'processing':
                    if check_count % 10 == 0:  # 每 10 次检查输出一次
                        bypass_logger.info(f"⏳ 任务处理中... (已等待: {elapsed:.1f}秒)")
                else:
                    error_code = result.get('errorCode')
                    error_desc = result.get('errorDescription', '未知错误')
                    bypass_logger.error(f"❌ 任务失败: {error_code} - {error_desc}")
                    return
                
            except requests.exceptions.RequestException as e:
                bypass_logger.warning(f"⚠️  获取任务结果失败: {e}")
            
            time.sleep(5)  # 每 5 秒检查一次
        
    except Exception as e:
        total_duration = time.time() - start_time
        bypass_logger.error(f"❌ 账号 {account.username} 运行异常 (耗时: {total_duration:.2f}秒)", exc_info=True)
    finally:
        total_duration = time.time() - start_time
        bypass_logger.info(f"========== Capsolver 过盾流程结束 (总耗时: {total_duration:.2f}秒) ==========")

