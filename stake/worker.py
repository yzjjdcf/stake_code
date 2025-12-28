import os
import random
import sys
import json
# 使用 curl_cffi 解决 10054 错误
from curl_cffi import requests as curl_requests
import django
import time
import threading
from concurrent.futures import ThreadPoolExecutor

# 1. 环境初始化
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'stake.settings')
django.setup()

from serverbot.models import StakeAccount, ProxyPool
# 导入归属地查询工具
from serverbot.utils import run_pre_logic, fetch_ip_location


def request_single_account(account, target_code):
    """
    单个账号处理逻辑：
    - 代理分配并识别归属地
    - 执行请求并打印带地区、耗时的 Log
    """
    needs_warmup = False

    # --- 第一步：代理检测与分配 ---
    if not account.proxy:
        print(f"[*] 账号 {account.username} 缺失代理，正在分配...")
        proxy = ProxyPool.objects.filter(is_active=True, stakeaccount__isnull=True).first()
        if not proxy:
            proxy = ProxyPool.objects.filter(is_active=True).order_by('?').first()

        if proxy:
            StakeAccount.objects.filter(pk=account.pk).update(proxy=proxy)
            account.proxy = proxy
            needs_warmup = True
        else:
            print(f"❌ {account.username}: 代理池空，跳过")
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

    # --- 第三步：异步触发过盾 ---
    if needs_warmup:
        print(f"🚀 {account.username} ({account.proxy.location}): 触发初始化过盾...")
        threading.Thread(target=run_pre_logic, args=(account,), daemon=True).start()
        return

    # --- 第四步：执行请求 ---
    proxy_addr = account.proxy.address.strip()
    log_port = proxy_addr.split(':')[-1]
    location = account.proxy.location or "未知"
    proxies = {"http": proxy_addr, "https": proxy_addr}

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

    # --- 【核心修复】：增加 3 次自动重试机制 ---
    max_retries = 3
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

    handle_response_result(
        response=response,
        account=account,
        log_port=log_port,
        location=location,
        elapsed_ms=elapsed_ms,
        last_error=last_error
    )


# ================= 2. 结果解析方法 (深度逻辑) =================
def handle_response_result(response, account, log_port, location, elapsed_ms, last_error):
    """
    深度解析 Stake GraphQL 返回的 JSON 数据
    """
    if not response:
        print(f"⚠️ {account.username} ({log_port} - {location}) 彻底异常: {last_error[:40]} | 耗时 {elapsed_ms}ms")
        return

    # 情况 A: 403 盾拦截
    if response.status_code == 403:
        print(f"🛑 {account.username} ({log_port} - {location}): 403 拦截 | 耗时 {elapsed_ms}ms")
        StakeAccount.objects.filter(pk=account.pk).update(cookies_json=None)
        threading.Thread(target=run_pre_logic, args=(account,), daemon=True).start()
        return

    # 情况 B: 200 请求成功 (开始细分业务逻辑)
    if response.status_code == 200:
        try:
            res_json = response.json()

            # 1. 先看有没有报错 (Errors 字段)
            errors = res_json.get('errors', [])
            if errors:
                err_msg = errors[0].get('message', '')
                if "Bonus code cannot be found" in err_msg:
                    print(f"❌ {account.username} ({log_port} - {location}): 找不到代码 | 耗时 {elapsed_ms}ms")
                    return
                else:
                    print(f"❓ {account.username} ({log_port} - {location}): 接口报错: {err_msg} | 耗时 {elapsed_ms}ms")
                    return

            # 2. 解析 Data 字段
            data_root = res_json.get('data', {})
            # 兼容处理，防止 data 为 None
            if not data_root:
                print(f"❌ {account.username} ({log_port} - {location}): 返回 Data 为空 | 耗时 {elapsed_ms}ms")
                return

            info = data_root.get('bonusCodeInformation')
            if info is None:
                # 这种情况通常是代码格式完全不对
                print(f"❌ {account.username} ({log_port} - {location}): 无效代码结构 | 耗时 {elapsed_ms}ms")
                return

            status = info.get('availabilityStatus')

            # 3. 根据 Stake 状态码分支判定
            if status == 'bonusCodeInactive':
                # 对应：獎金掉落限額已達到
                print(f"⌛ {account.username} ({log_port} - {location}): 奖金限额已满 (Inactive) | 耗时 {elapsed_ms}ms")
            elif status == 'available':
                print(f"💰 {account.username} ({log_port} - {location}): 代码有效(Available)！ | 耗时 {elapsed_ms}ms")
            elif status == 'alreadyClaimed':
                print(f"🔁 {account.username} ({log_port} - {location}): 该代码已领过 | 耗时 {elapsed_ms}ms")
            else:
                print(f"✅ {account.username} ({log_port} - {location}): [200 OK] 状态: {status} | 耗时 {elapsed_ms}ms")

        except Exception as e:
            print(f"⚠️ {account.username} ({log_port} - {location}): 解析 JSON 失败: {e} | 耗时 {elapsed_ms}ms")
    else:
        # 情况 C: 其他 HTTP 状态码 (500, 502 等)
        print(f"❌ {account.username} ({log_port} - {location}): 错误状态 {response.status_code} | 耗时 {elapsed_ms}ms")

def redeem_bonus_task(target_code):
    accounts = StakeAccount.objects.filter(is_active=True)
    if not accounts.exists():
        return

    unique_ports = accounts.exclude(proxy__isnull=True).values('proxy_id').distinct().count()
    max_workers = max(unique_ports, 10)

    print(f"🔥 开始抢码任务: {target_code} | 并发线程: {len(accounts)}")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for account in accounts:
            executor.submit(request_single_account, account, target_code)
            # --- 【核心修复】：错峰 0.3-0.5 秒 ---
            # 这样请求会变成排队发出，极大降低 56 错误
            time.sleep(random.uniform(0.1, 0.3))


if __name__ == "__main__":
    code = input("请输入要测试的 Code: ").strip()
    if code:
        redeem_bonus_task(code)