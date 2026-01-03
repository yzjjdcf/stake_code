import os
import sys
import django
import asyncio
import logging
import re
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
    
    # OpenAI 配置
    OPENAI_API_KEY = getattr(config_module, 'OPENAI_API_KEY', '')
    OPENAI_API_BASE_URL = getattr(config_module, 'OPENAI_API_BASE_URL', 'https://api.gpt.ge/v1/chat/completions')
    OPENAI_MODEL = getattr(config_module, 'OPENAI_MODEL', 'gpt-4o')
    
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

def parse_code_daily_code(text):
    """
    解析 Daily Code 频道的代码
    格式：
    🎁 Daily Code - AG7 🎁
    
    Сo​ɗ​e‍: stakecomg8f2t6l
    Code: @CodesArdag
    
    需要解析出 stakecomg8f2t6l（注意第一行可能包含特殊字符，第二行是用户名需要过滤）
    """
    import re
    if not text:
        return None
    
    # 按行分割
    lines = text.split('\n')
    
    # 策略1: 查找包含 "Code:" 或类似格式的行（可能包含特殊字符）
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # 查找包含 "Code:" 或类似格式的行（支持特殊字符，如西里尔字母）
        # 使用更宽松的匹配，查找任何包含 "code" 和冒号的行
        # 模式1: Code: stakecomg8f2t6l (标准格式)
        # 模式2: Сo​ɗ​e‍: stakecomg8f2t6l (特殊字符格式)
        # 使用正则表达式查找 "code" 后面跟着冒号，然后提取后面的代码
        
        # 先尝试标准格式
        match = re.search(r'[Cc]ode[：:]\s*([a-z0-9]+)', line, re.IGNORECASE)
        if match:
            code = match.group(1).strip()
            # 过滤掉以 @ 开头的（这是用户名，不是代码）
            if code.startswith('@'):
                continue
            # 验证代码格式（应该以 stakecom 开头，或者至少是小写字母和数字）
            if re.match(r'^[a-z0-9]+$', code) and len(code) >= 10:
                return code.lower()
        
        # 尝试特殊字符格式（查找包含 "code" 关键词的行，即使有特殊字符）
        # 查找行中包含 "code" 和冒号的情况
        if re.search(r'[Cc]ode|code|Сo|ɗ|e', line, re.IGNORECASE) and ':' in line:
            # 尝试提取冒号后面的内容
            parts = line.split(':', 1)
            if len(parts) > 1:
                potential_code = parts[1].strip()
                # 移除可能的后续内容（如 @CodesArdag 等）
                potential_code = re.split(r'[\s@\n]', potential_code)[0]
                # 过滤掉以 @ 开头的
                if potential_code.startswith('@'):
                    continue
                # 验证代码格式（stakecom 开头，或者至少是小写字母和数字）
                if re.match(r'^[a-z0-9]+$', potential_code) and len(potential_code) >= 10:
                    return potential_code.lower()
    
    # 策略2: 查找包含 "stakecom" 开头的代码（更宽松的匹配，直接从文本中提取）
    text_normalized = text.replace('\n', ' ').replace('\r', ' ')
    stakecom_pattern = r'stakecom[a-z0-9]{6,}'
    match = re.search(stakecom_pattern, text_normalized, re.IGNORECASE)
    if match:
        code = match.group(0).lower()
        # 确保不是用户名（不以 @ 开头）
        if not code.startswith('@'):
            return code
    
    return None

def parse_code_default(text):
    """
    默认解析器：截取前 20 个字符
    """
    if text:
        return text[:20].strip()
    return None

async def parse_code_stakecom_daily_drops(event, client):
    """
    解析 StakecomDailyDrops 频道的代码
    支持两种格式：
    1. 视频格式：下载视频，提取倒数第10帧，使用 ChatGPT 识别代码（优先）
    2. 文本格式：查找 "- Code: stakecomxxxxx" 格式（如果没有视频）
    
    逻辑：先判断是否有视频，如果有视频走视频解析，如果没有视频走文本解析
    """
    import tempfile
    
    # ================= 第一步：先判断是否有视频 =================
    has_video = False
    if event.video or event.document:
        # 检查是否是视频文件
        if event.video:
            has_video = True
        elif event.document:
            # 检查文档的 MIME 类型
            mime_type = getattr(event.document, 'mime_type', '')
            if mime_type and mime_type.startswith('video/'):
                has_video = True
    
    # ================= 第二步：如果有视频，只走视频解析（不走文本解析）=================
    if has_video:
        logger.info("   检测到视频，开始视频解析流程（有视频时不解析文本）...")
        try:
            # 尝试获取视频地址和详细信息
            try:
                if event.media:
                    # 尝试获取视频的详细信息
                    if hasattr(event.media, 'document'):
                            doc = event.media.document
                            file_id = doc.id if hasattr(doc, 'id') else 'N/A'
                            access_hash = doc.access_hash if hasattr(doc, 'access_hash') else 'N/A'
                            file_name = getattr(doc, 'file_name', 'N/A')
                            mime_type = getattr(doc, 'mime_type', 'N/A')
                            file_size = getattr(doc, 'size', 'N/A')
                            dc_id = getattr(doc, 'dc_id', 'N/A')
                            
                            logger.info(f"   视频信息:")
                            logger.info(f"     - 文件 ID: {file_id}")
                            logger.info(f"     - 访问哈希: {access_hash}")
                            logger.info(f"     - 文件名: {file_name}")
                            logger.info(f"     - MIME 类型: {mime_type}")
                            logger.info(f"     - 文件大小: {file_size} 字节")
                            logger.info(f"     - DC ID: {dc_id}")
                            
                            # Telegram 媒体文件通过 MTProto API 下载，不能直接通过 HTTP URL 访问
                            if file_id != 'N/A' and access_hash != 'N/A':
                                logger.info(f"     - 视频来源: Telegram DC{dc_id} 媒体服务器")
                                logger.info(f"     - 下载方式: 通过 Telethon MTProto API 下载（需要认证）")
                    elif hasattr(event.media, 'video'):
                            video = event.media.video
                            file_id = video.id if hasattr(video, 'id') else 'N/A'
                            access_hash = video.access_hash if hasattr(video, 'access_hash') else 'N/A'
                            duration = getattr(video, 'duration', 'N/A')
                            dc_id = getattr(video, 'dc_id', 'N/A')
                            
                            logger.info(f"   视频信息:")
                            logger.info(f"     - 文件 ID: {file_id}")
                            logger.info(f"     - 访问哈希: {access_hash}")
                            logger.info(f"     - 时长: {duration} 秒")
                            logger.info(f"     - DC ID: {dc_id}")
                            
                            if file_id != 'N/A' and access_hash != 'N/A':
                                logger.info(f"     - 视频来源: Telegram DC{dc_id} 媒体服务器")
                                logger.info(f"     - 下载方式: 通过 Telethon MTProto API 下载（需要认证）")
                    
                    # 尝试获取消息的完整 URL（如果可能）
                    try:
                        entity = await event.get_chat()
                        chat_username = getattr(entity, 'username', None)
                        if chat_username:
                            message_url = f"https://t.me/{chat_username}/{event.id}"
                            logger.info(f"     - 消息链接: {message_url}")
                    except Exception as e:
                        logger.debug(f"   无法获取消息链接: {e}")
            except Exception as e:
                logger.debug(f"   获取视频信息时出错: {e}")
            
            # 创建临时目录
            temp_dir = tempfile.mkdtemp()
            
            # 尝试获取原始文件名，如果没有则使用默认名称
            original_filename = None
            if event.media and hasattr(event.media, 'document'):
                original_filename = getattr(event.media.document, 'file_name', None)
            
            # 如果原始文件名存在，使用它；否则让 Telethon 自动处理
            if original_filename:
                video_path = os.path.join(temp_dir, original_filename)
            else:
                # 不指定扩展名，让 Telethon 自动处理
                video_path = os.path.join(temp_dir, 'video')
            
            logger.info(f"   视频将下载到: {video_path}")
            
            try:
                # 下载视频（不指定文件路径，让 Telethon 自动处理文件名和扩展名）
                logger.info("   开始下载视频...")
                
                # 【优化】尝试下载，最多重试2次（减少重试次数，加快失败响应）
                downloaded_path = None
                max_retries = 2  # 从3次减少到2次
                last_error = None
                
                for attempt in range(1, max_retries + 1):
                    try:
                        logger.debug(f"   下载尝试 {attempt}/{max_retries}...")
                        # 明确传入 event.message 或 event.media，而不是直接传入 event
                        # 这对于复杂消息（转发消息、相册等）更可靠
                        media_to_download = event.message if hasattr(event, 'message') else event.media
                        if not media_to_download:
                            media_to_download = event  # 如果都没有，回退到 event
                        
                        downloaded_path = await client.download_media(
                            media_to_download, 
                            file=temp_dir,
                            progress_callback=None  # 可以添加进度回调
                        )
                        
                        if downloaded_path:
                            logger.info(f"   ✅ 视频下载完成: {downloaded_path}")
                            video_path = downloaded_path  # 使用实际下载的路径
                            break
                        else:
                            logger.warning(f"   下载尝试 {attempt} 返回 None")
                            if attempt < max_retries:
                                await asyncio.sleep(0.5)  # 【优化】从1秒减少到0.5秒
                    except Exception as download_error:
                        last_error = download_error
                        logger.error(f"   下载尝试 {attempt} 出错: {download_error}")
                        if attempt < max_retries:
                            logger.debug(f"   等待0.5秒后重试...")
                            await asyncio.sleep(0.5)  # 【优化】从1秒减少到0.5秒
                        else:
                            raise  # 最后一次尝试失败，抛出异常
                
                # 如果下载返回 None，直接报错
                if not downloaded_path:
                    logger.error("   视频下载失败: download_media 返回 None")
                    if last_error:
                        logger.error(f"   最后错误: {last_error}")
                    logger.error(f"   临时目录路径: {temp_dir}")
                    if os.path.exists(temp_dir):
                        files_in_dir = os.listdir(temp_dir)
                        logger.error(f"   临时目录内容: {files_in_dir}")
                    return None
                
                # 确保 video_path 已设置
                if not video_path:
                    logger.error("   无法确定视频文件路径")
                    return None
                
                # 检查文件是否存在和大小
                if not os.path.exists(video_path):
                    logger.error(f"   视频文件不存在: {video_path}")
                    logger.error(f"   临时目录内容: {os.listdir(temp_dir) if os.path.exists(temp_dir) else '目录不存在'}")
                    return None
                
                file_size = os.path.getsize(video_path)
                logger.info(f"   视频文件大小: {file_size} 字节")
                
                if file_size == 0:
                    logger.error("   视频文件大小为0，下载可能失败")
                    return None
                
                # 验证文件是否真的是视频文件（检查文件头）
                try:
                    with open(video_path, 'rb') as f:
                        header = f.read(12)
                        # 检查是否是 MP4 文件（MP4 文件头通常是 ftyp 或 moov）
                        if not (header.startswith(b'\x00\x00\x00') or header.startswith(b'ftyp') or 
                                header.startswith(b'moov') or header.startswith(b'\x00\x00\x00\x18ftyp')):
                            logger.warning(f"   文件可能不是有效的视频文件，文件头: {header[:12]}")
                except Exception as e:
                    logger.warning(f"   无法验证文件头: {e}")
                
                # 提取倒数第10帧
                frame_path = await extract_frame_from_video(video_path, temp_dir, frame_index=-10)
                
                if frame_path and os.path.exists(frame_path):
                    logger.info(f"   成功提取帧: {frame_path}")
                    # 使用 ChatGPT 识别图片中的代码
                    code = await recognize_code_from_image(frame_path)
                    if code:
                        logger.info(f"   ChatGPT 识别到代码: {code}")
                        return code
                    else:
                        logger.warning("   ChatGPT 未能识别出代码")
                else:
                    logger.warning("   提取帧失败")
            except Exception as e:
                logger.error(f"   处理视频时出错: {e}", exc_info=True)
            finally:
                # 清理临时文件
                try:
                    import shutil
                    shutil.rmtree(temp_dir, ignore_errors=True)
                except:
                    pass
        except Exception as e:
            logger.error(f"   视频解析出错: {e}", exc_info=True)
        
        # 如果有视频，无论解析成功或失败，都不走文本解析
        # 如果视频解析成功，已经返回了代码；如果失败，直接返回 None
        logger.warning("   视频解析失败，但有视频时不解析文本，直接返回 None")
        return None
    
    # ================= 第三步：如果没有视频，走文本解析 =================
    logger.info("   没有视频，开始文本解析流程...")
    text = event.raw_text if event.raw_text else ""
    
    if text:
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            # 跳过空行
            if not line:
                continue
            
            # 匹配 "- Code: stakecomxxxxx" 格式（支持多种变体）
            # 模式1: - Code: stakecomxxxxx
            # 模式2: Code: stakecomxxxxx (没有前面的 -)
            patterns = [
                r'- Code:\s*([a-z0-9]+)',  # 标准格式：- Code: stakecomxxxxx
                r'Code:\s*([a-z0-9]+)',    # 简化格式：Code: stakecomxxxxx
            ]
            
            for pattern in patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    code = match.group(1).strip().lower()
                    # 验证代码格式（应该至少是小写字母和数字，长度至少10）
                    if re.match(r'^[a-z0-9]+$', code) and len(code) >= 10:
                        logger.info(f"   从文本中提取代码: {code} (匹配行: {line[:50]}...)")
                        return code
                    else:
                        logger.debug(f"   匹配到代码但验证失败: {code} (长度: {len(code)})")
    
    # 如果文本解析也没有找到代码，返回 None
    logger.warning("   文本解析也未找到代码")
    return None

async def extract_frame_from_video(video_path, output_dir, frame_index=-10):
    """
    从视频中提取指定帧（支持负数索引，从后往前）
    
    Args:
        video_path: 视频文件路径
        output_dir: 输出目录
        frame_index: 帧索引，负数表示从后往前（如 -10 表示倒数第10帧）
    
    Returns:
        提取的帧图片路径，如果失败返回 None
    """
    try:
        try:
            import cv2
        except ImportError:
            logger.error("   需要安装 opencv-python: pip install opencv-python")
            return None
        
        # 检查文件是否存在
        if not os.path.exists(video_path):
            logger.error(f"   视频文件不存在: {video_path}")
            return None
        
        # 使用 asyncio.to_thread 在后台线程中运行同步的 OpenCV 操作
        def _extract_frame_sync():
            # 打开视频
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                logger.error(f"   无法打开视频文件: {video_path}")
                # 尝试使用不同的后端
                logger.info("   尝试使用不同的视频后端...")
                cap = cv2.VideoCapture(video_path, cv2.CAP_FFMPEG)
                if not cap.isOpened():
                    logger.error(f"   使用 FFMPEG 后端也无法打开视频文件")
                    return None
            
            try:
                # 获取总帧数
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                fps = cap.get(cv2.CAP_PROP_FPS)
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                
                logger.info(f"   视频信息: {total_frames} 帧, {fps:.2f} FPS, {width}x{height}")
                
                if total_frames == 0:
                    logger.error("   视频没有帧")
                    return None
                
                # 计算目标帧索引
                if frame_index < 0:
                    target_frame = total_frames + frame_index  # 负数索引：从后往前
                else:
                    target_frame = frame_index
                
                # 确保索引有效
                if target_frame < 0:
                    target_frame = 0
                if target_frame >= total_frames:
                    target_frame = total_frames - 1
                
                logger.info(f"   尝试提取第 {target_frame}/{total_frames} 帧")
                
                # 跳转到目标帧
                cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
                
                # 读取帧
                ret, frame = cap.read()
                
                if not ret or frame is None:
                    logger.error(f"   无法读取第 {target_frame} 帧")
                    # 尝试读取第一帧作为备选
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, frame = cap.read()
                    if not ret or frame is None:
                        logger.error("   也无法读取第一帧")
                        return None
                    logger.warning("   使用第一帧作为备选")
                
                # 保存帧
                frame_path = os.path.join(output_dir, 'frame.jpg')
                success = cv2.imwrite(frame_path, frame)
                
                if not success:
                    logger.error(f"   无法保存帧图片到: {frame_path}")
                    return None
                
                logger.info(f"   成功提取第 {target_frame}/{total_frames} 帧，保存到: {frame_path}")
                return frame_path
            finally:
                cap.release()
        
        # 在后台线程中运行同步操作
        return await asyncio.to_thread(_extract_frame_sync)
        
    except Exception as e:
        logger.error(f"   提取帧时出错: {e}", exc_info=True)
        return None

def _recognize_code_from_image_sync(image_path, api_key, api_url, model):
    """
    同步函数：使用第三方 ChatGPT API 识别图片中的代码
    
    Args:
        image_path: 图片文件路径
        api_key: API Key
        api_url: API URL
        model: 模型名称
    
    Returns:
        识别出的代码，如果失败返回 None
    """
    try:
        import base64
        import json
        import requests
        
        if not api_key:
            logger.warning("   未配置 OPENAI_API_KEY，无法使用 ChatGPT 识别")
            return None
        
        # 【优化】压缩图片以减少传输时间和API处理时间
        try:
            from PIL import Image
            import io
            
            # 读取原始图片
            with open(image_path, 'rb') as f:
                img = Image.open(io.BytesIO(f.read()))
            
            # 如果图片太大，进行压缩（保持宽高比）
            max_size = 1024  # 最大宽度或高度
            if img.width > max_size or img.height > max_size:
                ratio = min(max_size / img.width, max_size / img.height)
                new_width = int(img.width * ratio)
                new_height = int(img.height * ratio)
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                logger.debug(f"   图片已压缩: {img.width}x{img.height}")
            
            # 转换为 JPEG 格式（更小的文件大小）
            output = io.BytesIO()
            img.save(output, format='JPEG', quality=85, optimize=True)
            image_bytes = output.getvalue()
            image_data = base64.b64encode(image_bytes).decode('utf-8')
            logger.debug(f"   图片已编码: {len(image_data)} 字符（base64）")
        except ImportError:
            # 如果没有 PIL，使用原始方法
            logger.debug("   未安装 Pillow，使用原始图片（未压缩）")
            with open(image_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')
        except Exception as e:
            logger.warning(f"   图片压缩失败，使用原始图片: {e}")
            with open(image_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')
        
        # 构建请求 payload
        payload = json.dumps({
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "请识别这张图片中的 Stake.com 代码。代码通常以 'stakecom' 开头，后面跟着字母和数字。只返回代码本身，不要返回其他内容。如果图片中没有代码，返回 'NONE'。"
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_data}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 300
        })
        
        # 构建请求 headers
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        # 【优化】发送请求（减少超时时间，因为图片已压缩）
        logger.debug(f"   正在调用 ChatGPT API: {api_url}")
        response = requests.post(api_url, headers=headers, data=payload, timeout=20)  # 从30秒减少到20秒
        
        # 检查响应状态
        if response.status_code != 200:
            logger.error(f"   ChatGPT API 请求失败: HTTP {response.status_code}")
            logger.error(f"   响应内容: {response.text}")
            return None
        
        # 解析响应
        response_data = response.json()
        
        # 提取代码
        if 'choices' in response_data and len(response_data['choices']) > 0:
            code = response_data['choices'][0]['message']['content'].strip()
        else:
            logger.error(f"   ChatGPT API 响应格式异常: {response_data}")
            return None
        
        # 验证返回的代码格式
        if code.upper() == 'NONE' or not code:
            return None
        
        # 清理代码（移除可能的标点符号和空格）
        code = re.sub(r'[^a-z0-9]', '', code.lower())
        
        # 验证代码格式
        if re.match(r'^[a-z0-9]+$', code) and len(code) >= 10:
            return code
        else:
            logger.warning(f"   ChatGPT 返回的代码格式不正确: {code}")
            return None
            
    except ImportError:
        logger.error("   需要安装 requests: pip install requests")
        return None
    except Exception as e:
        logger.error(f"   ChatGPT 识别时出错: {e}", exc_info=True)
        return None

async def recognize_code_from_image(image_path):
    """
    使用第三方 ChatGPT API 识别图片中的代码（异步包装）
    
    Args:
        image_path: 图片文件路径
    
    Returns:
        识别出的代码，如果失败返回 None
    """
    # 从配置中获取 API 配置
    api_key = OPENAI_API_KEY
    api_url = OPENAI_API_BASE_URL
    model = OPENAI_MODEL
    
    if not api_key:
        logger.warning("   未配置 OPENAI_API_KEY，无法使用 ChatGPT 识别")
        logger.warning("   请在 config/config.py 中设置 OPENAI_API_KEY")
        return None
    
    # 使用 asyncio.to_thread 在后台线程中运行同步请求
    return await asyncio.to_thread(_recognize_code_from_image_sync, image_path, api_key, api_url, model)

# 解析器映射
CODE_PARSERS = {
    'high_rollers_parser': parse_code_high_rollers,
    'rains_team_parser': parse_code_rains_team,
    'daily_code_parser': parse_code_daily_code,
    'stakecom_daily_drops_parser': parse_code_stakecom_daily_drops,  # 特殊解析器，需要 event 和 client
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

# 降低 Telethon 内部日志级别，过滤掉 "Got difference" 等内部消息
# 这些消息是正常的，表示 Telegram 服务器发送了频道更新差异
telethon_logger = logging.getLogger('telethon')
telethon_logger.setLevel(logging.WARNING)  # 只显示 WARNING 及以上级别

# 进一步过滤 telethon.network 模块的日志（通常包含 "Got difference" 消息）
telethon_network_logger = logging.getLogger('telethon.network')
telethon_network_logger.setLevel(logging.ERROR)  # 只显示 ERROR 及以上级别

# 过滤 telethon.session 模块的日志
telethon_session_logger = logging.getLogger('telethon.session')
telethon_session_logger.setLevel(logging.WARNING)

# 自定义日志过滤器：过滤 "Got difference" 等 Telethon 内部消息
class TelethonFilter(logging.Filter):
    """过滤 Telethon 内部日志消息"""
    def filter(self, record):
        # 过滤包含 "Got difference" 的消息
        if "Got difference" in record.getMessage():
            return False
        # 过滤其他常见的 Telethon 内部消息
        message = record.getMessage().lower()
        if any(keyword in message for keyword in [
            'got difference',
            'updates too long',
            'channel updates',
            'difference too long'
        ]):
            return False
        return True

# 为所有 handler 添加过滤器
for handler in logging.root.handlers:
    handler.addFilter(TelethonFilter())

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

# 连接状态标志
is_connected = False
reconnect_lock = asyncio.Lock()  # 防止并发重连
last_heartbeat_time = None
heartbeat_interval = 3  # 心跳检测间隔（秒）
reconnect_delay = 5  # 重连延迟（秒）
max_reconnect_attempts = 5  # 最大重连尝试次数

async def heartbeat_check():
    """
    心跳检测任务：定期检查 Telegram 连接状态
    """
    global is_connected, last_heartbeat_time
    
    while True:
        try:
            await asyncio.sleep(heartbeat_interval)
            
            # 检查连接状态
            if client.is_connected():
                if not is_connected:
                    logger.info("✅ Telegram 连接已恢复")
                    is_connected = True
                last_heartbeat_time = asyncio.get_event_loop().time()
                logger.info(f"💓 心跳检测：连接正常（间隔 {heartbeat_interval} 秒）")
            else:
                if is_connected:
                    logger.warning("⚠️  Telegram 连接已断开（心跳检测）")
                    is_connected = False
                # 触发重连
                await attempt_reconnect()
                
        except Exception as e:
            logger.error(f"❌ 心跳检测出错: {e}", exc_info=True)
            is_connected = False
            await attempt_reconnect()

async def attempt_reconnect():
    """
    尝试重新连接 Telegram
    """
    global is_connected
    
    # 使用锁防止并发重连
    if reconnect_lock.locked():
        logger.debug("   重连已在进行中，跳过...")
        return
    
    async with reconnect_lock:
        if client.is_connected():
            logger.debug("   连接已恢复，无需重连")
            is_connected = True
            return
        
        logger.warning("🔄 开始尝试重新连接 Telegram...")
        
        for attempt in range(1, max_reconnect_attempts + 1):
            try:
                logger.info(f"   重连尝试 {attempt}/{max_reconnect_attempts}...")
                
                # 如果已连接，先断开
                if client.is_connected():
                    await client.disconnect()
                
                # 等待一段时间后重连
                await asyncio.sleep(reconnect_delay)
                
                # 重新连接
                await client.connect()
                
                # 验证连接
                if client.is_connected():
                    logger.info("✅ Telegram 重连成功")
                    is_connected = True
                    
                    # 重新验证频道
                    await revalidate_channels()
                    return
                else:
                    logger.warning(f"   重连尝试 {attempt} 失败：连接状态为 False")
                    
            except Exception as e:
                logger.error(f"   重连尝试 {attempt} 出错: {e}")
                if attempt < max_reconnect_attempts:
                    await asyncio.sleep(reconnect_delay * attempt)  # 递增延迟
                else:
                    logger.error(f"❌ 达到最大重连次数 ({max_reconnect_attempts})，停止重连")
                    logger.error("   请检查网络连接和 Telegram 配置")
                    is_connected = False

async def revalidate_channels():
    """
    重新验证频道（重连后需要重新验证）
    """
    global CHANNEL_ENTITIES
    
    logger.info("🔄 重新验证频道...")
    CHANNEL_ENTITIES.clear()
    
    CHANNEL_LIST = list(TELEGRAM_CHANNELS.keys())
    failed_channels = []
    
    for channel_key in CHANNEL_LIST:
        try:
            entity = await client.get_entity(channel_key)
            channel_title = entity.title if hasattr(entity, 'title') else 'N/A'
            channel_id = entity.id if hasattr(entity, 'id') else 'N/A'
            parser_name = TELEGRAM_CHANNELS.get(channel_key, 'default_parser')
            CHANNEL_ENTITIES.append(entity)
            logger.info(f"✅ 频道验证成功: {channel_title} ({channel_key}) | ID: {channel_id} | 解析器: {parser_name}")
        except Exception as e:
            error_msg = str(e)
            failed_channels.append(channel_key)
            logger.warning(f"⚠️ 频道验证失败: {channel_key} - {error_msg}")
    
    if failed_channels:
        logger.warning(f"⚠️ 共有 {len(failed_channels)} 个频道验证失败")
    else:
        logger.info(f"✅ 成功重新验证 {len(CHANNEL_ENTITIES)} 个频道")

# 使用 Raw 事件直接监听频道消息（最快、最稳的方案）
# 核心思想：不用 iter_messages, 不等 history, 直接吃 updates
@client.on(events.Raw)
async def handle_raw_event(update):
    """
    使用 Raw 事件直接监听频道消息
    这是目前做频道监听最快、最稳的方案
    """
    global is_connected
    
    # 检查是否是消息更新
    if not hasattr(update, 'message'):
        # 不是消息更新，可能是其他类型的事件（用于连接状态检测）
        if hasattr(update, 'CONSTRUCTOR_ID'):
            pass  # 可以在这里添加特定的事件处理
        return
    
    # 提取消息
    msg = update.message
    if not msg:
        return
    
    # 检查是否是频道消息
    if not hasattr(msg, 'peer_id') or not hasattr(msg.peer_id, 'channel_id'):
        return  # 不是频道消息，跳过
    
    # 获取频道 ID（Raw 事件中的 channel_id 是正整数）
    raw_channel_id = msg.peer_id.channel_id
    
    # 检查是否是我们监听的频道
    is_target_channel = False
    channel_key = None
    channel_username = None
    channel_title = None
    parser_name = None
    
    # 方法1: 检查是否在 CHANNEL_ENTITIES 中（已验证的频道）
    # 优化：使用更快的匹配方式
    for ch_entity in CHANNEL_ENTITIES:
        if hasattr(ch_entity, 'id'):
            # Telegram 的完整频道 ID 格式是 -100xxxxxxxxx
            # Raw 事件中的 channel_id 是正整数部分
            # 快速匹配：完整 ID 的绝对值取模 1000000000 应该等于 raw_channel_id
            entity_id_abs = abs(ch_entity.id)
            # 快速匹配逻辑
            if entity_id_abs % 1000000000 == raw_channel_id:
                is_target_channel = True
                channel_title = getattr(ch_entity, 'title', None)
                channel_username = getattr(ch_entity, 'username', None)
                # 快速查找对应的 channel_key（使用用户名或 ID）
                if channel_username:
                    username_clean = channel_username.lstrip('@')
                    if username_clean in TELEGRAM_CHANNELS:
                        channel_key = username_clean
                        parser_name = TELEGRAM_CHANNELS[username_clean]
                    else:
                        # 尝试通过 ID 匹配
                        channel_id_str = f"-100{raw_channel_id}"
                        if channel_id_str in TELEGRAM_CHANNELS:
                            channel_key = channel_id_str
                            parser_name = TELEGRAM_CHANNELS[channel_id_str]
                else:
                    # 直接通过 ID 匹配
                    channel_id_str = f"-100{raw_channel_id}"
                    if channel_id_str in TELEGRAM_CHANNELS:
                        channel_key = channel_id_str
                        parser_name = TELEGRAM_CHANNELS[channel_id_str]
                break
    
    # 方法2: 如果不在 CHANNEL_ENTITIES 中，尝试通过配置匹配
    if not is_target_channel:
        # 尝试通过频道 ID 匹配（需要转换为字符串格式）
        channel_id_str = f"-100{raw_channel_id}"
        if channel_id_str in TELEGRAM_CHANNELS:
            is_target_channel = True
            channel_key = channel_id_str
            parser_name = TELEGRAM_CHANNELS[channel_id_str]
            logger.info(f"   ℹ️ 频道 ID {channel_id_str} 在配置中，但未在启动时验证成功，仍将处理消息")
    
    # 如果不是目标频道，跳过处理
    if not is_target_channel:
        return
    
    # 确定解析器
    if not parser_name:
        parser_name = TELEGRAM_CHANNELS.get(channel_key, 'default_parser')
    
    # 提取消息文本
    raw_text = ""
    if hasattr(msg, 'message') and msg.message:
        raw_text = msg.message.strip()
    
    # 记录收到消息的详细信息
    import datetime
    import time
    event_received_time = time.perf_counter()
    event_received_datetime = datetime.datetime.now()
    
    logger.info("=" * 50)
    logger.info("📩 收到新消息！(Raw Update ⚡)")
    logger.info(f"   事件接收时间: {event_received_datetime.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
    logger.info(f"   频道: {channel_title or channel_key or f'ID:{raw_channel_id}'} (Raw ID: {raw_channel_id})")
    logger.info(f"   解析器: {parser_name}")
    logger.info(f"   消息 ID: {msg.id if hasattr(msg, 'id') else 'N/A'}")
    logger.info(f"   原始文本长度: {len(raw_text) if raw_text else 0}")
    
    # 检查是否是特殊解析器（需要 event 和 client，支持视频和文本）
    if parser_name == 'stakecom_daily_drops_parser':
        # 特殊解析器：可以处理视频和文本
        # 需要从 Raw 事件中获取完整的消息对象
        parser_func = CODE_PARSERS.get(parser_name)
        if parser_func:
            try:
                # 从 Raw 事件中获取消息 ID 和频道信息，然后获取完整的消息对象
                msg_id = msg.id if hasattr(msg, 'id') else None
                if msg_id:
                    # 使用频道实体获取完整消息对象
                    # 找到对应的频道实体
                    channel_entity = None
                    for ch_entity in CHANNEL_ENTITIES:
                        entity_id_abs = abs(ch_entity.id)
                        if entity_id_abs == raw_channel_id or (entity_id_abs > 1000000000000 and entity_id_abs % 1000000000 == raw_channel_id):
                            channel_entity = ch_entity
                            break
                    
                    if channel_entity:
                        # 获取完整的消息对象（支持视频和文本）
                        try:
                            full_messages = await client.get_messages(channel_entity, ids=msg_id)
                            if full_messages and len(full_messages) > 0:
                                full_event = full_messages[0]
                                # 调用解析器，传入完整的 event 对象（支持视频和文本处理）
                                code = await parser_func(full_event, client)
                            else:
                                # 如果无法获取完整消息，尝试文本解析
                                logger.warning(f"   ⚠️ 无法获取完整消息对象，尝试文本解析")
                                if raw_text:
                                    import re
                                    match = re.search(r'- Code:\s*([a-z0-9]+)', raw_text, re.IGNORECASE)
                                    if match:
                                        code = match.group(1).strip().lower()
                                    else:
                                        code = None
                                else:
                                    code = None
                        except Exception as e:
                            logger.warning(f"   ⚠️ 获取完整消息对象失败: {e}，尝试文本解析")
                            # 如果获取失败，尝试文本解析
                            if raw_text:
                                import re
                                match = re.search(r'- Code:\s*([a-z0-9]+)', raw_text, re.IGNORECASE)
                                if match:
                                    code = match.group(1).strip().lower()
                                else:
                                    code = None
                            else:
                                code = None
                    else:
                        # 如果找不到频道实体，尝试使用 channel_id 构建 PeerChannel
                        try:
                            from telethon.tl.types import PeerChannel
                            channel_peer = PeerChannel(channel_id=raw_channel_id)
                            full_messages = await client.get_messages(channel_peer, ids=msg_id)
                            if full_messages and len(full_messages) > 0:
                                full_event = full_messages[0]
                                # 调用解析器，传入完整的 event 对象（支持视频和文本处理）
                                code = await parser_func(full_event, client)
                            else:
                                # 如果无法获取完整消息，尝试文本解析
                                logger.warning(f"   ⚠️ 无法获取完整消息对象，尝试文本解析")
                                if raw_text:
                                    import re
                                    match = re.search(r'- Code:\s*([a-z0-9]+)', raw_text, re.IGNORECASE)
                                    if match:
                                        code = match.group(1).strip().lower()
                                    else:
                                        code = None
                                else:
                                    code = None
                        except Exception as e:
                            logger.warning(f"   ⚠️ 使用 PeerChannel 获取消息失败: {e}，尝试文本解析")
                            if raw_text:
                                import re
                                match = re.search(r'- Code:\s*([a-z0-9]+)', raw_text, re.IGNORECASE)
                                if match:
                                    code = match.group(1).strip().lower()
                                else:
                                    code = None
                            else:
                                code = None
                else:
                    # 如果没有消息 ID，只能尝试文本解析
                    logger.warning(f"   ⚠️ 无法获取消息 ID，尝试文本解析")
                    if raw_text:
                        import re
                        match = re.search(r'- Code:\s*([a-z0-9]+)', raw_text, re.IGNORECASE)
                        if match:
                            code = match.group(1).strip().lower()
                        else:
                            code = None
                    else:
                        code = None
            except Exception as e:
                logger.error(f"   ❌ 处理特殊解析器失败: {e}", exc_info=True)
                code = None
        else:
            code = None
    else:
        # 普通解析器：只需要文本
        if not raw_text:
            logger.info("   消息为空，跳过处理")
            logger.info("=" * 50)
            return
        
        parser_func = CODE_PARSERS.get(parser_name, parse_code_default)
        code = parser_func(raw_text)
    
    if not code:
        logger.warning(f"   ⚠️ 无法从消息中提取代码，跳过处理")
        logger.info(f"   使用的解析器: {parser_name}")
        if raw_text:
            logger.info(f"   原始内容: {raw_text[:300]}...")
        logger.info("=" * 50)
        return

    logger.info(f"   使用的解析器: {parser_name}")
    logger.info(f"   原始内容预览: {raw_text[:200]}...")
    logger.info(f"   ✅ 提取的代码: {code}")
    logger.info(f"🚀 正在开启新线程执行同步请求任务...")

    # 记录收到消息的时间戳（用于计算总耗时）
    message_received_time = time.perf_counter()
    
    # 检查是否是测试频道，如果是则只发给特定账号
    filter_username = None
    # 检查频道是否是 stake_cn_chat_room
    is_test_channel = (
        channel_key == 'stake_cn_chat_room' or 
        (channel_username and channel_username.lstrip('@') == 'stake_cn_chat_room')
    )
    if is_test_channel:
        filter_username = 'yzjjdcf'
        logger.info(f"   🧪 测试频道模式：仅发送给账号名为 '{filter_username}' 的账号")

    # 使用 asyncio.create_task 让任务在后台运行，不阻塞事件循环
    async def run_task():
        await asyncio.to_thread(redeem_bonus_task, code, message_received_time, filter_username)
    
    asyncio.create_task(run_task())
    logger.info(f"🚀 任务已提交到后台线程（不阻塞）: {code}")
    logger.info("=" * 50)


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
        failed_channels = []
        
        for channel_key in CHANNEL_LIST:
            try:
                entity = await client.get_entity(channel_key)
                channel_title = entity.title if hasattr(entity, 'title') else 'N/A'
                channel_id = entity.id if hasattr(entity, 'id') else 'N/A'
                parser_name = TELEGRAM_CHANNELS.get(channel_key, 'default_parser')
                CHANNEL_ENTITIES.append(entity)
                logger.info(f"✅ 频道验证成功: {channel_title} ({channel_key}) | ID: {channel_id} | 解析器: {parser_name}")
            except Exception as e:
                error_msg = str(e)
                failed_channels.append(channel_key)
                logger.warning(f"⚠️ 频道验证失败: {channel_key} - {error_msg}")
                
                # 提供更详细的错误提示
                if "Cannot find any entity" in error_msg:
                    logger.warning(f"   可能的原因：")
                    logger.warning(f"   1. 频道ID或用户名不正确")
                    logger.warning(f"   2. 机器人已被移出该频道")
                    logger.warning(f"   3. 频道已被删除或私有化")
                    logger.warning(f"   4. 机器人没有访问该频道的权限")
                    logger.warning(f"   建议：如果该频道不再需要，可以从配置中移除或注释掉")
                else:
                    logger.warning(f"   错误详情: {error_msg}")
        
        if failed_channels:
            logger.warning(f"⚠️ 共有 {len(failed_channels)} 个频道验证失败，将跳过这些频道")
            logger.warning(f"   失败的频道: {', '.join(failed_channels)}")
            logger.warning(f"   程序将继续运行，只监听成功验证的频道")
        
        if not CHANNEL_ENTITIES:
            logger.error("❌ 没有成功验证任何频道，无法启动监听")
            logger.error("   请检查配置文件中的频道配置是否正确")
            logger.error("   或者确认机器人是否有访问这些频道的权限")
            raise ValueError("没有可用的频道")
        
        logger.info(f"✅ 成功加载 {len(CHANNEL_ENTITIES)} 个频道实体")
        
        # 标记为已连接
        is_connected = True
        last_heartbeat_time = asyncio.get_event_loop().time()
        
        # 启动心跳检测任务
        logger.info("💓 启动心跳检测任务（每 {} 秒检查一次）...".format(heartbeat_interval))
        heartbeat_task = asyncio.create_task(heartbeat_check())
        
        logger.info("🎧 开始监听消息...")
        logger.info("   等待新消息中...")
        
        try:
            await client.run_until_disconnected()
        except KeyboardInterrupt:
            logger.info("   收到停止信号...")
            raise
        except Exception as e:
            logger.error(f"❌ 连接异常: {e}", exc_info=True)
            is_connected = False
            # 尝试重连
            await attempt_reconnect()
            # 如果重连成功，继续运行
            if client.is_connected():
                await client.run_until_disconnected()
        finally:
            # 停止心跳检测
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
            logger.info("💓 心跳检测任务已停止")
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