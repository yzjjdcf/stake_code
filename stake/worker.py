import os
import sys
import json
import requests
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
from serverbot.utils import run_pre_logic


def request_single_account(account, target_code):
    """
    单个账号处理逻辑：
    - 代理/Cookie 缺失检测
    - 执行请求
    - 403 自动触发过盾修复 (调用 run_pre_logic)
    """
    needs_warmup = False

    # --- 第一步：代理检测与分配 ---
    if not account.proxy:
        print(f"[*] 账号 {account.username} 缺失代理，正在分配...")
        # 优先找没被占用的，没有就随机
        proxy = ProxyPool.objects.filter(is_active=True, stakeaccount__isnull=True).first()
        if not proxy:
            proxy = ProxyPool.objects.filter(is_active=True).order_by('?').first()

        if proxy:
            StakeAccount.objects.filter(pk=account.pk).update(proxy=proxy)
            account.proxy = proxy
            print(f"[+] {account.username} 已绑定新代理: {proxy.address.split(':')[-1]}")
            needs_warmup = True
        else:
            print(f"❌ {account.username}: 代理池空，跳过")
            return

    # --- 第二步：Cookie 缺失检测 ---
    if not account.cookies_json:
        needs_warmup = True

    # --- 第三步：异步触发过盾 ---
    if needs_warmup:
        print(f"🚀 {account.username}: 触发初始化过盾逻辑...")
        # 统一走你的 utils 逻辑
        threading.Thread(target=run_pre_logic, args=(account,), daemon=True).start()
        return

    # --- 第四步：执行请求 ---
    # 核心修正：直接使用数据库里的完整 URI
    proxy_addr = account.proxy.address.strip()
    # 仅用于日志显示端口
    log_port = proxy_addr.split(':')[-1]

    # 直接赋值，不要再加 "http://" 拼接
    proxies = {
        "http": proxy_addr,
        "https": proxy_addr
    }

    try:
        cookie_dict = {c['name']: c['value'] for c in json.loads(account.cookies_json)}
    except:
        print(f"⚠️ {account.username}: Cookie 解析失败")
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

    try:
        # 使用 Session 保持长连接性能更好
        with requests.Session() as session:
            response = session.post(
                "https://stake.com/_api/graphql",
                headers=headers,
                cookies=cookie_dict,
                json=payload,
                proxies=proxies,
                timeout=12  # 考虑代理延迟，稍微拉长
            )

            # --- 403 触发过盾 ---
            if response.status_code == 403:
                print(f"🛑 {account.username} ({log_port}): 遇到 403 盾！正在清除 Cookie 并调用 run_pre_logic...")
                StakeAccount.objects.filter(pk=account.pk).update(cookies_json=None)
                threading.Thread(target=run_pre_logic, args=(account,), daemon=True).start()
                return

            if response.status_code == 200:
                res_json = response.json()
                errors = res_json.get('errors') or []
                is_not_found = any("Bonus code cannot be found" in err.get('message', '') for err in errors)

                if is_not_found:
                    print(f"❌ {account.username} ({log_port}): 找不到代码")
                else:
                    print(f"✅ {account.username} ({log_port}) [200 OK]")
                    # 这里你可以写具体的抢码成功后的入库逻辑
            else:
                print(f"❌ {account.username} ({log_port}): 状态码 {response.status_code}")

    except Exception as e:
        print(f"⚠️ {account.username} ({log_port}) 异常: {str(e)}")


def redeem_bonus_task(target_code):
    """并发入口：每个代理一个 worker"""
    accounts = StakeAccount.objects.filter(is_active=True)
    if not accounts.exists():
        print("❌ 无激活账号")
        return

    # 根据独立代理数量决定线程数
    unique_ports = accounts.exclude(proxy__isnull=True).values('proxy_id').distinct().count()
    max_workers = max(unique_ports, 5)

    print(f"🔥 开始抢码任务: {target_code} | 并发线程: {max_workers}")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for account in accounts:
            executor.submit(request_single_account, account, target_code)


if __name__ == "__main__":
    # 测试代码：手动输入一个 code
    code = input("请输入要测试的 Code: ").strip()
    if code:
        redeem_bonus_task(code)