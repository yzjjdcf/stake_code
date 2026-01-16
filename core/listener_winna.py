"""
使用 python-telegram (TDLib) 的 Winna 监听器版本（完全独立于 Stake 业务）
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
from datetime import datetime

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
    TELEGRAM_SESSION_FILE = os.path.join(project_root, 'db', 'tdlib_winna')  # Winna 使用独立的 session 文件
    TELEGRAM_PROXY = getattr(config_module, 'TELEGRAM_PROXY', None)
    WEBSOCKET_PUBLIC_IP = getattr(config_module, 'WEBSOCKET_PUBLIC_IP', None)
else:
    raise ImportError(f"无法找到配置文件: {config_path}")

# 日志配置（在 Django setup 之前，避免 Django 添加 handlers）
log_dir = os.path.join(project_root, 'db', 'logs', 'listener')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'listener_winna.log')

# 初始化 Django 环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'manager.settings')
import django
django.setup()

# Django setup 之后，重新配置日志（清除 Django 可能添加的 handlers）
from parsers import CODE_PARSERS, parse_code_default
from video_processor import parse_code_daily_code_async
from winna_parsers import (
    parse_winna_code,
    parse_winna_code_video_async,
    detect_winna_code_type
)

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

# 配置日志（在 Django setup 之后，确保清除 Django 添加的 handlers）
def configure_logging():
    """配置日志系统，确保没有重复的 handlers"""
    # 清除所有现有的 handlers（包括 Django 可能添加的）
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    root_logger.setLevel(logging.WARNING)  # 根 logger 只显示警告和错误
    root_logger.propagate = False  # 根 logger 不传播
    
    # 获取当前模块的 logger（使用独立的 logger，避免与其他模块冲突）
    logger = logging.getLogger('listener_winna')
    logger.setLevel(logging.INFO)
    # 清除可能存在的旧 handlers（包括 Django 可能添加的）
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    logger.propagate = False  # 不传播到根 logger，避免重复日志
    
    # 为当前 logger 添加文件 handler（只添加一次）
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(MillisecondFormatter(
        '[%(asctime)s] %(levelname)s: %(message)s'
    ))
    logger.addHandler(file_handler)
    
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

# 目标频道列表（Winna 业务）
target_channels = [
    -1002472636693,  # Winna 主频道
    -1003637861334,  # Winna 测试频道
]

# 核心频道列表（用于 openChat 优化，最多 1-2 个最核心的频道）
# 这些频道会调用 openChat 获得最高优先级的推送
core_channels = [
    -1002472636693,  # Winna 主频道（最核心）
]

channel_id_map = {
    -1002472636693: 'default_parser',  # Winna 主频道，使用默认解析器
    -1003637861334: 'default_parser',  # Winna 测试频道，使用默认解析器
}

# 频道名称映射（用于日志输出）
channel_name_map = {
    -1002472636693: 'Winna主频道',
    -1003637861334: 'Winna测试频道',
}

# 代码转发目标频道（Winna 业务，如果需要转发，请修改此 ID）
CODE_FORWARD_CHANNEL_ID = None  # Winna 暂不转发，如需转发请设置频道 ID

# WebSocket 配置（Winna 使用独立端口）
# 如果使用 nginx 反向代理，监听本地地址（127.0.0.1）更安全
# 如果直接暴露，使用 0.0.0.0
WEBSOCKET_HOST = os.getenv('WEBSOCKET_HOST', '127.0.0.1')  # 默认本地，可通过环境变量覆盖
WEBSOCKET_PORT = 8766  # Winna 使用 8766，与 Stake 的 8765 区分
connected_clients = set()  # 存储所有连接的客户端
client_username_map = {}  # 存储客户端 WebSocket 到 username 的映射 {websocket: username}
client_addr_map = {}  # 存储客户端 WebSocket 到地址的映射 {websocket: (ip, port)}
websocket_loop = None  # 存储 WebSocket 服务器的事件循环

# 线程池执行器（用于异步处理消息，避免阻塞主线程）
# 使用最多 4 个工作线程，避免过多线程导致资源竞争
message_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="winna_msg_handler")

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
    包含所有耗时操作：视频下载、代码解析、转发等
    """
    # 第一时间记录收到 update 的时间
    update_received_time = datetime.now()
    update_received_timestamp = time.perf_counter()
    
    try:
        message = update.get('message', {})
        chat_id = message.get('chat_id')

        # 获取消息的原始发送时间（Telegram 服务器时间）
        message_date = message.get('date', 0)  # Unix 时间戳（秒）
        message_id = message.get('id', 0)
        
        chat_title = message.get('chat', {}).get('title', '未知频道')
        is_outgoing = message.get('is_outgoing', False)
        
        # 获取频道名称（优先使用映射的名称，如果没有则使用原始标题）
        channel_name = channel_name_map.get(chat_id, chat_title)
        
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

        # Winna 频道直接使用文本解析（不使用视频解析）
        code = None
        
        # 先记录日志，再提取代码
        # 计算延迟信息（用于日志和转发消息）
        delay_ms = None
        message_datetime = None
        if message_date > 0:
            message_datetime = datetime.fromtimestamp(message_date)
            # 计算延迟差值（毫秒）
            delay_seconds = (update_received_time - message_datetime).total_seconds()
            delay_ms = int(delay_seconds * 1000)
            # 记录消息接收时间和发送时间（合并为一条日志，减少 I/O）
            logger.info(
                f"📨 收到消息 | "
                f"频道: {channel_name} | "
                f"消息ID: {message_id} | "
                f"发送时间: {message_datetime.strftime('%H:%M:%S.%f')[:-3]} | "
                f"收到时间: {update_received_time.strftime('%H:%M:%S.%f')[:-3]} | "
                f"延迟: {delay_ms}ms"
            )
        else:
            # 如果没有发送时间，只记录收到时间
            logger.info(f"📨 收到消息 | 频道: {channel_name} | 消息ID: {message_id} | 收到时间: {update_received_time.strftime('%H:%M:%S.%f')[:-3]}")
        
        # 优化：合并日志输出，减少 I/O 次数
        logger.info(f"✅ 匹配到目标频道: {channel_name} ({chat_id}) | 类型: {'视频+文字' if has_video else '文字'} | 内容: {raw_text[:100] if raw_text else '[媒体]'}")
        
        # 使用 Winna 专用解析器
        code = None
        code_type = None
        
        # 检测代码类型
        code_part, detected_type = detect_winna_code_type(raw_text)
        
        if detected_type == 'video_text' and has_video:
            # 视频+文字类型：需要异步处理
            logger.info("🎬 检测到视频+文字类型，开始异步视频解析...")
            
            # 获取视频文件 ID
            video = content.get('video', {}).get('video', {})
            file_id = video.get('id')
            
            if file_id:
                # 下载视频文件（同步）
                video_path = download_video_file(file_id)
                
                if video_path:
                    # 创建适配对象
                    class DummyMessage:
                        pass
                    dummy_msg = DummyMessage()
                    dummy_msg.file_path = video_path
                    
                    # 定义下载函数（直接返回已下载的文件路径）
                    def download_func(msg):
                        return video_path
                    
                    # 异步解析视频
                    try:
                        import asyncio
                        try:
                            loop = asyncio.get_event_loop()
                        except RuntimeError:
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                        
                        code = loop.run_until_complete(
                            parse_winna_code_video_async(raw_text, dummy_msg, download_func)
                        )
                    except Exception as e:
                        logger.error(f"❌ Winna 视频解析失败: {e}", exc_info=True)
                        code = None
                else:
                    logger.error("❌ 视频下载失败")
                    code = None
            else:
                logger.warning("⚠️ 无法获取视频文件 ID")
                code = None
                
        elif detected_type == 'puzzle':
            # 猜谜类型：使用 AI 猜谜（同步）
            logger.info("🧩 检测到猜谜类型，使用 AI 猜谜...")
            code = parse_winna_code(raw_text, message, has_video)
            
        else:
            # 其他类型：使用普通文本解析
            code = parse_winna_code(raw_text, message, has_video)
            # 如果返回特殊标记，说明是视频类型但没有视频
            if code == 'VIDEO_TEXT_TYPE':
                logger.warning("⚠️ 检测到视频+文字类型，但消息中没有视频")
                code = None

        if not code:
            logger.warning(f"⚠️ 无法从消息中提取代码（类型: {detected_type}）")
            return

        logger.info(f"✅ 提取的代码: {code} | 类型: {detected_type} | 频道: {channel_name}")

        # 转发代码到指定频道（如果配置了转发频道）
        if CODE_FORWARD_CHANNEL_ID:
            try:
                # 获取当前时间（毫秒级精度）
                current_time = datetime.now()
                time_str = current_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]  # 格式：2026-01-09 14:45:11.123
                
                # 构建转发消息（包含延迟信息）
                if message_date > 0:
                    # 有延迟信息
                    forward_message = f"🎁 Winna新代码: {code}\n来源: {channel_name}\n时间: {time_str}\n延迟: {delay_ms}ms"
                else:
                    # 没有延迟信息
                    forward_message = f"🎁 Winna新代码: {code}\n来源: {channel_name}\n时间: {time_str}"
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
                if send_result.update:
                    logger.info(f"📤 代码已转发到频道 {CODE_FORWARD_CHANNEL_ID}: {code} | 来源: {channel_name} | 时间: {time_str}")
                else:
                    logger.warning(f"⚠️ 代码转发失败: {code} | 来源: {channel_name}")
            except Exception as e:
                logger.error(f"❌ 转发代码到频道失败: {e} | 来源: {channel_name}", exc_info=True)

        # 通过 WebSocket 分发代码给所有连接的客户端
        server_time = datetime.now()
        server_timestamp_ms = int(server_time.timestamp() * 1000)  # Unix 时间戳（毫秒）
        
        message_data = {
            'type': 'code_detected',
            'code': code,
            'channel_id': chat_id,
            'channel_title': channel_name,  # 使用映射的频道名称
            'parser': parser_name,
            'timestamp': server_time.isoformat(),
            'server_timestamp_ms': server_timestamp_ms,  # 服务器时间戳（毫秒），用于客户端同步时间
            'message_received_time': time.perf_counter()
        }
        
        # 异步发送到所有客户端（使用线程安全的方式）
        try:
            # 尝试获取 WebSocket 服务器的事件循环
            ws_loop = get_websocket_loop()
            if ws_loop and ws_loop.is_running():
                # 使用 run_coroutine_threadsafe 在线程安全的方式下执行协程
                asyncio.run_coroutine_threadsafe(
                    broadcast_to_clients(message_data),
                    ws_loop
                )
            else:
                # 如果 WebSocket 循环不可用，使用线程执行
                Thread(target=lambda: asyncio.run(broadcast_to_clients(message_data)), daemon=True).start()
        except Exception as e:
            logger.error(f"❌ 分发代码到客户端失败: {e}", exc_info=True)
        
        logger.info(f"📡 代码已通过 WebSocket 分发: {code} (客户端数: {len(connected_clients)})")

    except Exception as e:
        logger.error(f"❌ 处理 update 时出错: {e}", exc_info=True)


def get_websocket_loop():
    """获取 WebSocket 服务器的事件循环"""
    global websocket_loop
    return websocket_loop


def save_connections_to_file():
    """保存当前连接信息到文件"""
    try:
        conn_file = os.path.join(project_root, 'db', 'websocket_winna_connections.json')
        os.makedirs(os.path.dirname(conn_file), exist_ok=True)
        
        connections = []
        for client in connected_clients:
            addr = client_addr_map.get(client)
            username = client_username_map.get(client, '-')
            
            if addr:
                ip, port = addr
                connections.append({
                    'username': username,
                    'ip': ip,
                    'port': port,
                    'last_update': datetime.now().isoformat()
                })
        
        data = {
            'service': 'winna',
            'port': WEBSOCKET_PORT,
            'total_connections': len(connections),
            'last_update': datetime.now().isoformat(),
            'connections': connections
        }
        
        with open(conn_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.debug(f"保存连接信息失败: {e}")


def save_connections_to_file():
    """保存当前连接信息到文件"""
    try:
        conn_file = os.path.join(project_root, 'db', 'websocket_winna_connections.json')
        os.makedirs(os.path.dirname(conn_file), exist_ok=True)
        
        connections = []
        for client in connected_clients:
            addr = client_addr_map.get(client)
            username = client_username_map.get(client, '-')
            
            if addr:
                ip, port = addr
                connections.append({
                    'username': username,
                    'ip': ip,
                    'port': port,
                    'last_update': datetime.now().isoformat()
                })
        
        data = {
            'service': 'winna',
            'port': WEBSOCKET_PORT,
            'total_connections': len(connections),
            'last_update': datetime.now().isoformat(),
            'connections': connections
        }
        
        with open(conn_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.debug(f"保存连接信息失败: {e}")


async def broadcast_to_clients(message_data):
    """向所有连接的客户端广播消息"""
    if not connected_clients:
        logger.debug("⚠️ 没有连接的客户端，消息未发送")
        return
    
    message_json = json.dumps(message_data, ensure_ascii=False)
    disconnected = set()
    
    for client in connected_clients:
        try:
            await client.send(message_json)
        except Exception as e:
            logger.warning(f"⚠️ 发送消息到客户端失败: {e}")
            disconnected.add(client)
    
    # 移除断开的客户端
    connected_clients.difference_update(disconnected)
    if disconnected:
        logger.info(f"🔌 移除了 {len(disconnected)} 个断开的客户端连接")


async def websocket_handler(websocket, path):
    """WebSocket 连接处理器"""
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
    connected_clients.add(websocket)
    client_addr_map[websocket] = client_addr  # 保存地址映射
    logger.info(f"🔌 新客户端连接: {client_addr}")
    save_connections_to_file()  # 保存连接信息
    
    try:
        # 发送欢迎消息（包含服务器时间戳，用于客户端时间同步）
        server_time = datetime.now()
        server_timestamp_ms = int(server_time.timestamp() * 1000)  # Unix 时间戳（毫秒）
        
        welcome_msg = {
            'type': 'connected',
            'message': '已连接到代码分发服务',
            'timestamp': server_time.isoformat(),
            'server_timestamp_ms': server_timestamp_ms  # 服务器时间戳（毫秒），用于客户端同步时间
        }
        await websocket.send(json.dumps(welcome_msg, ensure_ascii=False))
        
        # 保持连接，等待客户端消息（心跳、领取结果等）
        async for message in websocket:
            try:
                logger.info(f"📨 收到原始消息（长度: {len(message)} 字节）: {message[:200]}...")
                data = json.loads(message)
                logger.info(f"📨 解析后的消息类型: {data.get('type')}, 完整数据: {json.dumps(data, ensure_ascii=False)[:300]}")
                if data.get('type') == 'init':
                    # 接收客户端初始化消息（包含 username）
                    client_username = data.get('username', '-')
                    if client_username and client_username != '-':
                        client_username_map[websocket] = client_username
                        logger.info(f"🔌 客户端账号信息: {client_addr} | 账号: {client_username}")
                        save_connections_to_file()  # 更新连接信息
                    else:
                        logger.info(f"🔌 客户端账号信息: {client_addr} | 账号: 未获取")
                elif data.get('type') == 'ping':
                    # 响应心跳
                    pong_msg = {
                        'type': 'pong',
                        'timestamp': datetime.now().isoformat()
                    }
                    await websocket.send(json.dumps(pong_msg, ensure_ascii=False))
                elif data.get('type') == 'claim_result':
                    # 处理领取结果（异步执行，不阻塞）
                    logger.info(f"📨 收到领取结果消息: code={data.get('code')}, status={data.get('status')}, user_id={data.get('user_id')}")
                    logger.info(f"📨 领取结果详情: {json.dumps(data, ensure_ascii=False)[:500]}")
                    asyncio.create_task(handle_claim_result(data))
                else:
                    # 记录未知消息类型
                    logger.warning(f"⚠️ 收到未知消息类型: {data.get('type')}, 完整数据: {json.dumps(data, ensure_ascii=False)[:200]}")
            except json.JSONDecodeError:
                logger.warning(f"⚠️ 收到无效的 JSON 消息: {message}")
            except Exception as e:
                logger.error(f"❌ 处理客户端消息时出错: {e}", exc_info=True)
    except (websockets.exceptions.ConnectionClosed,
            websockets.exceptions.ConnectionClosedError,
            websockets.exceptions.ConnectionClosedOK,
            asyncio.IncompleteReadError):
        # 客户端正常或异常断开，静默处理（避免 "Future exception was never retrieved" 警告）
        pass
    except Exception as e:
        logger.error(f"❌ WebSocket 处理错误: {e}", exc_info=True)
    finally:
        connected_clients.discard(websocket)
        client_username_map.pop(websocket, None)  # 移除 username 映射
        client_addr_map.pop(websocket, None)  # 移除地址映射
        logger.info(f"🔌 客户端已移除: {client_addr} (剩余连接: {len(connected_clients)})")
        save_connections_to_file()  # 更新连接信息


async def handle_claim_result(data):
    """处理客户端发送的领取结果，并入库到 ClaimRecord（不关联 account）"""
    try:
        from asgiref.sync import sync_to_async
        
        user_id = data.get('user_id')  # 用户标识符（用于区分不同使用者）
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
            'error': 'error'
        }
        final_status = status_mapping.get(status, 'error')
        
        # 创建 WinnaClaimRecord（只保存 username 字符串，不关联其他表）
        # 使用 sync_to_async 包装同步的 Django ORM 操作
        try:
            from winna.models import WinnaClaimRecord
            
            # 定义同步函数
            def create_claim_record():
                return WinnaClaimRecord.objects.create(
                    user_id=user_id,  # 用户标识符（用于区分不同使用者）
                    username=username,  # Winna 账号用户名字符串
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
            user_display = f"{user_id or '未知用户'}" + (f" ({username})" if username else "")
            logger.info(f"✅ Winna 领取结果已入库: {user_display} - {code} ({final_status})")
        except Exception as e:
            logger.error(f"❌ 创建 WinnaClaimRecord 失败: {e}", exc_info=True)
            
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
        cert_path = os.path.join(cert_dir, 'websocket_winna.crt')  # Winna 使用独立的证书文件
        key_path = os.path.join(cert_dir, 'websocket_winna.key')
        
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
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Winna Code Listener"),
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
            logger.info(f"📡 客户端应通过 Nginx 访问: wss://域名/winna (由 Nginx 提供 SSL)")
        else:
            logger.warning(f"⚠️ 未配置 SSL 证书，使用 WS (非加密): ws://{WEBSOCKET_HOST}:{WEBSOCKET_PORT}")
            logger.warning(f"   注意：HTTPS 页面需要使用 WSS，请配置 WEBSOCKET_SSL_CERT 和 WEBSOCKET_SSL_KEY 环境变量")
        logger.info(f"🚀 启动 WebSocket 服务器 (WS): ws://{WEBSOCKET_HOST}:{WEBSOCKET_PORT}")
    
    try:
        async with serve(websocket_handler, WEBSOCKET_HOST, WEBSOCKET_PORT, ssl=ssl_context):
            logger.info(f"✅ WebSocket 服务器已成功启动并监听端口 {WEBSOCKET_PORT}")
            await asyncio.Future()  # 永久运行
    except Exception as e:
        logger.error(f"❌ WebSocket 服务器启动失败: {e}", exc_info=True)
        raise


if __name__ == "__main__":
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
        
        # 优化：对核心频道调用 openChat，模拟用户打开聊天窗口
        # 这会让服务器以最高优先级推送这些频道的更新
        # 注意：只打开 1-2 个最核心的频道，避免被服务器认为是异常行为
        try:
            if core_channels:
                logger.info(f"📡 正在打开核心频道聊天窗口（提高更新优先级，共 {len(core_channels)} 个）...")
                for chat_id in core_channels:
                    try:
                        # 调用 openChat 模拟用户打开聊天窗口
                        open_result = tg.call_method("openChat", {"chat_id": chat_id})
                        open_result.wait(timeout=5)  # 设置超时
                        channel_name = channel_name_map.get(chat_id, f"频道{chat_id}")
                        logger.info(f"✅ 已打开核心频道: {channel_name} (将获得最高优先级推送)")
                    except Exception as e:
                        channel_name = channel_name_map.get(chat_id, f"频道{chat_id}")
                        logger.warning(f"⚠️ 打开核心频道 {channel_name} 失败: {e}")
                logger.info("✅ 核心频道已打开（将获得最高优先级的更新推送）")
            else:
                logger.info("ℹ️ 未配置核心频道，跳过 openChat 优化")
        except Exception as e:
            logger.warning(f"⚠️ 打开核心频道失败: {e}")

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
        
        logger.info("🎧 TDLib 监听启动，等待消息...")
        logger.info(f"📡 WebSocket 服务地址: ws://{WEBSOCKET_HOST}:{WEBSOCKET_PORT}")
        logger.info("⚡ 已启用延迟优化配置")
        
        # 启动定期拉取个人信息任务（提高账号活跃度）
        def fetch_user_info_periodically():
            """定期拉取个人信息，提高账号活跃度"""
            while True:
                try:
                    # 随机间隔 3-5 分钟（180-300 秒）
                    interval = random.randint(180, 300)
                    time.sleep(interval)
                    
                    # 获取个人信息
                    try:
                        result = tg.call_method("getMe")
                        result.wait()
                        user_info = result.update
                        
                        if user_info:
                            # logger.info("👤 拉取个人信息（提高账号活跃度）")
                            pass
                        else:
                            logger.debug("获取个人信息失败：返回为空")
                    except Exception as e:
                        logger.debug(f"获取个人信息失败: {e}")
                        
                except Exception as e:
                    logger.error(f"❌ 定期拉取个人信息任务异常: {e}", exc_info=True)
                    # 出错后等待一段时间再继续
                    time.sleep(60)
        
        # 启动定期拉取个人信息的后台线程
        user_info_thread = Thread(target=fetch_user_info_periodically, daemon=True)
        user_info_thread.start()
        logger.info("✅ 已启动定期拉取个人信息任务（每3-5分钟触发一次，提高账号活跃度）")
        
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

