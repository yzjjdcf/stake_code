"""
使用 Pyrogram 的监听器（简洁版本）
基于用户提供的可工作示例重写
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
    TELEGRAM_CHANNELS = getattr(config_module, 'TELEGRAM_CHANNELS', {})
    TELEGRAM_TARGET_CHANNEL = getattr(config_module, 'TELEGRAM_TARGET_CHANNEL', None)

    OPENAI_API_KEY = getattr(config_module, 'OPENAI_API_KEY', '')
    OPENAI_API_BASE_URL = getattr(config_module, 'OPENAI_API_BASE_URL', 'https://api.gpt.ge/v1/chat/completions')
    OPENAI_MODEL = getattr(config_module, 'OPENAI_MODEL', 'gpt-4o')

    if TELEGRAM_TARGET_CHANNEL and TELEGRAM_TARGET_CHANNEL not in TELEGRAM_CHANNELS:
        TELEGRAM_CHANNELS[TELEGRAM_TARGET_CHANNEL] = 'default_parser'
else:
    raise ImportError(f"无法找到配置文件: {config_path}")

# ================= 3. 初始化 Django 环境 =================
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'manager.settings')
django.setup()

from worker import redeem_bonus_task

# ================= 4. 解析器函数 =================
def parse_code_high_rollers(text):
    """解析 HighRollersStake 频道的代码"""
    import re
    if not text:
        return None
    text_normalized = text.replace('\n', ' ').replace('\r', ' ')
    patterns = [
        r'- Code:\s*([a-z0-9]+)',
        r'Code:\s*([a-z0-9]+)',
        r'-Code:\s*([a-z0-9]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text_normalized, re.IGNORECASE)
        if match:
            code = match.group(1).strip().lower()
            if re.match(r'^[a-z0-9]+$', code) and len(code) >= 10:
                return code
    return None

def parse_code_rains_team(text):
    """解析 RainsTEAM 频道的代码"""
    import re
    if not text:
        return None
    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        if not line or ' ' in line:
            continue
        if re.search(r'[!?.。！？]\s*$', line):
            continue
        if re.match(r'^(Number|Amount|Wager|Requirement|Total|Code|Value|Claims|Drop|Incoming|Normal|Alert|Bonus|Settings|Offers|Redeem|Click|Telegram|Channel|Safe|VIP|RTP|Duel|Gives)', line, re.IGNORECASE):
            continue
        common_words = ['drop', 'alert', 'bonus', 'value', 'total', 'limit', 'requirement', 'wagered', 'days', 'settings', 'offers', 'redeem', 'click', 'telegram', 'ads', 'channel', 'potential', 'scams', 'affiliated', 'safe', 'vip', 'rtp', 'duel', 'gives', 'normal', 'incoming', 'number', 'claims', 'amount']
        line_lower = line.lower()
        if any(word in line_lower for word in common_words):
            continue
        if re.match(r'^[a-zA-Z0-9]{1,25}$', line):
            if re.match(r'^\d{1,2}$', line):
                continue
            if line_lower in ['the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'her', 'was', 'one', 'our', 'out', 'day', 'get', 'has', 'him', 'his', 'how', 'its', 'may', 'new', 'now', 'old', 'see', 'two', 'way', 'who']:
                continue
            return line
    return None

def parse_code_daily_code(text):
    """解析 Daily Code 频道的代码"""
    import re
    if not text:
        return None
    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
        match = re.search(r'[Cc]ode[：:]\s*([a-z0-9]+)', line, re.IGNORECASE)
        if match:
            code = match.group(1).strip()
            if code.startswith('@'):
                continue
            if re.match(r'^[a-z0-9]+$', code) and len(code) >= 10:
                return code.lower()
    return None

def parse_code_default(text):
    """默认解析器"""
    if text:
        return text[:20].strip()
    return None

CODE_PARSERS = {
    'high_rollers_parser': parse_code_high_rollers,
    'rains_team_parser': parse_code_rains_team,
    'daily_code_parser': parse_code_daily_code,
    'default_parser': parse_code_default,
}

# ================= 5. 配置日志 =================
log_dir = os.path.join(project_root, 'db', 'logs')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'listener_pyrogram.log')

logging.basicConfig(
    level=logging.DEBUG,  # 临时改为 DEBUG 以便调试
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
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

# 转换代理格式
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

target_channels = [
    -1001738096535,
    -1001977383442,
    -1003315955015,
    -1002032779602
]

# 频道ID到解析器的映射
channel_id_map = {
    -1002032779602: 'high_rollers_parser',  # HighRollersStake
    -1001977383442: 'daily_code_parser',     # daily
    -1003315955015: 'rains_team_parser',    # stake_cn_chat_room
    -1001738096535: 'rains_team_parser',    # RainsTEAM
}

# 创建客户端
app = Client(
    TELEGRAM_SESSION_FILE or "pyrogram_session",
    api_id=TELEGRAM_API_ID,
    api_hash=TELEGRAM_API_HASH,
    proxy=pyrogram_proxy
)

# ================= 7. 消息处理 =================
# 先添加一个测试处理器，记录所有消息（放在最前面，确保能捕获所有消息）
# @app.on_message()
# async def test_all_messages(client, message):
#     """测试处理器：记录所有收到的消息"""
#     try:
#         chat_id = message.chat.id if message.chat else None
#         chat_type = message.chat.type.name if message.chat and hasattr(message.chat, 'type') else 'Unknown'
#         chat_title = message.chat.title if message.chat else 'Unknown'
#         is_outgoing = getattr(message, 'outgoing', False)
        
#         logger.info(f"🔍 [测试] 收到消息 - 频道: {chat_title} ({chat_id}) | 类型: {chat_type} | 是否自己发送: {is_outgoing} | 消息ID: {message.id}")
#     except Exception as e:
#         logger.error(f"❌ 测试处理器出错: {e}", exc_info=True)

@app.on_message()
async def handle_channel_message(client, message):
    """处理频道消息"""
    try:
        # 获取频道信息
        if not message.chat:
            return  # 没有聊天信息，忽略
        
        chat_id = message.chat.id
        chat_title = message.chat.title or "未知频道"
        chat_type = message.chat.type.name if hasattr(message.chat, 'type') else 'Unknown'
        is_outgoing = getattr(message, 'outgoing', False)
        
        # 只处理频道和超级群组消息
        if chat_type not in ['CHANNEL', 'SUPERGROUP']:
            return  # 不是频道或超级群组，忽略
        
        # 检查是否是我们监听的频道
        if chat_id not in target_channels:
            return  # 不是目标频道，忽略
        
        # 对于频道（CHANNEL）类型，通常只处理非自己发送的消息
        # 但对于超级群组（SUPERGROUP），处理所有消息（包括自己发送的，因为可能是管理员）
        if is_outgoing and chat_type == 'CHANNEL':
            logger.debug(f"⚠️ 忽略自己发送的频道消息: {chat_title} ({chat_id})")
            return
        
        logger.info(f"✅ 匹配到目标频道: {chat_title} ({chat_id}) | 类型: {chat_type} | 是否自己发送: {is_outgoing}")

        # 获取解析器
        parser_name = channel_id_map.get(chat_id, 'default_parser')
        parser_func = CODE_PARSERS.get(parser_name, parse_code_default)

        # 提取消息文本
        raw_text = message.text or message.caption or ""

        # 记录收到消息（添加调试信息）
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"[{now}] --- 收到新消息 ---")
        logger.info(f"来源频道: {chat_title} ({chat_id})")
        logger.info(f"频道类型: {message.chat.type.name if message.chat else 'Unknown'}")
        logger.info(f"消息ID: {message.id}")
        logger.info(f"消息内容: {raw_text[:200] if raw_text else '[媒体文件]'}")

        # 如果消息为空，跳过处理
        if not raw_text:
            logger.info("消息为空，跳过处理")
            return

        # 解析代码
        code = parser_func(raw_text)

        if not code:
            logger.warning(f"⚠️ 无法从消息中提取代码（解析器: {parser_name}）")
            return

        logger.info(f"✅ 提取的代码: {code}")
        logger.info(f"🚀 正在开启新线程执行同步请求任务...")

        # 记录收到消息的时间戳
        message_received_time = time.perf_counter()

        # 检查是否是测试频道
        filter_username = None
        channel_key = None
        for key, parser in TELEGRAM_CHANNELS.items():
            if channel_id_map.get(chat_id) == parser:
                channel_key = key
                break

        is_test_channel = (channel_key == 'stake_cn_chat_room')
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
    # 必须在 Pyrogram 启动之前设置，并且使用 signal.SIG_IGN 完全忽略信号
    def ignore_sigint(signum, frame):
        """忽略 SIGINT 信号（Ctrl+C），防止停止监听"""
        logger.info("⚠️ 收到 Ctrl+C 信号，但监听将继续运行（如需停止，请使用停止脚本）")
        # 不执行任何操作，完全忽略信号
    
    # 使用 SIG_IGN 完全忽略信号，而不是自定义处理函数
    # 这样可以防止 Pyrogram 内部接收到信号
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
    logger.info("🔍 测试模式已开启，将记录所有收到的消息（包括非目标频道）")
    logger.info("⚠️ 如果看不到消息，请检查：")
    logger.info("  1. 账号是否已加入目标频道")
    logger.info("  2. 频道ID是否正确")
    logger.info("  3. 查看日志文件，应该能看到 '[测试] 收到消息' 的日志")
    logger.info("  4. 如果连 '[测试] 收到消息' 都没有，说明 Pyrogram 没有收到任何消息")
    logger.info("⚠️ Ctrl+C 已被屏蔽，监听将继续运行（如需停止，请使用停止脚本）")

    # 使用 app.run() 启动（Pyrogram 的标准方式）
    # 注意：即使设置了 SIG_IGN，Pyrogram 内部可能仍然会处理信号
    # 如果仍然停止，需要检查 Pyrogram 的源码或使用其他方法
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
