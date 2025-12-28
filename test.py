import requests
from urllib.parse import quote

# 1. 这里填入你数据库里那个报错的完整地址
# 格式: http://user:pass@host:port
raw_proxy = "http://spgdc6kiiq:6q1woEkkut_SH5Qwv7@isp.decodo.com:10001"

# 2. 如果怀疑是密码特殊字符问题，可以尝试拆分手动拼装 (可选)
user = quote("spgdc6kiiq")
pwd = quote("6q1woEkkut_SH5Qwv7")
proxy_url = f"http://{user}:{pwd}@isp.decodo.com:10001"

proxies = {
    "http": raw_proxy,
    "https": raw_proxy
}

print(f"正在测试代理: {raw_proxy}")

try:
    # 访问一个简单的接口看是否通畅
    resp = requests.get(
        "https://httpbin.org/ip",
        proxies=proxies,
        timeout=10
    )
    print(f"状态码: {resp.status_code}")
    print(f"返回内容: {resp.text}")
except Exception as e:
    print(f"连接失败，具体错误如下:")
    print(e)