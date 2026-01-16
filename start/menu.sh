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
    echo -e "${BLUE}║     服务管理菜单                       ║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${GREEN}════════════════════════════════════════${NC}"
    echo -e "${GREEN}  Stake 业务${NC}"
    echo -e "${GREEN}════════════════════════════════════════${NC}"
    echo -e "${GREEN}1)${NC} 启动所有服务（Django + Stake Listener + Winna Listener）"
    echo -e "${GREEN}2)${NC} 停止所有服务"
    echo -e "${GREEN}3)${NC} 重启所有服务"
    echo -e "${GREEN}4)${NC} 查看服务状态"
    echo ""
    echo -e "${GREEN}1a)${NC} 仅启动 Django"
    echo -e "${GREEN}1b)${NC} 仅启动 Stake Listener"
    echo -e "${GREEN}2a)${NC} 仅停止 Django"
    echo -e "${GREEN}2b)${NC} 仅停止 Stake Listener"
    echo ""
    echo -e "${YELLOW}5)${NC} 查看 Django 日志 (按 q 退出)"
    echo -e "${YELLOW}6)${NC} 查看 Stake Listener 日志 (按 q 退出)"
    echo -e "${YELLOW}7)${NC} 查看过盾日志 (按 q 退出)"
    echo ""
    echo -e "${GREEN}════════════════════════════════════════${NC}"
    echo -e "${GREEN}  Winna 业务（完全隔离）${NC}"
    echo -e "${GREEN}════════════════════════════════════════${NC}"
    echo -e "${GREEN}1w)${NC} 仅启动 Winna Listener"
    echo -e "${GREEN}2w)${NC} 仅停止 Winna Listener"
    echo -e "${YELLOW}6w)${NC} 查看 Winna Listener 日志 (按 q 退出)"
    echo ""
    echo -e "${BLUE}════════════════════════════════════════${NC}"
    echo -e "${BLUE}  其他功能${NC}"
    echo -e "${BLUE}════════════════════════════════════════${NC}"
    echo -e "${YELLOW}8)${NC} 同时查看所有日志 (按 q 退出)"
    echo -e "${BLUE}9)${NC} 运行数据库迁移"
    echo -e "${BLUE}10)${NC} 创建超级管理员"
    echo -e "${BLUE}11)${NC} 检查 Listener 状态"
    echo -e "${BLUE}12)${NC} 校准服务器时间"
    echo -e "${BLUE}13)${NC} 实时时间对比（每秒更新）"
    echo -e "${BLUE}14)${NC} 查看连接的客户端列表（Stake + Winna）"
    echo -e "${BLUE}15)${NC} 更新脚本文件到服务器（从 scripts/ 复制到 /var/www/stake_code/scripts/）"
    echo -e "${BLUE}16)${NC} 启动高额投注监听（chat_cn.py）"
    echo ""
    echo -e "${RED}0)${NC} 退出"
    echo ""
    echo -n "请选择 [0-16, 1a-2b, 1w-2w, 6w]: "
}

# 启动所有服务
start_services() {
    echo -e "${GREEN}🚀 启动所有服务...${NC}"
    # 捕获所有输出，只显示脚本的控制信息，过滤掉所有服务日志
    bash "$PROJECT_DIR/start/start_all.sh" start 2>&1 | grep -vE '^\[|^\[[0-9]+\]\[t|^tail:|CryptographyDeprecationWarning|listener_tdlib\.py:|^[[:space:]]*$' || true
    echo ""
    read -p "按回车键继续..."
}

# 仅启动 Django
start_django_only() {
    echo -e "${GREEN}🚀 启动 Django 服务...${NC}"
    # 捕获所有输出，只显示脚本的控制信息，过滤掉所有服务日志
    bash "$PROJECT_DIR/start/start_all.sh" start_django 2>&1 | grep -vE '^\[|^\[[0-9]+\]\[t|^tail:|CryptographyDeprecationWarning|listener_tdlib\.py:|^[[:space:]]*$' || true
    echo ""
    read -p "按回车键继续..."
}

# 仅启动 Stake Listener
start_listener_only() {
    echo -e "${GREEN}🚀 启动 Stake Listener 服务...${NC}"
    # 捕获所有输出，只显示脚本的控制信息，过滤掉所有服务日志
    bash "$PROJECT_DIR/start/start_all.sh" start_listener 2>&1 | grep -vE '^\[|^\[[0-9]+\]\[t|^tail:|CryptographyDeprecationWarning|listener_tdlib\.py:|^[[:space:]]*$' || true
    echo ""
    read -p "按回车键继续..."
}

# 仅启动 Winna Listener
start_winna_listener_only() {
    echo -e "${GREEN}🚀 启动 Winna Listener 服务...${NC}"
    # 捕获所有输出，只显示脚本的控制信息，过滤掉所有服务日志
    bash "$PROJECT_DIR/start/start_all.sh" start_winna_listener 2>&1 | grep -vE '^\[|^\[[0-9]+\]\[t|^tail:|CryptographyDeprecationWarning|listener_winna\.py:|^[[:space:]]*$' || true
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

# 仅停止 Django
stop_django_only() {
    echo -e "${RED}🛑 停止 Django 服务...${NC}"
    bash "$PROJECT_DIR/start/start_all.sh" stop_django
    echo ""
    read -p "按回车键继续..."
}

# 仅停止 Stake Listener
stop_listener_only() {
    echo -e "${RED}🛑 停止 Stake Listener 服务...${NC}"
    bash "$PROJECT_DIR/start/start_all.sh" stop_listener
    echo ""
    read -p "按回车键继续..."
}

# 仅停止 Winna Listener
stop_winna_listener_only() {
    echo -e "${RED}🛑 停止 Winna Listener 服务...${NC}"
    bash "$PROJECT_DIR/start/start_all.sh" stop_winna_listener
    echo ""
    read -p "按回车键继续..."
}

# 重启所有服务
restart_services() {
    echo -e "${YELLOW}🔄 重启所有服务...${NC}"
    # 捕获所有输出，只显示脚本的控制信息，过滤掉所有服务日志
    bash "$PROJECT_DIR/start/start_all.sh" restart 2>&1 | grep -vE '^\[|^\[[0-9]+\]\[t|^tail:|CryptographyDeprecationWarning|listener_tdlib\.py:|^[[:space:]]*$' || true
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
    echo -e "${YELLOW}📋 查看 Django 日志 (按 q 退出，不会中断服务)...${NC}"
    echo ""
    DJANGO_LOG="$PROJECT_DIR/db/logs/django/django.log"
    if [ -f "$DJANGO_LOG" ]; then
        tail -f "$DJANGO_LOG" &
        TAIL_PID=$!
        OLD_STTY=$(stty -g)
        stty -echo -icanon min 1 time 0
        while true; do
            key=$(dd bs=1 count=1 2>/dev/null)
            if [ "$key" = "q" ] || [ "$key" = "Q" ]; then
                break
            fi
        done
        stty "$OLD_STTY"
        kill $TAIL_PID 2>/dev/null
        wait $TAIL_PID 2>/dev/null
    else
        echo -e "${RED}⚠️  日志文件不存在: $DJANGO_LOG${NC}"
        read -p "按回车键继续..."
    fi
}

# 查看 Stake Listener 日志
view_listener_log() {
    echo -e "${YELLOW}📋 查看 Stake Listener 日志 (按 q 退出，不会中断服务)...${NC}"
    echo ""
    LISTENER_LOG="$PROJECT_DIR/db/logs/listener/listener_tdlib.log"
    if [ ! -f "$LISTENER_LOG" ]; then
        LISTENER_LOG="$PROJECT_DIR/db/logs/listener/listener_pyrogram.log"
    fi
    if [ ! -f "$LISTENER_LOG" ]; then
        LISTENER_LOG="$PROJECT_DIR/db/logs/listener/worker.log"
    fi
    if [ -f "$LISTENER_LOG" ]; then
        # 使用 tail -f 在后台运行，按 q 退出时只杀死 tail 进程，不会影响 listener
        tail -f "$LISTENER_LOG" &
        TAIL_PID=$!
        # 保存当前终端设置
        OLD_STTY=$(stty -g)
        stty -echo -icanon min 1 time 0
        # 等待用户按 q
        while true; do
            key=$(dd bs=1 count=1 2>/dev/null)
            if [ "$key" = "q" ] || [ "$key" = "Q" ]; then
                break
            fi
        done
        # 恢复终端设置
        stty "$OLD_STTY"
        # 只杀死 tail 进程，不会影响 listener
        kill $TAIL_PID 2>/dev/null
        wait $TAIL_PID 2>/dev/null
    else
        echo -e "${RED}⚠️  日志文件不存在: $LISTENER_LOG${NC}"
        read -p "按回车键继续..."
    fi
}

# 查看 Winna Listener 日志
view_winna_listener_log() {
    echo -e "${YELLOW}📋 查看 Winna Listener 日志 (按 q 退出，不会中断服务)...${NC}"
    echo ""
    WINNA_LISTENER_LOG="$PROJECT_DIR/db/logs/listener/listener_winna.log"
    if [ -f "$WINNA_LISTENER_LOG" ]; then
        # 使用 tail -f 在后台运行，按 q 退出时只杀死 tail 进程，不会影响 listener
        tail -f "$WINNA_LISTENER_LOG" &
        TAIL_PID=$!
        # 保存当前终端设置
        OLD_STTY=$(stty -g)
        stty -echo -icanon min 1 time 0
        # 等待用户按 q
        while true; do
            key=$(dd bs=1 count=1 2>/dev/null)
            if [ "$key" = "q" ] || [ "$key" = "Q" ]; then
                break
            fi
        done
        # 恢复终端设置
        stty "$OLD_STTY"
        # 只杀死 tail 进程，不会影响 listener
        kill $TAIL_PID 2>/dev/null
        wait $TAIL_PID 2>/dev/null
    else
        echo -e "${RED}⚠️  日志文件不存在: $WINNA_LISTENER_LOG${NC}"
        read -p "按回车键继续..."
    fi
}

# 查看过盾日志
view_bypass_log() {
    echo -e "${YELLOW}📋 查看过盾日志 (按 q 退出，不会中断服务)...${NC}"
    echo ""
    BYPASS_LOG="$PROJECT_DIR/db/logs/django/bypass.log"
    if [ -f "$BYPASS_LOG" ]; then
        tail -f "$BYPASS_LOG" &
        TAIL_PID=$!
        OLD_STTY=$(stty -g)
        stty -echo -icanon min 1 time 0
        while true; do
            key=$(dd bs=1 count=1 2>/dev/null)
            if [ "$key" = "q" ] || [ "$key" = "Q" ]; then
                break
            fi
        done
        stty "$OLD_STTY"
        kill $TAIL_PID 2>/dev/null
        wait $TAIL_PID 2>/dev/null
    else
        echo -e "${RED}⚠️  日志文件不存在: $BYPASS_LOG${NC}"
        read -p "按回车键继续..."
    fi
}

# 同时查看所有日志
view_all_logs() {
    echo -e "${YELLOW}📋 同时查看所有日志 (按 q 退出，不会中断服务)...${NC}"
    echo ""
    LISTENER_DIR="$PROJECT_DIR/db/logs/listener"
    DJANGO_DIR="$PROJECT_DIR/db/logs/django"
    if [ -d "$LISTENER_DIR" ] || [ -d "$DJANGO_DIR" ]; then
        tail -f "$LISTENER_DIR"/*.log "$DJANGO_DIR"/*.log 2>/dev/null &
        TAIL_PID=$!
        OLD_STTY=$(stty -g)
        stty -echo -icanon min 1 time 0
        while true; do
            key=$(dd bs=1 count=1 2>/dev/null)
            if [ "$key" = "q" ] || [ "$key" = "Q" ]; then
                break
            fi
        done
        stty "$OLD_STTY"
        kill $TAIL_PID 2>/dev/null
        wait $TAIL_PID 2>/dev/null
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

# 创建超级管理员
create_superuser() {
    echo -e "${BLUE}👤 创建超级管理员...${NC}"
    if [ -f "$PROJECT_DIR/start/create_superuser.sh" ]; then
        bash "$PROJECT_DIR/start/create_superuser.sh"
    else
        echo -e "${RED}⚠️  创建脚本不存在${NC}"
        echo -e "${YELLOW}提示：请手动运行: cd $PROJECT_DIR/core && python create_superuser.py${NC}"
    fi
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

# 查看连接的客户端列表
view_connected_clients() {
    echo -e "${BLUE}📋 查看连接的客户端列表...${NC}"
    echo ""
    VENV_ACTIVATE="$PROJECT_DIR/venv/bin/activate"
    if [ -f "$VENV_ACTIVATE" ]; then
        source "$VENV_ACTIVATE"
    fi
    python3 "$PROJECT_DIR/start/查询连接客户端.py"
    echo ""
    read -p "按回车键继续..."
}

# 启动高额投注监听
start_chat_cn() {
    echo -e "${BLUE}🎰 启动高额投注监听（chat_cn.py）...${NC}"
    echo ""
    
    CHAT_CN_SCRIPT="$PROJECT_DIR/start/chat_cn.py"
    
    if [ ! -f "$CHAT_CN_SCRIPT" ]; then
        echo -e "${RED}❌ 脚本不存在: $CHAT_CN_SCRIPT${NC}"
        echo ""
        read -p "按回车键继续..."
        return
    fi
    
    # 检查是否已经运行
    if pgrep -f "chat_cn.py" > /dev/null; then
        echo -e "${YELLOW}⚠️  chat_cn.py 已经在运行中${NC}"
        echo -e "${YELLOW}进程信息:${NC}"
        ps aux | grep "chat_cn.py" | grep -v grep
        echo ""
        read -p "按回车键继续..."
        return
    fi
    
    echo -e "${GREEN}正在启动...${NC}"
    echo -e "${YELLOW}提示：按 Ctrl+C 可以停止监听${NC}"
    echo ""
    
    # 运行脚本（前台运行，方便查看输出）
    cd "$PROJECT_DIR/start" || exit 1
    python3 chat_cn.py
    
    echo ""
    read -p "按回车键继续..."
}

# 更新脚本文件到服务器
update_scripts() {
    echo -e "${BLUE}📦 更新脚本文件到服务器...${NC}"
    echo ""
    
    SOURCE_DIR="$PROJECT_DIR/scripts"
    TARGET_DIR="/var/www/stake_code/scripts"
    
    # 检查源目录是否存在
    if [ ! -d "$SOURCE_DIR" ]; then
        echo -e "${RED}❌ 源目录不存在: $SOURCE_DIR${NC}"
        echo -e "${YELLOW}提示：请先创建 scripts 目录并放入脚本文件${NC}"
        echo ""
        read -p "按回车键继续..."
        return
    fi
    
    # 检查源目录是否为空
    if [ -z "$(ls -A $SOURCE_DIR 2>/dev/null)" ]; then
        echo -e "${YELLOW}⚠️  源目录为空: $SOURCE_DIR${NC}"
        echo -e "${YELLOW}提示：请先放入脚本文件${NC}"
        echo ""
        read -p "按回车键继续..."
        return
    fi
    
    # 显示源目录内容
    echo -e "${GREEN}源目录: $SOURCE_DIR${NC}"
    echo -e "${GREEN}文件列表:${NC}"
    ls -lh "$SOURCE_DIR" | tail -n +2 | awk '{print "  " $9 " (" $5 ")"}'
    echo ""
    
    # 创建目标目录（如果不存在）
    echo -e "${YELLOW}创建目标目录...${NC}"
    sudo mkdir -p "$TARGET_DIR"
    
    # 检测 Nginx 用户
    NGINX_USER=$(ps aux | grep -E "nginx.*master" | grep -v grep | awk '{print $1}' | head -1)
    if [ -z "$NGINX_USER" ]; then
        NGINX_USER="www-data"  # 默认 Nginx 用户
    fi
    echo -e "${GREEN}检测到 Nginx 用户: $NGINX_USER${NC}"
    echo ""
    
    # 复制所有文件
    echo -e "${YELLOW}复制文件...${NC}"
    sudo cp -r "$SOURCE_DIR"/* "$TARGET_DIR/" 2>&1
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ 文件复制成功${NC}"
    else
        echo -e "${RED}❌ 文件复制失败${NC}"
        echo ""
        read -p "按回车键继续..."
        return
    fi
    
    # 设置权限
    echo -e "${YELLOW}设置文件权限...${NC}"
    sudo chown -R $NGINX_USER:$NGINX_USER "$TARGET_DIR"
    sudo chmod 755 "$TARGET_DIR"
    sudo find "$TARGET_DIR" -type f -exec chmod 644 {} \;
    sudo find "$TARGET_DIR" -type d -exec chmod 755 {} \;
    echo -e "${GREEN}✅ 权限已设置${NC}"
    echo ""
    
    # 显示目标目录内容
    echo -e "${GREEN}目标目录: $TARGET_DIR${NC}"
    echo -e "${GREEN}已复制的文件:${NC}"
    ls -lh "$TARGET_DIR" | tail -n +2 | awk '{print "  " $9 " (" $5 ")"}'
    echo ""
    
    # 测试访问（如果可能）
    DOMAIN=$(grep "server_name" /etc/nginx/sites-available/websocket 2>/dev/null | head -1 | awk '{print $2}' | tr -d ';' || echo "")
    if [ -n "$DOMAIN" ] && command -v curl &> /dev/null; then
        echo -e "${YELLOW}测试脚本访问...${NC}"
        # 测试第一个 .js 文件
        FIRST_JS=$(find "$TARGET_DIR" -name "*.js" -type f | head -1)
        if [ -n "$FIRST_JS" ]; then
            JS_NAME=$(basename "$FIRST_JS")
            TEST_URL="https://$DOMAIN/scripts/$JS_NAME"
            HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$TEST_URL" 2>/dev/null || echo "000")
            if [ "$HTTP_CODE" = "200" ]; then
                echo -e "${GREEN}✅ 脚本可访问: $TEST_URL (HTTP $HTTP_CODE)${NC}"
            else
                echo -e "${YELLOW}⚠️  脚本访问测试失败: $TEST_URL (HTTP $HTTP_CODE)${NC}"
            fi
        fi
    fi
    
    echo ""
    echo -e "${GREEN}✅ 更新完成！${NC}"
    echo ""
    read -p "按回车键继续..."
}

# 主循环
while true; do
    show_menu
    read choice
    case $choice in
        1)
            start_services
            ;;
        1a)
            start_django_only
            ;;
        1b)
            start_listener_only
            ;;
        1w)
            start_winna_listener_only
            ;;
        2)
            stop_services
            ;;
        2a)
            stop_django_only
            ;;
        2b)
            stop_listener_only
            ;;
        2w)
            stop_winna_listener_only
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
        6w)
            view_winna_listener_log
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
            create_superuser
            ;;
        11)
            check_listener
            ;;
        12)
            sync_server_time
            ;;
        13)
            realtime_time_compare
            ;;
        14)
            view_connected_clients
            ;;
        15)
            update_scripts
            ;;
        16)
            start_chat_cn
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

