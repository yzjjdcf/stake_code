# Windows 命令速查表

## 🚀 快速启动

### 最简单的方式（推荐）

```powershell
# 双击运行或命令行执行
.\start_windows.bat
```

### PowerShell 方式

```powershell
powershell -ExecutionPolicy Bypass -File start_windows.ps1
```

## 📋 常用命令

### 虚拟环境

```powershell
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境 (PowerShell)
.\venv\Scripts\Activate.ps1

# 激活虚拟环境 (CMD)
venv\Scripts\activate.bat

# 如果 PowerShell 执行策略错误
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 安装依赖

```powershell
cd config
pip install -r requirements.txt
cd ..
```

### 数据库迁移

```powershell
cd config
python manage.py migrate
cd ..
```

### 启动服务（手动）

```powershell
# 启动 Django
cd config
python manage.py runserver 0.0.0.0:8000

# 启动 Listener (新终端)
cd core
python listener.py
```

### 停止服务

```powershell
# 方式 1: 使用停止脚本
powershell -ExecutionPolicy Bypass -File stop_windows.ps1

# 方式 2: 通过端口停止
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# 方式 3: 停止所有 Python 进程（谨慎）
Get-Process python | Stop-Process
```

### 查看日志

```powershell
# Django 日志
Get-Content db\logs\django.log -Wait -Tail 50

# Listener 日志
Get-Content db\logs\listener.log -Wait -Tail 50

# 过盾日志
Get-Content db\logs\bypass.log -Wait -Tail 50

# 所有日志
Get-Content db\logs\*.log -Wait -Tail 20
```

### 查看服务状态

```powershell
# 查看端口占用
netstat -ano | findstr :8000

# 查看 Python 进程
Get-Process python

# 查看进程详情
Get-Process python | Format-List *
```

### 数据库操作

```powershell
cd config

# 运行迁移
python manage.py migrate

# 创建迁移
python manage.py makemigrations

# 查看迁移状态
python manage.py showmigrations

# 创建超级用户
python manage.py createsuperuser

cd ..
```

### 清理缓存

```powershell
# 删除 __pycache__ 目录
Get-ChildItem -Path . -Include __pycache__ -Recurse -Force | Remove-Item -Force -Recurse

# 删除 .pyc 文件
Get-ChildItem -Path . -Include *.pyc -Recurse -Force | Remove-Item -Force
```

## 🔧 故障排查

### 检查虚拟环境

```powershell
# 检查虚拟环境是否存在
Test-Path venv\Scripts\Activate.ps1

# 检查 Python 版本
python --version

# 检查已安装的包
pip list
```

### 检查端口

```powershell
# 查看 8000 端口占用
netstat -ano | findstr :8000

# 查看所有端口占用
netstat -ano
```

### 检查文件路径

```powershell
# 检查关键文件是否存在
Test-Path config\config.py
Test-Path db\db.sqlite3
Test-Path db\logs
```

## 📝 一键启动命令（复制粘贴）

```powershell
# 完整启动流程
.\venv\Scripts\Activate.ps1
cd config
python manage.py migrate
cd ..
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd D:\project\stake_code\config; .\..\venv\Scripts\Activate.ps1; python manage.py runserver 0.0.0.0:8000"
Start-Sleep -Seconds 3
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd D:\project\stake_code\core; .\..\venv\Scripts\Activate.ps1; python listener.py"
```

## 🌐 访问地址

- **Django Admin**: http://localhost:8000/admin
- **API**: http://localhost:8000/api/（如果有）

## 📚 相关文件

- `start_windows.bat` - 批处理启动脚本
- `start_windows.ps1` - PowerShell 启动脚本
- `stop_windows.ps1` - 停止服务脚本
- `Windows运行指南.md` - 详细使用指南

