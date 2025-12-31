# Linux 命令速查表

## 🚀 快速启动

### 最简单的方式（推荐）

```bash
# 使用交互式菜单
bash start/menu.sh
```

### 一键启动所有服务

```bash
# 启动 Django 和 Listener
bash start/start_all.sh start

# 停止所有服务
bash start/start_all.sh stop

# 重启所有服务
bash start/start_all.sh restart

# 查看服务状态
bash start/start_all.sh status
```

## 📋 常用命令

### 虚拟环境

```bash
# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate

# 退出虚拟环境
deactivate
```

### 安装依赖

```bash
# 安装 Python 依赖
cd config
pip install -r requirements.txt
cd ..

# 安装系统依赖（Xvfb - 虚拟显示服务器，用于无头模式运行浏览器）
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y xvfb

# CentOS/RHEL
sudo yum install -y xorg-x11-server-Xvfb

# 验证安装
Xvfb -help
```

### 启动服务（手动）

```bash
# 启动 Django（前台运行）
cd config
python manage.py runserver 0.0.0.0:8000

# 启动 Listener（前台运行，新终端）
cd core
python listener.py
```

### 后台运行服务

```bash
# 使用 nohup 后台运行 Django
cd config
nohup python manage.py runserver 0.0.0.0:8000 > ../db/logs/django.log 2>&1 &

# 使用 nohup 后台运行 Listener
cd core
nohup python listener.py > ../db/logs/listener.log 2>&1 &
```

### 停止服务

```bash
# 方式 1: 使用停止脚本
bash start/start_all.sh stop

# 方式 2: 通过端口停止
lsof -ti:8000 | xargs kill -9

# 方式 3: 查找并停止进程
ps aux | grep "manage.py runserver" | grep -v grep | awk '{print $2}' | xargs kill
ps aux | grep "listener.py" | grep -v grep | awk '{print $2}' | xargs kill

# 方式 4: 停止所有 Python 进程（谨慎）
pkill -f "manage.py runserver"
pkill -f "listener.py"
```

### 查看日志

```bash
# Django 日志（实时）
tail -f db/logs/django.log

# Listener 日志（实时）
tail -f db/logs/listener.log

# 过盾日志（实时）
tail -f db/logs/bypass.log

# 查看最后 50 行
tail -n 50 db/logs/django.log
tail -n 50 db/logs/listener.log
tail -n 50 db/logs/bypass.log

# 查看所有日志（最后 20 行）
tail -n 20 db/logs/*.log
```

### 使用 screen 查看日志（推荐）

```bash
# 创建 screen 会话查看 Django 日志
screen -S django_log
tail -f db/logs/django.log
# 按 Ctrl+A 然后按 D 退出（不关闭会话）

# 创建 screen 会话查看 Listener 日志
screen -S listener_log
tail -f db/logs/listener.log
# 按 Ctrl+A 然后按 D 退出

# 重新连接会话
screen -r django_log
screen -r listener_log

# 查看所有 screen 会话
screen -ls
```

### 查看服务状态

```bash
# 查看端口占用
lsof -i:8000
netstat -tulpn | grep 8000

# 查看 Python 进程
ps aux | grep python

# 查看特定进程
ps aux | grep "manage.py runserver"
ps aux | grep "listener.py"

# 检查 Listener 状态
bash start/检查listener状态.sh
```

## 🔧 故障排查

### 检查虚拟环境

```bash
# 检查虚拟环境是否存在
test -f venv/bin/activate && echo "存在" || echo "不存在"

# 检查 Python 版本
python3 --version

# 检查已安装的包
pip list
```

### 检查端口

```bash
# 查看 8000 端口占用
lsof -i:8000
netstat -tulpn | grep 8000

# 查看所有端口占用
netstat -tulpn
```

### 检查文件路径

```bash
# 检查关键文件是否存在
test -f config/config.py && echo "存在" || echo "不存在"
test -d db/logs && echo "存在" || echo "不存在"

# 检查目录结构
ls -la config/
ls -la core/
ls -la db/
```

### 检查服务是否运行

```bash
# 检查 Django 是否运行
curl http://localhost:8000/admin

# 检查进程是否在运行
pgrep -f "manage.py runserver"
pgrep -f "listener.py"
```

## 🛠️ 系统服务管理（systemd）

### 安装系统服务

```bash
# 复制服务文件到 systemd 目录
sudo cp start/stake-django.service /etc/systemd/system/
sudo cp start/stake-listener.service /etc/systemd/system/

# 重新加载 systemd
sudo systemctl daemon-reload

# 启用服务（开机自启）
sudo systemctl enable stake-django.service
sudo systemctl enable stake-listener.service
```

### 管理服务

```bash
# 启动服务
sudo systemctl start stake-django
sudo systemctl start stake-listener

# 停止服务
sudo systemctl stop stake-django
sudo systemctl stop stake-listener

# 重启服务
sudo systemctl restart stake-django
sudo systemctl restart stake-listener

# 查看服务状态
sudo systemctl status stake-django
sudo systemctl status stake-listener

# 查看服务日志
sudo journalctl -u stake-django -f
sudo journalctl -u stake-listener -f
```

## 📝 一键启动命令（复制粘贴）

```bash
# 完整启动流程（后台运行）
source venv/bin/activate
cd config
nohup python manage.py runserver 0.0.0.0:8000 > ../db/logs/django.log 2>&1 &
cd ../core
nohup python listener.py > ../db/logs/listener.log 2>&1 &
cd ..
echo "✅ 服务已启动"
echo "📊 查看日志: tail -f db/logs/django.log"
echo "📊 查看日志: tail -f db/logs/listener.log"
```

## 🌐 访问地址

- **Django Admin**: http://localhost:8000/admin
- **服务器 IP**: http://YOUR_SERVER_IP:8000/admin

## 📚 相关文件

- `start/menu.sh` - 交互式菜单脚本
- `start/start_all.sh` - 服务管理脚本
- `start/stake-django.service` - Django systemd 服务文件
- `start/stake-listener.service` - Listener systemd 服务文件
- `start/检查listener状态.sh` - Listener 状态检查脚本

## 💡 常用技巧

### 使用 Xvfb 运行浏览器（无头模式）

```bash
# 启动 Xvfb（显示编号 :99，分辨率 1920x1080x24）
Xvfb :99 -screen 0 1920x1080x24 &

# 设置 DISPLAY 环境变量
export DISPLAY=:99

# 验证 Xvfb 是否运行
ps aux | grep Xvfb

# 停止 Xvfb
pkill Xvfb
```

### 快速查看日志最后几行

```bash
# 查看最后 10 行
tail -n 10 db/logs/django.log

# 查看最后 100 行并实时更新
tail -n 100 -f db/logs/django.log
```

### 查找日志中的错误

```bash
# 查找错误信息
grep -i error db/logs/django.log
grep -i error db/logs/listener.log

# 查找特定关键词
grep "code" db/logs/listener.log
```

### 清理日志文件

```bash
# 清空日志文件（保留文件）
> db/logs/django.log
> db/logs/listener.log
> db/logs/bypass.log
```

