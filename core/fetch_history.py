"""
获取 Telegram 频道历史消息脚本
使用方法: python fetch_history.py
"""
import os
import sys
import logging
from datetime import datetime, timezone, timedelta

# ================= 1. 动态修正路径 =================
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
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
    TELEGRAM_PROXY = config_module.TELEGRAM_PROXY
    TELEGRAM_SESSION_FILE = config_module.TELEGRAM_SESSION_FILE
else:
    raise ImportError(f"无法找到配置文件: {config_path}")

# ================= 3. 配置日志 =================
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ================= 4. 导入 Pyrogram =================
try:
    from pyrogram import Client
except ImportError:
    logger.error("❌ 未安装 Pyrogram，请运行: pip install pyrogram")
    sys.exit(1)

# ================= 5. 配置代理 =================
pyrogram_proxy = None
if TELEGRAM_PROXY:
    if TELEGRAM_PROXY.get('type') == 'socks5':
        pyrogram_proxy = {
            "scheme": "socks5",
            "hostname": TELEGRAM_PROXY.get('host'),
            "port": TELEGRAM_PROXY.get('port'),
        }
        if TELEGRAM_PROXY.get('username') and TELEGRAM_PROXY.get('password'):
            pyrogram_proxy["username"] = TELEGRAM_PROXY.get('username')
            pyrogram_proxy["password"] = TELEGRAM_PROXY.get('password')
    elif TELEGRAM_PROXY.get('type') == 'http':
        pyrogram_proxy = {
            "scheme": "http",
            "hostname": TELEGRAM_PROXY.get('host'),
            "port": TELEGRAM_PROXY.get('port'),
        }
        if TELEGRAM_PROXY.get('username') and TELEGRAM_PROXY.get('password'):
            pyrogram_proxy["username"] = TELEGRAM_PROXY.get('username')
            pyrogram_proxy["password"] = TELEGRAM_PROXY.get('password')

# ================= 6. 目标频道 =================
TARGET_CHANNEL_ID = -1001977383442

# ================= 7. 创建客户端 =================
app = Client(
    TELEGRAM_SESSION_FILE or "pyrogram_session",
    api_id=TELEGRAM_API_ID,
    api_hash=TELEGRAM_API_HASH,
    proxy=pyrogram_proxy,
)

# ================= 8. 获取历史消息 =================
async def fetch_channel_history():
    """获取频道历史消息"""
    try:
        await app.start()
        logger.info("✅ 已连接到 Telegram")
        
        # 获取频道信息
        try:
            chat = await app.get_chat(TARGET_CHANNEL_ID)
            logger.info(f"📺 频道名称: {chat.title}")
            logger.info(f"📺 频道ID: {chat.id}")
            logger.info(f"📺 频道类型: {chat.type}")
        except Exception as e:
            logger.error(f"❌ 无法获取频道信息: {e}")
            return
        
        # 创建输出文件
        output_dir = os.path.join(project_root, 'db', 'history')
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, f'channel_{abs(TARGET_CHANNEL_ID)}_history.txt')
        
        logger.info(f"📝 开始获取历史消息，将保存到: {output_file}")
        logger.info("⏳ 这可能需要一些时间，请耐心等待...")
        
        # 东八区时区（UTC+8）
        tz_beijing = timezone(timedelta(hours=8))
        
        message_count = 0
        with open(output_file, 'w', encoding='utf-8') as f:
            # 获取当前时间（东八区）并格式化到毫秒
            now_beijing = datetime.now(tz_beijing)
            export_time = now_beijing.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]  # 精确到毫秒
            
            f.write(f"频道历史消息导出\n")
            f.write(f"频道ID: {TARGET_CHANNEL_ID}\n")
            f.write(f"频道名称: {chat.title}\n")
            f.write(f"导出时间: {export_time} (UTC+8)\n")
            f.write("=" * 80 + "\n\n")
            
            # 获取历史消息（从最新到最旧）
            # limit=0 表示获取所有消息，也可以设置具体数量，例如 limit=1000
            async for message in app.get_chat_history(TARGET_CHANNEL_ID, limit=10):
                message_count += 1
                
                # 格式化消息时间（转换为东八区并精确到毫秒）
                if message.date:
                    # message.date 是 UTC 时间，需要转换为东八区
                    # 如果 message.date 是 naive datetime，假设它是 UTC
                    if message.date.tzinfo is None:
                        # naive datetime，假设是 UTC
                        msg_utc = message.date.replace(tzinfo=timezone.utc)
                    else:
                        # 已经是 aware datetime
                        msg_utc = message.date.astimezone(timezone.utc)
                    
                    # 转换为东八区
                    msg_beijing = msg_utc.astimezone(tz_beijing)
                    # 格式化到毫秒
                    msg_date = msg_beijing.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3] + ' (UTC+8)'
                else:
                    msg_date = 'N/A'
                
                msg_text = message.text or message.caption or '[媒体文件]'
                
                # 写入文件
                f.write(f"[{msg_date}] 消息ID: {message.id}\n")
                f.write(f"内容: {msg_text}\n")
                
                # 如果有媒体
                if message.photo:
                    f.write(f"类型: 图片\n")
                elif message.video:
                    f.write(f"类型: 视频\n")
                elif message.document:
                    f.write(f"类型: 文档\n")
                
                f.write("-" * 80 + "\n")
                
                # 每 100 条消息打印一次进度
                if message_count % 100 == 0:
                    logger.info(f"📊 已获取 {message_count} 条消息...")
        
        logger.info(f"✅ 完成！共获取 {message_count} 条消息")
        logger.info(f"📁 消息已保存到: {output_file}")
        
    except Exception as e:
        logger.error(f"❌ 获取历史消息失败: {e}", exc_info=True)
    finally:
        await app.stop()

# ================= 9. 主函数 =================
if __name__ == "__main__":
    import asyncio
    asyncio.run(fetch_channel_history())

