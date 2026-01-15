"""
Winna 代码解析器模块
支持两种类型的代码：
1. 猜谜类型（下划线格式）：sp_n-p__ks-_ 需要 AI 猜测
2. 视频+文字类型（包含 check）：需要 OCR 识别
"""
import re
import logging
import os
import time
import asyncio
import cv2
import numpy as np
from typing import Optional, Tuple

logger = logging.getLogger('listener_winna')

# API 配置从 ocr_utils 导入（与 recognize_code_with_api 使用相同的配置）


def extract_winna_code_region(frame):
    """
    从 Winna 视频帧中提取代码区域
    
    Winna 的代码显示在右侧的发光白色虚线框中，背景是深色的。
    需要检测虚线框的边缘，裁剪到虚线框内部。
    
    Args:
        frame: OpenCV 读取的原始帧（numpy array，BGR 格式）
    
    Returns:
        裁剪后的帧（numpy array），裁剪到虚线框内部
    """
    start_time = time.perf_counter()
    
    try:
        height, width = frame.shape[:2]
        
        # Winna 代码通常在右侧，先裁剪右侧区域缩小搜索范围
        right_start_x = int(width * 0.4)  # 从 40% 开始（扩大搜索范围）
        top_start_y = int(height * 0.15)  # 从上方 15% 开始
        bottom_end_y = int(height * 0.85)  # 到下方 85% 结束
        
        # 裁剪右侧区域
        search_area = frame[top_start_y:bottom_end_y, right_start_x:width]
        
        # 转换为灰度图
        gray = cv2.cvtColor(search_area, cv2.COLOR_BGR2GRAY)
        
        # 使用 Canny 边缘检测来找到虚线框的边缘
        # 虚线框通常有较高的对比度
        edges = cv2.Canny(gray, 50, 150)
        
        # 形态学操作，连接断开的虚线
        kernel = np.ones((3, 3), np.uint8)
        edges = cv2.dilate(edges, kernel, iterations=2)  # 膨胀，连接虚线
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)  # 闭运算，填充小间隙
        
        # 查找轮廓（虚线框的轮廓）
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if contours:
            # 找到最大的矩形轮廓（通常是代码框）
            # 优先选择接近矩形的轮廓
            best_contour = None
            best_score = 0
            
            for contour in contours:
                area = cv2.contourArea(contour)
                if area < 100:  # 过滤太小的轮廓
                    continue
                
                # 计算轮廓的边界矩形
                x, y, w, h = cv2.boundingRect(contour)
                rect_area = w * h
                
                # 计算轮廓面积与边界矩形面积的比值（接近矩形则比值接近1）
                extent = area / rect_area if rect_area > 0 else 0
                
                # 计算宽高比（代码框通常是横向的）
                aspect_ratio = w / h if h > 0 else 0
                
                # 综合评分：面积 + 矩形度 + 宽高比（横向优先）
                score = area * extent * (1.0 if 1.5 <= aspect_ratio <= 5.0 else 0.5)
                
                if score > best_score:
                    best_score = score
                    best_contour = contour
            
            if best_contour is not None:
                # 获取边界矩形
                x, y, w, h = cv2.boundingRect(best_contour)
                
                # 向内收缩一点，避免包含虚线本身（虚线通常在边缘）
                # 收缩 5-10 像素，只保留框内的代码区域
                shrink = 8
                x = x + shrink
                y = y + shrink
                w = max(0, w - shrink * 2)
                h = max(0, h - shrink * 2)
                
                # 确保不越界
                x = max(0, x)
                y = max(0, y)
                w = min(search_area.shape[1] - x, w)
                h = min(search_area.shape[0] - y, h)
                
                if w > 0 and h > 0:
                    cropped = search_area[y:y+h, x:x+w]
                    elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                    logger.info(f"✂️ 提取 Winna 代码区域（虚线框）耗时: {elapsed_ms}ms | 区域大小: {w}x{h} | 位置: ({x}, {y})")
                    return cropped
        
        # 如果没有找到虚线框，尝试检测高亮区域（备用方案）
        hsv = cv2.cvtColor(search_area, cv2.COLOR_BGR2HSV)
        lower_bright = np.array([0, 0, 200])
        upper_bright = np.array([180, 30, 255])
        mask = cv2.inRange(hsv, lower_bright, upper_bright)
        
        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            largest_contour = max(contours, key=cv2.contourArea)
            x, y, w, h = cv2.boundingRect(largest_contour)
            shrink = 10
            x = max(0, x + shrink)
            y = max(0, y + shrink)
            w = max(0, min(search_area.shape[1] - x, w - shrink * 2))
            h = max(0, min(search_area.shape[0] - y, h - shrink * 2))
            
            if w > 0 and h > 0:
                cropped = search_area[y:y+h, x:x+w]
                elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                logger.info(f"✂️ 提取 Winna 代码区域（高亮区域）耗时: {elapsed_ms}ms | 区域大小: {w}x{h}")
                return cropped
        
        # 如果都失败，返回右侧区域（最后备选）
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        logger.warning(f"⚠️ 未找到虚线框，使用右侧区域 | 耗时: {elapsed_ms}ms")
        return search_area
        
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        logger.error(f"❌ 提取 Winna 代码区域失败（耗时 {elapsed_ms}ms）: {e}", exc_info=True)
        # 失败时返回右侧区域
        height, width = frame.shape[:2]
        right_start_x = int(width * 0.4)
        top_start_y = int(height * 0.15)
        bottom_end_y = int(height * 0.85)
        return frame[top_start_y:bottom_end_y, right_start_x:width]


def detect_winna_code_type(text: str) -> Tuple[Optional[str], str]:
    """
    检测 Winna 代码类型
    
    Args:
        text: 消息文本
        
    Returns:
        (code_part, code_type): 
        - code_part: "BONUS CODE:" 后面的部分，如果没有则返回 None
        - code_type: 'puzzle' (猜谜) 或 'video_text' (视频+文字) 或 'unknown'
    """
    if not text:
        return None, 'unknown'
    
    # 查找 "BONUS CODE:" 后面的内容（不区分大小写）
    pattern = r'BONUS\s+CODE\s*:\s*([^\n]+)'
    match = re.search(pattern, text, re.IGNORECASE)
    
    if not match:
        return None, 'unknown'
    
    code_part = match.group(1).strip()
    
    # 检查是否包含 "check" 字样（视频+文字类型）
    if 'check' in code_part.lower():
        return code_part, 'video_text'
    
    # 检查是否是下划线格式（猜谜类型）
    # 例如：sp_n-p__ks-_ 包含下划线和连字符
    if '_' in code_part or (code_part.count('-') > 0 and any(c.isalpha() for c in code_part)):
        # 进一步验证：包含字母、数字、下划线、连字符的组合
        if re.match(r'^[a-zA-Z0-9_\-]+$', code_part):
            return code_part, 'puzzle'
    
    return code_part, 'unknown'


def parse_winna_code(text: str, message=None, has_video=False) -> Optional[str]:
    """
    Winna 代码解析主函数
    
    根据代码类型选择不同的解析方式：
    1. 猜谜类型：使用 AI 猜测完整代码
    2. 视频+文字类型：使用 OCR 识别（异步处理）
    3. 其他：尝试文本解析
    
    Args:
        text: 消息文本
        message: 消息对象（用于视频下载）
        has_video: 是否有视频
        
    Returns:
        解析出的代码，如果失败返回 None
    """
    if not text:
        return None
    
    # 检测代码类型
    code_part, code_type = detect_winna_code_type(text)
    
    if code_type == 'puzzle':
        # 猜谜类型：使用 AI 猜测
        logger.info(f"🧩 检测到猜谜类型代码: {code_part}")
        return guess_puzzle_code(code_part, text)
    elif code_type == 'video_text':
        # 视频+文字类型：需要异步处理（在 listener 中处理）
        logger.info(f"🎬 检测到视频+文字类型代码: {code_part}")
        # 返回特殊标记，让 listener 知道需要异步处理
        return 'VIDEO_TEXT_TYPE'
    else:
        # 其他类型：尝试普通文本解析
        logger.info(f"📝 尝试普通文本解析...")
        return parse_winna_code_text(text)


def guess_puzzle_code(puzzle_code: str, full_text: str) -> Optional[str]:
    """
    使用 AI 猜测猜谜代码的完整内容
    使用与 recognize_code_with_api 相同的 API 端点
    
    Args:
        puzzle_code: 猜谜代码（例如：sp_n-p__ks-_）
        full_text: 完整的消息文本（包含上下文信息）
        
    Returns:
        猜测的完整代码，如果失败返回 None
    """
    # 从 ocr_utils 导入配置
    from ocr_utils import OPENAI_API_KEY, OPENAI_API_BASE_URL, OPENAI_MODEL
    
    if not OPENAI_API_KEY:
        logger.warning("⚠️ API Key 未配置，无法使用 AI 猜谜功能")
        return None
    
    try:
        import requests
        
        # 构建提示词
        prompt = f"""你是一个代码解析专家。请根据以下信息猜测完整的 Winna 奖励代码。

猜谜代码: {puzzle_code}

完整消息内容:
{full_text}

要求：
1. 根据猜谜代码中的下划线位置，猜测缺失的字母
2. 代码通常包含字母、数字、连字符和下划线
3. 根据消息上下文（如游戏名称、活动名称等）来辅助猜测
4. 只返回完整的代码，不要包含其他解释

示例：
- 输入: sp_n-p__ks-_
- 输出: spintopicks-8

请直接返回猜测的完整代码："""
        
        logger.info(f"🤖 正在使用 AI 猜测代码: {puzzle_code}")
        logger.info(f"🔗 请求地址: {OPENAI_API_BASE_URL}")
        logger.info(f"🔑 使用模型: {OPENAI_MODEL}")
        
        # 构建请求头
        headers = {
            'Authorization': f'Bearer {OPENAI_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        # 构建请求体（仿照 recognize_code_with_api 的格式）
        payload = {
            "model": OPENAI_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": "你是一个专业的代码解析助手，擅长根据部分代码和上下文信息猜测完整的代码。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.3,  # 降低温度，使输出更确定
            "max_tokens": 50
        }
        
        # 发送 POST 请求
        ai_start_time = time.perf_counter()
        response = requests.post(
            OPENAI_API_BASE_URL,
            headers=headers,
            json=payload,
            timeout=30
        )
        ai_elapsed_ms = int((time.perf_counter() - ai_start_time) * 1000)
        
        # 检查响应
        if response.status_code != 200:
            logger.error(f"❌ API 请求失败（耗时 {ai_elapsed_ms}ms）: HTTP {response.status_code}, 响应: {response.text[:200]}")
            return None
        
        # 解析响应
        response_data = response.json()
        if 'choices' not in response_data or len(response_data['choices']) == 0:
            logger.error(f"❌ API 响应格式错误（耗时 {ai_elapsed_ms}ms）: {response_data}")
            return None
        
        guessed_code = response_data['choices'][0]['message']['content'].strip()
        logger.info(f"📝 API 识别结果: {guessed_code} | API 请求耗时: {ai_elapsed_ms}ms")
        
        # 清理猜测结果（移除可能的引号、标点等）
        guessed_code = re.sub(r'^["\']|["\']$', '', guessed_code)  # 移除首尾引号
        guessed_code = guessed_code.split('\n')[0].strip()  # 只取第一行
        
        logger.info(f"✅ AI 猜测完成 (耗时: {ai_elapsed_ms}ms) | 猜测结果: {guessed_code}")
        
        # 验证猜测结果
        if guessed_code and len(guessed_code) >= 5:
            return guessed_code
        else:
            logger.warning(f"⚠️ AI 猜测结果无效: {guessed_code}")
            return None
            
    except ImportError:
        logger.error("❌ requests 库未安装，请运行: pip install requests")
        return None
    except Exception as e:
        logger.error(f"❌ AI 猜谜失败: {e}", exc_info=True)
        return None


def parse_winna_code_text(text: str) -> Optional[str]:
    """
    普通文本解析（用于非猜谜、非视频类型的代码）
    
    Args:
        text: 消息文本
        
    Returns:
        解析出的代码，如果失败返回 None
    """
    if not text:
        return None
    
    # 尝试多种格式
    patterns = [
        r'BONUS\s+CODE\s*:\s*([a-zA-Z0-9_\-]+)',  # BONUS CODE: xxx
        r'[Cc]ode\s*:\s*([a-zA-Z0-9_\-]+)',  # Code: xxx
        r'code\s*:\s*([a-zA-Z0-9_\-]+)',  # code: xxx
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            code = match.group(1).strip()
            if code and len(code) >= 5:
                return code
    
    return None


async def parse_winna_code_video_async(text: str, message=None, download_func=None) -> Optional[str]:
    """
    Winna 视频+文字类型代码解析（异步版本）
    
    从视频中提取代码，使用 OCR 识别
    
    Args:
        text: 消息文本
        message: 消息对象（用于视频下载）
        download_func: 下载视频的函数
        
    Returns:
        解析出的代码，如果失败返回 None
    """
    if not message or not download_func:
        logger.warning("⚠️ 视频解析需要 message 和 download_func 参数")
        return None
    
    try:
        import cv2
        from ocr_utils import (
            compress_image_to_base64,
            recognize_code_with_tesseract,
            recognize_code_with_api
        )
        
        logger.info("📹 开始从 Winna 视频中提取代码（倒数第十帧）...")
        parse_start_time = time.perf_counter()
        
        # 下载视频
        download_start_time = time.perf_counter()
        result = download_func(message)
        if asyncio.iscoroutine(result):
            video_file_path = await result
        else:
            video_file_path = result
        
        download_elapsed_ms = int((time.perf_counter() - download_start_time) * 1000)
        
        video_size = os.path.getsize(video_file_path)
        logger.info(f"✅ 视频已下载 | 大小: {video_size} 字节 | 耗时: {download_elapsed_ms}ms")
        
        try:
            # 提取视频帧
            extract_start_time = time.perf_counter()
            cap = cv2.VideoCapture(video_file_path)
            if not cap.isOpened():
                logger.error(f"❌ 无法打开视频文件: {video_file_path}")
                return None
            
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            duration = total_frames / fps if fps > 0 else 0
            
            logger.info(f"📊 视频信息: 总帧数={total_frames}, 帧率={fps:.2f}fps, 时长={duration:.2f}秒")
            
            # 计算倒数第十帧
            target_frame = max(0, total_frames - 10)
            cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            ret, frame = cap.read()
            cap.release()
            
            extract_elapsed_ms = int((time.perf_counter() - extract_start_time) * 1000)
            logger.info(f"⏱️ 提取视频帧耗时: {extract_elapsed_ms}ms")
            
            if not ret or frame is None:
                logger.error("❌ 无法读取视频帧")
                return None
            
            # 提取 Winna 代码区域（右侧发光白色框）
            cropped_frame = extract_winna_code_region(frame)
            
            # 优先使用 Tesseract OCR
            code = recognize_code_with_tesseract(cropped_frame)
            
            # 如果 Tesseract 失败，使用 OpenAI API
            if not code:
                logger.info("🔄 尝试使用 OpenAI API 识别...")
                compress_start_time = time.perf_counter()
                image_base64 = compress_image_to_base64(cropped_frame, quality=75, max_size=(800, 800))
                compress_elapsed_ms = int((time.perf_counter() - compress_start_time) * 1000)
                logger.info(f"📸 图片压缩并转换为 base64 (耗时 {compress_elapsed_ms}ms)")
                
                code = recognize_code_with_api(image_base64=image_base64)
            
            if code:
                parse_total_elapsed_ms = int((time.perf_counter() - parse_start_time) * 1000)
                logger.info(f"✅ 从 Winna 视频中提取的代码: {code} | 总耗时: {parse_total_elapsed_ms}ms")
                return code
            else:
                parse_total_elapsed_ms = int((time.perf_counter() - parse_start_time) * 1000)
                logger.warning(f"⚠️ Winna 视频识别失败 | 总耗时: {parse_total_elapsed_ms}ms")
                return None
                
        except Exception as e:
            logger.error(f"❌ 处理视频失败: {e}", exc_info=True)
            return None
        finally:
            # 清理临时文件
            try:
                if os.path.exists(video_file_path):
                    os.remove(video_file_path)
                    logger.debug(f"🗑️ 已清理临时文件: {video_file_path}")
            except Exception as e:
                logger.warning(f"⚠️ 清理临时文件失败: {e}")
                
    except ImportError as e:
        logger.error(f"❌ 缺少必要的库: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Winna 视频解析失败: {e}", exc_info=True)
        return None

