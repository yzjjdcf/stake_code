import os
import random
import sys
import json
import logging
# 使用 curl_cffi 解决 10054 错误
from curl_cffi import requests as curl_requests
import django
import time
import threading
from concurrent.futures import ThreadPoolExecutor

# 1. 环境初始化
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)  # 项目根目录（包含 config/ 目录）
if project_root not in sys.path:
    sys.path.insert(0, project_root)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'manager.settings')
django.setup()

# 配置日志（与 listener.py 保持一致）
log_dir = os.path.join(project_root, 'db', 'logs', 'listener')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'worker.log')  # worker 日志文件

# 使用 TimedRotatingFileHandler 实现每日轮转
from logging.handlers import TimedRotatingFileHandler
file_handler = TimedRotatingFileHandler(
    log_file,
    when='midnight',
    interval=1,
    backupCount=30,  # 保留30天的备份
    encoding='utf-8'
)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter(
    '[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
))

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter(
    '[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
))

logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, console_handler]
)

logger = logging.getLogger(__name__)

# 导入配置
import sys
import importlib.util
import os

config_path = os.path.join(project_root, 'config', 'config.py')
if os.path.exists(config_path):
    spec = importlib.util.spec_from_file_location("config_module", config_path)
    config_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config_module)
    MAX_RETRIES = config_module.MAX_RETRIES
    REQUEST_DELAY_MIN = config_module.REQUEST_DELAY_MIN
    REQUEST_DELAY_MAX = config_module.REQUEST_DELAY_MAX
else:
    raise ImportError(f"无法找到配置文件: {config_path}")

from serverbot.models import StakeAccount, ProxyPool, CodeRecord, ClaimRecord
from django.db.models import F
# 导入归属地查询工具
from serverbot.bypass import run_pre_logic_capsolver
from serverbot.utils import fetch_ip_location, parse_proxy_address
from urllib.parse import quote


# ================= 工具方法：从数据库获取账号请求配置 =================
def get_account_request_config(account):
    """
    从数据库获取账号的请求配置（代理、Cookie、User-Agent、Token等）
    
    Args:
        account: StakeAccount 对象
    
    Returns:
        dict: 包含以下键的字典
            - proxies: 代理配置字典 {"http": "...", "https": "..."}
            - cookie_dict: Cookie 字典
            - headers_base: 基础请求头（不包含 operation-name）
            - log_port: 日志端口（字符串）
            - location: 代理归属地
            - success: 是否成功获取配置
            - error: 错误信息（如果失败）
    """
    result = {
        'proxies': None,
        'cookie_dict': None,
        'headers_base': None,
        'log_port': None,
        'location': None,
        'success': False,
        'error': None
    }
    
    # 1. 检查并获取代理
    if not account.proxy:
        result['error'] = "账号未分配代理"
        return result
    
    proxy_addr = account.proxy.address.strip()
    location = account.proxy.location or "未知"
    
    # 解析代理地址
    proxy_info = parse_proxy_address(proxy_addr)
    if not proxy_info:
        result['error'] = f"无法解析代理地址: {proxy_addr}"
        return result
    
    # 构建代理 URL
    host = proxy_info['host']
    port = proxy_info['port']
    username = proxy_info.get('username') or ''
    password = proxy_info.get('password') or ''
    
    if username and password:
        encoded_username = quote(username, safe='')
        encoded_password = quote(password, safe='')
        proxy_url = f"http://{encoded_username}:{encoded_password}@{host}:{port}"
    else:
        proxy_url = f"http://{host}:{port}"
    
    result['proxies'] = {"http": proxy_url, "https": proxy_url}
    result['log_port'] = str(port)
    result['location'] = location
    
    # 2. 解析 Cookie
    if not account.cookies_json:
        result['error'] = "账号未设置 Cookie"
        return result
    
    try:
        cookie_dict = {c['name']: c['value'] for c in json.loads(account.cookies_json)}
        if 'cf_clearance' not in cookie_dict:
            logger.warning(f"⚠️ {account.username}: Cookie 中缺少 cf_clearance，可能需要重新过盾")
        result['cookie_dict'] = cookie_dict
    except Exception as e:
        result['error'] = f"解析 Cookie 失败: {str(e)}"
        return result
    
    # 3. 构建基础请求头
    if not account.user_agent or not account.token:
        result['error'] = "账号未设置 User-Agent 或 Token"
        return result
    
    result['headers_base'] = {
        "accept": "*/*",
        "content-type": "application/json",
        "origin": "https://stake.com",
        "user-agent": account.user_agent,
        "x-access-token": account.token,
    }
    
    result['success'] = True
    return result


# ================= 工具方法：使用代理发送请求（带重试） =================
def make_request_with_retry(url, headers, cookies, proxies, payload, max_retries=None, timeout=15):
    """
    使用代理发送请求，带自动重试机制
    
    Args:
        url: 请求 URL
        headers: 请求头字典
        cookies: Cookie 字典
        proxies: 代理配置字典
        payload: 请求体（JSON）
        max_retries: 最大重试次数（默认使用配置中的 MAX_RETRIES）
        timeout: 请求超时时间（秒）
    
    Returns:
        tuple: (response, elapsed_ms, last_error)
            - response: 响应对象（成功时）或 None（失败时）
            - elapsed_ms: 请求耗时（毫秒）
            - last_error: 错误信息（如果有）
    """
    if max_retries is None:
        max_retries = MAX_RETRIES
    
    response = None
    last_error = ""
    elapsed_ms = 0
    
    for attempt in range(max_retries):
        start_time = time.perf_counter()
        try:
            # 动态切换模拟指纹，增加迷惑性
            impersonate_ver = "chrome110" if attempt % 2 == 0 else "chrome120"
            
            response = curl_requests.post(
                url,
                headers=headers,
                cookies=cookies,
                json=payload,
                proxies=proxies,
                impersonate=impersonate_ver,
                timeout=timeout
            )
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            
            if response:
                break  # 成功拿到响应，跳出重试
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            last_error = str(e)
            # 如果是 (56) 连接重置，等待 1.5s 后重试
            if "curl: (56)" in last_error or "reset" in last_error.lower():
                time.sleep(1.5)
                continue
            break  # 其他严重错误直接中断
    
    return response, elapsed_ms, last_error


# ================= 工具方法：确保账号有代理并获取归属地 =================
def ensure_account_proxy(account):
    """
    确保账号已分配代理，并获取代理归属地
    
    Args:
        account: StakeAccount 对象
    
    Returns:
        tuple: (success, needs_warmup, error_msg)
            - success: 是否成功
            - needs_warmup: 是否需要过盾（新分配代理时需要）
            - error_msg: 错误信息（如果失败）
    """
    needs_warmup = False
    
    # 检查账号是否已有代理
    if not account.proxy:
        logger.info(f"[*] 账号 {account.username} 缺失代理，正在分配...")
        # 优先分配空闲代理
        proxy = ProxyPool.objects.filter(is_active=True, stakeaccount__isnull=True).first()
        if not proxy:
            # 如果没有空闲代理，随机选择一个
            proxy = ProxyPool.objects.filter(is_active=True).order_by('?').first()
        
        if proxy:
            StakeAccount.objects.filter(pk=account.pk).update(proxy=proxy)
            account.proxy = proxy
            needs_warmup = True
            logger.info(f"✅ 账号 {account.username} 已分配代理: {proxy.address}")
        else:
            error_msg = "代理池空，无法分配代理"
            logger.warning(f"❌ {account.username}: {error_msg}")
            return False, False, error_msg
    
    # 确保代理归属地已获取
    if not getattr(account.proxy, 'location', None):
        logger.info(f"[*] 账号 {account.username} 的代理归属地未设置，正在查询...")
        loc = fetch_ip_location(account.proxy.address)
        ProxyPool.objects.filter(pk=account.proxy.pk).update(location=loc)
        account.proxy.location = loc
        logger.info(f"✅ 账号 {account.username} 的代理归属地: {loc}")
    
    return True, needs_warmup, None


# ================= 工具方法：查询代码是否可用 =================
def query_code_availability(account, target_code, config):
    """
    第一步：查询代码是否可用（BonusCodeInformation 接口）
    
    Args:
        account: 账号对象
        target_code: 目标代码
        config: 从 get_account_request_config 获取的请求配置
    
    Returns:
        tuple: (response, elapsed_ms, last_error)
            - response: 响应对象（成功时）或 None（失败时）
            - elapsed_ms: 请求耗时（毫秒）
            - last_error: 错误信息（如果有）
    """
    # 构建查询接口的请求头
    headers = config['headers_base'].copy()
    headers.update({
        "referer": f"https://stake.com/zh/settings/offers?type=drop&code={target_code}",
        "x-operation-name": "BonusCodeInformation",
    })
    
    # 构建查询接口的请求体
    payload = {
        "query": "query BonusCodeInformation($code: String!, $couponType: CouponType!) {\n  bonusCodeInformation(code: $code, couponType: $couponType) {\n    availabilityStatus\n    bonusValue\n  }\n}",
        "variables": {"code": target_code, "couponType": "drop"}
    }
    
    # 使用统一的重试请求方法
    response, elapsed_ms, last_error = make_request_with_retry(
        url="https://stake.com/_api/graphql",
        headers=headers,
        cookies=config['cookie_dict'],
        proxies=config['proxies'],
        payload=payload
    )
    
    return response, elapsed_ms, last_error


# ================= 主处理函数：单个账号处理流程 =================
def request_single_account(account, target_code, code_record, message_received_time=None):
    """
    单个账号处理逻辑：
    1. 检查并分配代理
    2. 检查 Cookie 并触发过盾（如需要）
    3. 查询代码是否可用（第一步接口）
    4. 如果可用，调用领取接口（第二步接口）
    5. 解析结果并记录到数据库
    
    Args:
        account: 账号对象
        target_code: 目标代码
        code_record: 本次推送的 CodeRecord 对象（每次推送都是唯一的）
        message_received_time: Telegram 收到消息的时间戳（time.perf_counter()），用于计算总耗时
    """
    # 记录账号开始处理的时间（排除错峰延迟的影响）
    account_start_time = time.perf_counter()

    # --- 第一步：确保账号有代理并获取归属地 ---
    proxy_success, proxy_needs_warmup, proxy_error = ensure_account_proxy(account)
    if not proxy_success:
        logger.warning(f"⚠️ {account.username}: {proxy_error}")
        return
    
    needs_warmup = proxy_needs_warmup

    # --- 第二步：Cookie 缺失检测 ---
    if not account.cookies_json:
        needs_warmup = True

    # --- 第三步：异步触发过盾（使用 Capsolver，不使用浏览器）---
    if needs_warmup:
        logger.info(f"🚀 {account.username} ({account.proxy.location}): 触发初始化过盾（Capsolver）...")
        # 传递 target_code，过盾完成后会自动复抢
        threading.Thread(target=run_pre_logic_capsolver, args=(account, target_code), daemon=True).start()
        return

    # --- 第四步：获取账号请求配置（从数据库） ---
    config = get_account_request_config(account)
    if not config['success']:
        logger.warning(f"⚠️ {account.username}: 获取请求配置失败 - {config['error']}")
        return
    
    proxies = config['proxies']
    cookie_dict = config['cookie_dict']
    log_port = config['log_port']
    location = config['location']
    
    # --- 第五步：直接调用领取接口（跳过查询接口以节省时间） ---
    logger.info(f"🚀 {account.username} ({log_port} - {location}): 直接调用领取接口（跳过查询接口）...")
    
    # 直接调用领取接口
    claim_status, claim_response_body_str = claim_bonus_code(
        account, target_code, cookie_dict, proxies, log_port, location
    )
    
    # 计算总耗时（毫秒）
    total_elapsed_ms = None
    if account_start_time:
        # 从账号开始处理到请求完成的时间（排除错峰延迟）
        total_elapsed_ms = int((time.perf_counter() - account_start_time) * 1000)
    
    # 处理直接领取的结果
    _handle_direct_claim_result(
        claim_status=claim_status,
        claim_response_body_str=claim_response_body_str,
        account=account,
        log_port=log_port,
        location=location,
        total_elapsed_ms=total_elapsed_ms,
        target_code=target_code,
        code_record=code_record
    )


# ================= 2.1. 直接领取结果处理方法 =================
def _handle_direct_claim_result(claim_status, claim_response_body_str, account, log_port, location, total_elapsed_ms, target_code, code_record):
    """
    处理直接调用领取接口的结果（跳过查询接口）
    
    Args:
        claim_status: 领取状态 ('claim_success', 'claim_failure')
        claim_response_body_str: 领取接口的响应体（JSON字符串）
        account: 账号对象
        log_port: 日志端口
        location: 代理归属地
        total_elapsed_ms: 总耗时（毫秒）
        target_code: 目标代码
        code_record: 本次推送的 CodeRecord 对象
    """
    bonus_value = None
    error_msg = None
    
    # 格式化耗时信息
    if total_elapsed_ms is not None:
        time_info = f"领取接口总耗时 {total_elapsed_ms}ms"
    else:
        time_info = "领取接口完成"
    
    # 解析响应体以获取奖金金额和错误信息
    if claim_response_body_str:
        try:
            claim_res_json = json.loads(claim_response_body_str)
            
            if claim_status == 'claim_success':
                # 领取成功，提取奖金金额
                data = claim_res_json.get('data', {})
                claim_result = data.get('claimConditionBonusCode', {})
                if claim_result:
                    bonus_value = claim_result.get('amount')
                    currency = claim_result.get('currency', '')
                    if bonus_value:
                        logger.info(f"✅ {account.username} ({log_port} - {location}): 领取成功 - 金额: {bonus_value} {currency} | {time_info}")
            elif claim_status == 'not_found':
                # 代码未找到，提取错误信息
                errors = claim_res_json.get('errors', [])
                if errors:
                    error_msg = errors[0].get('message', '代码未找到或不可用')
                    logger.warning(f"❌ {account.username} ({log_port} - {location}): 代码无效（未找到或不可用）- {error_msg} | {time_info}")
            elif claim_status == 'inactive':
                # 代码次数领取完，提取错误信息
                errors = claim_res_json.get('errors', [])
                if errors:
                    error_msg = errors[0].get('message', '代码次数领取完')
                    logger.warning(f"❌ {account.username} ({log_port} - {location}): 代码无效（次数领取完）- {error_msg} | {time_info}")
            elif claim_status == 'session_expired':
                # 会话已过期，提取错误信息并停用账号
                errors = claim_res_json.get('errors', [])
                if errors:
                    error_msg = errors[0].get('message', '会话已过期')
                    logger.warning(f"❌ {account.username} ({log_port} - {location}): 会话已过期 - {error_msg} | {time_info}")
                # 停用账号
                try:
                    StakeAccount.objects.filter(pk=account.pk).update(is_active=False)
                    logger.warning(f"⚠️ {account.username}: 账号已停用（会话过期）")
                except Exception as e:
                    logger.error(f"⚠️ 停用账号失败: {e}")
            elif claim_status == 'already_claimed':
                # 代码已领过，提取错误信息
                errors = claim_res_json.get('errors', [])
                if errors:
                    error_msg = errors[0].get('message', '代码已领过')
                    logger.warning(f"❌ {account.username} ({log_port} - {location}): 代码已领过 - {error_msg} | {time_info}")
            else:
                # 领取失败，提取错误信息
                errors = claim_res_json.get('errors', [])
                if errors:
                    error_msg = errors[0].get('message', '未知错误')
                    logger.warning(f"❌ {account.username} ({log_port} - {location}): 领取失败 - {error_msg} | {time_info}")
        except Exception as e:
            logger.debug(f"解析响应体失败: {e}")
            if claim_status == 'claim_failure':
                error_msg = str(e)[:200]
    
    # 记录到数据库
    try:
        from serverbot.models import ClaimRecord, CodeRecord
        from django.db.models import F
        
        # 创建ClaimRecord
        ClaimRecord.objects.create(
            account=account,
            code_record=code_record,
            code=target_code,
            status=claim_status,
            bonus_value=str(bonus_value) if bonus_value else None,
            response_time_ms=None,  # 直接领取模式不记录单个请求耗时
            error_message=error_msg,
            query_response_body=None,  # 跳过查询接口，所以没有查询响应
            claim_response_body=claim_response_body_str  # 领取接口的响应体
        )
        
        # 更新CodeRecord统计信息（不再更新status字段，因为码是跟个人绑定的）
        update_fields = {}
        if claim_status == 'claim_success':
            # 领取成功
            update_fields['success_count'] = F('success_count') + 1
            if bonus_value:
                update_fields['actual_value'] = str(bonus_value)
        elif claim_status == 'not_found':
            # 代码未找到或不可用
            update_fields['failure_count'] = F('failure_count') + 1
        elif claim_status == 'inactive':
            # 代码次数领取完
            update_fields['failure_count'] = F('failure_count') + 1
        elif claim_status == 'session_expired':
            # 会话已过期（账号已停用）
            update_fields['failure_count'] = F('failure_count') + 1
        elif claim_status == 'claim_failure':
            # 领取失败
            update_fields['failure_count'] = F('failure_count') + 1
        
        # 所有状态都增加总尝试次数
        update_fields['total_attempts'] = F('total_attempts') + 1
        
        if update_fields:
            CodeRecord.objects.filter(pk=code_record.pk).update(**update_fields)
    except Exception as e:
        logger.error(f"⚠️ 记录数据库失败: {e}")


# ================= 2. 领取接口调用方法 =================
def claim_bonus_code(account, target_code, cookie_dict, proxies, log_port, location):
    """
    第二步：调用领取接口实际领取代码
    使用与查询接口相同的配置：代理、Cookie（包含 cf_clearance）、User-Agent、Token等
    
    Args:
        account: 账号对象
        target_code: 目标代码
        cookie_dict: Cookie字典（从数据库获取，包含 cf_clearance 等所有 Cookie）
        proxies: 代理配置（从数据库获取）
        log_port: 日志端口
        location: 代理归属地
    
    Returns:
        (claim_status, response_body_str): 领取状态和响应体
    """
    # 验证 CF Cookie 是否存在
    if 'cf_clearance' not in cookie_dict:
        logger.warning(f"⚠️ {account.username} ({log_port} - {location}): Cookie 中缺少 cf_clearance，领取请求可能失败")
    
    # 获取账号请求配置（复用方法）
    config = get_account_request_config(account)
    if not config['success']:
        logger.warning(f"⚠️ {account.username} ({log_port} - {location}): 获取请求配置失败 - {config['error']}")
        return 'claim_failure', f"配置获取失败: {config['error']}"
    
    # 使用传入的配置（确保与查询接口使用相同的配置）
    headers_base = config['headers_base'].copy()
    headers = headers_base.copy()
    headers.update({
        "referer": f"https://stake.com/zh/settings/offers?type=drop&code={target_code}",
        "x-operation-name": "ClaimConditionBonusCode",  # 领取接口的操作名
    })
    
    # 使用实际的 GraphQL mutation（根据用户提供的 payload）
    # 默认使用 USDT 作为货币类型，如果需要支持其他货币，可以从账号配置中获取
    currency = "usdt"  # 默认货币类型，可以根据需要从账号配置中获取
    
    # 获取 turnstileToken（通过 Capsolver API）
    logger.info(f"🔐 {account.username} ({log_port} - {location}): 开始获取 Turnstile token...")
    from serverbot.bypass import get_turnstile_token
    
    # 记录开始时间
    turnstile_start_time = time.perf_counter()
    
    # 调用 Capsolver API 获取 Turnstile token
    # TODO: site_key 需要从实际页面获取，或者从配置文件中读取
    # 目前先使用 None，让函数使用默认值（需要后续替换为实际值）
    # 构建包含动态参数的 site_url（需要在 currency 定义之后）
    site_url = f"https://stake.com/zh/settings/offers?type=drop&code={target_code}&currency={currency}&modal=redeemBonus"
    
    turnstile_token = get_turnstile_token(
        account=account,
        site_key=None,  # TODO: 需要替换为实际的 site_key
        site_url=site_url,  # 使用包含动态参数的完整 URL
        max_wait=60  # 最大等待 60 秒
    )
    
    # 计算 Turnstile token 获取耗时
    turnstile_elapsed_ms = int((time.perf_counter() - turnstile_start_time) * 1000)
    
    if not turnstile_token:
        logger.error(f"❌ {account.username} ({log_port} - {location}): 获取 Turnstile token 失败，无法继续领取 | 耗时 {turnstile_elapsed_ms}ms")
        return 'claim_failure', "获取 Turnstile token 失败"
    
    logger.info(f"✅ {account.username} ({log_port} - {location}): Turnstile token 获取成功 | 耗时 {turnstile_elapsed_ms}ms")
    
    # 注意：currency 在 variables 中应该是小写的 "usdt"，而不是大写的 "USDT"
    # GraphQL 的 CurrencyEnum 类型会自动处理大小写转换
    payload = {
        "query": "mutation ClaimConditionBonusCode($code: String!, $currency: CurrencyEnum!, $turnstileToken: String!) {\n  claimConditionBonusCode(\n    code: $code\n    currency: $currency\n    turnstileToken: $turnstileToken\n  ) {\n    bonusCode {\n      id\n      code\n    }\n    amount\n    currency\n    user {\n      id\n      balances {\n        available {\n          amount\n          currency\n        }\n      }\n    }\n  }\n}",
        "variables": {
            "code": target_code,
            "currency": currency.lower(),  # 使用小写（usdt），与用户提供的实际请求体一致
            "turnstileToken": turnstile_token
        }
    }
    
    # --- 使用统一的重试请求方法 ---
    claim_response, elapsed_ms, last_error = make_request_with_retry(
        url="https://stake.com/_api/graphql",
        headers=headers,
        cookies=cookie_dict,  # 使用传入的 cookie_dict（确保与查询接口一致）
        proxies=proxies,  # 使用传入的 proxies（确保与查询接口一致）
        payload=payload
    )
    
    # 提取并保存完整响应体（不进行严格解析）
    claim_response_body_str = None
    
    if claim_response:
        try:
            # 优先尝试获取 JSON 格式的响应体
            try:
                claim_response_body_str = json.dumps(claim_response.json(), ensure_ascii=False, indent=2)
            except (ValueError, json.JSONDecodeError):
                # 如果不是 JSON，获取文本格式
                try:
                    claim_response_body_str = claim_response.text
                except:
                    claim_response_body_str = f"无法获取响应体 (状态码: {claim_response.status_code})"
        except Exception as e:
            claim_response_body_str = f"提取响应体失败: {str(e)}"
        
        # 判断状态：HTTP 200 需要检查响应体中的错误
        if claim_response.status_code == 200:
            # HTTP 200 但可能包含错误，需要检查响应体
            try:
                claim_res_json = claim_response.json()
                errors = claim_res_json.get('errors', [])
                
                if errors:
                    # 有错误信息，检查错误类型
                    error_info = errors[0]
                    error_type = error_info.get('errorType', '')
                    error_msg = error_info.get('message', '未知错误')
                    
                    # 检查错误类型
                    if error_type == 'notFound' or 'not found' in error_msg.lower() or 'cannot be found' in error_msg.lower():
                        logger.warning(f"❌ {account.username} ({log_port} - {location}): 代码无效（未找到或不可用）| 领取接口请求耗时 {elapsed_ms}ms")
                        return 'not_found', claim_response_body_str
                    elif error_type == 'bonusCodeInactive' or 'unavailable' in error_msg.lower():
                        logger.warning(f"❌ {account.username} ({log_port} - {location}): 代码无效（次数领取完）| 领取接口请求耗时 {elapsed_ms}ms")
                        return 'inactive', claim_response_body_str
                    elif error_type == 'disabledSession' or 'session has expired' in error_msg.lower() or 'session expired' in error_msg.lower():
                        logger.warning(f"❌ {account.username} ({log_port} - {location}): 会话已过期，账号将被停用 | 领取接口请求耗时 {elapsed_ms}ms")
                        return 'session_expired', claim_response_body_str
                    elif error_type == 'codeAlreadyClaimed' or 'already claimed' in error_msg.lower() or 'already_claimed' in error_msg.lower():
                        logger.warning(f"❌ {account.username} ({log_port} - {location}): 代码已领过 | 领取接口请求耗时 {elapsed_ms}ms")
                        return 'already_claimed', claim_response_body_str
                    else:
                        # 其他类型的错误
                        logger.warning(f"❌ {account.username} ({log_port} - {location}): 领取失败 - {error_msg} | 领取接口请求耗时 {elapsed_ms}ms")
                        return 'claim_failure', claim_response_body_str
                else:
                    # 没有错误，说明领取成功
                    logger.info(f"✅ {account.username} ({log_port} - {location}): 领取成功 (HTTP 200) | 领取接口请求耗时 {elapsed_ms}ms")
                    return 'claim_success', claim_response_body_str
            except Exception as e:
                # 解析 JSON 失败，但 HTTP 200，假设成功
                logger.warning(f"⚠️ {account.username} ({log_port} - {location}): 无法解析响应体，但 HTTP 200，假设成功 | 领取接口请求耗时 {elapsed_ms}ms")
                return 'claim_success', claim_response_body_str
        else:
            status_code = claim_response.status_code
            logger.warning(f"❌ {account.username} ({log_port} - {location}): 领取失败 (HTTP {status_code}) | 领取接口请求耗时 {elapsed_ms}ms")
            if last_error:
                logger.warning(f"   错误信息: {last_error[:100]}")
            return 'claim_failure', claim_response_body_str if claim_response_body_str else f"HTTP {status_code}"
    else:
        # 无响应对象
        logger.warning(f"❌ {account.username} ({log_port} - {location}): 领取失败 (无响应) | 领取接口请求耗时 {elapsed_ms}ms")
        if last_error:
            logger.warning(f"   错误信息: {last_error[:100]}")
            claim_response_body_str = f"无响应对象\n错误信息: {last_error}"
        else:
            claim_response_body_str = "无响应对象"
        return 'claim_failure', claim_response_body_str


# ================= 3. 结果解析方法 (深度逻辑) =================
def handle_response_result(response, account, log_port, location, elapsed_ms, total_elapsed_ms, last_error, target_code, code_record, cookie_dict=None, proxies=None):
    """
    深度解析 Stake GraphQL 返回的 JSON 数据
    并记录到数据库
    
    Args:
        elapsed_ms: 单个请求的耗时（毫秒）
        total_elapsed_ms: 从 Telegram 收到消息到请求完成的总耗时（毫秒）
        cookie_dict: Cookie字典（用于第二步领取接口）
        proxies: 代理配置（用于第二步领取接口）
    """
    claim_status = 'error'
    bonus_value = None
    error_msg = None
    query_response_body_str = None  # 查询接口的响应体
    claim_response_body_str = None  # 领取接口的响应体（仅当走到第二步时才有）
    
    # 格式化耗时信息（标注是查询接口）
    if total_elapsed_ms is not None:
        time_info = f"查询接口请求耗时 {elapsed_ms}ms | 总耗时 {total_elapsed_ms}ms"
    else:
        time_info = f"查询接口耗时 {elapsed_ms}ms"
    
    if not response:
        logger.warning(f"❌ {account.username} ({log_port} - {location}): 代码无效（彻底异常: {last_error[:40]}）| {time_info}")
        claim_status = 'error'
        error_msg = last_error[:200] if last_error else "无响应"
    elif response.status_code == 403:
        # 情况 A: 403 盾拦截
        logger.warning(f"❌ {account.username} ({log_port} - {location}): 代码无效（403拦截）| {time_info}")
        claim_status = 'error_403'
        StakeAccount.objects.filter(pk=account.pk).update(cookies_json=None)
        # 传递 target_code，过盾完成后会自动复抢
        threading.Thread(target=run_pre_logic_capsolver, args=(account, target_code), daemon=True).start()
    elif response.status_code == 200:
        # 情况 B: 200 请求成功 (开始细分业务逻辑)
        try:
            res_json = response.json()

            # 1. 先看有没有报错 (Errors 字段)
            errors = res_json.get('errors', [])
            data_root = res_json.get('data')
            
            if errors:
                # 有错误信息，检查是否是无效码
                error_info = errors[0]
                err_msg = error_info.get('message', '')
                error_type = error_info.get('errorType', '')
                
                # 检查是否是无效码（未找到或不可用）
                if (error_type == 'notFound' or 
                    "未找到或不可用" in err_msg or 
                    "Bonus code cannot be found" in err_msg or
                    "not found" in err_msg.lower()):
                    logger.warning(f"❌ {account.username} ({log_port} - {location}): 代码无效（未找到或不可用）| {time_info}")
                    claim_status = 'not_found'
                    error_msg = err_msg
                else:
                    logger.warning(f"❌ {account.username} ({log_port} - {location}): 代码无效（接口报错: {err_msg}）| {time_info}")
                    claim_status = 'error'
                    error_msg = err_msg
            elif data_root is None:
                # data 为 null，且没有 errors（这种情况应该不会发生，但为了安全）
                logger.warning(f"❌ {account.username} ({log_port} - {location}): 代码无效（返回 Data 为 null）| {time_info}")
                claim_status = 'not_found'
                error_msg = "返回 Data 为 null"
            else:
                # 2. 解析 Data 字段（data 不为 null）
                info = data_root.get('bonusCodeInformation')
                if info is None:
                    logger.warning(f"❌ {account.username} ({log_port} - {location}): 代码无效（无效代码结构）| {time_info}")
                    claim_status = 'error'
                    error_msg = "无效代码结构"
                else:
                    status = info.get('availabilityStatus')
                    bonus_value = info.get('bonusValue')  # 获取奖金金额

                    # 3. 根据 Stake 状态码分支判定
                    if status == 'bonusCodeInactive':
                        # 码有效，但次数已用尽
                        logger.info(f"✅ {account.username} ({log_port} - {location}): 代码有效 - 次数领取完 | {time_info}")
                        claim_status = 'inactive'
                    elif status == 'available':
                        # 码有效且可用，需要调用第二步领取接口
                        logger.info(f"✅ {account.username} ({log_port} - {location}): 代码有效 - 可用，开始领取 | {time_info}")
                        # 调用第二步领取接口
                        claim_status, claim_response_body_str = claim_bonus_code(
                            account, target_code, cookie_dict, proxies, log_port, location
                        )
                        # 记录领取接口的响应体（仅当走到第二步时才有）
                        bonus_value = info.get('bonusValue')  # 保留第一步获取的奖金金额
                    elif status == 'alreadyClaimed':
                        logger.info(f"✅ {account.username} ({log_port} - {location}): 代码有效 - 次数领取完（已领过）| {time_info}")
                        claim_status = 'already_claimed'
                    elif status == 'weeklyWagerRequirement':
                        # 需要满足周投注要求（流水不够）
                        logger.info(f"✅ {account.username} ({log_port} - {location}): 代码有效 - 流水不够 | {time_info}")
                        claim_status = 'weekly_wager_requirement'
                        error_msg = "需要满足周投注要求才能使用此代码"
                    else:
                        logger.info(f"✅ {account.username} ({log_port} - {location}): [200 OK] 状态: {status} | {time_info}")
                        claim_status = 'error'
                        error_msg = f"未知状态: {status}"

        except Exception as e:
            logger.error(f"❌ {account.username} ({log_port} - {location}): 代码无效（解析 JSON 失败: {e}）| {time_info}")
            claim_status = 'error'
            error_msg = str(e)[:200]
    else:
        # 情况 C: 其他 HTTP 状态码 (500, 502 等)
        logger.warning(f"❌ {account.username} ({log_port} - {location}): 代码无效（错误状态 {response.status_code}）| {time_info}")
        claim_status = 'error'
        error_msg = f"HTTP {response.status_code}"
    
    # 提取查询接口的响应体（无论什么状态都记录）
    try:
        if response:
            # 尝试获取 JSON 格式的响应体
            try:
                query_response_body_str = json.dumps(response.json(), ensure_ascii=False, indent=2)
            except:
                # 如果不是 JSON，获取文本格式
                try:
                    query_response_body_str = response.text
                except:
                    query_response_body_str = f"无法获取响应体 (状态码: {response.status_code})"
        else:
            query_response_body_str = f"无响应对象 (错误: {last_error})"
    except Exception as e:
        query_response_body_str = f"提取响应体失败: {str(e)}"
    
    # 记录到ClaimRecord和CodeRecord
    # 无论什么状态都记录，并保存响应体
    try:
        # 创建ClaimRecord（所有状态都记录）
        ClaimRecord.objects.create(
            account=account,
            code_record=code_record,
            code=target_code,
            status=claim_status,
            bonus_value=str(bonus_value) if bonus_value else None,
            response_time_ms=elapsed_ms,
            error_message=error_msg,
            query_response_body=query_response_body_str,  # 查询接口的响应体（总是有）
            claim_response_body=claim_response_body_str  # 领取接口的响应体（仅当走到第二步时才有）
        )
        
        # 更新CodeRecord统计信息（不再更新status字段，因为码是跟个人绑定的）
        update_fields = {}
        if claim_status == 'claim_success':
            # 领取成功
            update_fields['success_count'] = F('success_count') + 1
            if bonus_value:
                update_fields['actual_value'] = str(bonus_value)
        elif claim_status == 'claim_failure':
            # 领取失败
            update_fields['failure_count'] = F('failure_count') + 1
        elif claim_status == 'inactive':
            # 次数领取完
            update_fields['failure_count'] = F('failure_count') + 1
        elif claim_status == 'already_claimed':
            # 已领过
            update_fields['failure_count'] = F('failure_count') + 1
        elif claim_status == 'weekly_wager_requirement':
            # 流水不够
            update_fields['failure_count'] = F('failure_count') + 1
        elif claim_status == 'error_403':
            # 403错误
            update_fields['error_403_count'] = F('error_403_count') + 1
        
        # 所有状态都增加总尝试次数
        update_fields['total_attempts'] = F('total_attempts') + 1
        
        if update_fields:
            CodeRecord.objects.filter(pk=code_record.pk).update(**update_fields)
    except Exception as e:
        logger.error(f"⚠️ 记录数据库失败: {e}")

def redeem_bonus_task(target_code, message_received_time=None, filter_username=None):
    """
    领取红包代码任务
    收到码直接执行请求，不检查是否有记录
    每次推送都创建唯一的 CodeRecord（以时间先后为准）
    
    Args:
        target_code: 目标代码
        message_received_time: Telegram 收到消息的时间戳（time.perf_counter()），用于计算总耗时
        filter_username: 如果指定，只使用该用户名的账号（用于测试频道）
    """
    # 获取激活的账号
    accounts = StakeAccount.objects.filter(is_active=True)
    
    # 如果指定了过滤用户名，只使用该用户名的账号
    if filter_username:
        accounts = accounts.filter(username=filter_username)
        logger.info(f"🧪 测试模式：仅使用账号名为 '{filter_username}' 的账号")
        if not accounts.exists():
            logger.warning(f"⚠️ 没有找到账号名为 '{filter_username}' 的激活账号")
            return
    elif not accounts.exists():
        logger.warning("⚠️ 没有激活的账号")
        return

    # 每次推送都创建新的 CodeRecord（唯一记录，不合并相同代码）
    code_record = CodeRecord.objects.create(
        code=target_code,
        status='unknown'
    )
    logger.info(f"📝 创建新的推送记录 ID: {code_record.id} | 代码: {target_code} | 时间: {code_record.created_at}")

    # 最大线程数 = 激活的账号数
    max_workers = len(accounts)

    logger.info(f"🔥 开始抢码任务: {target_code} | 并发线程: {len(accounts)} | 最大线程数: {max_workers} | 推送记录ID: {code_record.id}")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for account in accounts:
            executor.submit(request_single_account, account, target_code, code_record, message_received_time)
            # --- 【核心修复】：错峰请求 ---
            # 这样请求会变成排队发出，极大降低 56 错误
            time.sleep(random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX))


if __name__ == "__main__":
    code = input("请输入要测试的 Code: ").strip()
    if code:
        redeem_bonus_task(code)