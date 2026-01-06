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

# 数据目录（代理扩展、浏览器配置等）- 现在在 db/ 目录下
DB_DIR = os.path.join(BASE_DIR, 'db')
DATA_DIR = os.path.join(DB_DIR, 'data')
PROFILES_DIR = os.path.join(DATA_DIR, 'profiles')
PROXY_EXT_DIR = os.path.join(DATA_DIR, 'proxy_ext')

# 确保目录存在
os.makedirs(DB_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(PROFILES_DIR, exist_ok=True)
os.makedirs(PROXY_EXT_DIR, exist_ok=True)

# ==================== Telegram 配置 ====================
TELEGRAM_API_ID = 29656021
TELEGRAM_API_HASH = 'bb23c410c63a820d7c4209e0606d4aea'

# 多频道配置（支持多个频道，每个频道有不同的解析规则）
# 格式：{频道ID或用户名: 解析器名称}
# 注意：可以使用频道用户名（如 'stake_cn_chat_room'）或频道ID（如 '-1003315955015'）
# TELEGRAM_CHANNELS = {
#     'HighRollersStake': 'high_rollers_parser',  # 频道1：HighRollersStake
#     'RainsTEAM': 'rains_team_parser',  # 频道2：RainsTEAM（复杂消息格式，无空格代码）
#     'stakeimgantengofficial': 'rains_team_parser',  # 频道3：Stake.com - Challenge Info & Bonus Drop（使用 rains_team_parser）
#     # 'Stakelivechallenges': 'rains_team_parser',  # 频道4：Daily Code 频道（使用 daily_code_parser）
#     # 'StakecomDailyDrops': 'stakecom_daily_drops_parser',  # 频道5：Stake.com - Daily Drops（支持视频和文本）
#     'stake_cn_chat_room': 'rains_team_parser',  # 频道6：测试频道（使用 stakecom_daily_drops_parser 进行测试）
#     # '-1003315955015': 'stakecom_daily_drops_parser',  # 频道6的ID（stake中文避风港），确保能匹配到
# }

# 兼容旧配置（如果设置了 TELEGRAM_TARGET_CHANNEL，会自动添加到 TELEGRAM_CHANNELS）
# TELEGRAM_TARGET_CHANNEL = 'stake_cn_chat_room'  # 保留用于兼容

# Telegram 代理配置（根据平台不同）
# 会话文件路径（在 db/ 目录下）
TELEGRAM_SESSION_FILE = os.path.join(DB_DIR, 'stake_listener_session.session')

if IS_WINDOWS:
    # ==================== Windows 代理配置 ====================
    # Telethon 需要使用字典格式的代理配置
    
    # 方式 1: SOCKS5 代理（无用户名密码）
    TELEGRAM_PROXY = {
        'proxy_type': 'socks5',
        'addr': '127.0.0.1',
        'port': 10808,
        'rdns': True
    }
    
    # 方式 2: SOCKS5 代理（带用户名密码）
    # TELEGRAM_PROXY = {
    #     'proxy_type': 'socks5',
    #     'addr': '127.0.0.1',
    #     'port': 10808,
    #     'username': 'your_username',
    #     'password': 'your_password',
    #     'rdns': True
    # }
    
    # 方式 3: HTTP 代理（无用户名密码）
    # TELEGRAM_PROXY = {
    #     'proxy_type': 'http',
    #     'addr': '127.0.0.1',
    #     'port': 8080,
    #     'rdns': True
    # }
    
    # 方式 4: HTTP 代理（带用户名密码）
    # TELEGRAM_PROXY = {
    #     'proxy_type': 'http',
    #     'addr': '127.0.0.1',
    #     'port': 8080,
    #     'username': 'your_username',
    #     'password': 'your_password',
    #     'rdns': True
    # }
    
    # 方式 5: 不使用代理（如果有 VPN 或可以直接访问）
    # TELEGRAM_PROXY = None
    
    # 常见代理软件默认端口：
    # - Clash: 7890 (HTTP), 7891 (SOCKS5)
    # - V2Ray: 10808 (SOCKS5)
    # - Shadowsocks: 1080 (SOCKS5)
    # - 请根据你的实际代理端口修改
else:
    # Linux 配置（通常不需要代理，可以直接访问）
    TELEGRAM_PROXY = None  # Linux 服务器通常可以直接访问 Telegram

# ==================== 浏览器配置 ====================
# DrissionPage 浏览器配置
if IS_WINDOWS:
    # Windows: 使用默认浏览器路径
    BROWSER_PATH = None  # None 表示使用系统默认
    BROWSER_HEADLESS = False  # Windows 可以显示浏览器窗口
else:
    # Linux: 通常需要无头模式
    # ==================== 浏览器选择 ====================
    # 可选值: 'auto', 'chromium', 'google-chrome', 'chromium-browser', 'google-chrome-stable'
    # 或者直接指定路径，例如: '/usr/bin/chromium'
    BROWSER_TYPE = 'google-chrome'  # 'auto' 表示自动检测，按优先级选择
    
    # 浏览器检测优先级（从高到低）
    BROWSER_PRIORITY = [
        'chromium',              # 推荐：chromium（不带 -browser 后缀）
        'google-chrome',         # Google Chrome
        'google-chrome-stable',  # Google Chrome Stable
        'chromium-browser',      # chromium-browser（可能有问题）
    ]
    
    # 自动检测浏览器路径
    import shutil
    _browser_path = None
    
    if BROWSER_TYPE == 'auto':
        # 按优先级自动检测
        for browser_name in BROWSER_PRIORITY:
            _browser_path = shutil.which(browser_name)
            if _browser_path:
                break
    elif BROWSER_TYPE.startswith('/'):
        # 直接指定路径
        _browser_path = BROWSER_TYPE if os.path.exists(BROWSER_TYPE) else None
    else:
        # 指定浏览器名称
        _browser_path = shutil.which(BROWSER_TYPE)
    
    # 如果自动检测失败，可以手动指定路径
    # BROWSER_PATH = '/usr/bin/chromium'
    # BROWSER_PATH = '/usr/bin/google-chrome'
    BROWSER_PATH = _browser_path  # 自动检测的路径，如果为 None 则需要手动配置
    
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

# ==================== OpenAI 配置 ====================
# 第三方 ChatGPT API 配置（用于识别视频中的代码）
# API URL（完整的请求地址）
OPENAI_API_BASE_URL = 'https://api.gpt.ge/v1/chat/completions'
# API Key（用于 ChatGPT 识别视频中的代码）
# 如果不需要视频识别功能，可以留空或注释掉
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', 'sk-HPmHTarniTbZStbf5bF0Ec061fC748459e208e4fF93fAd39')  # 优先从环境变量读取，如果没有则使用默认值
# 使用的模型（必须是支持图片分析的模型）
OPENAI_MODEL = 'gpt-4o'  # 或使用其他支持图片分析的模型

# ==================== OCR API 配置 ====================
# OCR API 服务配置（formData 方式，用于识别视频中的代码）
# API URL（基础地址，会自动拼接 /task/pic/ocr）
OCR_API_URL = os.getenv('OCR_API_URL', 'https://api.gpt.ge/task/pic/ocr')  # 例如: 'https://api.example.com'
# API Token（用于 Authorization header）
OCR_API_TOKEN = os.getenv('OCR_API_TOKEN', '')  # Bearer Token

# ==================== Turnstile 配置 ====================
# Cloudflare Turnstile 配置（用于领取代码时的验证）
# Site Key（需要从实际页面获取，可以通过浏览器开发者工具查看）
# 在 stake.com 的页面上，找到 Turnstile widget 的 site-key
TURNSTILE_SITE_KEY = os.getenv('TURNSTILE_SITE_KEY', '0x4AAAAAAAGD4gMGOTFnvupz')  # 优先从环境变量读取，如果没有则使用空字符串（需要手动配置）
# Site URL（领取代码时的页面 URL）
TURNSTILE_SITE_URL = 'https://stake.com/'  # 默认值，可以根据需要修改