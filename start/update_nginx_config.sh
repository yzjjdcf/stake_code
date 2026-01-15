#!/bin/bash
# Nginx 配置更新脚本
# 用于将 nginx_websocket.conf 应用到 Nginx 服务器

PROJECT_DIR="/root/stake_code"
cd "$PROJECT_DIR" || exit 1

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Nginx 配置更新工具 ===${NC}\n"

# 检查是否以 root 运行
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}❌ 请使用 sudo 运行此脚本${NC}"
    exit 1
fi

# 配置文件路径
SOURCE_CONF="$PROJECT_DIR/start/nginx_websocket.conf"
TARGET_CONF="/etc/nginx/sites-available/websocket"
ENABLED_LINK="/etc/nginx/sites-enabled/websocket"

# 检查源文件是否存在
if [ ! -f "$SOURCE_CONF" ]; then
    echo -e "${RED}❌ 源配置文件不存在: $SOURCE_CONF${NC}"
    exit 1
fi

echo -e "${YELLOW}📋 配置信息：${NC}"
echo -e "  源文件: ${GREEN}$SOURCE_CONF${NC}"
echo -e "  目标文件: ${GREEN}$TARGET_CONF${NC}"
echo -e "  启用链接: ${GREEN}$ENABLED_LINK${NC}"
echo ""

# 1. 备份现有配置（如果存在）
if [ -f "$TARGET_CONF" ]; then
    BACKUP_FILE="${TARGET_CONF}.backup.$(date +%Y%m%d_%H%M%S)"
    echo -e "${YELLOW}📦 备份现有配置...${NC}"
    cp "$TARGET_CONF" "$BACKUP_FILE"
    echo -e "${GREEN}✅ 已备份到: $BACKUP_FILE${NC}\n"
fi

# 2. 复制配置文件
echo -e "${YELLOW}📝 复制配置文件...${NC}"
cp "$SOURCE_CONF" "$TARGET_CONF"
chmod 644 "$TARGET_CONF"
echo -e "${GREEN}✅ 配置文件已复制${NC}\n"

# 3. 创建软链接（如果不存在）
if [ ! -L "$ENABLED_LINK" ]; then
    echo -e "${YELLOW}🔗 创建启用链接...${NC}"
    if [ -f "$ENABLED_LINK" ]; then
        echo -e "${YELLOW}⚠️  发现已存在的文件（非软链接），是否删除？(y/n):${NC} "
        read -r REMOVE_FILE
        if [ "$REMOVE_FILE" == "y" ] || [ "$REMOVE_FILE" == "Y" ]; then
            rm -f "$ENABLED_LINK"
            ln -s "$TARGET_CONF" "$ENABLED_LINK"
            echo -e "${GREEN}✅ 软链接已创建${NC}\n"
        else
            echo -e "${YELLOW}⚠️  跳过创建软链接${NC}\n"
        fi
    else
        ln -s "$TARGET_CONF" "$ENABLED_LINK"
        echo -e "${GREEN}✅ 软链接已创建${NC}\n"
    fi
else
    echo -e "${GREEN}✅ 软链接已存在${NC}\n"
fi

# 4. 测试 Nginx 配置
echo -e "${YELLOW}🧪 测试 Nginx 配置...${NC}"
if nginx -t 2>&1 | grep -q "successful"; then
    echo -e "${GREEN}✅ Nginx 配置测试通过${NC}\n"
    
    # 5. 询问是否重载配置
    echo -e "${YELLOW}是否立即重载 Nginx 配置？(y/n):${NC} "
    read -r RELOAD_NGINX
    if [ "$RELOAD_NGINX" == "y" ] || [ "$RELOAD_NGINX" == "Y" ]; then
        echo -e "${YELLOW}🔄 重载 Nginx 配置...${NC}"
        if systemctl reload nginx; then
            echo -e "${GREEN}✅ Nginx 配置已重载${NC}\n"
        else
            echo -e "${RED}❌ Nginx 配置重载失败${NC}\n"
            exit 1
        fi
    else
        echo -e "${YELLOW}⚠️  请稍后手动重载: ${GREEN}sudo systemctl reload nginx${NC}\n"
    fi
else
    echo -e "${RED}❌ Nginx 配置测试失败${NC}"
    echo -e "${YELLOW}请检查配置文件: $TARGET_CONF${NC}\n"
    nginx -t
    exit 1
fi

# 6. 显示配置摘要
echo -e "${BLUE}════════════════════════════════════════${NC}"
echo -e "${BLUE}  配置更新完成${NC}"
echo -e "${BLUE}════════════════════════════════════════${NC}"
echo -e "配置文件: ${GREEN}$TARGET_CONF${NC}"
echo -e "启用链接: ${GREEN}$ENABLED_LINK${NC}"
echo ""
echo -e "${YELLOW}📝 配置的服务：${NC}"
echo -e "  - WebSocket (Stake): ${GREEN}wss://stakefav.xyz/${NC}"
echo -e "  - WebSocket (Winna): ${GREEN}wss://stakefav.xyz/winna${NC}"
echo -e "  - 脚本更新服务: ${GREEN}https://stakefav.xyz/scripts/${NC}"
echo ""

