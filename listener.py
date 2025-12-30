import os
import sys
import django
import asyncio
from telethon import TelegramClient, events

# ================= 1. 动态修正路径 =================
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = current_dir  # 现在 config.py 在项目根目录
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# ================= 2. 导入配置 =================
from config import (
    TELEGRAM_API_ID,
    TELEGRAM_API_HASH,
    TELEGRAM_TARGET_CHANNEL,
    TELEGRAM_PROXY,
    TELEGRAM_SESSION_FILE
)

# ================= 3. 初始化 Django 环境 =================
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'manager.settings')
django.setup()

# 导入领取函数
from worker import redeem_bonus_task

# ================= 4. Telegram 配置 =================
# 使用配置文件中的设置
client = TelegramClient(
    TELEGRAM_SESSION_FILE,
    TELEGRAM_API_ID,
    TELEGRAM_API_HASH,
    proxy=TELEGRAM_PROXY if TELEGRAM_PROXY else None
)


# ================= 5. 监听事件处理 =================
@client.on(events.NewMessage(chats=TELEGRAM_TARGET_CHANNEL))
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


# ================= 6. 启动 =================
async def main():
    print(f"🚀 监听机器人已启动...")
    await client.start()
    await client.run_until_disconnected()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 停止运行")