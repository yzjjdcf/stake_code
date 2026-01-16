#!/bin/bash

# 迁移脚本文件到 /var/www/stake_code/scripts/
# 解决 Nginx 权限问题

set -e

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== 迁移脚本文件到 /var/www/stake_code/scripts/ ===${NC}\n"

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OLD_SCRIPTS_DIR="$PROJECT_DIR/scripts"
NEW_SCRIPTS_DIR="/var/www/stake_code/scripts"

# 检测 Nginx 用户
NGINX_USER=$(ps aux | grep -E "nginx.*master" | grep -v grep | awk '{print $1}' | head -1)
if [ -z "$NGINX_USER" ]; then
    NGINX_USER="www-data"  # 默认 Nginx 用户
fi
echo -e "${YELLOW}检测到 Nginx 用户: $NGINX_USER${NC}\n"

# 1. 创建新目录
echo -e "${YELLOW}1. 创建新目录...${NC}"
sudo mkdir -p "$NEW_SCRIPTS_DIR"
sudo chown -R $NGINX_USER:$NGINX_USER "$NEW_SCRIPTS_DIR"
sudo chmod 755 "$NEW_SCRIPTS_DIR"
echo -e "${GREEN}   ✅ 目录已创建: $NEW_SCRIPTS_DIR${NC}\n"

# 2. 复制脚本文件
echo -e "${YELLOW}2. 复制脚本文件...${NC}"
if [ -d "$OLD_SCRIPTS_DIR" ] && [ -n "$(ls -A $OLD_SCRIPTS_DIR/*.js 2>/dev/null)" ]; then
    echo -e "   从旧目录复制: $OLD_SCRIPTS_DIR"
    sudo cp "$OLD_SCRIPTS_DIR"/*.js "$NEW_SCRIPTS_DIR/" 2>/dev/null || true
else
    echo -e "   从项目根目录复制源文件"
    if [ -f "$PROJECT_DIR/jiaoben.js" ]; then
        sudo cp "$PROJECT_DIR/jiaoben.js" "$NEW_SCRIPTS_DIR/stake.user.js"
        echo -e "${GREEN}   ✅ Stake 脚本已复制${NC}"
    fi
    if [ -f "$PROJECT_DIR/winna_script.js" ]; then
        sudo cp "$PROJECT_DIR/winna_script.js" "$NEW_SCRIPTS_DIR/winna.user.js"
        echo -e "${GREEN}   ✅ Winna 脚本已复制${NC}"
    fi
fi

# 设置文件权限
sudo chown -R $NGINX_USER:$NGINX_USER "$NEW_SCRIPTS_DIR"
sudo chmod 644 "$NEW_SCRIPTS_DIR"/*.js 2>/dev/null || true
echo -e "${GREEN}   ✅ 文件权限已设置${NC}\n"

# 3. 验证文件
echo -e "${YELLOW}3. 验证文件...${NC}"
if [ -f "$NEW_SCRIPTS_DIR/stake.user.js" ]; then
    echo -e "${GREEN}   ✅ Stake 脚本存在${NC}"
    echo -e "   文件大小: $(du -h "$NEW_SCRIPTS_DIR/stake.user.js" | cut -f1)"
else
    echo -e "${RED}   ❌ Stake 脚本不存在${NC}"
fi

if [ -f "$NEW_SCRIPTS_DIR/winna.user.js" ]; then
    echo -e "${GREEN}   ✅ Winna 脚本存在${NC}"
    echo -e "   文件大小: $(du -h "$NEW_SCRIPTS_DIR/winna.user.js" | cut -f1)"
else
    echo -e "${RED}   ❌ Winna 脚本不存在${NC}"
fi
echo ""

# 4. 更新 Nginx 配置
echo -e "${YELLOW}4. 更新 Nginx 配置...${NC}"
NGINX_CONF="/etc/nginx/sites-available/websocket"
if [ -f "$NGINX_CONF" ]; then
    # 备份原配置
    sudo cp "$NGINX_CONF" "$NGINX_CONF.bak.$(date +%Y%m%d_%H%M%S)"
    
    # 更新 alias 路径
    sudo sed -i "s|alias /root/stake_code/scripts/|alias $NEW_SCRIPTS_DIR/|g" "$NGINX_CONF"
    sudo sed -i "s|alias /root/stake_code/scripts|alias $NEW_SCRIPTS_DIR/|g" "$NGINX_CONF"
    
    echo -e "${GREEN}   ✅ 配置已更新${NC}"
    
    # 验证配置
    if grep -q "alias $NEW_SCRIPTS_DIR/" "$NGINX_CONF"; then
        echo -e "${GREEN}   ✅ alias 路径已更新为: $NEW_SCRIPTS_DIR/${NC}"
    else
        echo -e "${YELLOW}   ⚠️  请手动检查配置${NC}"
    fi
else
    echo -e "${YELLOW}   ⚠️  Nginx 配置文件不存在: $NGINX_CONF${NC}"
    echo -e "   请手动更新配置中的 alias 路径为: $NEW_SCRIPTS_DIR/"
fi
echo ""

# 5. 测试并重载 Nginx
echo -e "${YELLOW}5. 测试并重载 Nginx...${NC}"
if sudo nginx -t 2>&1 | grep -q "successful"; then
    echo -e "${GREEN}   ✅ Nginx 配置测试通过${NC}"
    if sudo systemctl reload nginx; then
        echo -e "${GREEN}   ✅ Nginx 已重载${NC}"
    else
        echo -e "${RED}   ❌ Nginx 重载失败${NC}"
        exit 1
    fi
else
    echo -e "${RED}   ❌ Nginx 配置测试失败${NC}"
    sudo nginx -t
    exit 1
fi
echo ""

# 6. 测试访问
echo -e "${YELLOW}6. 测试访问...${NC}"
DOMAIN=$(grep "server_name" "$NGINX_CONF" 2>/dev/null | head -1 | awk '{print $2}' | tr -d ';' || echo "stakefav.xyz")

if command -v curl &> /dev/null; then
    echo -e "   测试 Stake 脚本..."
    STAKE_CODE=$(curl -s -o /dev/null -w "%{http_code}" "https://$DOMAIN/scripts/stake.user.js" 2>/dev/null || echo "000")
    if [ "$STAKE_CODE" = "200" ]; then
        echo -e "${GREEN}   ✅ Stake 脚本可访问 (HTTP $STAKE_CODE)${NC}"
    else
        echo -e "${RED}   ❌ Stake 脚本访问失败 (HTTP $STAKE_CODE)${NC}"
    fi
    
    echo -e "   测试 Winna 脚本..."
    WINNA_CODE=$(curl -s -o /dev/null -w "%{http_code}" "https://$DOMAIN/scripts/winna.user.js" 2>/dev/null || echo "000")
    if [ "$WINNA_CODE" = "200" ]; then
        echo -e "${GREEN}   ✅ Winna 脚本可访问 (HTTP $WINNA_CODE)${NC}"
    else
        echo -e "${RED}   ❌ Winna 脚本访问失败 (HTTP $WINNA_CODE)${NC}"
    fi
else
    echo -e "${YELLOW}   ⚠️  curl 未安装，跳过测试${NC}"
fi
echo ""

echo -e "${GREEN}=== 迁移完成 ===${NC}\n"
echo -e "${YELLOW}📝 重要提示：${NC}"
echo -e "1. 脚本文件已迁移到: $NEW_SCRIPTS_DIR"
echo -e "2. 以后更新脚本时，请复制到新目录："
echo -e "   ${GREEN}sudo cp $PROJECT_DIR/jiaoben.js $NEW_SCRIPTS_DIR/stake.user.js${NC}"
echo -e "   ${GREEN}sudo cp $PROJECT_DIR/winna_script.js $NEW_SCRIPTS_DIR/winna.user.js${NC}"
echo -e "3. 旧目录 $OLD_SCRIPTS_DIR 可以保留作为备份，或删除"
echo ""

