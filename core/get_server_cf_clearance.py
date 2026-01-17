"""
获取服务器 Cloudflare Clearance Token 的工具模块
在服务启动时调用，使用服务器真实IP获取 cf_clearance（通过 Capsolver API）
"""
import logging
import time
import os
import sys
import requests

logger = logging.getLogger(__name__)


def get_server_cf_clearance():
    """
    通过 Capsolver API 获取服务器的 Cloudflare Clearance Token 和 User-Agent（使用指定的代理）
    
    Returns:
        tuple: (cf_clearance, user_agent) 如果成功，否则返回 (None, None)
    """
    try:
        # 导入配置
        current_dir = os.path.dirname(os.path.abspath(__file__))
        core_dir = current_dir  # core/ 目录
        project_root = os.path.dirname(core_dir)  # 项目根目录
        
        config_path = os.path.join(project_root, 'config', 'config.py')
        if os.path.exists(config_path):
            import importlib.util
            spec = importlib.util.spec_from_file_location("config_module", config_path)
            config_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(config_module)
        else:
            logger.error(f"❌ 无法找到配置文件: {config_path}")
            return None, None
        
        # 获取 Capsolver API Key
        capsolver_api_key = os.getenv('CAPSOLVER_API_KEY', 'CAP-5B4B10EB54FE9A54BF32F113839720F39D1F6EC069121A3E25D5B205BDF076E7')
        if not capsolver_api_key:
            logger.error("❌ 未设置 CAPSOLVER_API_KEY 环境变量")
            return None, None
        
        capsolver_api_url = 'https://api.capsolver.com'
        target_url = 'https://stake.com'
        
        # 服务器代理配置（用于获取 cf_clearance）
        server_proxy = "isp.decodo.com:10003:spoigpsfuo:xkp5JeXPk3Ly+tn92h"
        
        logger.info("🔐 开始获取服务器 Cloudflare Clearance Token（使用 Capsolver API）...")
        start_time = time.time()
        
        # 解析代理地址为 Capsolver 格式
        proxy_parts = server_proxy.split(':')
        if len(proxy_parts) >= 4:
            proxy_host = proxy_parts[0]
            proxy_port = int(proxy_parts[1])
            proxy_user = proxy_parts[2]
            proxy_pass = ':'.join(proxy_parts[3:])  # 密码可能包含冒号
            proxy_type = 'http'  # 默认使用 http
            
            # Capsolver 代理格式（字符串格式）
            capsolver_proxy = f"{proxy_type}:{proxy_host}:{proxy_port}:{proxy_user}:{proxy_pass}"
        else:
            logger.error(f"❌ 代理地址格式错误: {server_proxy}")
            return None, None
        
        # 创建 Capsolver 客户端
        session = requests.Session()
        session.headers.update({'Content-Type': 'application/json'})
        session.proxies = {}  # 确保不使用代理访问 Capsolver API
        
        # 硬编码的 User-Agent（从 ocr_utils.py 中获取相同的值）
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
        
        # html 字段（硬代码中没有，使用模板默认值或留空）
        # 注意：如果需要，可以先访问网站获取 HTML，这里先留空，Capsolver 会自动获取
        html_template = ""  # 留空，让 Capsolver 自动获取
        
        # 创建任务（使用代理）
        task_config = {
            "type": "AntiCloudflareTask",
            "websiteURL": target_url,
            "userAgent": user_agent,
            "proxy": capsolver_proxy,
        }
        
        # 如果有 html，添加到配置中（Capsolver 会自动获取，所以这里可以留空）
        if html_template:
            task_config["html"] = html_template
        
        payload = {
            "clientKey": capsolver_api_key,
            "task": task_config
        }
        
        logger.info("📤 创建 Capsolver 任务...")
        import json as json_module
        logger.info(f"请求 payload: {json_module.dumps(payload, ensure_ascii=False, indent=2)}")
        try:
            response = session.post(f"{capsolver_api_url}/createTask", json=payload, timeout=30)
            logger.info(f"响应状态码: {response.status_code}")
            logger.info(f"响应内容: {response.text}")
            response.raise_for_status()
            create_result = response.json()
        except requests.exceptions.HTTPError as e:
            logger.error(f"❌ Capsolver API 请求失败 (HTTP {response.status_code}): {e}")
            try:
                error_detail = response.json()
                logger.error(f"错误详情: {json_module.dumps(error_detail, ensure_ascii=False, indent=2)}")
            except:
                logger.error(f"响应内容: {response.text}")
            return None, None
        
        if create_result.get('errorId') != 0:
            error_code = create_result.get('errorCode') or create_result.get('errorId')
            error_desc = create_result.get('errorDescription', '未知错误')
            logger.error(f"❌ 任务创建失败: {error_code} - {error_desc}")
            logger.error(f"完整响应: {create_result}")
            return None, None
        
        task_id = create_result.get('taskId')
        if not task_id:
            logger.error("❌ 未获取到任务 ID")
            return None, None
        
        logger.info(f"✅ 任务创建成功，任务 ID: {task_id}")
        
        # 等待任务完成
        logger.info(f"⏳ 等待任务完成（最大等待 300 秒）...")
        max_wait = 300
        wait_start = time.time()
        check_count = 0
        
        while True:
            elapsed = time.time() - wait_start
            if elapsed > max_wait:
                logger.warning(f"⏱️  等待超时（已等待 {elapsed:.1f} 秒）")
                return None, None
            
            time.sleep(3)  # 每 3 秒检查一次
            check_count += 1
            
            get_payload = {"clientKey": capsolver_api_key, "taskId": task_id}
            get_response = session.post(f"{capsolver_api_url}/getTaskResult", json=get_payload, timeout=30)
            get_response.raise_for_status()
            result = get_response.json()
            
            status = result.get('status')
            
            if status == 'ready':
                logger.info(f"✅ 任务完成！")
                solution = result.get('solution', {})
                
                # 获取 cookies
                cookies_dict = solution.get('cookies', {})
                
                if 'cf_clearance' in cookies_dict:
                    cf_clearance = cookies_dict['cf_clearance']
                    # 获取 userAgent（从 solution 中，如果有）
                    user_agent = solution.get('userAgent', '')
                    
                    total_duration = time.time() - start_time
                    logger.info(f"✅ 成功获取服务器 cf_clearance Token!")
                    logger.info(f"总耗时: {total_duration:.2f}秒 | 检查次数: {check_count}")
                    logger.debug(f"cf_clearance 值: {cf_clearance[:50]}...")
                    if user_agent:
                        logger.debug(f"userAgent: {user_agent[:50]}...")
                    
                    # 返回 cf_clearance 和 userAgent
                    return cf_clearance, user_agent
                else:
                    logger.error("❌ 任务完成但未获取到 cf_clearance cookie")
                    logger.debug(f"获取到的 cookies: {list(cookies_dict.keys())}")
                    return None, None
            elif status == 'processing':
                if check_count % 10 == 0:  # 每10次输出一次日志
                    logger.debug(f"⏳ 任务处理中... (已等待 {elapsed:.1f} 秒，检查 {check_count} 次)")
            else:
                error_code = result.get('errorCode') or result.get('errorId')
                error_desc = result.get('errorDescription', '未知错误')
                logger.error(f"❌ 任务失败: {error_code} - {error_desc}")
                return None, None
                
    except Exception as e:
        logger.error(f"❌ 获取服务器 cf_clearance 失败: {e}", exc_info=True)
        return None, None

