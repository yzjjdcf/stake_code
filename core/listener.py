"""
使用 Pyrogram 的监听器
基于 TDLib 的 Telegram 客户端
"""
import os
import sys
import django
import logging
import time
import signal
from datetime import datetime
from threading import Thread

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
    OPENAI_API_KEY = getattr(config_module, 'OPENAI_API_KEY', '')
    OPENAI_API_BASE_URL = getattr(config_module, 'OPENAI_API_BASE_URL', 'https://api.gpt.ge/v1/chat/completions')
    OPENAI_MODEL = getattr(config_module, 'OPENAI_MODEL', 'gpt-4o')
    OCR_API_URL = getattr(config_module, 'OCR_API_URL', '')
    OCR_API_TOKEN = getattr(config_module, 'OCR_API_TOKEN', '')
else:
    raise ImportError(f"无法找到配置文件: {config_path}")

# ================= 3. 初始化 Django 环境 =================
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'manager.settings')
django.setup()

from worker import redeem_bonus_task

# ================= 4. 导入可复用模块 =================
from parsers import CODE_PARSERS, parse_code_default
from ocr_utils import set_ocr_config
from video_processor import parse_code_daily_code_async

# 设置 OCR 配置
set_ocr_config(
    api_key=OPENAI_API_KEY,
    api_base_url=OPENAI_API_BASE_URL,
    model=OPENAI_MODEL,
    ocr_api_url=OCR_API_URL,
    ocr_api_token=OCR_API_TOKEN
)

# ================= 5. 配置日志 =================
log_dir = os.path.join(project_root, 'db', 'logs', 'listener')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'listener_pyrogram.log')

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

# ================= 6. Pyrogram 客户端配置 =================
try:
    from pyrogram import Client, filters
except ImportError:
    logger.error("❌ 未安装 Pyrogram，请运行: pip install pyrogram")
    sys.exit(1)

# 配置 Pyrogram 的 logger，确保它能够输出日志
pyrogram_logger = logging.getLogger("pyrogram")
pyrogram_logger.setLevel(logging.INFO)
pyrogram_logger.propagate = True

# 目标频道列表
target_channels = [
    -1001738096535,
    -1001977383442,
    -1003315955015,
    -1002032779602
]

# 频道ID到解析器的映射
channel_id_map = {
    -1002032779602: 'high_rollers_parser',  # HighRollersStake
    -1001977383442: 'daily_code_parser',  # daily
    -1003315955015: 'daily_code_parser',  # stake_cn_chat_room
    -1001738096535: 'rains_team_parser',  # RainsTEAM
}

# 转换代理格式（Pyrogram 使用不同的格式）
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

# 创建 Pyrogram 客户端
app = Client(
    TELEGRAM_SESSION_FILE or "pyrogram_session",
    api_id=TELEGRAM_API_ID,
    api_hash=TELEGRAM_API_HASH,
    proxy=pyrogram_proxy,
)


# ================= 7. 消息处理 =================
@app.on_message()
async def handle_channel_message(client, message):
    """处理频道消息"""
    try:
        # 忽略无法解析的频道
        if not message or not message.chat:
            return

        chat_id = message.chat.id
        chat_title = message.chat.title or "未知频道"
        chat_type = message.chat.type.name if hasattr(message.chat, 'type') else 'Unknown'
        is_outgoing = getattr(message, 'outgoing', False)

        # 只处理频道和超级群组消息
        if chat_type not in ['CHANNEL', 'SUPERGROUP']:
            return

        # 检查是否是我们监听的频道
        if chat_id not in target_channels:
            return

        # 对于频道（CHANNEL）类型，通常只处理非自己发送的消息
        # 但对于超级群组（SUPERGROUP），处理所有消息（包括自己发送的，因为可能是管理员）
        if is_outgoing and chat_type == 'CHANNEL':
            logger.debug(f"⚠️ 忽略自己发送的频道消息: {chat_title} ({chat_id})")
            return

        logger.info(f"✅ 匹配到目标频道: {chat_title} ({chat_id}) | 类型: {chat_type} | 是否自己发送: {is_outgoing}")

        # 获取解析器
        parser_name = channel_id_map.get(chat_id, 'default_parser')
        parser_func = CODE_PARSERS.get(parser_name, parse_code_default)

        # 提取消息文本和媒体信息
        raw_text = message.text or message.caption or ""
        has_video = message.video is not None

        # 记录收到消息
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"[{now}] --- 收到新消息 ---")
        logger.info(f"来源频道: {chat_title} ({chat_id})")
        logger.info(f"频道类型: {chat_type}")
        logger.info(f"消息ID: {message.id}")
        if has_video:
            logger.info(f"消息类型: 视频+文字")
        logger.info(f"消息内容: {raw_text[:200] if raw_text else '[媒体文件]'}")

        # 如果消息为空，跳过处理
        if not raw_text:
            logger.info("消息为空，跳过处理")
            return

        # 解析代码（支持视频和纯文字）
        parse_start_time = time.perf_counter()

        # 定义下载函数（适配 Pyrogram）
        async def download_video(message):
            """下载视频文件（Pyrogram 适配）"""
            return await message.download()

        if parser_name == 'daily_code_parser' and has_video:
            # 有视频的情况，需要异步处理
            logger.info("🎬 开始视频解析任务...")
            code = await parse_code_daily_code_async(
                raw_text,
                message=message,
                has_video=True,
                download_func=download_video
            )
        else:
            # 纯文字的情况，使用原来的解析方式
            code = parser_func(raw_text)

        parse_elapsed_ms = int((time.perf_counter() - parse_start_time) * 1000)
        if parser_name == 'daily_code_parser' and has_video:
            logger.info(f"⏱️ 视频解析总耗时: {parse_elapsed_ms}ms")

        if not code:
            logger.warning(f"⚠️ 无法从消息中提取代码（解析器: {parser_name}）")
            return

        logger.info(f"✅ 提取的代码: {code}")
        logger.info(f"🚀 正在开启新线程执行同步请求任务...")

        # 记录收到消息的时间戳
        message_received_time = time.perf_counter()

        # 检查是否是测试频道
        filter_username = None
        is_test_channel = (chat_id == -1003315955015)
        if is_test_channel:
            filter_username = 'yzjjdcf'
            logger.debug(f"🧪 测试频道模式：仅发送给账号名为 '{filter_username}' 的账号")

        # 使用线程执行同步任务
        def run_task():
            redeem_bonus_task(code, message_received_time, filter_username)

        thread = Thread(target=run_task, daemon=True)
        thread.start()
        logger.info(f"🚀 任务已提交到后台线程（不阻塞）: {code}")
        logger.info("-" * 40)

    except Exception as e:
        logger.error(f"❌ 处理消息时出错: {e}", exc_info=True)


# ================= 8. 启动 =================
if __name__ == "__main__":
    # 屏蔽 Ctrl+C 信号，防止停止监听
    def ignore_sigint(signum, frame):
        """忽略 SIGINT 信号（Ctrl+C），防止停止监听"""
        logger.info("⚠️ 收到 Ctrl+C 信号，但监听将继续运行（如需停止，请使用停止脚本）")


    # 使用 SIG_IGN 完全忽略信号，而不是自定义处理函数
    try:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    except (ValueError, OSError):
        # 某些平台可能不支持 SIG_IGN，使用自定义处理函数
        signal.signal(signal.SIGINT, ignore_sigint)
        signal.signal(signal.SIGTERM, ignore_sigint)

    logger.info("🚀 监听机器人正在启动（使用 Pyrogram）...")
    logger.info(f"📡 监听频道数量: {len(target_channels)}")
    channel_list = [f'{id} ({channel_id_map.get(id, "default_parser")})' for id in target_channels]
    logger.info(f"频道列表: {channel_list}")
    logger.info("🎧 开始监听消息...")
    logger.info("等待新消息中...")
    
    # 使用 app.run() 启动（Pyrogram 的标准方式）
    try:
        app.run()
    except KeyboardInterrupt:
        # 即使捕获到 KeyboardInterrupt，也不退出
        logger.info("⚠️ 收到中断信号，但监听将继续运行")
        # 重新设置信号处理并继续运行
        try:
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
        except (ValueError, OSError):
            signal.signal(signal.SIGINT, ignore_sigint)
            signal.signal(signal.SIGTERM, ignore_sigint)
        # 继续运行，不退出
        while True:
            time.sleep(1)
