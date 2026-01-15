# 油猴脚本自动更新说明

## 📋 目录结构

```
/root/stake_code/
├── jiaoben.js              # Stake 脚本源文件
├── winna_script.js         # Winna 脚本源文件
└── scripts/                 # 脚本发布目录（由 Nginx 提供）
    ├── stake.user.js        # Stake 脚本（用于自动更新）
    └── winna.user.js         # Winna 脚本（用于自动更新）
```

## 🚀 使用方法

### 1. 首次设置（在 Linux 服务器上执行）

```bash
cd /root/stake_code

# 创建脚本目录
mkdir -p scripts

# 复制脚本到发布目录
cp jiaoben.js scripts/stake.user.js
cp winna_script.js scripts/winna.user.js

# 设置权限
chmod +x start/update_script_version.sh
```

### 2. 更新脚本版本

```bash
# 显示当前版本
bash start/update_script_version.sh show

# 同步脚本到发布目录（不更新版本）
bash start/update_script_version.sh sync

# 更新所有脚本版本并同步
bash start/update_script_version.sh update 1.0.1

# 只更新 Stake 脚本版本
bash start/update_script_version.sh stake 1.0.2

# 只更新 Winna 脚本版本
bash start/update_script_version.sh winna 1.0.2
```

### 3. 配置 Nginx

确保 Nginx 配置已更新并重载：

```bash
# 测试配置
sudo nginx -t

# 重载配置
sudo systemctl reload nginx
```

## 📡 访问地址

脚本更新 URL（由 Tampermonkey 自动检查）：

- **Stake 脚本**: `https://stakefav.xyz/scripts/stake.user.js`
- **Winna 脚本**: `https://stakefav.xyz/scripts/winna.user.js`

## 🔄 自动更新流程

1. **用户安装脚本**：从源文件安装到 Tampermonkey
2. **Tampermonkey 检查更新**：定期访问 `@updateURL`
3. **版本对比**：如果服务器上的版本号更高，自动下载更新
4. **自动安装**：下载新版本并替换旧版本

## ⚙️ 版本号格式

使用语义化版本号：`主版本号.次版本号.修订号`

例如：
- `1.0.0` - 初始版本
- `1.0.1` - 修复 bug
- `1.1.0` - 新功能
- `2.0.0` - 重大更新

## 📝 注意事项

1. **更新版本后必须同步**：使用 `sync` 或 `update` 命令将脚本复制到 `scripts/` 目录
2. **版本号必须递增**：新版本号必须大于旧版本号，否则 Tampermonkey 不会更新
3. **Nginx 配置**：确保 `/scripts/` 路径在 Nginx 配置中正确设置
4. **HTTPS 必需**：Tampermonkey 要求更新 URL 使用 HTTPS

## 🔍 测试更新

1. 修改脚本中的版本号（例如：1.0.0 → 1.0.1）
2. 运行同步命令：`bash start/update_script_version.sh sync`
3. 在浏览器中访问：`https://stakefav.xyz/scripts/stake.user.js`
4. 检查 Tampermonkey 是否检测到更新

