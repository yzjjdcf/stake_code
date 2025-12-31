#!/bin/bash
# 启动所有服务脚本（Django + Listener）
# 使用方法: ./start_all.sh [start|stop|restart|status]

set -e

# 配置
PROJECT_DIR="/root/stake_code"
VENV_DIR="$PROJECT_DIR/venv"
PYTHON="$VENV_DIR/bin/python"
DJANGO_LOG="$PROJECT_DIR/db/logs/django.log"
LISTENER_LOG="$PROJECT_DIR/db/logs/listener.log"
PID_DIR="$PROJECT_DIR/pids"
DJANGO_PID="$PID_DIR/django.pid"
LISTENER_PID="$PID_DIR/listener.pid"

# 创建必要的目录
mkdir -p "$PROJECT_DIR/db/logs"
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

# 函数：启动 Django
start_django() {
    if [ -f "$DJANGO_PID" ] && kill -0 "$(cat "$DJANGO_PID")" 2>/dev/null; then
        echo "⚠️  Django 服务已在运行 (PID: $(cat "$DJANGO_PID"))"
        return 1
    fi
    
    echo "🚀 启动 Django 服务..."
    cd "$PROJECT_DIR/config" || exit 1
    nohup "$PYTHON" manage.py runserver 0.0.0.0:8000 > "$DJANGO_LOG" 2>&1 &
    DJANGO_PID_VALUE=$!
    cd "$PROJECT_DIR" || exit 1
    echo $DJANGO_PID_VALUE > "$DJANGO_PID"
    echo "   ✅ Django 已启动 (PID: $DJANGO_PID_VALUE)"
    echo "   📋 日志: $DJANGO_LOG"
    return 0
}

# 函数：启动 Listener
start_listener() {
    if [ -f "$LISTENER_PID" ] && kill -0 "$(cat "$LISTENER_PID")" 2>/dev/null; then
        echo "⚠️  Listener 服务已在运行 (PID: $(cat "$LISTENER_PID"))"
        return 1
    fi
    
    echo "🚀 启动 Telegram Listener 服务..."
    cd "$PROJECT_DIR/core" || exit 1
    nohup "$PYTHON" listener.py > "$LISTENER_LOG" 2>&1 &
    LISTENER_PID_VALUE=$!
    cd "$PROJECT_DIR" || exit 1
    echo $LISTENER_PID_VALUE > "$LISTENER_PID"
    echo "   ✅ Listener 已启动 (PID: $LISTENER_PID_VALUE)"
    echo "   📋 日志: $LISTENER_LOG"
    return 0
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
    
    # Listener 状态
    if [ -f "$LISTENER_PID" ] && kill -0 "$(cat "$LISTENER_PID")" 2>/dev/null; then
        LISTENER_PID_VALUE=$(cat "$LISTENER_PID")
        echo "✅ Listener: 运行中 (PID: $LISTENER_PID_VALUE)"
        echo "   📋 日志: $LISTENER_LOG"
    else
        echo "❌ Listener: 未运行"
    fi
    
    echo ""
    echo "📋 查看日志："
    echo "   Django:   tail -f $DJANGO_LOG"
    echo "   Listener: tail -f $LISTENER_LOG"
    echo "   Bypass:   tail -f $PROJECT_DIR/db/logs/bypass.log"
}

# 主逻辑
case "${1:-start}" in
    start)
        echo "🚀 启动所有服务..."
        echo ""
        start_django
        sleep 2
        start_listener
        sleep 1
        echo ""
        show_status
        ;;
    stop)
        echo "🛑 停止所有服务..."
        echo ""
        stop_listener
        stop_django
        ;;
    restart)
        echo "🔄 重启所有服务..."
        echo ""
        stop_listener
        stop_django
        sleep 2
        start_django
        sleep 2
        start_listener
        sleep 1
        echo ""
        show_status
        ;;
    status)
        show_status
        ;;
    *)
        echo "使用方法: $0 {start|stop|restart|status}"
        echo ""
        echo "命令说明："
        echo "  start   - 启动所有服务"
        echo "  stop    - 停止所有服务"
        echo "  restart - 重启所有服务"
        echo "  status  - 查看服务状态"
        exit 1
        ;;
esac

