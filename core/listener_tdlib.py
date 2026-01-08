"""
使用 python-telegram (TDLib) 的监听器版本
"""
import os
import sys
import logging
import tempfile
import time
import asyncio
from threading import Thread

# 动态修正路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 导入配置
import importlib.util
config_path = os.path.join(project_root, 'config', 'config.py')
if os.path.exists(config_path):
    spec = importlib.util.spec_from_file_location("config_module", config_path)
    config_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config_module)

    TELEGRAM_API_ID = config_module.TELEGRAM_API_ID
    TELEGRAM_API_HASH = config_module.TELEGRAM_API_HASH
    TELEGRAM_SESSION_FILE = os.path.join(project_root, 'db', 'tdlib')
    TELEGRAM_PROXY = getattr(config_module, 'TELEGRAM_PROXY', None)
else:
    raise ImportError(f"无法找到配置文件: {config_path}")

# 初始化 Django 环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'manager.settings')
import django
django.setup()

from worker import redeem_bonus_task
from parsers import CODE_PARSERS, parse_code_default
from video_processor import parse_code_daily_code_async

# 日志配置
log_dir = os.path.join(project_root, 'db', 'logs', 'listener')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'listener_tdlib.log')

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)

# 目标频道列表
target_channels = [
    -1001738096535,
    -1001977383442,
    -1003315955015,
    -1002032779602
]

channel_id_map = {
    -1002032779602: 'high_rollers_parser',  # HighRollersStake
    -1001977383442: 'daily_code_parser',    # daily
    -1003315955015: 'daily_code_parser',    # stake_cn_chat_room
    -1001738096535: 'rains_team_parser',    # RainsTEAM
}

# telegram 客户端 (python-telegram / tdlib)
try:
    from telegram.client import Telegram
except ImportError:
    logger.error("❌ 未安装 python-telegram，请运行: pip install python-telegram")
    sys.exit(1)

# 创建 Telegram 客户端
tg = Telegram(
    api_id=TELEGRAM_API_ID,
    api_hash=TELEGRAM_API_HASH,
    phone=os.getenv('TELEGRAM_PHONE', '8613341403236'),  # 需在运行时输入验证码
    database_encryption_key='changekey123',
    files_directory=TELEGRAM_SESSION_FILE,
)
def download_video_file(file_id: int) -> str:
    """
    使用 TDLib 原生 downloadFile 下载文件（python-telegram）
    自动处理跨文件系统拷贝
    """
    try:
        tmp_dir = tempfile.mkdtemp(
            prefix="tdvideo_",
            dir="/dev/shm" if os.path.exists("/dev/shm") else None
        )

        # 1️⃣ 触发下载（同步）
        r = tg.call_method(
            "downloadFile",
            {
                "file_id": file_id,
                "priority": 32,
                "offset": 0,
                "limit": 0,
                "synchronous": True
            }
        )
        r.wait()

        # 2️⃣ 轮询直到下载完成
        while True:
            r2 = tg.call_method("getFile", {"file_id": file_id})
            r2.wait()

            file_obj = r2.update
            local = file_obj.get("local", {})

            if local.get("is_downloading_completed"):
                src_path = local.get("path")
                if src_path and os.path.exists(src_path):
                    dst_path = os.path.join(tmp_dir, "video.mp4")

                    # ✅ 关键修复：跨设备安全拷贝
                    import shutil
                    shutil.copy2(src_path, dst_path)

                    logger.info(f"✅ 视频已下载: {dst_path}")
                    return dst_path

            time.sleep(0.1)

    except Exception as e:
        logger.error(f"❌ 视频下载失败: {e}", exc_info=True)

    return ""


def handle_update(update):
    """
    处理 tdlib update（只关注 updateNewMessage）
    """
    try:
        if update.get('@type') != 'updateNewMessage':
            return
        message = update.get('message', {})
        chat_id = message.get('chat_id')
        if chat_id not in target_channels:
            return

        chat_title = message.get('chat', {}).get('title', '未知频道')
        is_outgoing = message.get('is_outgoing', False)

        # 文本/caption
        content = message.get('content', {})
        msg_type = content.get('@type')
        text_entities = ""
        if msg_type == 'messageText':
            text_entities = content.get('text', {}).get('text', '') or ''
        caption = content.get('caption', {}).get('text', '') if 'caption' in content else ''
        raw_text = text_entities or caption or ''

        has_video = msg_type == 'messageVideo'
        logger.info(f"✅ 匹配到目标频道: {chat_title} ({chat_id}) | 是否自己发送: {is_outgoing}")
        logger.info(f"消息类型: {'视频+文字' if has_video else '文字'}")
        logger.info(f"消息内容: {raw_text[:200] if raw_text else '[媒体]'}")

        if not raw_text and not has_video:
            return

        parser_name = channel_id_map.get(chat_id, 'default_parser')
        parser_func = CODE_PARSERS.get(parser_name, parse_code_default)

        # 视频解析
        code = None
        if parser_name == 'daily_code_parser' and has_video:
            video = content.get('video', {}).get('video', {})
            file_id = video.get('id')
            if file_id:
                video_path = download_video_file(file_id)
                if video_path:
                    class DummyMessage:
                        # 适配 parse_code_daily_code_async 的 download_func 使用路径
                        pass
                    dummy_msg = DummyMessage()
                    dummy_msg.file_path = video_path
                    # parse_code_daily_code_async 是协程，需等待
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    code = loop.run_until_complete(
                        parse_code_daily_code_async(
                            raw_text,
                            message=dummy_msg,
                            has_video=True,
                            download_func=lambda m: video_path
                        )
                    )
        else:
            code = parser_func(raw_text)

        if not code:
            logger.warning(f"⚠️ 无法从消息中提取代码（解析器: {parser_name}）")
            return

        logger.info(f"✅ 提取的代码: {code}")

        message_received_time = time.perf_counter()
        filter_username = 'yzjjdcf' if chat_id == -1003315955015 else None

        def run_task():
            redeem_bonus_task(code, message_received_time, filter_username)

        Thread(target=run_task, daemon=True).start()
        logger.info("🚀 任务已提交到后台线程（不阻塞）")

    except Exception as e:
        logger.error(f"❌ 处理 update 时出错: {e}", exc_info=True)


if __name__ == "__main__":
    try:
        tg.login()
        # 预加载 dialogs，减少 ghost peer
        try:
            tg.get_chats().wait()
        except Exception as e:
            logger.warning(f"⚠️ 预加载对话失败: {e}")

        tg.add_message_handler(handle_update)
        logger.info("🎧 TDLib 监听启动，等待消息...")
        tg.idle()
    except KeyboardInterrupt:
        logger.info("⚠️ 收到中断信号，准备退出")
    finally:
        try:
            tg.stop()
        except Exception:
            pass

