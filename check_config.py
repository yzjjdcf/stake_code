#!/usr/bin/env python
"""
配置检查脚本
用于验证平台配置是否正确
"""
import os
import sys
import platform

# 添加当前目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

try:
    import config
    print("✅ 配置文件导入成功")
except ImportError as e:
    print(f"❌ 配置文件导入失败: {e}")
    sys.exit(1)

print("\n" + "="*50)
print("平台配置检查")
print("="*50)

# 检查平台检测
detected_platform = platform.system().lower()
env_platform = os.getenv('STAKE_PLATFORM', '未设置')
print(f"系统平台: {detected_platform}")
print(f"环境变量 STAKE_PLATFORM: {env_platform}")
print(f"配置中的平台: {config.PLATFORM}")
print(f"是否为 Windows: {config.IS_WINDOWS}")
print(f"是否为 Linux: {config.IS_LINUX}")

# 检查路径配置
print("\n" + "="*50)
print("路径配置检查")
print("="*50)
print(f"项目根目录: {config.BASE_DIR}")
print(f"数据目录: {config.DATA_DIR}")
print(f"Profiles 目录: {config.PROFILES_DIR}")
print(f"代理扩展目录: {config.PROXY_EXT_DIR}")

# 检查目录是否存在
for dir_name, dir_path in [
    ("数据目录", config.DATA_DIR),
    ("Profiles 目录", config.PROFILES_DIR),
    ("代理扩展目录", config.PROXY_EXT_DIR)
]:
    if os.path.exists(dir_path):
        print(f"✅ {dir_name}: {dir_path} (存在)")
    else:
        print(f"⚠️  {dir_name}: {dir_path} (不存在，将自动创建)")

# 检查浏览器配置
print("\n" + "="*50)
print("浏览器配置检查")
print("="*50)
print(f"浏览器路径: {config.BROWSER_PATH or '使用系统默认'}")
print(f"无头模式: {config.BROWSER_HEADLESS}")
print(f"端口范围: {config.BROWSER_PORT_START} - {config.BROWSER_PORT_START + config.BROWSER_PORT_RANGE - 1}")

# 检查 Chrome/Chromium（仅Linux）
if config.IS_LINUX:
    print("\n检查 Chrome/Chromium 安装:")
    chrome_paths = [
        '/usr/bin/google-chrome',
        '/usr/bin/chromium-browser',
        '/usr/bin/chromium',
        '/snap/bin/chromium'
    ]
    found = False
    for path in chrome_paths:
        if os.path.exists(path):
            print(f"✅ 找到浏览器: {path}")
            found = True
            break
    if not found:
        print("⚠️  未找到 Chrome/Chromium，请确保已安装")
        print("   如果已安装但不在标准路径，请在 config.py 中设置 BROWSER_PATH")

# 检查 Telegram 配置
print("\n" + "="*50)
print("Telegram 配置检查")
print("="*50)
print(f"API ID: {config.TELEGRAM_API_ID}")
print(f"目标频道: {config.TELEGRAM_TARGET_CHANNEL}")
print(f"代理配置: {config.TELEGRAM_PROXY or '不使用代理'}")
print(f"Session 文件: {config.TELEGRAM_SESSION_FILE}")

# 检查其他配置
print("\n" + "="*50)
print("其他配置")
print("="*50)
print(f"过盾超时: {config.BYPASS_TIMEOUT} 秒")
print(f"最大重试次数: {config.MAX_RETRIES}")
print(f"请求延迟: {config.REQUEST_DELAY_MIN} - {config.REQUEST_DELAY_MAX} 秒")

print("\n" + "="*50)
print("✅ 配置检查完成")
print("="*50)

