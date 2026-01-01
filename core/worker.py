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
log_dir = os.path.join(project_root, 'db', 'logs')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'listener.log')  # 使用同一个日志文件

# 配置 logging（如果还没有配置过）
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] %(levelname)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
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
from serverbot.utils import fetch_ip_location


def request_single_account(account, target_code, code_record, message_received_time=None):
    """
    单个账号处理逻辑：
    - 代理分配并识别归属地
    - 执行请求并打印带地区、耗时的 Log
    
    Args:
        account: 账号对象
        target_code: 目标代码
        code_record: 本次推送的 CodeRecord 对象（每次推送都是唯一的）
        message_received_time: Telegram 收到消息的时间戳（time.perf_counter()），用于计算总耗时
    """
    # 记录账号开始处理的时间（排除错峰延迟的影响）
    account_start_time = time.perf_counter()
    needs_warmup = False

    # --- 第一步：代理检测与分配 ---
    if not account.proxy:
        logger.info(f"[*] 账号 {account.username} 缺失代理，正在分配...")
        proxy = ProxyPool.objects.filter(is_active=True, stakeaccount__isnull=True).first()
        if not proxy:
            proxy = ProxyPool.objects.filter(is_active=True).order_by('?').first()

        if proxy:
            StakeAccount.objects.filter(pk=account.pk).update(proxy=proxy)
            account.proxy = proxy
            needs_warmup = True
        else:
            logger.warning(f"❌ {account.username}: 代理池空，跳过")
            return

    # --- 【新增逻辑】：确保打印前拿到归属地 ---
    # 如果数据库里还没存过这个代理的地区，查一下
    if not getattr(account.proxy, 'location', None):
        loc = fetch_ip_location(account.proxy.address)
        ProxyPool.objects.filter(pk=account.proxy.pk).update(location=loc)
        account.proxy.location = loc  # 更新到当前对象

    # --- 第二步：Cookie 缺失检测 ---
    if not account.cookies_json:
        needs_warmup = True

    # --- 第三步：异步触发过盾（使用 Capsolver，不使用浏览器）---
    if needs_warmup:
        logger.info(f"🚀 {account.username} ({account.proxy.location}): 触发初始化过盾（Capsolver）...")
        # 传递 target_code，过盾完成后会自动复抢
        threading.Thread(target=run_pre_logic_capsolver, args=(account, target_code), daemon=True).start()
        return

    # --- 第四步：执行请求 ---
    proxy_addr = account.proxy.address.strip()
    location = account.proxy.location or "未知"
    
    # 解析代理地址（新格式：host:port:username:password）
    from serverbot.utils import parse_proxy_address
    proxy_info = parse_proxy_address(proxy_addr)
    
    if not proxy_info:
        logger.warning(f"⚠️ {account.username}: 无法解析代理地址: {proxy_addr}")
        return
    
    # 构建 curl_cffi 需要的代理格式
    # curl_cffi 需要 http://user:pass@host:port 格式（从新格式转换）
    # 注意：需要对用户名和密码进行 URL 编码，避免特殊字符（如 +、@、: 等）导致解析错误
    from urllib.parse import quote
    host = proxy_info['host']
    port = proxy_info['port']
    username = proxy_info.get('username') or ''
    password = proxy_info.get('password') or ''
    
    if username and password:
        # 有认证信息的代理，对用户名和密码进行 URL 编码
        encoded_username = quote(username, safe='')
        encoded_password = quote(password, safe='')
        proxy_url = f"http://{encoded_username}:{encoded_password}@{host}:{port}"
    else:
        # 无认证信息的代理
        proxy_url = f"http://{host}:{port}"
    
    proxies = {"http": proxy_url, "https": proxy_url}
    log_port = str(port)  # 用于日志显示

    try:
        cookie_dict = {c['name']: c['value'] for c in json.loads(account.cookies_json)}
    except:
        return

    headers = {
        "accept": "*/*",
        "content-type": "application/json",
        "origin": "https://stake.com",
        "referer": f"https://stake.com/zh/settings/offers?type=drop&code={target_code}",
        "user-agent": account.user_agent,
        "x-access-token": account.token,
        "x-operation-name": "BonusCodeInformation",
    }

    payload = {
        "query": "query BonusCodeInformation($code: String!, $couponType: CouponType!) {\n  bonusCodeInformation(code: $code, couponType: $couponType) {\n    availabilityStatus\n    bonusValue\n  }\n}",
        "variables": {"code": target_code, "couponType": "drop"}
    }

    # --- 【核心修复】：增加自动重试机制 ---
    max_retries = MAX_RETRIES
    response = None
    last_error = ""

    for attempt in range(max_retries):
        start_time = time.perf_counter()
        try:
            # 动态切换模拟指纹，增加迷惑性
            impersonate_ver = "chrome110" if attempt % 2 == 0 else "chrome120"

            response = curl_requests.post(
                "https://stake.com/_api/graphql",
                headers=headers,
                cookies=cookie_dict,
                json=payload,
                proxies=proxies,
                impersonate=impersonate_ver,
                timeout=15
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

    # 计算总耗时（毫秒）
    # 优先使用账号开始处理时间，这样不受错峰延迟影响
    # 如果提供了 message_received_time，也计算从收到消息到完成的时间
    total_elapsed_ms = None
    if account_start_time:
        # 从账号开始处理到请求完成的时间（排除错峰延迟）
        total_elapsed_ms = int((time.perf_counter() - account_start_time) * 1000)
    
    # 可选：也计算从收到消息到完成的时间（包含错峰延迟）
    # 如果需要看到包含错峰延迟的总耗时，可以取消下面的注释
    # if message_received_time:
    #     total_elapsed_from_message = int((time.perf_counter() - message_received_time) * 1000)
    #     logger.debug(f"   从收到消息到完成: {total_elapsed_from_message}ms (包含错峰延迟)")
    
    handle_response_result(
        response=response,
        account=account,
        log_port=log_port,
        location=location,
        elapsed_ms=elapsed_ms,
        total_elapsed_ms=total_elapsed_ms,  # 从收到消息到请求完成的总耗时
        last_error=last_error,
        target_code=target_code,
        code_record=code_record
    )


# ================= 2. 结果解析方法 (深度逻辑) =================
def handle_response_result(response, account, log_port, location, elapsed_ms, total_elapsed_ms, last_error, target_code, code_record):
    """
    深度解析 Stake GraphQL 返回的 JSON 数据
    并记录到数据库
    
    Args:
        elapsed_ms: 单个请求的耗时（毫秒）
        total_elapsed_ms: 从 Telegram 收到消息到请求完成的总耗时（毫秒）
    """
    claim_status = 'error'
    bonus_value = None
    error_msg = None
    
    # 格式化耗时信息
    if total_elapsed_ms is not None:
        time_info = f"请求耗时 {elapsed_ms}ms | 总耗时 {total_elapsed_ms}ms"
    else:
        time_info = f"耗时 {elapsed_ms}ms"
    
    if not response:
        logger.warning(f"⚠️ {account.username} ({log_port} - {location}) 彻底异常: {last_error[:40]} | {time_info}")
        claim_status = 'error'
        error_msg = last_error[:200] if last_error else "无响应"
    elif response.status_code == 403:
        # 情况 A: 403 盾拦截
        logger.warning(f"🛑 {account.username} ({log_port} - {location}): 403 拦截 | {time_info}")
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
                    logger.warning(f"❌ {account.username} ({log_port} - {location}): 无效码（未找到或不可用）| {time_info}")
                    claim_status = 'not_found'
                    error_msg = err_msg
                else:
                    logger.warning(f"❓ {account.username} ({log_port} - {location}): 接口报错: {err_msg} | {time_info}")
                    claim_status = 'error'
                    error_msg = err_msg
            elif data_root is None:
                # data 为 null，且没有 errors（这种情况应该不会发生，但为了安全）
                logger.warning(f"❌ {account.username} ({log_port} - {location}): 返回 Data 为 null | {time_info}")
                claim_status = 'not_found'
                error_msg = "返回 Data 为 null"
            else:
                # 2. 解析 Data 字段（data 不为 null）
                info = data_root.get('bonusCodeInformation')
                if info is None:
                    logger.warning(f"❌ {account.username} ({log_port} - {location}): 无效代码结构 | {time_info}")
                    claim_status = 'error'
                    error_msg = "无效代码结构"
                else:
                    status = info.get('availabilityStatus')
                    bonus_value = info.get('bonusValue')  # 获取奖金金额

                    # 3. 根据 Stake 状态码分支判定
                    if status == 'bonusCodeInactive':
                        # 码有效，但次数已用尽
                        logger.info(f"⌛ {account.username} ({log_port} - {location}): code次数用尽 (Inactive) | {time_info}")
                        claim_status = 'inactive'
                    elif status == 'available':
                        # 码有效且可用
                        logger.info(f"💰 {account.username} ({log_port} - {location}): 代码有效且可用 (Available)！ | {time_info}")
                        claim_status = 'success'
                        # 如果代码有效且有金额，会在 handle_response_result 中更新 CodeRecord
                    elif status == 'alreadyClaimed':
                        logger.info(f"🔁 {account.username} ({log_port} - {location}): 该代码已领过 | {time_info}")
                        claim_status = 'already_claimed'
                    elif status == 'weeklyWagerRequirement':
                        # 需要满足周投注要求
                        logger.info(f"📋 {account.username} ({log_port} - {location}): 需要周投注要求 (WeeklyWagerRequirement) | {time_info}")
                        claim_status = 'weekly_wager_requirement'
                        error_msg = "需要满足周投注要求才能使用此代码"
                    else:
                        logger.info(f"✅ {account.username} ({log_port} - {location}): [200 OK] 状态: {status} | {time_info}")
                        claim_status = 'error'
                        error_msg = f"未知状态: {status}"

        except Exception as e:
            logger.error(f"⚠️ {account.username} ({log_port} - {location}): 解析 JSON 失败: {e} | {time_info}")
            claim_status = 'error'
            error_msg = str(e)[:200]
    else:
        # 情况 C: 其他 HTTP 状态码 (500, 502 等)
        logger.warning(f"❌ {account.username} ({log_port} - {location}): 错误状态 {response.status_code} | {time_info}")
        claim_status = 'error'
        error_msg = f"HTTP {response.status_code}"
    
    # 提取响应体（无论什么状态都记录）
    response_body_str = None
    try:
        if response:
            # 尝试获取 JSON 格式的响应体
            try:
                response_body_str = json.dumps(response.json(), ensure_ascii=False, indent=2)
            except:
                # 如果不是 JSON，获取文本格式
                try:
                    response_body_str = response.text
                except:
                    response_body_str = f"无法获取响应体 (状态码: {response.status_code})"
        else:
            response_body_str = f"无响应对象 (错误: {last_error})"
    except Exception as e:
        response_body_str = f"提取响应体失败: {str(e)}"
    
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
            response_body=response_body_str
        )
        
        # 更新CodeRecord统计信息（只更新特定状态）
        update_fields = {}
        if claim_status == 'success':
            update_fields['success_count'] = F('success_count') + 1
            if bonus_value:
                update_fields['actual_value'] = str(bonus_value)
                update_fields['status'] = 'valid'
        elif claim_status == 'inactive':
            update_fields['failure_count'] = F('failure_count') + 1
            if code_record.status == 'unknown':
                update_fields['status'] = 'expired'
        elif claim_status == 'already_claimed':
            update_fields['failure_count'] = F('failure_count') + 1
        elif claim_status == 'weekly_wager_requirement':
            # 需要周投注要求：代码有效但账号不满足条件，视为失败但不影响代码有效性
            update_fields['failure_count'] = F('failure_count') + 1
        elif claim_status == 'error_403':
            update_fields['error_403_count'] = F('error_403_count') + 1
        
        # 所有状态都增加总尝试次数
        update_fields['total_attempts'] = F('total_attempts') + 1
        
        if update_fields:
            CodeRecord.objects.filter(pk=code_record.pk).update(**update_fields)
    except Exception as e:
        logger.error(f"⚠️ 记录数据库失败: {e}")

def redeem_bonus_task(target_code, message_received_time=None):
    """
    领取红包代码任务
    收到码直接执行请求，不检查是否有记录
    每次推送都创建唯一的 CodeRecord（以时间先后为准）
    
    Args:
        target_code: 目标代码
        message_received_time: Telegram 收到消息的时间戳（time.perf_counter()），用于计算总耗时
    """
    accounts = StakeAccount.objects.filter(is_active=True)
    if not accounts.exists():
        logger.warning("⚠️ 没有激活的账号")
        return

    # 每次推送都创建新的 CodeRecord（唯一记录，不合并相同代码）
    code_record = CodeRecord.objects.create(
        code=target_code,
        status='unknown'
    )
    logger.info(f"📝 创建新的推送记录 ID: {code_record.id} | 代码: {target_code} | 时间: {code_record.created_at}")

    unique_ports = accounts.exclude(proxy__isnull=True).values('proxy_id').distinct().count()
    max_workers = max(unique_ports, 10)

    logger.info(f"🔥 开始抢码任务: {target_code} | 并发线程: {len(accounts)} | 推送记录ID: {code_record.id}")

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