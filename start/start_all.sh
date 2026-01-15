#!/bin/bash
# 启动所有服务脚本（Django + Listener）
# 使用方法: ./start_all.sh [start|stop|restart|status]

set -e

# 配置
PROJECT_DIR="/root/stake_code"
VENV_DIR="$PROJECT_DIR/venv"
PYTHON="$VENV_DIR/bin/python"
DJANGO_LOG="$PROJECT_DIR/db/logs/django/django.log"
LISTENER_LOG="$PROJECT_DIR/db/logs/listener/listener_tdlib.log"
WINNA_LISTENER_LOG="$PROJECT_DIR/db/logs/listener/listener_winna.log"
PID_DIR="$PROJECT_DIR/pids"
DJANGO_PID="$PID_DIR/django.pid"
LISTENER_PID="$PID_DIR/listener.pid"
WINNA_LISTENER_PID="$PID_DIR/winna_listener.pid"

# 创建必要的目录
mkdir -p "$PROJECT_DIR/db/logs/listener"
mkdir -p "$PROJECT_DIR/db/logs/django"
mkdir -p "$PID_DIR"

# 进入项目目录
cd "$PROJECT_DIR" || exit 1

# 激活虚拟环境
if [ -f "$VENV_DIR/bin/activate" ]; then
    source "$VENV_DIR/bin/activate"
else
    echo "❌ 虚拟环境不存在: $VENV_DIR"
    exit 1
fi

# 设置环境变量
export STAKE_PLATFORM=linux

# 加载 SSL 证书配置（如果存在）
SSL_ENV_FILE="$PROJECT_DIR/.env.ssl"
if [ -f "$SSL_ENV_FILE" ]; then
    echo "📝 加载 SSL 证书配置..."
    source "$SSL_ENV_FILE"
    if [ -n "$WEBSOCKET_SSL_CERT" ] && [ -n "$WEBSOCKET_SSL_KEY" ]; then
        echo "   ✅ SSL 证书已配置: $WEBSOCKET_SSL_CERT"
    fi
fi

# 函数：启动 Django
start_django() {
    if [ -f "$DJANGO_PID" ] && kill -0 "$(cat "$DJANGO_PID")" 2>/dev/null; then
        echo "⚠️  Django 服务已在运行 (PID: $(cat "$DJANGO_PID"))"
        return 1
    fi
    
    echo "🚀 启动 Django 服务..."
    
    # 检查 manage.py 是否存在
    if [ ! -f "$PROJECT_DIR/config/manage.py" ]; then
        echo "   ❌ 错误: manage.py 不存在: $PROJECT_DIR/config/manage.py"
        return 1
    fi
    
    # 检查 Python 是否可用
    if [ ! -f "$PYTHON" ]; then
        echo "   ❌ 错误: Python 不存在: $PYTHON"
        return 1
    fi
    
    cd "$PROJECT_DIR/config" || exit 1
    # 使用 setsid 创建新会话，完全分离进程，避免输出显示在终端
    setsid "$PYTHON" manage.py runserver 0.0.0.0:8000 >> "$DJANGO_LOG" 2>&1 < /dev/null &
    DJANGO_PID_VALUE=$!
    cd "$PROJECT_DIR" || exit 1
    
    # 等待一下，检查进程是否真的启动了
    sleep 3
    if kill -0 "$DJANGO_PID_VALUE" 2>/dev/null; then
        echo $DJANGO_PID_VALUE > "$DJANGO_PID"
        echo "   ✅ Django 已启动 (PID: $DJANGO_PID_VALUE)"
        echo "   📋 日志: $DJANGO_LOG"
        return 0
    else
        echo "   ❌ Django 启动失败，进程已退出"
        echo ""
        echo "   📋 错误日志（最后 30 行）："
        echo "   ----------------------------------------"
        if [ -f "$DJANGO_LOG" ]; then
            tail -n 30 "$DJANGO_LOG" | sed 's/^/   /'
        else
            echo "   ⚠️  日志文件不存在"
        fi
        echo "   ----------------------------------------"
        echo ""
        echo "   💡 常见问题排查："
        echo "      1. 检查端口是否被占用: lsof -i:8000"
        echo "      2. 检查数据库文件: ls -la $PROJECT_DIR/db/db.sqlite3"
        echo "      3. 检查配置文件: ls -la $PROJECT_DIR/config/config.py"
        echo "      4. 检查虚拟环境: $PYTHON --version"
        echo "      5. 手动测试: cd $PROJECT_DIR/config && $PYTHON manage.py runserver 0.0.0.0:8000"
        rm -f "$DJANGO_PID"
        return 1
    fi
}

# 函数：启动 Listener
start_listener() {
    if [ -f "$LISTENER_PID" ] && kill -0 "$(cat "$LISTENER_PID")" 2>/dev/null; then
        echo "⚠️  Listener 服务已在运行 (PID: $(cat "$LISTENER_PID"))"
        return 1
    fi
    
    echo "🚀 启动 Telegram Listener 服务..."
    
    # 检查 listener_tdlib.py 是否存在
    if [ ! -f "$PROJECT_DIR/core/listener_tdlib.py" ]; then
        echo "   ❌ 错误: listener_tdlib.py 不存在: $PROJECT_DIR/core/listener_tdlib.py"
        return 1
    fi
    
    # 检查 Python 是否可用
    if [ ! -f "$PYTHON" ]; then
        echo "   ❌ 错误: Python 不存在: $PYTHON"
        return 1
    fi
    
    cd "$PROJECT_DIR/core" || exit 1
    # 使用 setsid 创建新会话，完全分离进程，避免输出显示在终端
    # 使用 unbuffered 模式，并完全重定向所有输出（包括 TDLib 的 C++ 日志）
    # 将 stderr 和 stdout 都重定向到日志文件，并丢弃所有输出到终端
    # 注意：使用 &> 同时重定向 stdout 和 stderr，避免影响 SSH 连接
    setsid stdbuf -oL -eL "$PYTHON" -u listener_tdlib.py &>> "$LISTENER_LOG" < /dev/null &
    LISTENER_PID_VALUE=$!
    cd "$PROJECT_DIR" || exit 1
    
    # 等待一下，检查进程是否真的启动了
    sleep 3
    if kill -0 "$LISTENER_PID_VALUE" 2>/dev/null; then
        echo $LISTENER_PID_VALUE > "$LISTENER_PID"
        echo "   ✅ Listener 已启动 (PID: $LISTENER_PID_VALUE)"
        echo "   📋 日志: $LISTENER_LOG"
        return 0
    else
        echo "   ❌ Listener 启动失败，进程已退出"
        echo ""
        echo "   📋 错误日志（最后 30 行）："
        echo "   ----------------------------------------"
        if [ -f "$LISTENER_LOG" ]; then
            tail -n 30 "$LISTENER_LOG" | sed 's/^/   /'
        else
            echo "   ⚠️  日志文件不存在"
        fi
        echo "   ----------------------------------------"
        echo ""
        echo "   💡 常见问题排查："
        echo "      1. 检查配置文件: ls -la $PROJECT_DIR/config/config.py"
        echo "      2. 检查 Telegram 配置是否正确"
        echo "      3. 检查虚拟环境: $PYTHON --version"
        echo "      4. 手动测试: cd $PROJECT_DIR/core && $PYTHON listener_tdlib.py"
        rm -f "$LISTENER_PID"
        return 1
    fi
}

# 函数：停止 Django
stop_django() {
    if [ ! -f "$DJANGO_PID" ]; then
        echo "⚠️  Django 服务未运行"
        return 1
    fi
    
    PID=$(cat "$DJANGO_PID")
    if kill -0 "$PID" 2>/dev/null; then
        echo "🛑 停止 Django 服务 (PID: $PID)..."
        kill "$PID"
        sleep 2
        if kill -0 "$PID" 2>/dev/null; then
            kill -9 "$PID"
        fi
        rm -f "$DJANGO_PID"
        echo "   ✅ Django 已停止"
    else
        echo "⚠️  Django 进程不存在，清理 PID 文件"
        rm -f "$DJANGO_PID"
    fi
    return 0
}

# 函数：停止 Listener
stop_listener() {
    if [ ! -f "$LISTENER_PID" ]; then
        echo "⚠️  Listener 服务未运行"
        return 1
    fi
    
    PID=$(cat "$LISTENER_PID")
    if kill -0 "$PID" 2>/dev/null; then
        echo "🛑 停止 Listener 服务 (PID: $PID)..."
        kill "$PID"
        sleep 2
        if kill -0 "$PID" 2>/dev/null; then
            kill -9 "$PID"
        fi
        rm -f "$LISTENER_PID"
        echo "   ✅ Listener 已停止"
    else
        echo "⚠️  Listener 进程不存在，清理 PID 文件"
        rm -f "$LISTENER_PID"
    fi
    return 0
}

# 函数：启动 Winna Listener
start_winna_listener() {
    if [ -f "$WINNA_LISTENER_PID" ] && kill -0 "$(cat "$WINNA_LISTENER_PID")" 2>/dev/null; then
        echo "⚠️  Winna Listener 服务已在运行 (PID: $(cat "$WINNA_LISTENER_PID"))"
        return 1
    fi
    
    echo "🚀 启动 Winna Listener 服务..."
    
    # 检查 listener_winna.py 是否存在
    if [ ! -f "$PROJECT_DIR/core/listener_winna.py" ]; then
        echo "   ❌ 错误: listener_winna.py 不存在: $PROJECT_DIR/core/listener_winna.py"
        return 1
    fi
    
    # 检查 Python 是否可用
    if [ ! -f "$PYTHON" ]; then
        echo "   ❌ 错误: Python 不存在: $PYTHON"
        return 1
    fi
    
    cd "$PROJECT_DIR/core" || exit 1
    # 使用 setsid 创建新会话，完全分离进程，避免输出显示在终端
    setsid stdbuf -oL -eL "$PYTHON" -u listener_winna.py &>> "$WINNA_LISTENER_LOG" < /dev/null &
    WINNA_LISTENER_PID_VALUE=$!
    cd "$PROJECT_DIR" || exit 1
    
    # 等待一下，检查进程是否真的启动了
    sleep 3
    if kill -0 "$WINNA_LISTENER_PID_VALUE" 2>/dev/null; then
        echo $WINNA_LISTENER_PID_VALUE > "$WINNA_LISTENER_PID"
        echo "   ✅ Winna Listener 已启动 (PID: $WINNA_LISTENER_PID_VALUE)"
        echo "   📋 日志: $WINNA_LISTENER_LOG"
        return 0
    else
        echo "   ❌ Winna Listener 启动失败，进程已退出"
        echo ""
        echo "   📋 错误日志（最后 30 行）："
        echo "   ----------------------------------------"
        if [ -f "$WINNA_LISTENER_LOG" ]; then
            tail -n 30 "$WINNA_LISTENER_LOG" | sed 's/^/   /'
        else
            echo "   ⚠️  日志文件不存在"
        fi
        echo "   ----------------------------------------"
        rm -f "$WINNA_LISTENER_PID"
        return 1
    fi
}

# 函数：停止 Winna Listener
stop_winna_listener() {
    if [ ! -f "$WINNA_LISTENER_PID" ]; then
        echo "⚠️  Winna Listener 服务未运行"
        return 1
    fi
    
    PID=$(cat "$WINNA_LISTENER_PID")
    if kill -0 "$PID" 2>/dev/null; then
        echo "🛑 停止 Winna Listener 服务 (PID: $PID)..."
        kill "$PID"
        sleep 2
        if kill -0 "$PID" 2>/dev/null; then
            kill -9 "$PID"
        fi
        rm -f "$WINNA_LISTENER_PID"
        echo "   ✅ Winna Listener 已停止"
    else
        echo "⚠️  Winna Listener 进程不存在，清理 PID 文件"
        rm -f "$WINNA_LISTENER_PID"
    fi
    return 0
}

# 函数：查看状态
show_status() {
    echo "📊 服务状态："
    echo ""
    
    # Django 状态
    if [ -f "$DJANGO_PID" ] && kill -0 "$(cat "$DJANGO_PID")" 2>/dev/null; then
        DJANGO_PID_VALUE=$(cat "$DJANGO_PID")
        echo "✅ Django: 运行中 (PID: $DJANGO_PID_VALUE)"
        echo "   📋 日志: $DJANGO_LOG"
    else
        echo "❌ Django: 未运行"
    fi
    
    echo ""
    
    # Stake Listener 状态
    if [ -f "$LISTENER_PID" ] && kill -0 "$(cat "$LISTENER_PID")" 2>/dev/null; then
        LISTENER_PID_VALUE=$(cat "$LISTENER_PID")
        echo "✅ Stake Listener: 运行中 (PID: $LISTENER_PID_VALUE)"
        echo "   📋 日志: $LISTENER_LOG"
    else
        echo "❌ Stake Listener: 未运行"
    fi
    
    echo ""
    
    # Winna Listener 状态
    if [ -f "$WINNA_LISTENER_PID" ] && kill -0 "$(cat "$WINNA_LISTENER_PID")" 2>/dev/null; then
        WINNA_LISTENER_PID_VALUE=$(cat "$WINNA_LISTENER_PID")
        echo "✅ Winna Listener: 运行中 (PID: $WINNA_LISTENER_PID_VALUE)"
        echo "   📋 日志: $WINNA_LISTENER_LOG"
    else
        echo "❌ Winna Listener: 未运行"
    fi
    
    echo ""
    echo "📋 查看日志："
    echo "   Django:        tail -f $DJANGO_LOG"
    echo "   Stake Listener: tail -f $LISTENER_LOG"
    echo "   Winna Listener: tail -f $WINNA_LISTENER_LOG"
    echo "   Bypass:        tail -f $PROJECT_DIR/db/logs/django/bypass.log"
}

# 主逻辑
case "${1:-start}" in
    start)
        echo "🚀 启动所有服务..."
        echo ""
        start_django
        sleep 2
        start_listener
        sleep 2
        start_winna_listener
        sleep 1
        echo ""
        show_status
        ;;
    start_django)
        start_django
        ;;
    start_listener)
        start_listener
        ;;
    start_winna_listener)
        start_winna_listener
        ;;
    stop)
        echo "🛑 停止所有服务..."
        echo ""
        stop_winna_listener
        stop_listener
        stop_django
        ;;
    stop_django)
        stop_django
        ;;
    stop_listener)
        stop_listener
        ;;
    stop_winna_listener)
        stop_winna_listener
        ;;
    restart)
        echo "🔄 重启所有服务..."
        echo ""
        # 停止服务（如果未运行，只显示警告，不阻止后续启动）
        stop_winna_listener || true
        stop_listener || true
        stop_django || true
        sleep 2
        start_django
        sleep 2
        start_listener
        sleep 2
        start_winna_listener
        sleep 1
        echo ""
        show_status
        ;;
    status)
        show_status
        ;;
    *)
        echo "使用方法: $0 {start|stop|restart|status|start_django|start_listener|start_winna_listener|stop_django|stop_listener|stop_winna_listener}"
        echo ""
        echo "命令说明："
        echo "  start                - 启动所有服务（Django + Stake Listener + Winna Listener）"
        echo "  start_django         - 仅启动 Django"
        echo "  start_listener       - 仅启动 Stake Listener"
        echo "  start_winna_listener - 仅启动 Winna Listener"
        echo "  stop                 - 停止所有服务"
        echo "  stop_django          - 仅停止 Django"
        echo "  stop_listener        - 仅停止 Stake Listener"
        echo "  stop_winna_listener  - 仅停止 Winna Listener"
        echo "  restart              - 重启所有服务"
        echo "  status               - 查看服务状态"
        exit 1
        ;;
esac

