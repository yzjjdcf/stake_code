#!/bin/bash
# 交互式菜单脚本 - 通过数字选择操作

PROJECT_DIR="/root/stake_code"
cd "$PROJECT_DIR" || exit 1

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 显示菜单
show_menu() {
    clear
    echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║     Stake 服务管理菜单                 ║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${GREEN}1)${NC} 启动所有服务"
    echo -e "${GREEN}2)${NC} 停止所有服务"
    echo -e "${GREEN}3)${NC} 重启所有服务"
    echo -e "${GREEN}4)${NC} 查看服务状态"
    echo ""
    echo -e "${YELLOW}5)${NC} 查看 Django 日志"
    echo -e "${YELLOW}6)${NC} 查看 Listener 日志"
    echo -e "${YELLOW}7)${NC} 查看过盾日志"
    echo -e "${YELLOW}8)${NC} 同时查看所有日志"
    echo ""
    echo -e "${BLUE}9)${NC} 运行数据库迁移"
    echo -e "${BLUE}10)${NC} 检查 Listener 状态"
    echo -e "${BLUE}11)${NC} 校准服务器时间"
    echo -e "${BLUE}12)${NC} 实时时间对比（每秒更新）"
    echo ""
    echo -e "${RED}0)${NC} 退出"
    echo ""
    echo -n "请选择 [0-12]: "
}

# 启动所有服务
start_services() {
    echo -e "${GREEN}🚀 启动所有服务...${NC}"
    bash "$PROJECT_DIR/start/start_all.sh" start
    echo ""
    read -p "按回车键继续..."
}

# 停止所有服务
stop_services() {
    echo -e "${RED}🛑 停止所有服务...${NC}"
    bash "$PROJECT_DIR/start/start_all.sh" stop
    echo ""
    read -p "按回车键继续..."
}

# 重启所有服务
restart_services() {
    echo -e "${YELLOW}🔄 重启所有服务...${NC}"
    bash "$PROJECT_DIR/start/start_all.sh" restart
    echo ""
    read -p "按回车键继续..."
}

# 查看服务状态
show_status() {
    echo -e "${BLUE}📊 服务状态：${NC}"
    bash "$PROJECT_DIR/start/start_all.sh" status
    echo ""
    read -p "按回车键继续..."
}

# 查看 Django 日志
view_django_log() {
    echo -e "${YELLOW}📋 查看 Django 日志 (按 Ctrl+Q 退出)...${NC}"
    echo ""
    DJANGO_LOG="$PROJECT_DIR/db/logs/django/django.log"
    if [ -f "$DJANGO_LOG" ]; then
        (trap 'exit' QUIT; tail -f "$DJANGO_LOG")
    else
        echo -e "${RED}⚠️  日志文件不存在: $DJANGO_LOG${NC}"
        read -p "按回车键继续..."
    fi
}

# 查看 Listener 日志
view_listener_log() {
    echo -e "${YELLOW}📋 查看 Listener 日志 (按 Ctrl+Q 退出)...${NC}"
    echo ""
    LISTENER_LOG="$PROJECT_DIR/db/logs/listener/listener_pyrogram.log"
    if [ ! -f "$LISTENER_LOG" ]; then
        LISTENER_LOG="$PROJECT_DIR/db/logs/listener/worker.log"
    fi
    if [ -f "$LISTENER_LOG" ]; then
        (trap 'exit' QUIT; tail -f "$LISTENER_LOG")
    else
        echo -e "${RED}⚠️  日志文件不存在: $LISTENER_LOG${NC}"
        read -p "按回车键继续..."
    fi
}

# 查看过盾日志
view_bypass_log() {
    echo -e "${YELLOW}📋 查看过盾日志 (按 Ctrl+Q 退出)...${NC}"
    echo ""
    BYPASS_LOG="$PROJECT_DIR/db/logs/django/bypass.log"
    if [ -f "$BYPASS_LOG" ]; then
        (trap 'exit' QUIT; tail -f "$BYPASS_LOG")
    else
        echo -e "${RED}⚠️  日志文件不存在: $BYPASS_LOG${NC}"
        read -p "按回车键继续..."
    fi
}

# 同时查看所有日志
view_all_logs() {
    echo -e "${YELLOW}📋 同时查看所有日志 (按 Ctrl+Q 退出)...${NC}"
    echo ""
    LISTENER_DIR="$PROJECT_DIR/db/logs/listener"
    DJANGO_DIR="$PROJECT_DIR/db/logs/django"
    if [ -d "$LISTENER_DIR" ] || [ -d "$DJANGO_DIR" ]; then
        (trap 'exit' QUIT; tail -f "$LISTENER_DIR"/*.log "$DJANGO_DIR"/*.log 2>/dev/null)
    else
        echo -e "${RED}⚠️  日志目录不存在${NC}"
        read -p "按回车键继续..."
    fi
}

# 运行数据库迁移
run_migration() {
    echo -e "${BLUE}🗄️  运行数据库迁移...${NC}"
    VENV_ACTIVATE="$PROJECT_DIR/venv/bin/activate"
    if [ -f "$VENV_ACTIVATE" ]; then
        source "$VENV_ACTIVATE"
    fi
    cd "$PROJECT_DIR/config" || exit 1
    python manage.py migrate
    cd "$PROJECT_DIR" || exit 1
    echo ""
    read -p "按回车键继续..."
}

# 检查 Listener 状态
check_listener() {
    echo -e "${BLUE}🔍 检查 Listener 状态...${NC}"
    if [ -f "$PROJECT_DIR/start/检查listener状态.sh" ]; then
        bash "$PROJECT_DIR/start/检查listener状态.sh"
    else
        echo -e "${RED}⚠️  检查脚本不存在${NC}"
    fi
    echo ""
    read -p "按回车键继续..."
}

# 校准服务器时间
sync_server_time() {
    echo -e "${BLUE}🕐 校准服务器时间...${NC}"
    if [ -f "$PROJECT_DIR/start/Linux时间同步工具.sh" ]; then
        bash "$PROJECT_DIR/start/Linux时间同步工具.sh"
    else
        echo -e "${RED}⚠️  时间同步脚本不存在${NC}"
        echo -e "${YELLOW}提示：请确保 start/Linux时间同步工具.sh 文件存在${NC}"
    fi
    echo ""
    read -p "按回车键继续..."
}

# 实时时间对比
realtime_time_compare() {
    echo -e "${BLUE}🕐 启动实时时间对比工具...${NC}"
    if [ -f "$PROJECT_DIR/start/实时时间对比.sh" ]; then
        bash "$PROJECT_DIR/start/实时时间对比.sh"
    else
        echo -e "${RED}⚠️  实时时间对比脚本不存在${NC}"
        read -p "按回车键继续..."
    fi
}

# 主循环
while true; do
    show_menu
    read choice
    case $choice in
        1)
            start_services
            ;;
        2)
            stop_services
            ;;
        3)
            restart_services
            ;;
        4)
            show_status
            ;;
        5)
            view_django_log
            ;;
        6)
            view_listener_log
            ;;
        7)
            view_bypass_log
            ;;
        8)
            view_all_logs
            ;;
        9)
            run_migration
            ;;
        10)
            check_listener
            ;;
        11)
            sync_server_time
            ;;
        12)
            realtime_time_compare
            ;;
        0)
            echo -e "${GREEN}👋 再见！${NC}"
            exit 0
            ;;
        *)
            echo -e "${RED}❌ 无效选择，请重新输入${NC}"
            sleep 1
            ;;
    esac
done

