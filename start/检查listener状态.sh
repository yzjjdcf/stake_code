#!/bin/bash
# 检查 Listener 服务状态和日志

PROJECT_DIR="/root/stake_code"
LISTENER_LOG="$PROJECT_DIR/db/logs/listener.log"
LISTENER_PID="$PROJECT_DIR/pids/listener.pid"

echo "📊 Listener 服务状态检查"
echo ""

# 检查进程
if [ -f "$LISTENER_PID" ]; then
    PID=$(cat "$LISTENER_PID")
    if kill -0 "$PID" 2>/dev/null; then
        echo "✅ Listener 进程运行中 (PID: $PID)"
    else
        echo "❌ Listener 进程不存在 (PID 文件存在但进程已停止)"
    fi
else
    echo "⚠️  Listener PID 文件不存在"
fi

echo ""

# 检查进程（另一种方式）
# 注意：listener.py 已废弃，现在使用 listener_tdlib.py
echo "🔍 查找 listener.py 进程（已废弃，仅供参考）："
ps aux | grep "listener.py[^_]" | grep -v grep || echo "   未找到运行中的 listener.py 进程（正常，已废弃）"
echo ""
echo "🔍 查找 listener_tdlib.py 进程（当前使用的）："
ps aux | grep listener_tdlib.py | grep -v grep || echo "   未找到运行中的 listener_tdlib.py 进程"

echo ""

# 检查日志文件
echo "📋 日志文件状态："
if [ -f "$LISTENER_LOG" ]; then
    LOG_SIZE=$(du -h "$LISTENER_LOG" | cut -f1)
    LOG_LINES=$(wc -l < "$LISTENER_LOG")
    echo "   ✅ 日志文件存在: $LISTENER_LOG"
    echo "   📏 文件大小: $LOG_SIZE"
    echo "   📝 行数: $LOG_LINES"
    echo ""
    echo "📄 最后 20 行日志："
    echo "   ----------------------------------------"
    tail -n 20 "$LISTENER_LOG" | sed 's/^/   /'
    echo "   ----------------------------------------"
else
    echo "   ❌ 日志文件不存在: $LISTENER_LOG"
    echo "   💡 可能原因："
    echo "      - Listener 未启动"
    echo "      - 日志目录不存在"
    echo "      - 权限问题"
fi

echo ""

# 检查日志目录
if [ ! -d "$PROJECT_DIR/db/logs" ]; then
    echo "⚠️  日志目录不存在，创建中..."
    mkdir -p "$PROJECT_DIR/db/logs"
    echo "   ✅ 已创建: $PROJECT_DIR/db/logs"
fi

echo ""
echo "💡 启动 Listener："
echo "   bash $PROJECT_DIR/start/start_all.sh start"
echo ""
echo "💡 查看实时日志："
echo "   tail -f $LISTENER_LOG"

