# Stake 自动化系统 - Linux 部署指南

## 平台配置说明

项目已支持 Windows 和 Linux 双平台，通过 `stake/config.py` 配置文件自动识别平台。

### 自动识别平台

系统会自动检测运行平台：
- **Windows**: 自动识别为 `windows`
- **Linux**: 自动识别为 `linux`

### 手动指定平台

如果需要手动指定平台，可以设置环境变量：

```bash
# Linux
export STAKE_PLATFORM=linux

# Windows (PowerShell)
$env:STAKE_PLATFORM="windows"
```

## Linux 环境准备

### 1. 安装 Python 依赖

```bash
# 创建虚拟环境（推荐）
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 安装 Chrome/Chromium（必需）

Linux 服务器需要安装 Chrome 或 Chromium 浏览器用于过盾：

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y chromium-browser

# 或者安装 Google Chrome
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo dpkg -i google-chrome-stable_current_amd64.deb
sudo apt-get install -f

# CentOS/RHEL
sudo yum install -y chromium
```

### 3. 安装系统依赖

```bash
# Ubuntu/Debian
sudo apt-get install -y \
    python3-dev \
    python3-pip \
    build-essential \
    libssl-dev \
    libffi-dev

# CentOS/RHEL
sudo yum install -y \
    python3-devel \
    gcc \
    openssl-devel \
    libffi-devel
```

## 配置文件说明

### `stake/config.py` 主要配置项

#### 平台相关配置

```python
# Linux 浏览器配置
BROWSER_HEADLESS = True  # Linux 服务器通常需要无头模式
BROWSER_PATH = None  # 如果 Chrome 不在 PATH，可指定路径，例如：
# BROWSER_PATH = '/usr/bin/google-chrome'
```

#### Telegram 代理配置

如果 Linux 服务器需要代理访问 Telegram：

```python
# Linux 配置
TELEGRAM_PROXY = ('socks5', '127.0.0.1', 10808)  # 如果有代理服务器
# 或者不使用代理
# TELEGRAM_PROXY = None
```

## 启动服务

### 方式一：使用启动脚本

```bash
# 给脚本添加执行权限
chmod +x start_django.sh
chmod +x start_listener.sh

# 启动 Django 服务（后台运行）
nohup ./start_django.sh > django.log 2>&1 &

# 启动 Telegram 监听器（后台运行）
nohup ./start_listener.sh > listener.log 2>&1 &
```

### 方式二：直接运行

```bash
cd stake

# 启动 Django
python manage.py runserver 0.0.0.0:8000

# 启动监听器（新终端）
python listener.py
```

### 方式三：使用 systemd（推荐生产环境）

创建服务文件 `/etc/systemd/system/stake-django.service`:

```ini
[Unit]
Description=Stake Django Service
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/stake_code/stake
ExecStart=/path/to/venv/bin/python manage.py runserver 0.0.0.0:8000
Restart=always

[Install]
WantedBy=multi-user.target
```

创建服务文件 `/etc/systemd/system/stake-listener.service`:

```ini
[Unit]
Description=Stake Telegram Listener
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/stake_code/stake
ExecStart=/path/to/venv/bin/python listener.py
Restart=always

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable stake-django
sudo systemctl enable stake-listener
sudo systemctl start stake-django
sudo systemctl start stake-listener
```

## PyCharm 配置

### 1. 配置 Python 解释器

1. 打开 PyCharm
2. File → Settings → Project → Python Interpreter
3. 选择虚拟环境的 Python 解释器（`venv/bin/python`）

### 2. 配置运行配置

#### Django 服务配置

1. Run → Edit Configurations
2. 点击 `+` → 选择 `Django Server`
3. 配置如下：
   - **Name**: `Django Server`
   - **Host**: `0.0.0.0`
   - **Port**: `8000`
   - **Working directory**: `stake`（项目根目录下的 stake 文件夹）
   - **Environment variables**: 
     ```
     DJANGO_SETTINGS_MODULE=stake.settings
     STAKE_PLATFORM=linux
     ```

#### Telegram 监听器配置

1. Run → Edit Configurations
2. 点击 `+` → 选择 `Python`
3. 配置如下：
   - **Name**: `Telegram Listener`
   - **Script path**: `stake/listener.py`
   - **Working directory**: `stake`
   - **Environment variables**:
     ```
     DJANGO_SETTINGS_MODULE=stake.settings
     STAKE_PLATFORM=linux
     ```

### 3. 配置路径映射（如果使用远程开发）

如果使用 PyCharm 远程开发功能：

1. File → Settings → Build, Execution, Deployment → Deployment
2. 配置服务器连接
3. 设置路径映射：
   - Local path: `D:\project\stake_code`
   - Deployment path: `/path/to/stake_code`

## 常见问题

### 1. 浏览器启动失败

**问题**: `DrissionPage` 无法找到 Chrome

**解决**:
- 确保已安装 Chrome/Chromium
- 在 `config.py` 中指定浏览器路径：
  ```python
  BROWSER_PATH = '/usr/bin/google-chrome'  # 或 '/usr/bin/chromium-browser'
  ```

### 2. 权限错误

**问题**: 无法创建目录或文件

**解决**:
```bash
# 确保有写入权限
chmod -R 755 stake/data
```

### 3. 代理连接失败

**问题**: Telegram 无法连接

**解决**:
- 检查代理配置是否正确
- 如果不需要代理，设置 `TELEGRAM_PROXY = None`

### 4. 数据库锁定

**问题**: SQLite 数据库锁定错误

**解决**:
- 检查是否有多个进程同时访问数据库
- 确保使用正确的数据库路径

## 目录结构

```
stake_code/
├── stake/
│   ├── config.py          # 平台配置文件
│   ├── listener.py        # Telegram 监听器
│   ├── worker.py          # 工作逻辑
│   ├── manage.py          # Django 管理脚本
│   ├── serverbot/         # Django 应用
│   └── stake/             # Django 项目配置
├── data/                   # 运行时数据（自动创建）
│   ├── profiles/          # 浏览器配置
│   └── proxy_ext/         # 代理扩展
├── requirements.txt        # Python 依赖
├── start_django.sh         # Django 启动脚本
└── start_listener.sh      # 监听器启动脚本
```

## 验证部署

1. **检查 Django 服务**:
   ```bash
   curl http://localhost:8000/admin/
   ```

2. **检查监听器日志**:
   ```bash
   tail -f listener.log
   ```

3. **测试过盾功能**:
   - 在 Django Admin 中创建一个账号
   - 点击"强制更新 CF"按钮
   - 查看日志确认浏览器启动成功

