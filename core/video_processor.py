"""
视频处理模块
包含视频帧提取、代码区域识别等功能
"""
import asyncio
import os
import logging
import time
import tempfile
import threading
import cv2
import numpy as np

logger = logging.getLogger(__name__)

# 导入 OCR 工具
from ocr_utils import (
    compress_image_to_base64,
    recognize_code_with_tesseract,
    recognize_code_with_api,
    recognize_code_with_ocr_api
)
# 导入解析器
from parsers import parse_code_daily_code


def extract_white_code_region(frame):
    """
    从视频帧中提取白色代码区域
    
    根据图片特征，代码通常显示在一个白色的矩形区域中。
    通过检测白色区域并找到最大的白色矩形来裁剪代码区域。
    
    Args:
        frame: OpenCV 读取的原始帧（numpy array，BGR 格式）
    
    Returns:
        裁剪后的帧（numpy array），如果未找到白色区域则返回原始帧
    """
    start_time = time.perf_counter()
    
    try:
        # 转换为 HSV 颜色空间，更容易检测白色
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        
        # 定义白色的 HSV 范围
        # 白色在 HSV 中：H 可以是任意值，S 接近 0（低饱和度），V 接近 255（高亮度）
        lower_white = np.array([0, 0, 200])  # 较低的白色阈值
        upper_white = np.array([180, 30, 255])  # 较高的白色阈值
        
        # 创建白色区域的掩码
        mask = cv2.inRange(hsv, lower_white, upper_white)
        
        # 形态学操作，去除噪点，连接白色区域
        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        
        # 查找轮廓
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            logger.warning("⚠️ 未找到白色区域，使用原始帧")
            return frame
        
        # 找到最大的白色区域（通常是代码框）
        largest_contour = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest_contour)
        
        # 如果白色区域太小，可能不是代码框
        frame_area = frame.shape[0] * frame.shape[1]
        if area < frame_area * 0.01:  # 如果白色区域小于图片的 1%，可能不是代码框
            logger.warning("⚠️ 白色区域太小，使用原始帧")
            return frame
        
        # 获取边界矩形
        x, y, w, h = cv2.boundingRect(largest_contour)
        
        # 添加一些边距（扩大裁剪区域，确保包含完整代码）
        margin = 10
        x = max(0, x - margin)
        y = max(0, y - margin)
        w = min(frame.shape[1] - x, w + margin * 2)
        h = min(frame.shape[0] - y, h + margin * 2)
        
        # 裁剪白色区域
        cropped = frame[y:y+h, x:x+w]
        
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        logger.info(f"✂️ 提取白色代码区域耗时: {elapsed_ms}ms | 区域大小: {w}x{h} | 位置: ({x}, {y})")
        
        return cropped
        
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        logger.error(f"❌ 提取白色区域失败（耗时 {elapsed_ms}ms）: {e}", exc_info=True)
        return frame  # 失败时返回原始帧


async def parse_code_daily_code_async(text, message=None, has_video=False, download_func=None, send_code_callback=None):
    """
    解析 Daily Code 频道的代码（异步版本，用于视频）
    支持两种情况：
    1. 有视频+文字：从视频的倒数第十帧中提取代码（使用 OCR）
    2. 纯文字：从文本中解析
    
    Args:
        text: 消息文本
        message: 消息对象（不同库的格式不同，需要适配）
        has_video: 是否有视频
        download_func: 下载视频的函数，接受 message 参数，返回文件路径
        send_code_callback: 可选的回调函数，用于发送代码（用于二次识别后的发送）
                           函数签名: send_code_callback(code: str) -> None
    """
    parse_start_time = time.perf_counter()
    
    # 如果有视频，从视频的倒数第十帧中提取代码
    if has_video and message and download_func:
        try:
            # 直接从视频帧中提取代码
            logger.info("📹 开始从视频中提取代码（倒数第十帧）...")
            
            # 下载视频到临时目录
            download_start_time = time.perf_counter()

            result = download_func(message)
            if asyncio.iscoroutine(result):
                video_file_path = await result
            else:
                video_file_path = result

            download_elapsed_ms = int((time.perf_counter() - download_start_time) * 1000)
            
            # 获取文件大小
            video_size = os.path.getsize(video_file_path)
            logger.info(f"✅ 视频已下载到临时目录 | 大小: {video_size} 字节 | 耗时: {download_elapsed_ms}ms | 路径: {video_file_path}")
            
            try:
                # 提取视频帧（OpenCV 支持直接跳转到指定帧，比 imageio 快）
                extract_start_time = time.perf_counter()
                
                # 打开视频文件
                cap = cv2.VideoCapture(video_file_path)
                if not cap.isOpened():
                    logger.error(f"❌ 无法打开视频文件: {video_file_path}")
                    return None
                
                # 获取视频信息
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                fps = cap.get(cv2.CAP_PROP_FPS)
                duration = total_frames / fps if fps > 0 else 0
                
                logger.info(f"📊 视频总帧数: {total_frames}, 帧率: {fps:.2f}fps, 时长: {duration:.2f}秒")
                
                # 计算倒数第十帧的帧号（倒数第十帧 = 总帧数 - 10）
                target_frame = max(0, total_frames - 10)
                
                # 直接跳转到目标帧（OpenCV 的优势：快速随机访问）
                cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
                
                # 读取帧
                ret, frame = cap.read()
                cap.release()
                
                extract_elapsed_ms = int((time.perf_counter() - extract_start_time) * 1000)
                logger.info(f"⏱️ 提取视频帧耗时: {extract_elapsed_ms}ms")
                
                if not ret or frame is None:
                    logger.error("❌ 无法读取视频帧")
                    return None
                
                # 提取白色代码区域
                cropped_frame = extract_white_code_region(frame)
                
                # 初始化 code 变量
                code = None
                
                # 优先使用 Tesseract OCR（本地识别，速度快）
                code = recognize_code_with_tesseract(cropped_frame)
                
                # 如果首次识别成功，进行验证和二次识别流程
                if code:
                    # 保存图片用于二次识别（如果需要）
                    image_base64 = compress_image_to_base64(cropped_frame, quality=75, max_size=(800, 800))
                    
                    # 首次识别成功，立即返回（让原有流程通过 WebSocket 发送）
                    # 同时在后台进行验证，如果失败则二次识别并再次发送
                    def verify_and_retry(code1, image_base64_for_retry, callback):
                        """后台验证和二次识别"""
                        try:
                            from ocr_utils import query_code_simple
                            
                            # 调用查询接口验证
                            is_not_found, response_data = query_code_simple(code1)
                            
                            if is_not_found:
                                logger.info(f"🔄 首次识别代码不存在，开始二次识别: {code1}")
                                
                                # 二次识别（使用 AI API）
                                from ocr_utils import recognize_code_with_api
                                code2 = recognize_code_with_api(image_base64=image_base64_for_retry)
                                
                                if code2 and code2 != code1:
                                    logger.info(f"✅ 二次识别成功: {code2} (首次: {code1})")
                                    # 如果提供了发送回调函数，调用它发送二次识别的代码
                                    if callback:
                                        try:
                                            callback(code2)
                                            logger.info(f"📤 二次识别代码已发送: {code2}")
                                        except Exception as send_err:
                                            logger.error(f"❌ 发送二次识别代码失败: {send_err}")
                                else:
                                    logger.warning(f"⚠️ 二次识别失败或结果相同: {code2}")
                            else:
                                logger.info(f"✅ 首次识别验证通过，无需二次识别: {code1}")
                        except Exception as e:
                            logger.error(f"❌ 验证和二次识别过程出错: {e}", exc_info=True)
                    
                    # 在后台线程中执行验证和二次识别（不阻塞）
                    thread = threading.Thread(target=verify_and_retry, args=(code, image_base64, send_code_callback), daemon=True)
                    thread.start()
                    logger.info(f"🚀 首次识别完成: {code}，已启动后台验证流程")
                
                # 如果 Tesseract 识别失败，尝试 OCR API（formData 方式）
                # if not code:
                #     logger.info("🔄 尝试使用 OCR API 识别...")
                #     # 使用 Pillow 压缩图片并转换为 base64（不保存文件）
                #     compress_start_time = time.perf_counter()
                #     image_base64 = compress_image_to_base64(cropped_frame, quality=75, max_size=(800, 800))
                #     compress_elapsed_ms = int((time.perf_counter() - compress_start_time) * 1000)
                #     logger.info(f"📸 图片压缩并转换为 base64 (耗时 {compress_elapsed_ms}ms) | 大小: {len(image_base64)} 字符")
                #
                #     # 使用 OCR API 识别（formData 方式）
                #     code = recognize_code_with_ocr_api(image_base64=image_base64)
                #
                # # 如果 OCR API 也失败，使用 OpenAI API 识别（最后备选）
                if not code:
                    logger.info("尝试使用 OpenAI API 识别...")
                    # 使用 Pillow 压缩图片并转换为 base64（不保存文件）
                    compress_start_time = time.perf_counter()
                    image_base64 = compress_image_to_base64(cropped_frame, quality=75, max_size=(800, 800))
                    compress_elapsed_ms = int((time.perf_counter() - compress_start_time) * 1000)
                    logger.info(f"📸 图片压缩并转换为 base64 (耗时 {compress_elapsed_ms}ms) | 大小: {len(image_base64)} 字符")
                    
                    # # 打印 base64 图片（用于调试）
                    # logger.info(f"📋 Base64 图片数据: {image_base64[:200]}..." if len(image_base64) > 200 else f"📋 Base64 图片数据: {image_base64}")
                    # print(f"\n{'='*60}")
                    # print(f"Base64 图片数据:")
                    # print(f"{image_base64}")
                    # print(f"{'='*60}\n")
                    
                    # 使用 OpenAI API 识别
                    code = recognize_code_with_api(image_base64=image_base64)
                
                if code:
                    parse_total_elapsed_ms = int((time.perf_counter() - parse_start_time) * 1000)
                    logger.info(f"✅ 从视频中提取的代码: {code} | 总耗时: {parse_total_elapsed_ms}ms")
                    return code
                else:
                    parse_total_elapsed_ms = int((time.perf_counter() - parse_start_time) * 1000)
                    logger.warning(f"⚠️ 所有识别方法都失败 | 总耗时: {parse_total_elapsed_ms}ms")
                    return None
            except Exception as e:
                logger.error(f"❌ 从临时文件读取视频失败: {e}", exc_info=True)
                return None
            finally:
                # 确保临时文件被清理
                try:
                    if os.path.exists(video_file_path):
                        os.remove(video_file_path)
                        logger.debug(f"🗑️ 已清理临时文件: {video_file_path}")
                except Exception as e:
                    logger.warning(f"⚠️ 清理临时文件失败: {e}")
        except Exception as e:
            logger.error(f"❌ 从视频中提取代码失败: {e}", exc_info=True)
            return None
    
    # 纯文字消息的解析（回退逻辑）
    return parse_code_daily_code(text, message=None, has_video=False)

