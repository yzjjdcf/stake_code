"""
代码解析器模块
包含所有频道代码解析函数
"""
import re


def parse_code_high_rollers(text):
    """解析 HighRollersStake 频道的代码"""
    if not text:
        return None
    text_normalized = text.replace('\n', ' ').replace('\r', ' ')
    patterns = [
        r'- Code:\s*([a-z0-9]+)',
        r'Code:\s*([a-z0-9]+)',
        r'-Code:\s*([a-z0-9]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text_normalized, re.IGNORECASE)
        if match:
            code = match.group(1).strip().lower()
            if re.match(r'^[a-z0-9]+$', code) and len(code) >= 10:
                return code
    return None


def parse_code_rains_team(text):
    """解析 RainsTEAM 频道的代码"""
    if not text:
        return None
    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        if not line or ' ' in line:
            continue
        if re.search(r'[!?.。！？]\s*$', line):
            continue
        if re.match(r'^(Number|Amount|Wager|Requirement|Total|Code|Value|Claims|Drop|Incoming|Normal|Alert|Bonus|Settings|Offers|Redeem|Click|Telegram|Channel|Safe|VIP|RTP|Duel|Gives)', line, re.IGNORECASE):
            continue
        common_words = ['drop', 'alert', 'bonus', 'value', 'total', 'limit', 'requirement', 'wagered', 'days', 'settings', 'offers', 'redeem', 'click', 'telegram', 'ads', 'channel', 'potential', 'scams', 'affiliated', 'safe', 'vip', 'rtp', 'duel', 'gives', 'normal', 'incoming', 'number', 'claims', 'amount']
        line_lower = line.lower()
        # 只过滤整行完全匹配常见单词的情况，避免误过滤包含这些单词的代码
        # 例如 "doredeemit" 包含 "redeem" 但不应该被过滤，只有整行是 "redeem" 才过滤
        if line_lower in common_words:
            continue
        if re.match(r'^[a-zA-Z0-9]{1,25}$', line):
            if re.match(r'^\d{1,2}$', line):
                continue
            if line_lower in ['the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'her', 'was', 'one', 'our', 'out', 'day', 'get', 'has', 'him', 'his', 'how', 'its', 'may', 'new', 'now', 'old', 'see', 'two', 'way', 'who']:
                continue
            return line
    return None


def parse_code_daily_code(text, message=None, has_video=False):
    """
    解析 Daily Code 频道的代码（同步版本，用于纯文字）
    支持两种情况：
    1. 有视频+文字：使用 video_processor.parse_code_daily_code_async（异步版本）
    2. 纯文字：从文本中解析
    """
    # 纯文字消息的解析
    if not text:
        return None
    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
        match = re.search(r'[Cc]ode[：:]\s*([a-z0-9]+)', line, re.IGNORECASE)
        if match:
            code = match.group(1).strip()
            if code.startswith('@'):
                continue
            if re.match(r'^[a-z0-9]+$', code) and len(code) >= 10:
                return code.lower()
    return None


def parse_code_code_format(text):
    """解析 Code: stakecode 或 code:stakecode 格式的代码"""
    if not text:
        return None
    text_normalized = text.replace('\n', ' ').replace('\r', ' ')
    # 匹配 Code: stakecode 或 code:stakecode 格式（不区分大小写，冒号前后可能有空格）
    patterns = [
        r'[Cc]ode\s*:\s*([a-zA-Z0-9]+)',  # Code: stakecode 或 code: stakecode
        r'[Cc]ode:\s*([a-zA-Z0-9]+)',     # Code:stakecode 或 code:stakecode
    ]
    for pattern in patterns:
        match = re.search(pattern, text_normalized, re.IGNORECASE)
        if match:
            code = match.group(1).strip()
            # 验证代码格式（只包含字母和数字，不限制长度，保留原始大小写）
            if re.match(r'^[a-zA-Z0-9]+$', code):
                return code
    return None


def parse_code_user_submitted(text):
    """解析 CodeStats.gg 频道的 USER SUBMITTED STAKE CODE 格式"""
    if not text:
        return None
    
    # 首先检查消息是否包含 "USER SUBMITTED STAKE CODE"（不区分大小写）
    if 'USER SUBMITTED STAKE CODE' not in text.upper():
        return None
    
    # 查找 "Code: " 后面的代码（支持多种格式）
    patterns = [
        r'[Cc]ode\s*:\s*([a-zA-Z0-9]+)',  # Code: staketr2r6z9f
        r'[Cc]ode:\s*([a-zA-Z0-9]+)',     # Code:staketr2r6z9f
        r'-\s*[Cc]ode:\s*([a-zA-Z0-9]+)', # - Code: staketr2r6z9f
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            code = match.group(1).strip()
            # 验证代码格式（只包含字母和数字）
            if re.match(r'^[a-zA-Z0-9]+$', code):
                return code.lower()
    
    return None


def parse_code_default(text):
    """默认解析器"""
    if text:
        return text[:20].strip()
    return None


# 解析器映射字典
CODE_PARSERS = {
    'high_rollers_parser': parse_code_high_rollers,
    'rains_team_parser': parse_code_rains_team,
    'daily_code_parser': parse_code_daily_code,
    'code_format_parser': parse_code_code_format,
    'user_submitted_parser': parse_code_user_submitted,
    'default_parser': parse_code_default,
}

