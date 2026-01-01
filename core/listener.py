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
    TELEGRAM_PROXY = config_module.TELEGRAM_PROXY
    TELEGRAM_SESSION_FILE = config_module.TELEGRAM_SESSION_FILE
    
    # 多频道配置
    TELEGRAM_CHANNELS = getattr(config_module, 'TELEGRAM_CHANNELS', {})
    TELEGRAM_TARGET_CHANNEL = getattr(config_module, 'TELEGRAM_TARGET_CHANNEL', None)
    
    # 兼容旧配置：如果设置了 TELEGRAM_TARGET_CHANNEL 但没有在 TELEGRAM_CHANNELS 中，自动添加
    if TELEGRAM_TARGET_CHANNEL and TELEGRAM_TARGET_CHANNEL not in TELEGRAM_CHANNELS:
        TELEGRAM_CHANNELS[TELEGRAM_TARGET_CHANNEL] = 'default_parser'
else:
    raise ImportError(f"无法找到配置文件: {config_path}")

# ================= 3. 初始化 Django 环境 =================
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'manager.settings')
django.setup()

# 导入领取函数
from worker import redeem_bonus_task

# ================= 3.5. 频道代码解析器 =================
def parse_code_high_rollers(text):
    """
    解析 HighRollersStake 频道的代码
    格式：- Code: stakecomxxxxx
    """
    import re
    if not text:
        return None
    
    # 处理换行符，统一为空格
    text_normalized = text.replace('\n', ' ').replace('\r', ' ')
    
    # 查找 "- Code: " 后面的内容（支持多种格式）
    # 模式1: - Code: stakecomxxxxx
    # 模式2: Code: stakecomxxxxx (没有前面的 -)
    patterns = [
        r'- Code:\s*([a-z0-9]+)',  # 标准格式
        r'Code:\s*([a-z0-9]+)',    # 没有 - 的格式
        r'-Code:\s*([a-z0-9]+)',    # 没有空格的格式
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text_normalized, re.IGNORECASE)
        if match:
            code = match.group(1).strip()
            if code:
                # 确保是小写
                code = code.lower()
                # 验证代码格式（应该以 stakecom 开头，或者至少是小写字母和数字）
                if re.match(r'^[a-z0-9]+$', code) and len(code) >= 10:
                    return code
    
    # 如果正则匹配失败，尝试更宽松的匹配
    # 查找包含 "Code:" 的行
    lines = text.split('\n')
    for line in lines:
        if 'Code:' in line or 'code:' in line:
            # 尝试提取冒号后面的内容
            parts = re.split(r'[Cc]ode:\s*', line, 1)
            if len(parts) > 1:
                potential_code = parts[1].strip()
                # 移除可能的后续内容（如 Value: 等）
                potential_code = re.split(r'[\s\-]', potential_code)[0]
                if re.match(r'^[a-z0-9]+$', potential_code) and len(potential_code) >= 10:
                    return potential_code.lower()
    
    return None

def parse_code_rains_team(text):
    """
    解析 RainsTEAM 频道的代码
    特点：
    - code 是单独一行的（整行就是一个代码）
    - 没有空格
    - 长度不确定，但基本小于25
    - 可能包含字母、数字、特殊字符（如 x）
    - 例如：3x7, stakecomxxxxx 等
    """
    import re
    if not text:
        return None
    
    # 按行分割
    lines = text.split('\n')
    
    # 策略1: 查找单独一行的代码（整行就是一个代码，无空格，长度1-25）
    for line in lines:
        line = line.strip()
        # 跳过空行
        if not line:
            continue
        
        # 跳过明显的句子（包含多个单词，有空格）
        if ' ' in line:
            continue
        
        # 跳过明显的句子（包含标点符号，如 "4th NORMAL DROP INCOMING!"）
        if re.search(r'[!?.。！？]\s*$', line):
            continue
        
        # 跳过以常见单词开头的行（如 "Number", "Amount", "Wager" 等）
        if re.match(r'^(Number|Amount|Wager|Requirement|Total|Code|Value|Claims|Drop|Incoming|Normal|Alert|Bonus|Settings|Offers|Redeem|Click|Telegram|Channel|Safe|VIP|RTP|Duel|Gives)', line, re.IGNORECASE):
            continue
        
        # 跳过包含常见单词的行
        common_words = ['drop', 'alert', 'bonus', 'value', 'total', 'limit', 'requirement', 'wagered', 'days', 'settings', 'offers', 'redeem', 'click', 'telegram', 'ads', 'channel', 'potential', 'scams', 'affiliated', 'safe', 'vip', 'rtp', 'duel', 'gives', 'normal', 'incoming', 'number', 'claims', 'amount']
        line_lower = line.lower()
        if any(word in line_lower for word in common_words):
            continue
        
        # 检查是否是可能的代码格式（字母数字组合，无空格，长度1-25）
        if re.match(r'^[a-zA-Z0-9]{1,25}$', line):
            # 排除纯数字且长度很短的（可能是编号）
            if re.match(r'^\d{1,2}$', line):
                continue
            # 排除明显的单词（全小写，常见单词）
            if line_lower in ['the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'her', 'was', 'one', 'our', 'out', 'day', 'get', 'has', 'him', 'his', 'how', 'its', 'may', 'new', 'now', 'old', 'see', 'two', 'way', 'who']:
                continue
            # 如果通过了所有检查，认为是代码
            return line
    
    # 策略2: 查找常见的代码格式标识（Code: xxx）
    text_normalized = text.replace('\n', ' ').replace('\r', ' ')
    code_patterns = [
        r'[Cc]ode:\s*([^\s]{1,25})',  # Code: 后面的内容（最多25字符，无空格）
        r'代码[：:]\s*([^\s]{1,25})',  # 中文：代码：xxx
    ]
    
    for pattern in code_patterns:
        match = re.search(pattern, text_normalized)
        if match:
            code = match.group(1).strip()
            # 移除可能的标点符号结尾
            code = re.sub(r'[.,;!?。，；！？]+$', '', code)
            if code and len(code) <= 25 and re.match(r'^[a-zA-Z0-9]+$', code):
                return code
    
    # 策略3: 如果整个消息很短且无空格（可能是纯代码），直接返回
    text_clean = text.strip()
    if len(text_clean) <= 25 and ' ' not in text_clean and not re.search(r'[!?.。！？]', text_clean):
        if re.match(r'^[a-zA-Z0-9]{3,25}$', text_clean):
            return text_clean
    
    return None

def parse_code_default(text):
    """
    默认解析器：截取前 20 个字符
    """
    if text:
        return text[:20].strip()
    return None

# 解析器映射
CODE_PARSERS = {
    'high_rollers_parser': parse_code_high_rollers,
    'rains_team_parser': parse_code_rains_team,
    'default_parser': parse_code_default,
}

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
# 频道实体列表（在启动时解析）
CHANNEL_ENTITIES = []

@client.on(events.NewMessage())
async def my_event_handler(event):
    try:
        # 获取频道信息
        chat_id = event.chat_id
        channel_username = None
        channel_title = None
        
        # 检查是否是我们监听的频道
        is_target_channel = False
        
        try:
            entity = await event.get_chat()
            channel_username = getattr(entity, 'username', None)
            channel_title = getattr(entity, 'title', None)
            
            # 检查是否在监听列表中
            for ch_entity in CHANNEL_ENTITIES:
                if hasattr(ch_entity, 'id') and ch_entity.id == chat_id:
                    is_target_channel = True
                    break
                if hasattr(ch_entity, 'username') and ch_entity.username and channel_username:
                    if ch_entity.username == channel_username or ch_entity.username.lstrip('@') == channel_username.lstrip('@'):
                        is_target_channel = True
                        break
        except:
            pass
        
        # 如果不是目标频道，跳过处理
        if not is_target_channel:
            return
        
        # 确定使用哪个解析器
        parser_name = None
        channel_key = None
        
        # 优先通过用户名匹配
        if channel_username:
            # 去掉 @ 符号
            username_clean = channel_username.lstrip('@')
            if username_clean in TELEGRAM_CHANNELS:
                channel_key = username_clean
                parser_name = TELEGRAM_CHANNELS[username_clean]
                logger.debug(f"   通过用户名匹配: {username_clean} -> {parser_name}")
        
        # 如果用户名匹配失败，尝试通过 ID 匹配（需要先获取频道实体）
        if not parser_name:
            for ch_key in TELEGRAM_CHANNELS:
                try:
                    entity = await client.get_entity(ch_key)
                    if hasattr(entity, 'id') and entity.id == chat_id:
                        channel_key = ch_key
                        parser_name = TELEGRAM_CHANNELS[ch_key]
                        logger.debug(f"   通过ID匹配: {ch_key} (ID: {entity.id}) -> {parser_name}")
                        break
                except Exception as e:
                    logger.debug(f"   尝试匹配频道 {ch_key} 失败: {e}")
                    continue
        
        # 如果还是找不到，尝试通过频道标题匹配（模糊匹配）
        if not parser_name and channel_title:
            # 尝试在配置中查找包含频道标题关键词的配置
            # 或者直接使用 chat_id 作为 key（如果配置中有）
            if str(chat_id) in TELEGRAM_CHANNELS:
                channel_key = str(chat_id)
                parser_name = TELEGRAM_CHANNELS[str(chat_id)]
                logger.debug(f"   通过ID字符串匹配: {chat_id} -> {parser_name}")
        
        # 如果还是找不到，使用默认解析器
        if not parser_name:
            parser_name = 'default_parser'
            channel_key = f"unknown_{chat_id}"
            logger.warning(f"   ⚠️ 未找到频道配置，使用默认解析器")
        
        # 记录收到消息的详细信息
        logger.info("=" * 50)
        logger.info("📩 收到新消息！")
        logger.info(f"   频道: {channel_title or channel_key} (ID: {chat_id})")
        logger.info(f"   解析器: {parser_name}")
        logger.info(f"   消息 ID: {event.id}")
        logger.info(f"   发送者 ID: {event.sender_id}")
        logger.info(f"   原始文本长度: {len(event.raw_text) if event.raw_text else 0}")
        
        raw_text = event.raw_text.strip() if event.raw_text else ""
        if not raw_text:
            logger.info("   消息为空，跳过处理")
            logger.info("=" * 50)
            return

        # 使用对应的解析器提取代码
        parser_func = CODE_PARSERS.get(parser_name, parse_code_default)
        code = parser_func(raw_text)
        
        if not code:
            logger.warning(f"   ⚠️ 无法从消息中提取代码，跳过处理")
            logger.info(f"   使用的解析器: {parser_name}")
            logger.info(f"   原始内容: {raw_text[:300]}...")
            logger.info("=" * 50)
            return

        logger.info(f"   使用的解析器: {parser_name}")
        logger.info(f"   原始内容预览: {raw_text[:200]}...")
        logger.info(f"   ✅ 提取的代码: {code}")
        logger.info(f"🚀 正在开启新线程执行同步请求任务...")

        # --- 修复核心：使用 asyncio.to_thread 运行同步函数 ---
        # 这样就不会触发 SynchronousOnlyOperation 错误
        await asyncio.to_thread(redeem_bonus_task, code)
        logger.info(f"✅ 任务线程已结束: {code}")
        logger.info("=" * 50)
    except Exception as e:
        logger.error(f"❌ 处理代码失败: {e}", exc_info=True)
        logger.error("=" * 50)

# ================= 7. 启动 =================
async def main():
    logger.info("🚀 监听机器人正在启动...")
    try:
        logger.info("正在连接 Telegram 服务器...")
        await client.start()
        logger.info("✅ Telegram 客户端已连接")
        logger.info(f"📡 监听频道数量: {len(TELEGRAM_CHANNELS)}")
        
        # 验证所有频道是否存在，并解析实体
        CHANNEL_LIST = list(TELEGRAM_CHANNELS.keys())
        for channel_key in CHANNEL_LIST:
            try:
                entity = await client.get_entity(channel_key)
                channel_title = entity.title if hasattr(entity, 'title') else 'N/A'
                channel_id = entity.id if hasattr(entity, 'id') else 'N/A'
                parser_name = TELEGRAM_CHANNELS.get(channel_key, 'default_parser')
                CHANNEL_ENTITIES.append(entity)
                logger.info(f"✅ 频道验证成功: {channel_title} ({channel_key}) | ID: {channel_id} | 解析器: {parser_name}")
            except Exception as e:
                logger.warning(f"⚠️ 频道验证失败: {channel_key} - {e}")
                logger.warning(f"   请确认频道名称或 ID 是否正确")
                logger.warning(f"   提示：可以使用频道用户名（如 @channel_name）或频道 ID（如 -1001234567890）")
        
        if not CHANNEL_ENTITIES:
            logger.error("❌ 没有成功验证任何频道，无法启动监听")
            raise ValueError("没有可用的频道")
        
        logger.info(f"✅ 成功加载 {len(CHANNEL_ENTITIES)} 个频道实体")
        
        logger.info("🎧 开始监听消息...")
        logger.info("   等待新消息中...")
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