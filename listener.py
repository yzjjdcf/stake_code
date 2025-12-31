import os
import sys
import django
import asyncio
import logging
from datetime import datetime
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

# ================= 4. 配置日志 =================
# 配置日志输出到文件和控制台（必须在其他代码之前）
log_dir = os.path.join(project_root, 'logs')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'listener.log')

# 配置 logging
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

# ================= 5. Telegram 配置 =================
# 使用配置文件中的设置
client = TelegramClient(
    TELEGRAM_SESSION_FILE,
    TELEGRAM_API_ID,
    TELEGRAM_API_HASH,
    proxy=TELEGRAM_PROXY if TELEGRAM_PROXY else None
)


# ================= 6. 监听事件处理 =================
@client.on(events.NewMessage(chats=TELEGRAM_TARGET_CHANNEL))
async def my_event_handler(event):
    raw_text = event.raw_text.strip()
    if not raw_text:
        return

    # 直接截取前 10 个字符
    code = raw_text[:10]

    logger.info(f"📩 收到消息，原始内容: {raw_text[:50]}...")
    logger.info(f"📝 截取前10位代码: {code}")
    logger.info(f"🚀 正在开启新线程执行同步请求任务...")

    try:
        # --- 修复核心：使用 asyncio.to_thread 运行同步函数 ---
        # 这样就不会触发 SynchronousOnlyOperation 错误
        await asyncio.to_thread(redeem_bonus_task, code)
        logger.info(f"✅ 任务线程已结束: {code}")
    except Exception as e:
        logger.error(f"❌ 处理代码失败 {code}: {e}", exc_info=True)

# ================= 7. 启动 =================
async def main():
    logger.info("🚀 监听机器人正在启动...")
    try:
        await client.start()
        logger.info("✅ Telegram 客户端已连接")
        logger.info(f"📡 监听频道: {TELEGRAM_TARGET_CHANNEL}")
        await client.run_until_disconnected()
    except Exception as e:
        logger.error(f"❌ 启动失败: {e}", exc_info=True)
        raise


if __name__ == '__main__':
    try:
        logger.info("=" * 50)
        logger.info("启动 Telegram 监听器")
        logger.info(f"日志文件: {log_file}")
        logger.info("=" * 50)
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 停止运行")
    except Exception as e:
        logger.error(f"❌ 程序异常退出: {e}", exc_info=True)
        sys.exit(1)