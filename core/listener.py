import os
import sys
import django
import asyncio
import logging
from datetime import datetime
from telethon import TelegramClient, events

# ================= 1. 动态修正路径 =================
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)  # 项目根目录（包含 config/ 目录）
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# ================= 2. 导入配置 =================
import importlib.util
config_path = os.path.join(project_root, 'config', 'config.py')
if os.path.exists(config_path):
    spec = importlib.util.spec_from_file_location("config_module", config_path)
    config_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config_module)
    
    TELEGRAM_API_ID = config_module.TELEGRAM_API_ID
    TELEGRAM_API_HASH = config_module.TELEGRAM_API_HASH
    TELEGRAM_TARGET_CHANNEL = config_module.TELEGRAM_TARGET_CHANNEL
    TELEGRAM_PROXY = config_module.TELEGRAM_PROXY
    TELEGRAM_SESSION_FILE = config_module.TELEGRAM_SESSION_FILE
else:
    raise ImportError(f"无法找到配置文件: {config_path}")

# ================= 3. 初始化 Django 环境 =================
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'manager.settings')
django.setup()

# 导入领取函数
from worker import redeem_bonus_task

# ================= 4. 配置日志 =================
# 配置日志输出到文件和控制台（必须在其他代码之前）
log_dir = os.path.join(project_root, 'db', 'logs')
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
if TELEGRAM_PROXY:
    # 格式化显示代理信息（隐藏密码）
    if isinstance(TELEGRAM_PROXY, dict):
        proxy_type = TELEGRAM_PROXY.get('proxy_type', 'unknown')
        proxy_host = TELEGRAM_PROXY.get('addr', 'unknown')
        proxy_port = TELEGRAM_PROXY.get('port', 'unknown')
        has_auth = 'username' in TELEGRAM_PROXY or 'password' in TELEGRAM_PROXY
        proxy_info = f"{proxy_type}://{proxy_host}:{proxy_port}"
        if has_auth:
            proxy_info += " (带认证)"
        logger.info(f"使用代理连接: {proxy_info}")
        
        # 测试代理连接
        try:
            import socket
            test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_socket.settimeout(3)
            result = test_socket.connect_ex((proxy_host, proxy_port))
            test_socket.close()
            if result != 0:
                logger.warning(f"⚠️  代理服务器 {proxy_host}:{proxy_port} 无法连接，请检查代理是否运行")
                logger.warning(f"   请确认代理服务已启动，端口 {proxy_port} 正在监听")
            else:
                logger.info(f"✅ 代理服务器 {proxy_host}:{proxy_port} 连接正常")
        except Exception as e:
            logger.warning(f"⚠️  代理测试失败: {e}")
    else:
        logger.info(f"使用代理连接: {TELEGRAM_PROXY}")
else:
    logger.info("直接连接 Telegram（不使用代理）")

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
        logger.info("正在连接 Telegram 服务器...")
        await client.start()
        logger.info("✅ Telegram 客户端已连接")
        logger.info(f"📡 监听频道: {TELEGRAM_TARGET_CHANNEL}")
        await client.run_until_disconnected()
    except ConnectionError as e:
        logger.error(f"❌ 连接失败: {e}")
        if TELEGRAM_PROXY:
            logger.error("💡 提示：")
            logger.error("   1. 请检查代理服务是否正在运行")
            logger.error(f"   2. 请检查代理地址和端口是否正确: {TELEGRAM_PROXY}")
            logger.error("   3. 如果不需要代理，请在 config/config.py 中设置 TELEGRAM_PROXY = None")
        else:
            logger.error("💡 提示：")
            logger.error("   1. 请检查网络连接")
            logger.error("   2. 如果无法直接访问 Telegram，请配置代理")
            logger.error("   3. 在 config/config.py 中设置 TELEGRAM_PROXY = ('socks5', '127.0.0.1', 10808)")
        raise
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