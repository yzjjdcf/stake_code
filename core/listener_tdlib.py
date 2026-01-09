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
from threading import Thread
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
    TELEGRAM_SESSION_FILE = os.path.join(project_root, 'db', 'tdlib')
    TELEGRAM_PROXY = getattr(config_module, 'TELEGRAM_PROXY', None)
    WEBSOCKET_PUBLIC_IP = getattr(config_module, 'WEBSOCKET_PUBLIC_IP', None)
else:
    raise ImportError(f"无法找到配置文件: {config_path}")

# 初始化 Django 环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'manager.settings')
import django
django.setup()

from parsers import CODE_PARSERS, parse_code_default
from video_processor import parse_code_daily_code_async

# WebSocket 相关
try:
    import websockets
    from websockets.server import serve
except ImportError:
    print("❌ 未安装 websockets，请运行: pip install websockets")
    sys.exit(1)

# 日志配置
log_dir = os.path.join(project_root, 'db', 'logs', 'listener')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'listener_tdlib.log')

# 清除所有现有的 handlers，避免重复
root_logger = logging.getLogger()
for handler in root_logger.handlers[:]:
    root_logger.removeHandler(handler)

# 配置根 logger（只输出到文件，避免重复）
file_handler = logging.FileHandler(log_file, encoding='utf-8')
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter(
    '[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
))

# 只添加文件 handler，不添加 StreamHandler
root_logger.setLevel(logging.INFO)
root_logger.addHandler(file_handler)

# 获取当前模块的 logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
# 确保当前 logger 没有重复的 handler
logger.handlers = []
logger.propagate = True  # 传播到根 logger，使用根 logger 的 handler

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

# WebSocket 配置
WEBSOCKET_HOST = '0.0.0.0'
WEBSOCKET_PORT = 8765
connected_clients = set()  # 存储所有连接的客户端
websocket_loop = None  # 存储 WebSocket 服务器的事件循环

# telegram 客户端 (python-telegram / tdlib)
try:
    from telegram.client import Telegram
except ImportError:
    logger.error("❌ 未安装 python-telegram，请运行: pip install python-telegram")
    sys.exit(1)

# 创建 Telegram 客户端
# 设置 TDLib 日志级别为 0（只显示错误），避免输出详细日志到 stderr
tg = Telegram(
    api_id=TELEGRAM_API_ID,
    api_hash=TELEGRAM_API_HASH,
    phone=os.getenv('TELEGRAM_PHONE', '8613341403236'),  # 需在运行时输入验证码
    database_encryption_key='changekey123',
    files_directory=TELEGRAM_SESSION_FILE,
    tdlib_verbosity=0,  # 0=错误, 1=警告, 2=信息, 3=调试。设置为0只显示错误
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

        # 通过 WebSocket 分发代码给所有连接的客户端
        message_data = {
            'type': 'code_detected',
            'code': code,
            'channel_id': chat_id,
            'channel_title': chat_title,
            'parser': parser_name,
            'timestamp': datetime.now().isoformat(),
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
    client_addr = websocket.remote_address
    logger.info(f"🔌 新客户端连接: {client_addr}")
    connected_clients.add(websocket)
    
    try:
        # 发送欢迎消息
        welcome_msg = {
            'type': 'connected',
            'message': '已连接到代码分发服务',
            'timestamp': datetime.now().isoformat()
        }
        await websocket.send(json.dumps(welcome_msg, ensure_ascii=False))
        
        # 保持连接，等待客户端消息（心跳、领取结果等）
        async for message in websocket:
            try:
                data = json.loads(message)
                if data.get('type') == 'ping':
                    # 响应心跳
                    pong_msg = {
                        'type': 'pong',
                        'timestamp': datetime.now().isoformat()
                    }
                    await websocket.send(json.dumps(pong_msg, ensure_ascii=False))
                elif data.get('type') == 'claim_result':
                    # 处理领取结果（异步执行，不阻塞）
                    asyncio.create_task(handle_claim_result(data))
            except json.JSONDecodeError:
                logger.warning(f"⚠️ 收到无效的 JSON 消息: {message}")
            except Exception as e:
                logger.error(f"❌ 处理客户端消息时出错: {e}", exc_info=True)
    except websockets.exceptions.ConnectionClosed:
        logger.info(f"🔌 客户端断开连接: {client_addr}")
    except Exception as e:
        logger.error(f"❌ WebSocket 处理错误: {e}", exc_info=True)
    finally:
        connected_clients.discard(websocket)
        logger.info(f"🔌 客户端已移除: {client_addr} (剩余连接: {len(connected_clients)})")


async def handle_claim_result(data):
    """处理客户端发送的领取结果，并入库到 ClaimRecord（不关联 account）"""
    try:
        from asgiref.sync import sync_to_async
        
        code = data.get('code')
        username = data.get('username')
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
        
        # 创建 ClaimRecord（只保存 username 字符串，不关联其他表）
        # 使用 sync_to_async 包装同步的 Django ORM 操作
        try:
            from serverbot.models import ClaimRecord
            
            # 定义同步函数
            def create_claim_record():
                return ClaimRecord.objects.create(
                    username=username,  # 保存用户名字符串
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
            logger.info(f"✅ 领取结果已入库: {username or '未知用户'} - {code} ({final_status})")
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
    # 检查是否配置了 SSL 证书（用于 WSS）
    ssl_cert_path = os.getenv('WEBSOCKET_SSL_CERT', None)
    ssl_key_path = os.getenv('WEBSOCKET_SSL_KEY', None)
    
    # 如果没有配置，尝试自动生成自签名证书
    if not ssl_cert_path or not ssl_key_path:
        cert_path, key_path = generate_self_signed_cert()
        if cert_path and key_path:
            ssl_cert_path = cert_path
            ssl_key_path = key_path
    
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
        # 预加载 dialogs，减少 ghost peer
        try:
            tg.get_chats().wait()
        except Exception as e:
            logger.warning(f"⚠️ 预加载对话失败: {e}")

        tg.add_message_handler(handle_update)
        logger.info("🎧 TDLib 监听启动，等待消息...")
        logger.info(f"📡 WebSocket 服务地址: ws://{WEBSOCKET_HOST}:{WEBSOCKET_PORT}")
        tg.idle()
    except KeyboardInterrupt:
        logger.info("⚠️ 收到中断信号，准备退出")
    finally:
        try:
            tg.stop()
        except Exception:
            pass

