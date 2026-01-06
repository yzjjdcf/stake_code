"""
OCR 和图片处理工具模块
包含图片压缩、OCR 识别等功能
"""
import logging
import base64
import io
import re
import time

logger = logging.getLogger(__name__)

# 全局配置（从外部设置）
OPENAI_API_KEY = None
OPENAI_API_BASE_URL = 'https://api.gpt.ge/v1/chat/completions'
OPENAI_MODEL = 'gpt-4o'

# OCR API 配置（新增）
OCR_API_URL = None
OCR_API_TOKEN = None


def set_ocr_config(api_key=None, api_base_url=None, model=None, ocr_api_url=None, ocr_api_token=None):
    """设置 OCR 配置"""
    global OPENAI_API_KEY, OPENAI_API_BASE_URL, OPENAI_MODEL, OCR_API_URL, OCR_API_TOKEN
    if api_key is not None:
        OPENAI_API_KEY = api_key
    if api_base_url is not None:
        OPENAI_API_BASE_URL = api_base_url
    if model is not None:
        OPENAI_MODEL = model
    if ocr_api_url is not None:
        OCR_API_URL = ocr_api_url
    if ocr_api_token is not None:
        OCR_API_TOKEN = ocr_api_token


def compress_image_to_base64(image_frame, quality=75, max_size=(800, 800)):
    """
    使用 Pillow 压缩图片并转换为 base64
    
    Args:
        image_frame: OpenCV 读取的图片帧（numpy array，BGR 格式）
        quality: JPEG 压缩质量（1-100，默认 75）
        max_size: 最大尺寸 (width, height)，如果图片更大则等比例缩放
    
    Returns:
        base64 编码的图片字符串
    """
    import cv2
    from PIL import Image
    import numpy as np
    
    try:
        # 将 OpenCV BGR 格式转换为 RGB 格式（Pillow 需要 RGB）
        rgb_frame = cv2.cvtColor(image_frame, cv2.COLOR_BGR2RGB)
        
        # 转换为 PIL Image
        pil_image = Image.fromarray(rgb_frame)
        
        # 如果图片尺寸超过最大尺寸，等比例缩放
        if pil_image.size[0] > max_size[0] or pil_image.size[1] > max_size[1]:
            pil_image.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # 压缩并转换为字节流
        buffer = io.BytesIO()
        pil_image.save(buffer, format='JPEG', quality=quality, optimize=True)
        buffer.seek(0)
        
        # 转换为 base64
        image_base64 = base64.b64encode(buffer.read()).decode('utf-8')
        
        return image_base64
    except Exception as e:
        logger.error(f"❌ 图片压缩失败: {e}", exc_info=True)
        # 如果压缩失败，使用 OpenCV 直接编码
        _, buffer = cv2.imencode('.jpg', image_frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return base64.b64encode(buffer).decode('utf-8')


def recognize_code_with_tesseract(image_frame):
    """
    使用 Tesseract OCR 识别图片中的代码（本地识别，速度快）
    
    Args:
        image_frame: OpenCV 读取的图片帧（numpy array，BGR 格式）
    
    Returns:
        识别出的代码字符串，如果失败返回 None
    """
    import cv2
    import pytesseract
    
    try:
        ocr_start_time = time.perf_counter()
        logger.info("🤖 正在使用 Tesseract OCR 识别图片中的代码...")
        
        # Tesseract 需要 PIL Image 或文件路径
        # 将 OpenCV BGR 格式转换为 RGB 格式
        rgb_frame = cv2.cvtColor(image_frame, cv2.COLOR_BGR2RGB)
        
        # 转换为 PIL Image
        from PIL import Image
        pil_image = Image.fromarray(rgb_frame)
        
        # 使用 Tesseract OCR 识别（只识别字母和数字）
        # --psm 7: 单行文本
        # -c tessedit_char_whitelist: 只识别字母和数字
        custom_config = r'--psm 7 -c tessedit_char_whitelist=abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        text = pytesseract.image_to_string(pil_image, config=custom_config)
        
        ocr_elapsed_ms = int((time.perf_counter() - ocr_start_time) * 1000)
        logger.info(f"⏱️ Tesseract OCR 识别耗时: {ocr_elapsed_ms}ms")
        logger.info(f"📝 Tesseract OCR 识别结果: {text.strip()}")
        
        # 清理文本，只保留字母和数字
        code = re.sub(r'[^a-z0-9]', '', text.lower())
        
        if len(code) >= 8 and len(code) <= 25:
            logger.info(f"✅ Tesseract OCR 识别代码: {code}")
            return code
        else:
            logger.warning(f"⚠️ Tesseract OCR 识别代码长度不符合要求: {code} (长度: {len(code)})")
            return None
            
    except ImportError:
        logger.error("❌ Tesseract OCR 未安装，请运行: pip install pytesseract，并安装 Tesseract 系统包")
        return None
    except Exception as e:
        logger.error(f"❌ Tesseract OCR 识别失败: {e}", exc_info=True)
        return None


def recognize_code_with_api(image_path=None, image_base64=None):
    """
    使用第三方 API 识别图片中的代码
    
    Args:
        image_path: 图片文件路径（如果提供，则从文件读取）
        image_base64: base64 编码的图片字符串（如果提供，则直接使用）
    
    Returns:
        识别出的代码字符串，如果失败返回 None
    """
    import requests
    
    if not OPENAI_API_KEY:
        logger.warning("⚠️ API Key 未配置，无法识别视频中的代码")
        return None
    
    try:
        # 获取 base64 编码的图片
        base64_start_time = time.perf_counter()
        if image_base64:
            # 直接使用提供的 base64
            image_base64_str = image_base64
        elif image_path:
            # 从文件读取并转换为 base64
            with open(image_path, 'rb') as image_file:
                image_data = image_file.read()
                image_base64_str = base64.b64encode(image_data).decode('utf-8')
        else:
            logger.error("❌ 必须提供 image_path 或 image_base64 之一")
            return None
        
        base64_elapsed_ms = int((time.perf_counter() - base64_start_time) * 1000)
        logger.info(f"⏱️ 图片转 base64 耗时: {base64_elapsed_ms}ms | 大小: {len(image_base64_str)} 字符")
        
        # 从全局配置读取
        api_url = OPENAI_API_BASE_URL
        api_key = OPENAI_API_KEY
        model = OPENAI_MODEL
        
        logger.info(f"🔗 请求地址: {api_url}")
        logger.info(f"🔑 使用模型: {model}")
        logger.info("🤖 正在使用第三方 API 识别图片中的代码...")
        
        # 构建请求头
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        # 构建请求体
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "请识别图片中的代码，只返回代码本身，不要其他文字。代码通常是字母和数字的组合，长度在8-25个字符之间。"
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64_str}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 50
        }
        
        # 发送 POST 请求
        api_start_time = time.perf_counter()
        response = requests.post(
            api_url,
            headers=headers,
            json=payload,
            timeout=30
        )
        api_elapsed_ms = int((time.perf_counter() - api_start_time) * 1000)
        
        # 检查响应
        if response.status_code != 200:
            logger.error(f"❌ API 请求失败（耗时 {api_elapsed_ms}ms）: HTTP {response.status_code}, 响应: {response.text[:200]}")
            return None
        
        # 解析响应
        response_data = response.json()
        if 'choices' not in response_data or len(response_data['choices']) == 0:
            logger.error(f"❌ API 响应格式错误（耗时 {api_elapsed_ms}ms）: {response_data}")
            return None
        
        code_text = response_data['choices'][0]['message']['content'].strip()
        logger.info(f"📝 API 识别结果: {code_text} | API 请求耗时: {api_elapsed_ms}ms")
        
        # 清理代码文本，只保留字母和数字
        code = re.sub(r'[^a-z0-9]', '', code_text.lower())
        if len(code) >= 10:
            logger.info(f"✅ API 识别代码: {code}")
            return code
        else:
            logger.warning(f"⚠️ API 识别代码长度不足: {code}")
            return None
            
    except Exception as e:
        logger.error(f"❌ API 识别失败: {e}", exc_info=True)
        return None


def recognize_code_with_ocr_api(image_path=None, image_base64=None):
    """
    使用 OCR API 服务识别图片中的代码（formData 方式）
    
    API 文档：
    - 端点: POST /task/pic/ocr
    - 使用 formData 方式发送请求
    - 需要 Authorization header (Bearer Token)
    - 支持 image_file (文件) 或 image_url (URL)
    
    Args:
        image_path: 图片文件路径（如果提供，则从文件读取）
        image_base64: base64 编码的图片字符串（如果提供，则转换为临时文件）
    
    Returns:
        识别出的代码字符串，如果失败返回 None
    """
    import requests
    import tempfile
    import os
    
    if not OCR_API_URL or not OCR_API_TOKEN:
        logger.warning("⚠️ OCR API 未配置（URL 或 Token），无法使用 OCR API 识别")
        return None
    
    try:
        ocr_start_time = time.perf_counter()
        logger.info("🤖 正在使用 OCR API 识别图片中的代码...")
        
        # 准备文件数据
        temp_file = None
        try:
            if image_path and os.path.exists(image_path):
                # 直接使用文件路径
                file_data = open(image_path, 'rb')
                file_name = os.path.basename(image_path)
            elif image_base64:
                # 将 base64 转换为临时文件
                import base64
                image_data = base64.b64decode(image_base64)
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
                temp_file.write(image_data)
                temp_file.close()
                file_data = open(temp_file.name, 'rb')
                file_name = 'image.jpg'
            else:
                logger.error("❌ 必须提供 image_path 或 image_base64 之一")
                return None
            
            # 构建请求
            url = f"{OCR_API_URL.rstrip('/')}/task/pic/ocr"
            headers = {
                'Authorization': f'Bearer {OCR_API_TOKEN}'
            }
            
            # 使用 formData 方式发送（multipart/form-data）
            files = {
                'image_file': (file_name, file_data, 'image/jpeg')
            }
            
            logger.info(f"🔗 请求地址: {url}")
            logger.info(f"📤 发送图片文件: {file_name}")
            
            # 发送 POST 请求
            api_start_time = time.perf_counter()
            response = requests.post(
                url,
                headers=headers,
                files=files,
                timeout=30
            )
            api_elapsed_ms = int((time.perf_counter() - api_start_time) * 1000)
            
            # 关闭文件
            file_data.close()
            
            # 检查响应
            if response.status_code != 200:
                logger.error(f"❌ OCR API 请求失败（耗时 {api_elapsed_ms}ms）: HTTP {response.status_code}, 响应: {response.text[:200]}")
                return None
            
            # 解析响应
            try:
                response_data = response.json()
            except:
                logger.error(f"❌ OCR API 响应格式错误（耗时 {api_elapsed_ms}ms）: 无法解析 JSON")
                logger.debug(f"响应内容: {response.text[:500]}")
                return None
            
            ocr_elapsed_ms = int((time.perf_counter() - ocr_start_time) * 1000)
            logger.info(f"⏱️ OCR API 识别耗时: {ocr_elapsed_ms}ms")
            logger.debug(f"📝 OCR API 响应: {response_data}")
            
            # 提取识别结果（根据实际 API 响应格式调整）
            # 假设响应格式为 {"code": 0, "data": {"text": "识别结果"}, "message": "success"}
            # 或者 {"result": "识别结果"}
            code_text = None
            if isinstance(response_data, dict):
                # 尝试多种可能的响应格式
                if 'data' in response_data and isinstance(response_data['data'], dict):
                    if 'text' in response_data['data']:
                        code_text = response_data['data']['text']
                    elif 'result' in response_data['data']:
                        code_text = response_data['data']['result']
                elif 'result' in response_data:
                    code_text = response_data['result']
                elif 'text' in response_data:
                    code_text = response_data['text']
                elif 'data' in response_data and isinstance(response_data['data'], str):
                    code_text = response_data['data']
            
            if not code_text:
                logger.warning(f"⚠️ OCR API 响应格式不符合预期: {response_data}")
                return None
            
            logger.info(f"📝 OCR API 识别结果: {code_text}")
            
            # 清理代码文本，只保留字母和数字
            code = re.sub(r'[^a-z0-9]', '', code_text.lower())
            if len(code) >= 8 and len(code) <= 25:
                logger.info(f"✅ OCR API 识别代码: {code}")
                return code
            else:
                logger.warning(f"⚠️ OCR API 识别代码长度不符合要求: {code} (长度: {len(code)})")
                return None
            
        finally:
            # 清理临时文件
            if temp_file and os.path.exists(temp_file.name):
                try:
                    os.remove(temp_file.name)
                except:
                    pass
            
    except Exception as e:
        logger.error(f"❌ OCR API 识别失败: {e}", exc_info=True)
        return None

