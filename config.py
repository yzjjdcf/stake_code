"""
平台配置文件
通过 PLATFORM 变量来区分 Windows 和 Linux 环境
"""
import os
import platform

# 自动检测平台，也可以通过环境变量手动指定
PLATFORM = os.getenv('STAKE_PLATFORM', platform.system().lower())

# 平台配置
IS_WINDOWS = PLATFORM in ('windows', 'win32', 'win')
IS_LINUX = PLATFORM in ('linux', 'linux2')

# ==================== 路径配置 ====================
# 项目根目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 数据目录（代理扩展、浏览器配置等）
DATA_DIR = os.path.join(BASE_DIR, 'data')
PROFILES_DIR = os.path.join(DATA_DIR, 'profiles')
PROXY_EXT_DIR = os.path.join(DATA_DIR, 'proxy_ext')

# 确保目录存在
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(PROFILES_DIR, exist_ok=True)
os.makedirs(PROXY_EXT_DIR, exist_ok=True)

# ==================== Telegram 配置 ====================
TELEGRAM_API_ID = 29656021
TELEGRAM_API_HASH = 'bb23c410c63a820d7c4209e0606d4aea'
TELEGRAM_TARGET_CHANNEL = 'stake_cn_chat_room'

# Telegram 代理配置（根据平台不同）
if IS_WINDOWS:
    # Windows 配置
    TELEGRAM_PROXY = ('socks5', '127.0.0.1', 10808)
    TELEGRAM_SESSION_FILE = 'stake_listener_session'
else:
    # Linux 配置（如果没有本地代理，可以设置为 None）
    # TELEGRAM_PROXY = None  # 不使用代理
    TELEGRAM_PROXY = ('socks5', '127.0.0.1', 10808)  # 如果有代理服务器
    TELEGRAM_SESSION_FILE = 'stake_listener_session'

# ==================== 浏览器配置 ====================
# DrissionPage 浏览器配置
if IS_WINDOWS:
    # Windows: 使用默认浏览器路径
    BROWSER_PATH = None  # None 表示使用系统默认
    BROWSER_HEADLESS = False  # Windows 可以显示浏览器窗口
else:
    # Linux: 通常需要无头模式
    BROWSER_PATH = None  # 如果系统安装了 Chrome/Chromium，可以设置为 None
    # 如果 Chrome 不在 PATH 中，可以指定路径，例如：
    # BROWSER_PATH = '/usr/bin/google-chrome'  # 或 '/usr/bin/chromium-browser'
    BROWSER_HEADLESS = True  # Linux 服务器通常无显示器，使用无头模式

# 浏览器端口范围（每个账号使用独立端口）
BROWSER_PORT_START = 9000
BROWSER_PORT_RANGE = 1000  # 端口范围：9000-9999

# ==================== 其他配置 ====================
# 过盾超时时间（秒）
BYPASS_TIMEOUT = 300

# 请求重试次数
MAX_RETRIES = 3

# 请求错峰延迟（秒）
REQUEST_DELAY_MIN = 0.1
REQUEST_DELAY_MAX = 0.3

# 日志配置
LOG_LEVEL = 'INFO'  # DEBUG, INFO, WARNING, ERROR

