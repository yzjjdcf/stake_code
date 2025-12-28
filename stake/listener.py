import os
import sys
import django
import asyncio
from telethon import TelegramClient, events

# ================= 1. 动态修正路径 =================
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# ================= 2. 初始化 Django 环境 =================
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'stake.settings')
django.setup()

# 导入领取函数
from worker import redeem_bonus_task

# ================= 3. Telegram 配置 =================
API_ID = 29656021
API_HASH = 'bb23c410c63a820d7c4209e0606d4aea'
TARGET_CHANNEL = 'stake_cn_chat_room'

proxy = ('socks5', '127.0.0.1', 10808)
client = TelegramClient('stake_listener_session', API_ID, API_HASH, proxy=proxy)


# ================= 4. 监听事件处理 =================
@client.on(events.NewMessage(chats=TARGET_CHANNEL))
async def my_event_handler(event):
    raw_text = event.raw_text.strip()
    if not raw_text:
        return

    # 直接截取前 10 个字符
    code = raw_text[:10]

    print(f"\n[📩] 收到消息，截取前10位代码: {code}")
    print(f"🚀 正在开启新线程执行同步请求任务...")

    # --- 修复核心：使用 asyncio.to_thread 运行同步函数 ---
    # 这样就不会触发 SynchronousOnlyOperation 错误
    await asyncio.to_thread(redeem_bonus_task, code)

    print(f"✅ 任务线程已结束")


# ================= 5. 启动 =================
async def main():
    print(f"🚀 监听机器人已启动...")
    await client.start()
    await client.run_until_disconnected()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 停止运行")