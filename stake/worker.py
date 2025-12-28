import os
import django
import json
import requests

# 1. 修正设置模块路径：根据你的 settings.py，这里应该是 'stake.settings'
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'stake.settings')

# 2. 初始化 Django 环境
# 必须先执行这一步，才能导入下方的 StakeAccount 模型，否则会报错或出红浪线
django.setup()

# 3. 在 setup 之后进行模型导入
from serverbot.models import StakeAccount

def redeem_bonus_task(target_code):
    """
    结合 Django 数据库执行领取任务
    """
    # 筛选激活状态且有 cookie 的账号
    accounts = StakeAccount.objects.filter(is_active=True).exclude(cookies_json__isnull=True)

    if not accounts.exists():
        print("❌ 没有找到有效的激活账号，请先完成过盾。")
        return

    for account in accounts:
        # --- 数据提取 ---
        token = account.token
        ua = account.user_agent

        # 处理代理：Django 会自动通过 proxy_id 找到关联的 address
        proxy_addr = account.proxy.address if account.proxy else None
        proxies = {"http": proxy_addr, "https": proxy_addr} if proxy_addr else None

        # 处理 Cookies：将数据库存的列表格式转换为 requests 字典格式
        try:
            # DrissionPage 存的是 [{}, {}] 列表
            raw_cookies = json.loads(account.cookies_json)
            cookie_dict = {c['name']: c['value'] for c in raw_cookies}
        except Exception as e:
            print(f"⚠️ 账号 {account.username} Cookie 解析失败: {e}")
            continue

        # --- 请求头与载荷 (保持你的原始逻辑) ---
        headers = {
            "accept": "*/*",
            "content-type": "application/json",
            "origin": "https://stake.com",
            "referer": f"https://stake.com/zh/settings/offers?type=drop&code={target_code}",
            "user-agent": ua,
            "x-access-token": token,
            "x-operation-name": "BonusCodeInformation",
        }

        payload = {
            "query": "query BonusCodeInformation($code: String!, $couponType: CouponType!) {\n  bonusCodeInformation(code: $code, couponType: $couponType) {\n    availabilityStatus\n    bonusValue\n  }\n}",
            "variables": {"code": target_code, "couponType": "drop"}
        }

        # --- 发送请求 ---
        try:
            print(f"\n🚀 正在尝试账号: {account.username} (Token: {token[:10]}...)")
            response = requests.post(
                "https://stake.com/_api/graphql",
                headers=headers,
                cookies=cookie_dict,
                json=payload,
                proxies=proxies,
                timeout=10
            )

            if response.status_code == 200:
                print(f"✅ {account.username} 请求成功")
                result = response.json()
                print(json.dumps(result, indent=4, ensure_ascii=False))
            else:
                print(f"❌ {account.username} 失败，状态码: {response.status_code}")
                # print(response.text) # 调试时开启

        except Exception as e:
            print(f"⚠️ {account.username} 请求异常: {e}")

if __name__ == "__main__":
    # 示例运行
    redeem_bonus_task("AJ3S7Y")