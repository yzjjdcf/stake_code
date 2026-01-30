"""
使用 python-telegram (TDLib) 的监听器版本
"""
import os
import sys
import logging
import tempfile
import time
import asyncio
import json
import ipaddress
import random
from threading import Thread
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import shutil

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
    WEBSOCKET_PUBLIC_IP = getattr(config_module, 'WEBSOCKET_PUBLIC_IP', None)
else:
    raise ImportError(f"无法找到配置文件: {config_path}")

# 日志配置（在 Django setup 之前，避免 Django 添加 handlers）
log_dir = os.path.join(project_root, 'db', 'logs', 'listener')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'listener_tdlib.log')

# 初始化 Django 环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'manager.settings')
import django
django.setup()

# Django setup 之后，导入 Django 模型（确保在 Django 完全初始化后导入）
from frontend.models import StakeAccount, UserProfile

# Django setup 之后，重新配置日志（清除 Django 可能添加的 handlers）
from parsers import CODE_PARSERS, parse_code_default
from video_processor import parse_code_daily_code_async

# WebSocket 相关
try:
    import websockets
    from websockets.server import serve
except ImportError:
    print("❌ 未安装 websockets，请运行: pip install websockets")
    sys.exit(1)

# 自定义 Formatter，支持毫秒精度
class MillisecondFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        # 获取时间并格式化为包含毫秒的格式
        ct = self.converter(record.created)
        t = time.strftime('%Y-%m-%d %H:%M:%S', ct)
        s = '%s.%03d' % (t, record.msecs)
        return s

# 全局变量，用于日志轮转
current_file_handler = None

def rotate_log_file():
    """轮转日志文件：将当前日志保存为带日期的文件，创建新的日志文件"""
    global current_file_handler
    logger_instance = logging.getLogger('listener_tdlib')
    
    try:
        # 获取当前时间（服务器时区应该是 UTC+8 北京时间）
        now = datetime.now()
        # 获取昨天的日期（用于命名轮转后的日志文件，因为是在 0 点轮转，所以是昨天的日志）
        yesterday = now - timedelta(days=1)
        date_str = yesterday.strftime('%Y-%m-%d')
        
        # 如果日志文件存在且有内容，则重命名
        if os.path.exists(log_file) and os.path.getsize(log_file) > 0:
            dated_log_file = os.path.join(log_dir, f'listener_tdlib_{date_str}.log')
            
            # 先创建新的 FileHandler（避免日志写入中断）
            new_file_handler = logging.FileHandler(log_file, encoding='utf-8')
            new_file_handler.setLevel(logging.INFO)
            new_file_handler.setFormatter(MillisecondFormatter(
                '[%(asctime)s] %(levelname)s: %(message)s'
            ))
            logger_instance.addHandler(new_file_handler)
            
            # 然后关闭旧的 handler
            if current_file_handler:
                current_file_handler.flush()  # 确保所有日志都已写入
                current_file_handler.close()
                logger_instance.removeHandler(current_file_handler)
            
            # 重命名日志文件
            if os.path.exists(log_file):
                # 先复制文件内容到新文件（保留旧文件用于重命名）
                temp_file = log_file + '.tmp'
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                shutil.copy2(log_file, temp_file)
                
                # 重命名旧文件
                if os.path.exists(dated_log_file):
                    os.remove(dated_log_file)  # 如果已存在同名文件，先删除
                shutil.move(temp_file, dated_log_file)
                
                # 清空当前日志文件（因为新 handler 已经创建，会继续写入）
                with open(log_file, 'w', encoding='utf-8') as f:
                    f.write('')  # 清空文件
            
            # 更新全局 handler 引用
            current_file_handler = new_file_handler
            logger_instance.info(f"📁 日志已轮转: listener_tdlib.log -> listener_tdlib_{date_str}.log")
            logger_instance.info(f"📝 新日志文件已创建: {log_file}")
    except Exception as e:
        # 如果轮转失败，记录错误但不影响主程序
        try:
            logger_instance.error(f"❌ 日志轮转失败: {e}", exc_info=True)
        except:
            print(f"❌ 日志轮转失败: {e}")

def log_rotation_scheduler():
    """日志轮转调度器：每天北京时间 0 点执行轮转和清空 sent_codes"""
    logger_instance = logging.getLogger('listener_tdlib')
    
    while True:
        try:
            # 获取当前时间（服务器时区应该是 UTC+8 北京时间）
            now = datetime.now()
            
            # 计算到今天 0 点的时间
            target_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
            if now >= target_time:
                # 如果已经过了 0 点，则设置为明天的 0 点
                target_time += timedelta(days=1)
            
            # 计算需要等待的秒数
            wait_seconds = (target_time - now).total_seconds()
            
            logger_instance.info(f"📅 日志轮转调度器：将在 {wait_seconds/3600:.2f} 小时后（北京时间 {target_time.strftime('%Y-%m-%d %H:%M:%S')}）执行日志轮转和清空代码集合")
            
            # 等待到 0 点
            time.sleep(wait_seconds)
            
            # 执行轮转
            rotate_log_file()
            
            # 清空 sent_codes 集合（每天零点清空，避免代码去重集合过大）
            global sent_codes
            codes_count = len(sent_codes)
            sent_codes.clear()
            logger_instance.info(f"🔄 已清空代码去重集合（共 {codes_count} 个代码），新的一天开始")
            
            # 等待 2 分钟，确保轮转完成后再继续
            time.sleep(120)
            
        except Exception as e:
            try:
                logger_instance.error(f"❌ 日志轮转调度器错误: {e}", exc_info=True)
            except:
                print(f"❌ 日志轮转调度器错误: {e}")
            # 如果出错，等待 1 小时后重试
            time.sleep(3600)

# 配置日志（在 Django setup 之后，确保清除 Django 添加的 handlers）
def configure_logging():
    """配置日志系统，确保没有重复的 handlers"""
    global current_file_handler
    
    # 清除所有现有的 handlers（包括 Django 可能添加的）
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    root_logger.setLevel(logging.WARNING)  # 根 logger 只显示警告和错误
    root_logger.propagate = False  # 根 logger 不传播
    
    # 获取当前模块的 logger（使用独立的 logger，避免与其他模块冲突）
    logger = logging.getLogger('listener_tdlib')
    logger.setLevel(logging.INFO)
    # 清除可能存在的旧 handlers（包括 Django 可能添加的）
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    logger.propagate = False  # 不传播到根 logger，避免重复日志
    
    # 为当前 logger 添加文件 handler（只添加一次）
    current_file_handler = logging.FileHandler(log_file, encoding='utf-8')
    current_file_handler.setLevel(logging.INFO)
    current_file_handler.setFormatter(MillisecondFormatter(
        '[%(asctime)s] %(levelname)s: %(message)s'
    ))
    logger.addHandler(current_file_handler)
    
    # 确保没有 StreamHandler（避免输出到 stdout/stderr，导致重复）
    # 因为 start_all.sh 使用 &>> 重定向 stdout/stderr 到日志文件
    # 如果 logger 也输出到 stdout/stderr，就会导致日志重复
    for handler in logger.handlers[:]:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            logger.removeHandler(handler)
    
    # 确保只有一个 FileHandler
    file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
    if len(file_handlers) > 1:
        # 如果多个 FileHandler，只保留第一个
        for handler in file_handlers[1:]:
            logger.removeHandler(handler)
    
    return logger

# Django setup 之后，配置日志并获取 logger
logger = configure_logging()

# 禁用 websockets 库的日志输出（避免重复日志）
websockets_logger = logging.getLogger('websockets')
websockets_logger.setLevel(logging.WARNING)  # 只显示警告和错误，不显示 INFO
websockets_logger.propagate = False  # 不传播到根 logger，避免重复
websockets_logger.handlers = []  # 清除所有 handlers

# 禁用其他可能产生重复日志的库
asyncio_logger = logging.getLogger('asyncio')
asyncio_logger.setLevel(logging.WARNING)
asyncio_logger.propagate = False
asyncio_logger.handlers = []

# 禁用 python-telegram 库的日志输出（避免重复日志）
telegram_logger = logging.getLogger('telegram')
telegram_logger.setLevel(logging.WARNING)
telegram_logger.propagate = False
telegram_logger.handlers = []

# 禁用 TDLib 相关的日志输出
tdlib_logger = logging.getLogger('tdlib')
tdlib_logger.setLevel(logging.WARNING)
tdlib_logger.propagate = False
tdlib_logger.handlers = []

# 禁用所有 Django 相关的 logger（避免 Django 的日志配置导致重复）
django_loggers = [
    'django',
    'django.request',
    'django.server',
    'django.db',
    'django.db.backends',
    'django.core',
    'django.utils',
    'django.template',
    'django.contrib',
    'manager',
    'core',
]
for logger_name in django_loggers:
    django_log = logging.getLogger(logger_name)
    django_log.setLevel(logging.WARNING)
    django_log.propagate = False
    for handler in django_log.handlers[:]:
        django_log.removeHandler(handler)

# 目标频道列表
target_channels = [
    -1001738096535,  # RainsTEAM
    -1001977383442,  # daily
    -1003315955015,  # 测试频道
    -1001992047801,  # HighRollersStake
    -1002140237447,  # FC频道，使用 code_format_parser
    -1003538327109,  # 补码频道，使用 code_format_parser
    -1002493460363,  # private_code，使用 rains_team_parser
    -1002252848959,  # fast_code，使用 code_format_parser
    -1002375522843,  # CodeStats.gg，使用 user_submitted_parser
]

# 核心频道列表（用于 openChat 优化，提高更新优先级）
# 包含所有目标频道，用于拉活和提高优先级
core_channels = target_channels.copy()  # 包含所有频道，包括测试频道

# 测试频道 ID（用于消息处理逻辑，判断是否是测试频道）
TEST_CHANNEL_ID = -1003315955015

channel_id_map = {
    -1001992047801: 'high_rollers_parser',  # HighRollersStake
    -1001977383442: 'daily_code_parser',    # daily
    -1003315955015: 'daily_code_parser',    # stake_cn_chat_room
    -1001738096535: 'rains_team_parser',    # RainsTEAM
    -1002140237447: 'code_format_parser',   # FC频道，解析 Code: stakecode 格式
    -1003538327109: 'code_format_parser',   # 补码频道，解析 Code: stakecode 格式
    -1002493460363: 'rains_team_parser',    # private_code，使用 rains_team_parser
    -1002252848959: 'code_format_parser',    # fast_code，使用 code_format_parser
    -1002375522843: 'user_submitted_parser', # CodeStats.gg，解析 USER SUBMITTED STAKE CODE 格式
}

# 频道名称映射（用于日志输出）
channel_name_map = {
    -1001992047801: 'high_roller',      # HighRollersStake
    -1001977383442: 'daily_drop',       # daily
    -1003315955015: '测试频道',          # stake_cn_chat_room
    -1001738096535: '周奖频道',          # RainsTEAM
    -1002140237447: 'FC频道',            # FC频道
    -1003538327109: '补码频道',          # 补码频道
    -1002493460363: 'private_code',     # private_code
    -1002252848959: 'fast_code',        # fast_code
    -1002375522843: 'CodeStats.gg',     # CodeStats.gg
}

# 代码转发目标频道
CODE_FORWARD_CHANNEL_ID = -1003559537591

# WebSocket 配置
# 如果使用 nginx 反向代理，监听本地地址（127.0.0.1）更安全
# 如果直接暴露，使用 0.0.0.0
WEBSOCKET_HOST = os.getenv('WEBSOCKET_HOST', '127.0.0.1')  # 默认本地，可通过环境变量覆盖
WEBSOCKET_PORT = 8765
connected_clients = set()  # 存储所有连接的客户端
client_username_map = {}  # 存储客户端 WebSocket 到 username 的映射 {websocket: username}
client_user_id_map = {}  # 存储客户端 WebSocket 到 user_id 的映射 {websocket: user_id}
client_addr_map = {}  # 存储客户端 WebSocket 到地址的映射 {websocket: (ip, port)}
client_connect_time_map = {}  # 存储客户端 WebSocket 到连接时间的映射 {websocket: datetime}
account_to_websocket_v1 = {}  # 存储账号到 V1 WebSocket 的映射 {username: set(websockets)}，同一账号可以有多个V1连接
account_to_websocket_v2 = {}  # 存储账号到 V2 WebSocket 的映射 {username: set(websockets)}，同一账号可以有多个V2连接
websocket_version_map = {}  # 存储 WebSocket 到版本的映射 {websocket: 'v1' or 'v2'}
websocket_user_map = {}  # 存储 WebSocket 到用户的映射 {websocket: User对象}，用于V2数据归属（在验证时确定）
websocket_loop = None  # 存储 WebSocket 服务器的事件循环
sent_codes = set()  # 存储已下发的代码（用于去重，避免重复下发）

# 线程池执行器（用于异步处理消息，避免阻塞主线程）
# 使用最多 4 个工作线程，避免过多线程导致资源竞争
message_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="msg_handler")

# telegram 客户端 (python-telegram / tdlib)
try:
    from telegram.client import Telegram
except ImportError:
    logger.error("❌ 未安装 python-telegram，请运行: pip install python-telegram")
    sys.exit(1)

# 创建 Telegram 客户端
# 优化配置以减少消息接收延迟
tg = Telegram(
    api_id=TELEGRAM_API_ID,
    api_hash=TELEGRAM_API_HASH,
    phone=os.getenv('TELEGRAM_PHONE', '8618686513193'),  # 需在运行时输入验证码
    database_encryption_key='changekey123',
    files_directory=TELEGRAM_SESSION_FILE,
    tdlib_verbosity=0,  # 0=错误, 1=警告, 2=信息, 3=调试。设置为0只显示错误
    # 优化参数：使用生产环境（更快）
    use_test_dc=False,
    # 设备信息（用于优化连接）
    device_model='Server',
    system_version='Linux',
    application_version='1.0.0',
    # 库路径（如果需要指定）
    # library_path=None,  # 使用系统默认路径
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
    优化：快速检查，耗时操作异步处理，避免阻塞消息接收
    """
    # 快速检查：只做最基本的过滤，避免阻塞
    if update.get('@type') != 'updateNewMessage':
        return
    
    message = update.get('message', {})
    chat_id = message.get('chat_id')
    if chat_id not in target_channels:
        return
    
    # 将耗时处理提交到线程池，避免阻塞主线程
    # 这样可以快速返回，让 TDLib 继续处理下一个消息
    message_executor.submit(process_message_async, update)


def process_message_async(update):
    """
    异步处理消息（在线程池中执行）
    优化：提取到 code 后第一时间发送给客户端，其他操作异步执行
    """
    # 第一时间记录收到 update 的时间
    update_received_time = datetime.now()
    update_received_timestamp = time.perf_counter()
    
    try:
        message = update.get('message', {})
        chat_id = message.get('chat_id')
        message_date = message.get('date', 0)
        message_id = message.get('id', 0)
        channel_name = channel_name_map.get(chat_id, message.get('chat', {}).get('title', '未知频道'))
        
        # 文本/caption
        content = message.get('content', {})
        msg_type = content.get('@type')
        text_entities = ""
        if msg_type == 'messageText':
            text_entities = content.get('text', {}).get('text', '') or ''
        caption = content.get('caption', {}).get('text', '') if 'caption' in content else ''
        raw_text = text_entities or caption or ''
        has_video = msg_type == 'messageVideo'
        
        if not raw_text and not has_video:
            return

        parser_name = channel_id_map.get(chat_id, 'default_parser')
        parser_func = CODE_PARSERS.get(parser_name, parse_code_default)
        TEST_USERNAMES = ['yzjjdcf', 'qqqq465430525']
        is_test_channel = (chat_id == TEST_CHANNEL_ID)
        FC_CHANNEL_ID = -1002140237447
        is_fc_channel = (chat_id == FC_CHANNEL_ID)
        
        # 快速提取代码
        code = None
        if is_fc_channel:
            code = parser_func(raw_text)
            if not code:
                return
        
        # 计算延迟（保留延迟日志）
        delay_ms = None
        if message_date > 0:
            message_datetime = datetime.fromtimestamp(message_date)
            delay_seconds = (update_received_time - message_datetime).total_seconds()
            delay_ms = int(delay_seconds * 1000)
        
        # 定义发送代码的函数（用于二次识别后的发送）
        def send_code_via_websocket(code_to_send):
            """通过 WebSocket 发送代码给客户端（带去重检查，测试频道不做去重）"""
            try:
                # 检查代码是否已下发过（测试频道不做去重）
                if not is_test_channel:
                    if code_to_send in sent_codes:
                        current_time = datetime.now()
                        time_str = current_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                        logger.debug(f"[{time_str}] ⏭️ 代码已下发过，跳过: {code_to_send}")
                        return
                    
                    # 添加到已下发集合
                    sent_codes.add(code_to_send)
                
                server_time = datetime.now()
                server_timestamp_ms = int(server_time.timestamp() * 1000)
                message_data = {
                    'type': 'code_detected',
                    'code': code_to_send,
                    'channel_id': chat_id,
                    'channel_title': channel_name,
                    'parser': parser_name,
                    'timestamp': server_time.isoformat(),
                    'server_timestamp_ms': server_timestamp_ms,
                    'message_received_time': time.perf_counter(),
                    'is_retry': True  # 标记为二次识别
                }
                
                filter_usernames = TEST_USERNAMES if is_test_channel else None
                ws_loop = get_websocket_loop()
                if ws_loop and ws_loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        broadcast_to_clients(message_data, filter_usernames=filter_usernames),
                        ws_loop
                    )
                else:
                    Thread(target=lambda: asyncio.run(broadcast_to_clients(message_data, filter_usernames=filter_usernames)), daemon=True).start()
                logger.info(f"📤 二次识别代码已发送: {code_to_send}")
            except Exception as e:
                logger.error(f"❌ 发送二次识别代码失败: {e}")
        
        # 视频解析（如果需要）
        if not code:
            if parser_name == 'daily_code_parser' and has_video:
                video = content.get('video', {}).get('video', {})
                file_id = video.get('id')
                if file_id:
                    video_path = download_video_file(file_id)
                    if video_path:
                        class DummyMessage:
                            pass
                        dummy_msg = DummyMessage()
                        dummy_msg.file_path = video_path
                        # 在线程池中运行时，创建新的事件循环（避免与 WebSocket 循环冲突）
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            code = loop.run_until_complete(
                                parse_code_daily_code_async(
                                    raw_text,
                                    message=dummy_msg,
                                    has_video=True,
                                    download_func=lambda m: video_path,
                                    send_code_callback=send_code_via_websocket
                                )
                            )
                        finally:
                            loop.close()
            else:
                code = parser_func(raw_text)

        if not code:
            return
        
        # ✅ 第一时间发送给客户端（最高优先级，带去重检查）
        # 检查代码是否已下发过（测试频道不做去重）
        if not is_test_channel:
            if code in sent_codes:
                current_time = datetime.now()
                time_str = current_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                logger.debug(f"[{time_str}] ⏭️ 代码已下发过，跳过: {code} (来源: {channel_name})")
                return
            
            # 添加到已下发集合
            sent_codes.add(code)
        
        server_time = datetime.now()
        server_timestamp_ms = int(server_time.timestamp() * 1000)
        message_data = {
            'type': 'code_detected',
            'code': code,
            'channel_id': chat_id,
            'channel_title': channel_name,
            'parser': parser_name,
            'timestamp': server_time.isoformat(),
            'server_timestamp_ms': server_timestamp_ms,
            'message_received_time': time.perf_counter()
        }
        
        filter_usernames = TEST_USERNAMES if is_test_channel else None
        try:
            ws_loop = get_websocket_loop()
            if ws_loop and ws_loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    broadcast_to_clients(message_data, filter_usernames=filter_usernames),
                    ws_loop
                )
            else:
                Thread(target=lambda: asyncio.run(broadcast_to_clients(message_data, filter_usernames=filter_usernames)), daemon=True).start()
        except Exception as e:
            logger.error(f"❌ 分发代码失败: {e}")
        
        # 关键日志：代码信息写入文件，延迟信息只输出到控制台（不写入文件）
        logger.info(f"📨 {channel_name} | 代码: {code}")
        # 延迟信息只输出到控制台，不写入文件
        if delay_ms is not None:
            print(f"📨 {channel_name} | 延迟: {delay_ms}ms | 代码: {code}")
        else:
            print(f"📨 {channel_name} | 代码: {code}")

        # 其他操作异步执行（不阻塞客户端发送）
        def do_other_tasks():
            try:
                # 转发代码到指定频道
                if CODE_FORWARD_CHANNEL_ID:
                    current_time = datetime.now()
                    time_str = current_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    forward_message = f"🎁 新代码: {code}\n来源: {channel_name}\n时间: {time_str}" + (f"\n延迟: {delay_ms}ms" if delay_ms else "")
                    send_result = tg.call_method(
                        "sendMessage",
                        {
                            "chat_id": CODE_FORWARD_CHANNEL_ID,
                            "input_message_content": {
                                "@type": "inputMessageText",
                                "text": {
                                    "@type": "formattedText",
                                    "text": forward_message
                                }
                            }
                        }
                    )
                    send_result.wait()
            except Exception:
                pass  # 静默失败，不影响主流程
        
        # 异步执行其他任务
        message_executor.submit(do_other_tasks)

    except Exception as e:
        logger.error(f"❌ 处理 update 时出错: {e}", exc_info=True)


def get_websocket_loop():
    """获取 WebSocket 服务器的事件循环"""
    global websocket_loop
    return websocket_loop


def keep_alive_with_openchat():
    """
    使用 openChat 拉活，提高账号活跃度和频道更新优先级
    对核心频道（除测试频道外的所有频道）调用 openChat，模拟用户打开聊天窗口
    """
    try:
        if not core_channels:
            logger.info("ℹ️ 未配置核心频道，跳过 openChat 拉活")
            return
        
        logger.info(f"📡 正在打开核心频道聊天窗口（拉活 + 提高更新优先级，共 {len(core_channels)} 个）...")
        success_count = 0
        
        for chat_id in core_channels:
            try:
                # 调用 openChat 模拟用户打开聊天窗口
                open_result = tg.call_method("openChat", {"chat_id": chat_id})
                open_result.wait(timeout=5)  # 设置超时
                channel_name = channel_name_map.get(chat_id, f"频道{chat_id}")
                logger.info(f"✅ 已打开核心频道: {channel_name} (将获得最高优先级推送)")
                success_count += 1
            except Exception as e:
                channel_name = channel_name_map.get(chat_id, f"频道{chat_id}")
                logger.warning(f"⚠️ 打开核心频道 {channel_name} 失败: {e}")
        
        if success_count > 0:
            logger.info(f"✅ 核心频道已打开（{success_count}/{len(core_channels)} 成功，将获得最高优先级的更新推送）")
        else:
            logger.warning("⚠️ 所有核心频道打开失败")
    except Exception as e:
        logger.warning(f"⚠️ openChat 拉活失败: {e}")


def periodic_keep_alive():
    """
    定期拉活（每 5 分钟执行一次 openChat 和 getChats，保持连接活跃并提高消息接收优先级）
    """
    while True:
        try:
            time.sleep(300)  # 等待 5 分钟
            # 定期打开核心频道（拉活）
            keep_alive_with_openchat()
            # 定期获取对话列表（保持连接活跃）
            try:
                tg.get_chats().wait(timeout=10)
                logger.debug("✅ 定期拉活：已刷新对话列表")
            except Exception as e:
                logger.debug(f"⚠️ 定期拉活：刷新对话列表失败: {e}")
        except Exception as e:
            logger.warning(f"⚠️ 定期拉活异常: {e}")


def save_connections_to_file():
    """保存当前连接信息到文件"""
    try:
        conn_file = os.path.join(project_root, 'db', 'websocket_stake_connections.json')
        os.makedirs(os.path.dirname(conn_file), exist_ok=True)
        
        connections = []
        for client in connected_clients:
            addr = client_addr_map.get(client)
            username = client_username_map.get(client, '-')
            user_id = client_user_id_map.get(client, '-')
            connect_time = client_connect_time_map.get(client)
            
            if addr:
                ip, port = addr
                # 使用连接时间而不是当前时间
                connect_time_str = connect_time.isoformat() if connect_time else datetime.now().isoformat()
                connections.append({
                    'username': username,
                    'user_id': user_id,
                    'ip': ip,
                    'port': port,
                    'connected_at': connect_time_str  # 改为 connected_at，表示连接时间
                })
        
        data = {
            'service': 'stake',
            'port': WEBSOCKET_PORT,
            'total_connections': len(connections),
            'last_update': datetime.now().isoformat(),
            'connections': connections
        }
        
        with open(conn_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.debug(f"保存连接信息失败: {e}")


async def broadcast_to_clients(message_data, filter_usernames=None):
    """
    向所有连接的客户端广播消息（增强稳定性：超时控制、错误处理、并发发送）
    
    Args:
        message_data: 要发送的消息数据
        filter_usernames: 如果指定，只发送给这些 username 的客户端（用于测试频道）
    """
    if not connected_clients:
        logger.debug("⚠️ 没有连接的客户端，消息未发送")
        return
    
    message_json = json.dumps(message_data, ensure_ascii=False)
    disconnected = set()
    sent_count = 0
    
    # 定义发送给单个客户端的协程函数
    async def send_to_client(client):
        nonlocal sent_count
        try:
            # 检查连接是否已关闭
            if client.closed:
                disconnected.add(client)
                return False
            
            # 如果指定了过滤条件，检查客户端的 username
            if filter_usernames:
                client_username = client_username_map.get(client)
                if client_username not in filter_usernames:
                    return False  # 跳过不在测试账号列表中的客户端
            
            # 发送消息，设置超时（5秒）
            try:
                await asyncio.wait_for(client.send(message_json), timeout=5.0)
                sent_count += 1
                return True
            except asyncio.TimeoutError:
                # 发送超时，连接可能有问题
                disconnected.add(client)
                return False
            except websockets.exceptions.ConnectionClosed:
                disconnected.add(client)
                return False
            except websockets.exceptions.ConnectionClosedError:
                disconnected.add(client)
                return False
            except websockets.exceptions.ConnectionClosedOK:
                disconnected.add(client)
                return False
        except Exception as e:
            # 其他异常，标记为断开
            disconnected.add(client)
            return False
    
    # 并发发送给所有客户端
    clients_list = list(connected_clients)  # 使用列表副本，避免迭代时修改
    if clients_list:
        # 使用 asyncio.gather 并发执行所有发送任务
        await asyncio.gather(*[send_to_client(client) for client in clients_list], return_exceptions=True)
    
    # 移除断开的客户端
    for client in disconnected:
        connected_clients.discard(client)
        client_username_map.pop(client, None)  # 同时移除 username 映射
        client_user_id_map.pop(client, None)  # 移除 user_id 映射
        client_addr_map.pop(client, None)  # 移除地址映射
    
    if disconnected:
        save_connections_to_file()  # 更新连接信息
    
    if filter_usernames:
        logger.info(f"📡 测试频道消息已发送给 {sent_count} 个测试账号客户端")


async def verify_username_for_v2(username):
    """验证 V2 客户端的用户名是否绑定到用户且激活
    
    Returns:
        tuple: (is_valid, user_obj, error_message)
            - is_valid: 是否验证通过
            - user_obj: 关联的用户对象（如果验证通过）
            - error_message: 错误信息（如果验证失败）
    """
    try:
        from asgiref.sync import sync_to_async
        
        # 定义同步函数：检查账号是否存在且激活
        def check_account():
            try:
                # 由于账号唯一性保证（一个账号只能属于一个用户），直接查找即可
                account = StakeAccount.objects.filter(
                    stake_account_id=username,
                    is_active=True
                ).first()
                
                if account:
                    return account.user  # 返回用户对象
                else:
                    return None
            except Exception as e:
                logger.error(f"❌ 验证用户失败: {e}", exc_info=True)
                raise
        
        # 使用 sync_to_async 异步执行
        user_obj = await sync_to_async(check_account)()
        
        if user_obj:
            return True, user_obj, None  # 验证通过，返回用户对象
        else:
            return False, None, "账号未绑定或未激活"
    except Exception as e:
        error_msg = str(e)
        # 截断过长的错误消息（WebSocket 关闭帧 reason 不能超过 123 字节）
        if len(error_msg) > 100:
            error_msg = error_msg[:100] + "..."
        logger.error(f"❌ 验证用户: {error_msg}", exc_info=True)
        return False, None, f"验证失败: {error_msg}"


async def disconnect_account_connections(username, reason="账号状态已变更"):
    """断开指定账号的所有连接（V1 和 V2）
    
    Args:
        username: 账号用户名
        reason: 断开原因
    """
    try:
        disconnected_count = 0
        
        # 断开 V1 连接
        v1_websockets = account_to_websocket_v1.get(username, set()).copy()
        for websocket in v1_websockets:
            if not websocket.closed:
                try:
                    await websocket.close(code=1000, reason=reason)
                    disconnected_count += 1
                except:
                    pass
                # 清理连接
                account_to_websocket_v1.get(username, set()).discard(websocket)
                connected_clients.discard(websocket)
                client_username_map.pop(websocket, None)
                client_user_id_map.pop(websocket, None)
                client_addr_map.pop(websocket, None)
                client_connect_time_map.pop(websocket, None)
                websocket_version_map.pop(websocket, None)
        
        # 断开 V2 连接
        v2_websockets = account_to_websocket_v2.get(username, set()).copy()
        for websocket in v2_websockets:
            if not websocket.closed:
                try:
                    await websocket.close(code=1000, reason=reason)
                    disconnected_count += 1
                except:
                    pass
                # 清理连接
                account_to_websocket_v2.get(username, set()).discard(websocket)
                connected_clients.discard(websocket)
                client_username_map.pop(websocket, None)
                client_user_id_map.pop(websocket, None)
                client_addr_map.pop(websocket, None)
                client_connect_time_map.pop(websocket, None)
                websocket_version_map.pop(websocket, None)
                websocket_user_map.pop(websocket, None)
        
        # 清空映射（如果为空）
        if not account_to_websocket_v1.get(username):
            account_to_websocket_v1.pop(username, None)
        if not account_to_websocket_v2.get(username):
            account_to_websocket_v2.pop(username, None)
        
        if disconnected_count > 0:
            logger.info(f"🔌 已断开账号 {username} 的 {disconnected_count} 个连接，原因: {reason}")
        
        return disconnected_count
    except Exception as e:
        logger.warning(f"⚠️ 断开账号连接时出错: {e}")
        return 0


def disconnect_account_connections_sync(username, reason="账号状态已变更"):
    """同步包装函数：断开指定账号的所有连接（用于 Django 视图调用）
    
    Args:
        username: 账号用户名
        reason: 断开原因
    
    Returns:
        int: 断开的连接数
    """
    try:
        global websocket_loop
        if websocket_loop and websocket_loop.is_running():
            # 如果事件循环正在运行，使用 run_coroutine_threadsafe 调度
            future = asyncio.run_coroutine_threadsafe(
                disconnect_account_connections(username, reason),
                websocket_loop
            )
            try:
                return future.result(timeout=5)  # 5秒超时
            except Exception as e:
                logger.warning(f"⚠️ 断开账号连接超时或出错: {e}")
                return 0
        else:
            # 如果事件循环未运行，尝试获取当前事件循环或创建新的
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 如果循环正在运行，使用 run_coroutine_threadsafe
                    future = asyncio.run_coroutine_threadsafe(
                        disconnect_account_connections(username, reason),
                        loop
                    )
                    return future.result(timeout=5)
                else:
                    return loop.run_until_complete(disconnect_account_connections(username, reason))
            except RuntimeError:
                # 没有事件循环，创建新的
                return asyncio.run(disconnect_account_connections(username, reason))
    except Exception as e:
        logger.warning(f"⚠️ 同步断开账号连接时出错: {e}")
        return 0


async def disconnect_opposite_version_connections(username, new_websocket, new_version):
    """断开同一账号的相反版本的连接（互斥逻辑：V1和V2互斥，但同版本可以共存）"""
    try:
        if new_version == 'v1':
            # 新连接是V1，断开所有V2连接
            v2_websockets = account_to_websocket_v2.get(username, set()).copy()
            for old_websocket in v2_websockets:
                if old_websocket != new_websocket and not old_websocket.closed:
                    logger.info(f"🔌 检测到同一账号 {username} 的V1连接，断开V2连接")
                    try:
                        await old_websocket.close(code=1000, reason="同一账号的V1连接已建立，V2连接被断开")
                    except:
                        pass
                    # 清理V2连接
                    account_to_websocket_v2.get(username, set()).discard(old_websocket)
                    connected_clients.discard(old_websocket)
                    client_username_map.pop(old_websocket, None)
                    client_user_id_map.pop(old_websocket, None)
                    client_addr_map.pop(old_websocket, None)
                    client_connect_time_map.pop(old_websocket, None)
                    websocket_version_map.pop(old_websocket, None)
            # 清空该账号的V2映射（如果为空）
            if not account_to_websocket_v2.get(username):
                account_to_websocket_v2.pop(username, None)
        elif new_version == 'v2':
            # 新连接是V2，断开所有V1连接
            v1_websockets = account_to_websocket_v1.get(username, set()).copy()
            for old_websocket in v1_websockets:
                if old_websocket != new_websocket and not old_websocket.closed:
                    logger.info(f"🔌 检测到同一账号 {username} 的V2连接，断开V1连接")
                    try:
                        await old_websocket.close(code=1000, reason="同一账号的V2连接已建立，V1连接被断开")
                    except:
                        pass
                    # 清理V1连接
                    account_to_websocket_v1.get(username, set()).discard(old_websocket)
                    connected_clients.discard(old_websocket)
                    client_username_map.pop(old_websocket, None)
                    client_user_id_map.pop(old_websocket, None)
                    client_addr_map.pop(old_websocket, None)
                    client_connect_time_map.pop(old_websocket, None)
                    websocket_version_map.pop(old_websocket, None)
            # 清空该账号的V1映射（如果为空）
            if not account_to_websocket_v1.get(username):
                account_to_websocket_v1.pop(username, None)
    except Exception as e:
        logger.warning(f"⚠️ 断开相反版本连接时出错: {e}")


async def websocket_handler(websocket, path):
    """WebSocket 连接处理器（增强稳定性：心跳检测、超时控制、V1/V2 互斥）"""
    # 判断是 V1 还是 V2（通过路径区分）
    is_v2 = path == '/v2'
    # 记录连接路径（用于调试）
    logger.info(f"🔌 WebSocket 连接: 路径={path}, 版本={'V2' if is_v2 else 'V1'}")
    
    # 获取真实客户端IP（优先从 Nginx 反向代理头中获取）
    client_addr = websocket.remote_address
    try:
        # 尝试从请求头中获取真实IP（Nginx 反向代理会设置这些头）
        headers = websocket.request_headers
        real_ip = headers.get('X-Real-IP') or headers.get('X-Forwarded-For')
        if real_ip:
            # X-Forwarded-For 可能包含多个IP，取第一个
            if ',' in real_ip:
                real_ip = real_ip.split(',')[0].strip()
            # 只更新IP，保留端口
            client_addr = (real_ip, client_addr[1])
    except Exception:
        # 如果获取失败，使用默认的 remote_address
        pass
    
    client_username = None  # 客户端用户名（等待初始化消息）
    client_user_id = None  # 客户端用户标识（V1使用）
    is_verified = False  # V2 是否已验证
    connection_version = 'v2' if is_v2 else 'v1'  # 记录连接版本
    connected_clients.add(websocket)
    client_addr_map[websocket] = client_addr  # 保存地址映射
    client_connect_time_map[websocket] = datetime.now()  # 记录连接时间
    websocket_version_map[websocket] = connection_version  # 记录版本
    save_connections_to_file()  # 保存连接信息
    
    # 设置 WebSocket 超时和保活参数
    websocket.timeout = 60  # 60秒超时
    last_ping_time = time.time()
    ping_interval = 30  # 每30秒发送一次 ping
    
    try:
        # V2 不立即发送欢迎消息，等待验证通过后再发送
        if not is_v2:
            # V1 立即发送欢迎消息
            server_time = datetime.now()
            server_timestamp_ms = int(server_time.timestamp() * 1000)  # Unix 时间戳（毫秒）
            
            welcome_msg = {
                'type': 'connected',
                'message': '已连接到代码分发服务',
                'timestamp': server_time.isoformat(),
                'server_timestamp_ms': server_timestamp_ms  # 服务器时间戳（毫秒），用于客户端同步时间
            }
            await websocket.send(json.dumps(welcome_msg, ensure_ascii=False))
        
        # 启动心跳任务（服务器主动发送 ping）
        async def heartbeat_task():
            """服务器主动心跳检测"""
            try:
                while True:
                    await asyncio.sleep(ping_interval)
                    if websocket.closed:
                        break
                    try:
                        # 发送 ping 帧
                        await websocket.ping()
                        last_ping_time = time.time()
                    except (websockets.exceptions.ConnectionClosed,
                            websockets.exceptions.ConnectionClosedError,
                            websockets.exceptions.ConnectionClosedOK):
                        # 连接已关闭，退出循环
                        break
                    except Exception as e:
                        # ping 失败，连接可能已断开
                        logger.debug(f"心跳 ping 失败: {e}")
                        break
            except asyncio.CancelledError:
                # 任务被取消，正常退出
                pass
            except Exception as e:
                # 捕获所有其他异常，避免 Future exception 警告
                logger.debug(f"心跳任务异常: {e}")
        
        heartbeat = asyncio.create_task(heartbeat_task())
        
        # V2 超时检查任务
        init_timeout_task = None
        if is_v2:
            async def init_timeout_check():
                """V2 超时检查：如果10秒内未收到init消息，断开连接"""
                await asyncio.sleep(10.0)
                if not is_verified:
                    logger.warning(f"⚠️ V2 客户端未在超时时间内发送 init 消息，断开连接: {client_addr}")
                    try:
                        await websocket.close(code=1008, reason="未在超时时间内发送初始化消息")
                    except:
                        pass
            init_timeout_task = asyncio.create_task(init_timeout_check())
        
        try:
            # 保持连接，等待客户端消息（心跳、领取结果等）
            async for message in websocket:
                try:
                    data = json.loads(message)
                    if data.get('type') == 'init':
                        # 接收客户端初始化消息
                        client_username = data.get('username', '-')
                        client_user_id = data.get('user_id', '-')
                        
                        # V2 需要验证账号绑定
                        if is_v2:
                            # 取消超时检查任务
                            if init_timeout_task:
                                init_timeout_task.cancel()
                                try:
                                    await init_timeout_task
                                except asyncio.CancelledError:
                                    pass
                            
                            # 如果已经验证过，忽略重复的init
                            if is_verified:
                                logger.debug(f"V2 客户端发送了重复的 init 消息，已忽略")
                                continue
                            
                            if not client_username or client_username == '-':
                                logger.warning(f"⚠️ V2 客户端未提供用户名，断开连接: {client_addr}")
                                await websocket.close(code=1008, reason="V2 客户端必须提供用户名")
                                break
                            
                            # 验证用户名
                            is_valid, verified_user, error_msg = await verify_username_for_v2(client_username)
                            if not is_valid:
                                logger.warning(f"⚠️ V2 客户端验证失败: {client_addr} | 账号: {client_username} | 错误: {error_msg}")
                                # WebSocket 关闭帧 reason 不能超过 123 字节，截断过长的消息
                                close_reason = f"验证失败: {error_msg}"
                                if len(close_reason.encode('utf-8')) > 123:
                                    close_reason = "验证失败"
                                await websocket.close(code=1008, reason=close_reason)
                                break
                            
                            is_verified = True
                            
                            # 断开同一账号的相反版本连接（互斥逻辑：V1和V2互斥）
                            await disconnect_opposite_version_connections(client_username, websocket, 'v2')
                            
                            # 保存账号映射（V2使用集合，支持多个连接）
                            if client_username not in account_to_websocket_v2:
                                account_to_websocket_v2[client_username] = set()
                            account_to_websocket_v2[client_username].add(websocket)
                            
                            # 保存 username 映射
                            client_username_map[websocket] = client_username
                            # 保存 V2 连接对应的用户对象（用于数据归属，确保数据归属到验证时的用户）
                            if verified_user:
                                websocket_user_map[websocket] = verified_user
                                logger.info(f"✅ V2 客户端验证通过: {client_addr} | 账号: {client_username} | 用户: {verified_user.username}")
                            if client_user_id and client_user_id != '-':
                                client_user_id_map[websocket] = client_user_id
                            
                            # 发送验证通过消息
                            server_time = datetime.now()
                            server_timestamp_ms = int(server_time.timestamp() * 1000)
                            welcome_msg = {
                                'type': 'connected',
                                'message': '已连接到代码分发服务（V2）',
                                'timestamp': server_time.isoformat(),
                                'server_timestamp_ms': server_timestamp_ms
                            }
                            await websocket.send(json.dumps(welcome_msg, ensure_ascii=False))
                            logger.info(f"✅ V2 客户端验证通过: {client_addr} | 账号: {client_username}")
                            save_connections_to_file()
                        else:
                            # V1 不需要验证，直接保存
                            # 如果提供了用户名，断开同一账号的V2连接（互斥逻辑：V1和V2互斥）
                            if client_username and client_username != '-':
                                await disconnect_opposite_version_connections(client_username, websocket, 'v1')
                                # 保存账号映射（V1使用集合，支持多个连接）
                                if client_username not in account_to_websocket_v1:
                                    account_to_websocket_v1[client_username] = set()
                                account_to_websocket_v1[client_username].add(websocket)
                            
                            # 保存 username 和 user_id 映射
                            if client_username and client_username != '-':
                                client_username_map[websocket] = client_username
                            if client_user_id and client_user_id != '-':
                                client_user_id_map[websocket] = client_user_id
                            if client_username and client_username != '-':
                                user_id_display = f" | 用户标识: {client_user_id}" if client_user_id and client_user_id != '-' else ""
                                logger.info(f"🔌 客户端账号信息: {client_addr} | 账号: {client_username}{user_id_display} (V1)")
                                save_connections_to_file()  # 更新连接信息
                    elif data.get('type') == 'ping':
                        # V2 未验证前不响应心跳
                        if is_v2 and not is_verified:
                            continue
                        # 响应心跳
                        pong_msg = {
                            'type': 'pong',
                            'timestamp': datetime.now().isoformat()
                        }
                        await websocket.send(json.dumps(pong_msg, ensure_ascii=False))
                    elif data.get('type') == 'claim_result':
                        # V2 未验证前不处理领取结果
                        if is_v2 and not is_verified:
                            continue
                        # 处理领取结果（异步执行，不阻塞，传入 websocket 用于判断版本）
                        # 使用 create_task 并添加异常处理，避免 Future exception 警告
                        task = asyncio.create_task(handle_claim_result(data, websocket))
                        # 添加异常回调，确保异常被处理
                        def handle_task_exception(task):
                            try:
                                task.result()  # 获取结果，如果有异常会抛出
                            except Exception as e:
                                # 异常已在 handle_claim_result 内部处理，这里只记录
                                logger.debug(f"领取结果处理任务异常（已处理）: {e}")
                        task.add_done_callback(handle_task_exception)
                except json.JSONDecodeError:
                    logger.warning(f"⚠️ 收到无效的 JSON 消息: {message}")
                except Exception as e:
                    logger.error(f"❌ 处理客户端消息时出错: {e}", exc_info=True)
        except (websockets.exceptions.ConnectionClosed, 
                websockets.exceptions.ConnectionClosedError,
                websockets.exceptions.ConnectionClosedOK,
                asyncio.IncompleteReadError):
            # 客户端正常或异常断开，静默处理
            pass
        except Exception as e:
            # 捕获其他异常，避免未处理的异常
            logger.error(f"❌ 读取消息时出错: {e}", exc_info=True)
        finally:
            # 取消心跳任务（静默处理所有异常，避免 Future exception 警告）
            if heartbeat and not heartbeat.done():
                heartbeat.cancel()
                try:
                    await asyncio.wait_for(heartbeat, timeout=1.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
                except Exception:
                    pass  # 忽略所有其他异常
            
            # 取消V2超时检查任务
            if init_timeout_task and not init_timeout_task.done():
                init_timeout_task.cancel()
                try:
                    await asyncio.wait_for(init_timeout_task, timeout=1.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
                except Exception:
                    pass  # 忽略所有其他异常
                
    except websockets.exceptions.ConnectionClosed:
        pass
    except websockets.exceptions.ConnectionClosedError:
        pass
    except websockets.exceptions.ConnectionClosedOK:
        pass
    except asyncio.TimeoutError:
        pass
    except asyncio.IncompleteReadError:
        # 客户端异常断开（网络中断、浏览器关闭等）
        pass
    except Exception as e:
        # 捕获所有其他异常，避免 "Future exception was never retrieved" 警告
        logger.error(f"❌ WebSocket 处理错误: {e}", exc_info=True)
    finally:
        # 记录移除日志（如果有用户名）
        client_username = client_username_map.get(websocket)
        connection_version = websocket_version_map.get(websocket, 'unknown')
        if client_username:
            logger.info(f"🔌 客户端账号信息: {client_addr} | 账号: {client_username} | 版本: {connection_version} | 已断开")
        
        # 从账号映射中移除
        if client_username:
            if connection_version == 'v1':
                account_to_websocket_v1.get(client_username, set()).discard(websocket)
                if not account_to_websocket_v1.get(client_username):
                    account_to_websocket_v1.pop(client_username, None)
            elif connection_version == 'v2':
                account_to_websocket_v2.get(client_username, set()).discard(websocket)
                if not account_to_websocket_v2.get(client_username):
                    account_to_websocket_v2.pop(client_username, None)
        
        connected_clients.discard(websocket)
        client_username_map.pop(websocket, None)  # 移除 username 映射
        client_user_id_map.pop(websocket, None)  # 移除 user_id 映射
        client_addr_map.pop(websocket, None)  # 移除地址映射
        client_connect_time_map.pop(websocket, None)  # 移除连接时间映射
        websocket_version_map.pop(websocket, None)  # 移除版本映射
        websocket_user_map.pop(websocket, None)  # 移除 V2 用户映射
        save_connections_to_file()  # 更新连接信息


async def handle_claim_result(data, websocket=None):
    """处理客户端发送的领取结果，并入库到 ClaimRecord
    
    Args:
        data: 领取结果数据
        websocket: WebSocket 连接对象（可选，用于判断是 V1 还是 V2）
    """
    try:
        from asgiref.sync import sync_to_async
        from django.contrib.auth.models import User
        
        user_id = data.get('user_id')  # 用户标识符（V1 使用）
        code = data.get('code')
        username = data.get('username')  # Stake 账号用户名
        status = data.get('status', 'error')
        success = data.get('success', False)
        amount = data.get('amount')
        currency = data.get('currency')
        response_time = data.get('responseTime')
        response_body = data.get('responseBody')
        error_message = data.get('errorMessage')
        
        if not code:
            logger.warning("⚠️ 收到无效的领取结果（缺少代码）")
            return
        
        # 判断是 V1 还是 V2 连接
        is_v2 = False
        if websocket:
            connection_version = websocket_version_map.get(websocket)
            is_v2 = (connection_version == 'v2')
        # 如果没有提供 websocket，通过是否有 user_id 判断（V2 不发送 user_id）
        elif not user_id:
            is_v2 = True
        
        # V2 版本：根据连接时验证的用户对象确定归属（确保数据归属到验证时的用户）
        user_obj = None
        if is_v2:
            # 优先使用连接时验证的用户对象（确保数据归属正确）
            if websocket and websocket in websocket_user_map:
                user_obj = websocket_user_map[websocket]
                logger.info(f"✅ V2 领取结果：使用连接时验证的用户 {user_obj.username} (账号: {username})")
            elif username and username != '-':
                # 备用方案：如果连接对象不存在，根据 username 查找用户
                def find_user_by_username():
                    try:
                        # 查找 StakeAccount，获取关联的用户
                        # 由于账号唯一性保证（一个账号只能属于一个用户），直接查找即可
                        account = StakeAccount.objects.filter(
                            stake_account_id=username,
                            is_active=True
                        ).first()
                        if account:
                            return account.user
                        return None
                    except Exception as e:
                        logger.error(f"❌ 查找用户失败: {e}", exc_info=True)
                        return None
                
                # 使用 sync_to_async 异步执行
                user_obj = await sync_to_async(find_user_by_username)()
                if user_obj:
                    logger.info(f"✅ V2 领取结果：通过数据库查找找到用户 {user_obj.username} (账号: {username})")
                else:
                    logger.warning(f"⚠️ V2 领取结果：未找到账号 {username} 对应的用户")
        else:
            # V1 版本：根据 user_id 查找用户（通过 UserProfile.user_flag）
            if user_id and user_id != '-':
                def find_user_by_user_id():
                    try:
                        profile = UserProfile.objects.filter(user_flag=user_id).first()
                        if profile:
                            return profile.user
                        return None
                    except Exception as e:
                        logger.error(f"❌ 查找用户失败: {e}", exc_info=True)
                        return None
                
                user_obj = await sync_to_async(find_user_by_user_id)()
                if user_obj:
                    logger.info(f"✅ V1 领取结果：找到用户 {user_obj.username} (标识: {user_id})")
        
        # CodeRecord 已删除，不再查找
        
        # 构建奖金金额（分别保存数值和货币类型，便于计算）
        bonus_value = None  # 显示用的字符串
        bonus_amount = None  # 数值，便于计算
        bonus_currency = None  # 货币类型
        
        # 处理奖金金额（分别保存数值和货币类型，便于计算）
        # 处理 amount 可能为 null 的情况
        if amount is not None and str(amount).strip() and str(amount).upper() != 'N/A':
            try:
                from decimal import Decimal, InvalidOperation
                # 尝试将 amount 转换为 Decimal（保持精度）
                bonus_amount = Decimal(str(amount))
                bonus_currency = currency.upper() if currency else None
                # 构建显示字符串
                if currency:
                    bonus_value = f"{amount} {currency.upper()}"
                else:
                    bonus_value = str(amount)
            except (ValueError, TypeError, InvalidOperation) as e:
                # 如果转换失败，只保存字符串
                logger.warning(f"⚠️ 金额转换失败: {amount}, 错误: {e}")
                bonus_value = str(amount) if amount else None
                bonus_amount = None
                bonus_currency = currency.upper() if currency else None
        else:
            # amount 为空、None 或 'N/A'
            bonus_value = None
            bonus_amount = None
            bonus_currency = None
        
        # 状态映射（确保使用 ClaimRecord 中定义的状态）
        status_mapping = {
            'claim_success': 'claim_success',
            'not_found': 'not_found',
            'inactive': 'inactive',
            'session_expired': 'session_expired',
            'already_claimed': 'already_claimed',
            'weekly_wager_requirement': 'weekly_wager_requirement',
            'drop_unavailable': 'drop_unavailable',
            'error_403': 'error_403',
            'error': 'error'
        }
        final_status = status_mapping.get(status, 'error')
        
        # 创建 ClaimRecord
        # 使用 sync_to_async 包装同步的 Django ORM 操作
        try:
            from serverbot.models import ClaimRecord
            
            # 定义同步函数
            def create_claim_record():
                return ClaimRecord.objects.create(
                    user=user_obj,  # 关联的用户对象（V2 通过 username 查找，V1 通过 user_id 查找）
                    user_flag=user_id,  # 用户标识符（V1 使用，V2 为 None）
                    username=username,  # Stake 账号用户名（用于 WebSocket 领取记录）
                    code=code,
                    status=final_status,
                    bonus_value=bonus_value,  # 显示用的字符串
                    bonus_amount=bonus_amount,  # 数值，便于计算
                    bonus_currency=bonus_currency,  # 货币类型
                    response_time_ms=response_time,
                    is_retry=False,
                    error_message=error_message,
                    claim_response_body=response_body
                )
            
            # 使用 sync_to_async 异步执行
            claim_record = await sync_to_async(create_claim_record)()
            version_str = "V2" if is_v2 else "V1"
            user_display = f"{user_obj.username if user_obj else '未知用户'}" + (f" ({username})" if username else "")
            if is_v2:
                user_display = f"{user_display} [账号绑定验证]"
            logger.info(f"✅ {version_str} 领取结果已入库: {user_display} - {code} ({final_status})")
        except Exception as e:
            logger.error(f"❌ 创建 ClaimRecord 失败: {e}", exc_info=True)
            
    except Exception as e:
        logger.error(f"❌ 处理领取结果时出错: {e}", exc_info=True)


def generate_self_signed_cert():
    """自动生成自签名证书（用于 WSS）"""
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from datetime import datetime, timedelta
        
        cert_dir = os.path.join(project_root, 'db', 'ssl')
        os.makedirs(cert_dir, exist_ok=True)
        cert_path = os.path.join(cert_dir, 'websocket.crt')
        key_path = os.path.join(cert_dir, 'websocket.key')
        
        # 如果证书已存在且未过期，直接使用
        if os.path.exists(cert_path) and os.path.exists(key_path):
            try:
                with open(cert_path, 'rb') as f:
                    cert = x509.load_pem_x509_certificate(f.read())
                if cert.not_valid_after > datetime.utcnow():
                    logger.info(f"✅ 使用现有证书: {cert_path}")
                    return cert_path, key_path
            except:
                pass
        
        # 生成新的自签名证书
        logger.info("🔐 正在生成自签名证书...")
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "CN"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Internet"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "Internet"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Stake Code Listener"),
            x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
        ])
        
        # 添加服务器 IP 到证书（支持外部访问）
        san_list = [
            x509.DNSName("localhost"),
            x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
        ]
        
        # 尝试添加服务器 IP（如果配置了）
        try:
            # 添加常见的本地 IP
            san_list.append(x509.IPAddress(ipaddress.IPv4Address("0.0.0.0")))
            
            # 尝试获取服务器公网 IP（优先从配置文件，其次从环境变量）
            server_ip = None
            try:
                # 从配置模块获取（如果已导入）
                if 'WEBSOCKET_PUBLIC_IP' in globals():
                    server_ip = WEBSOCKET_PUBLIC_IP
            except:
                pass
            
            # 如果配置文件中没有，尝试从环境变量获取
            if not server_ip:
                server_ip = os.getenv('WEBSOCKET_PUBLIC_IP', None)
            
            if server_ip:
                try:
                    ip = ipaddress.ip_address(server_ip)
                    san_list.append(x509.IPAddress(ip))
                    logger.info(f"📝 证书将包含服务器 IP: {server_ip}")
                except ValueError:
                    san_list.append(x509.DNSName(server_ip))
                    logger.info(f"📝 证书将包含服务器域名: {server_ip}")
            else:
                logger.warning("⚠️  未配置 WEBSOCKET_PUBLIC_IP，证书可能不包含服务器 IP，外部连接可能失败")
        except Exception as e:
            logger.warning(f"⚠️ 添加服务器 IP 到证书失败: {e}")
        
        cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            issuer
        ).public_key(
            private_key.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.utcnow()
        ).not_valid_after(
            datetime.utcnow() + timedelta(days=365)
        ).add_extension(
            x509.SubjectAlternativeName(san_list),
            critical=False,
        ).sign(private_key, hashes.SHA256())
        
        # 保存证书和私钥
        with open(cert_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        
        with open(key_path, "wb") as f:
            f.write(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ))
        
        logger.info(f"✅ 自签名证书已生成: {cert_path}")
        logger.warning("⚠️  这是自签名证书，浏览器会显示安全警告，请点击'高级'->'继续访问'")
        logger.info(f"💡 提示：如果连接失败，请设置环境变量 WEBSOCKET_PUBLIC_IP=你的服务器IP")
        return cert_path, key_path
        
    except ImportError:
        logger.error("❌ 需要安装 cryptography 库: pip install cryptography")
        return None, None
    except Exception as e:
        logger.error(f"❌ 生成证书失败: {e}")
        return None, None


async def start_websocket_server():
    """启动 WebSocket 服务器"""
    # 检查是否使用 Nginx 反向代理（监听本地时，通常使用 Nginx 处理 SSL）
    use_nginx_proxy = (WEBSOCKET_HOST == '127.0.0.1' or WEBSOCKET_HOST == 'localhost')
    
    # 如果使用 Nginx 反向代理，明确不使用 SSL 证书（由 Nginx 处理 SSL）
    # 即使环境变量设置了 SSL 证书，也要忽略（相当于 unset）
    if use_nginx_proxy:
        logger.info("ℹ️  检测到使用 Nginx 反向代理（监听本地），将不配置 SSL 证书（由 Nginx 处理 SSL）")
        logger.info("ℹ️  忽略环境变量 WEBSOCKET_SSL_CERT 和 WEBSOCKET_SSL_KEY（使用 Nginx 的证书）")
        ssl_cert_path = None
        ssl_key_path = None
    else:
        # 不使用 Nginx 时，检查环境变量中的 SSL 证书配置
        ssl_cert_path = os.getenv('WEBSOCKET_SSL_CERT', None)
        ssl_key_path = os.getenv('WEBSOCKET_SSL_KEY', None)
    
    ssl_context = None
    if ssl_cert_path and ssl_key_path and os.path.exists(ssl_cert_path) and os.path.exists(ssl_key_path):
        try:
            import ssl
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_context.load_cert_chain(ssl_cert_path, ssl_key_path)
            logger.info(f"🚀 启动 WebSocket 服务器 (WSS): wss://{WEBSOCKET_HOST}:{WEBSOCKET_PORT}")
            # 获取公网 IP（优先从配置，其次从环境变量）
            public_ip = None
            try:
                if 'WEBSOCKET_PUBLIC_IP' in globals():
                    public_ip = WEBSOCKET_PUBLIC_IP
            except:
                pass
            if not public_ip:
                public_ip = os.getenv('WEBSOCKET_PUBLIC_IP', None)
            
            if public_ip:
                logger.info(f"📡 公网访问地址: wss://{public_ip}:{WEBSOCKET_PORT}")
            else:
                logger.warning(f"⚠️  未设置 WEBSOCKET_PUBLIC_IP，客户端请使用服务器实际 IP 地址")
        except Exception as e:
            logger.error(f"❌ 加载 SSL 证书失败: {e}")
            logger.warning(f"⚠️ 将使用 WS (非加密) 模式")
            ssl_context = None
    else:
        if use_nginx_proxy:
            logger.info(f"✅ 使用 WS (非加密) 模式，SSL 由 Nginx 处理: ws://{WEBSOCKET_HOST}:{WEBSOCKET_PORT}")
            logger.info(f"📡 客户端应通过 Nginx 访问: wss://域名/ (由 Nginx 提供 SSL)")
        else:
            logger.warning(f"⚠️ 未配置 SSL 证书，使用 WS (非加密): ws://{WEBSOCKET_HOST}:{WEBSOCKET_PORT}")
            logger.warning(f"   注意：HTTPS 页面需要使用 WSS，请配置 WEBSOCKET_SSL_CERT 和 WEBSOCKET_SSL_KEY 环境变量")
        logger.info(f"🚀 启动 WebSocket 服务器 (WS): ws://{WEBSOCKET_HOST}:{WEBSOCKET_PORT}")
    
    try:
        # 增强稳定性配置
        # 注意：max_queue 是每个连接的消息队列大小，不影响总连接数
        # 支持大量并发连接（100+），每个连接独立队列
        async with serve(
            websocket_handler, 
            WEBSOCKET_HOST, 
            WEBSOCKET_PORT, 
            ssl=ssl_context,
            ping_interval=30,  # 每30秒发送一次 ping
            ping_timeout=30,   # ping 超时时间30秒（增加超时时间，避免网络延迟导致误判）
            close_timeout=10,  # 关闭超时时间10秒
            max_size=10 * 1024 * 1024,  # 最大消息大小 10MB
            max_queue=256,  # 每个连接的最大队列大小（支持高并发消息发送）
            read_limit=2**16,  # 读取限制
            write_limit=2**16  # 写入限制
        ):
            logger.info(f"✅ WebSocket 服务器已成功启动并监听端口 {WEBSOCKET_PORT}")
            await asyncio.Future()  # 永久运行
    except Exception as e:
        logger.error(f"❌ WebSocket 服务器启动失败: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    # 在启动时获取服务器 Cloudflare Clearance Token
    def init_server_cf_clearance():
        """在后台线程中获取服务器 cf_clearance token 和 userAgent"""
        try:
            from get_server_cf_clearance import get_server_cf_clearance
            from ocr_utils import set_server_cf_clearance, set_server_user_agent
            
            logger.info("🔐 开始获取服务器 Cloudflare Clearance Token...")
            cf_clearance, user_agent = get_server_cf_clearance()
            if cf_clearance:
                set_server_cf_clearance(cf_clearance)
                logger.info("✅ 服务器 cf_clearance Token 已设置")
                if user_agent:
                    set_server_user_agent(user_agent)
                    logger.info("✅ 服务器 User-Agent 已设置")
                else:
                    logger.warning("⚠️ 未获取到 User-Agent，将使用硬编码值")
            else:
                logger.warning("⚠️ 获取服务器 cf_clearance Token 失败")
        except Exception as e:
            logger.error(f"❌ 初始化服务器 cf_clearance Token 失败: {e}", exc_info=True)
    
    # 在后台线程中获取 cf_clearance（不阻塞主流程）
    cf_thread = Thread(target=init_server_cf_clearance, daemon=True)
    cf_thread.start()
    logger.info("🔐 已启动后台线程获取服务器 cf_clearance Token")
    
    # 启动 WebSocket 服务器（在后台线程）
    def run_websocket_server():
        """在独立线程中运行 WebSocket 服务器"""
        global websocket_loop
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            websocket_loop = loop  # 保存事件循环引用
            loop.run_until_complete(start_websocket_server())
        except Exception as e:
            logger.error(f"❌ WebSocket 服务器错误: {e}", exc_info=True)
    
    ws_thread = Thread(target=run_websocket_server, daemon=True)
    ws_thread.start()
    logger.info("✅ WebSocket 服务器已启动")
    
    # 等待一下让 WebSocket 服务器完全启动
    time.sleep(1)
    
    try:
        tg.login()
        
        # 优化：设置 TDLib 参数以加快消息接收
        try:
            # 设置网络类型为 WiFi（通常延迟更低）
            tg.call_method("setNetworkType", {"type": {"@type": "networkTypeWiFi"}}).wait()
            logger.info("✅ 已设置网络类型为 WiFi（优化连接速度）")
        except Exception as e:
            logger.debug(f"设置网络类型失败（可能不支持）: {e}")
        
        # 优化：设置选项以加快消息推送（基于 TDLib 官方文档：https://core.telegram.org/tdlib/options）
        try:
            # 启用 PFS（完美前向保密），可能提高连接稳定性
            # 官方文档：use_pfs - If true, Perfect Forward Secrecy will be enabled
            tg.call_method("setOption", {
                "name": "use_pfs",
                "value": {"@type": "optionValueBoolean", "value": True}
            }).wait()
            logger.info("✅ 已启用 PFS（完美前向保密）")
        except Exception as e:
            logger.debug(f"设置 PFS 选项失败: {e}")
        
        try:
            # 启用快速确认（use_quick_ack）
            # 官方文档：use_quick_ack - If true, quick acknowledgement will be enabled for outgoing messages
            # 这可能有助于减少往返延迟
            tg.call_method("setOption", {
                "name": "use_quick_ack",
                "value": {"@type": "optionValueBoolean", "value": True}
            }).wait()
            logger.info("✅ 已启用快速确认（use_quick_ack）")
        except Exception as e:
            logger.debug(f"设置快速确认失败: {e}")
        
        try:
            # 禁用网络统计以减少处理开销
            # 官方文档：disable_network_statistics - If true, then network statistics will be completely disabled
            tg.call_method("setOption", {
                "name": "disable_network_statistics",
                "value": {"@type": "optionValueBoolean", "value": True}
            }).wait()
            logger.info("✅ 已禁用网络统计（减少处理开销）")
        except Exception as e:
            logger.debug(f"禁用网络统计失败: {e}")
        
        try:
            # 禁用持久网络统计以减少磁盘 I/O
            # 官方文档：disable_persistent_network_statistics - If true, persistent network statistics will be disabled
            tg.call_method("setOption", {
                "name": "disable_persistent_network_statistics",
                "value": {"@type": "optionValueBoolean", "value": True}
            }).wait()
            logger.info("✅ 已禁用持久网络统计（减少磁盘 I/O）")
        except Exception as e:
            logger.debug(f"禁用持久网络统计失败: {e}")
        
        try:
            # 禁用 Top Chats 以减少处理开销
            # 官方文档：disable_top_chats - If true, support for top chats and statistics collection is disabled
            tg.call_method("setOption", {
                "name": "disable_top_chats",
                "value": {"@type": "optionValueBoolean", "value": True}
            }).wait()
            logger.info("✅ 已禁用 Top Chats（减少处理开销）")
        except Exception as e:
            logger.debug(f"禁用 Top Chats 失败: {e}")
        
        try:
            # 减少消息在内存中的存储时间（加快处理）
            # 官方文档：message_unload_delay - The maximum time messages are stored in memory before they are unloaded, 60-86400; in seconds
            # 设置为最小值 60 秒，减少内存占用和处理延迟
            tg.call_method("setOption", {
                "name": "message_unload_delay",
                "value": {"@type": "optionValueInteger", "value": 60}
            }).wait()
            logger.info("✅ 已设置消息卸载延迟为 60 秒（最小值）")
        except Exception as e:
            logger.debug(f"设置消息卸载延迟失败: {e}")
        
        try:
            # 设置 is_offline 为 false，保持连接活跃
            # 让客户端显示为在线状态，保持连接活跃
            tg.call_method("setOption", {
                "name": "is_offline",
                "value": {"@type": "optionValueBoolean", "value": False}
            }).wait()
            logger.info("✅ 已设置 is_offline 为 false（保持连接活跃，客户端显示为在线状态）")
        except Exception as e:
            logger.debug(f"设置 is_offline 失败: {e}")
        
        # 预加载 dialogs，减少 ghost peer
        try:
            tg.get_chats().wait()
            logger.info("✅ 已预加载对话列表")
        except Exception as e:
            logger.warning(f"⚠️ 预加载对话失败: {e}")

        # 初始化时打开核心频道（拉活）
        keep_alive_with_openchat()
        
        # 启动定期拉活线程（每 5 分钟执行一次，保持连接活跃并提高消息接收优先级）
        keep_alive_thread = Thread(target=periodic_keep_alive, daemon=True)
        keep_alive_thread.start()
        logger.info("✅ 已启动定期拉活线程（每 5 分钟执行一次）")

        # 优化：设置消息接收优先级
        try:
            # 设置消息文本最大长度（避免处理超长消息的延迟）
            tg.call_method("setOption", {
                "name": "message_text_length_max",
                "value": {"@type": "optionValueInteger", "value": 4096}
            }).wait()
        except Exception as e:
            logger.debug(f"设置消息长度选项失败: {e}")
        
        # 优化：针对超级群组的性能优化
        try:
            # 设置连接超时（减少重连延迟）
            tg.call_method("setOption", {
                "name": "connection_timeout",
                "value": {"@type": "optionValueInteger", "value": 10}
            }).wait()
            logger.info("✅ 已设置连接超时为 10 秒")
        except Exception as e:
            logger.debug(f"设置连接超时失败: {e}")
        
        try:
            # 启用消息数据库（提高查询速度）
            tg.call_method("setOption", {
                "name": "use_message_database",
                "value": {"@type": "optionValueBoolean", "value": True}
            }).wait()
        except Exception as e:
            logger.debug(f"设置消息数据库选项失败: {e}")
        
        try:
            # 启用文件数据库（提高文件访问速度）
            tg.call_method("setOption", {
                "name": "use_file_database",
                "value": {"@type": "optionValueBoolean", "value": True}
            }).wait()
        except Exception as e:
            logger.debug(f"设置文件数据库选项失败: {e}")
        
        try:
            # 启用聊天信息数据库（提高聊天信息查询速度）
            tg.call_method("setOption", {
                "name": "use_chat_info_database",
                "value": {"@type": "optionValueBoolean", "value": True}
            }).wait()
        except Exception as e:
            logger.debug(f"设置聊天信息数据库选项失败: {e}")

        tg.add_message_handler(handle_update)
        
        # 验证日志配置（确保只有一个 FileHandler，没有 StreamHandler）
        handler_info = [f"{type(h).__name__}" for h in logger.handlers]
        if len(logger.handlers) != 1 or 'StreamHandler' in str(handler_info):
            logger.warning(f"⚠️ 日志配置异常: {len(logger.handlers)} 个 handlers: {handler_info}")
            # 重新配置日志
            logger = configure_logging()
        
        # 启动日志轮转调度器（后台线程）
        rotation_thread = Thread(target=log_rotation_scheduler, daemon=True)
        rotation_thread.start()
        logger.info("📅 日志轮转调度器已启动（每天北京时间 0 点自动轮转）")
        
        logger.info("🎧 TDLib 监听启动，等待消息...")
        logger.info(f"📡 WebSocket 服务地址: ws://{WEBSOCKET_HOST}:{WEBSOCKET_PORT}")
        logger.info("⚡ 已启用延迟优化配置")
        
        tg.idle()
    except KeyboardInterrupt:
        logger.info("⚠️ 收到中断信号，准备退出")
    finally:
        try:
            # 关闭线程池执行器，等待所有任务完成
            logger.info("🔄 正在关闭消息处理线程池...")
            # timeout 参数在 Python 3.9+ 才支持，需要兼容旧版本
            import sys
            if sys.version_info >= (3, 9):
                message_executor.shutdown(wait=True, timeout=30)
            else:
                message_executor.shutdown(wait=True)
            logger.info("✅ 消息处理线程池已关闭")
        except Exception as e:
            logger.warning(f"⚠️ 关闭线程池时出错: {e}")
        try:
            tg.stop()
        except Exception:
            pass

