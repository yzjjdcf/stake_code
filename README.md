# Stake 自动化项目

## 📁 项目目录结构

```
stake_code/
├── 📄 核心配置文件
│   ├── config.py              # 项目配置文件（平台、Telegram、浏览器等）
│   ├── requirements.txt       # Python 依赖包
│   └── manage.py              # Django 管理脚本
│
├── 🚀 服务管理脚本
│   ├── menu.sh                # 交互式菜单（主要使用）
│   ├── start_all.sh           # 启动/停止/重启服务
│   └── 检查listener状态.sh    # 检查 Listener 状态
│
├── 💻 核心功能代码
│   ├── listener.py            # Telegram 消息监听器
│   ├── worker.py              # 工作逻辑（领取红包）
│   │
│   ├── manager/               # Django 项目配置
│   │   ├── settings.py       # Django 设置
│   │   ├── urls.py           # URL 路由
│   │   └── wsgi.py           # WSGI 配置
│   │
│   └── serverbot/            # Django 应用
│       ├── models.py          # 数据模型
│       ├── admin.py           # Django Admin 配置
│       ├── utils.py           # 工具函数（过盾逻辑）
│       ├── views.py           # 视图函数
│       ├── forms.py           # 表单
│       ├── migrations/        # 数据库迁移文件
│       └── templates/         # 模板文件
│
├── 📊 数据目录
│   ├── db.sqlite3             # SQLite 数据库（核心数据）
│   ├── data/                  # 运行时数据
│   │   ├── profiles/          # 浏览器配置目录
│   │   └── proxy_ext/         # 代理扩展目录
│   └── logs/                  # 日志目录
│       ├── django.log         # Django 日志
│       ├── listener.log       # Listener 日志
│       └── bypass.log         # 过盾日志
│
├── 🔧 系统服务配置（Linux）
│   ├── stake-django.service   # systemd 服务配置
│   └── stake-listener.service # systemd 服务配置
│
└── 🔐 会话文件
    └── stake_listener_session.session  # Telegram 会话文件
```

## 🗂️ 目录说明

### 核心目录

- **根目录**：项目主目录，包含所有核心文件
- **manager/**：Django 项目配置目录
- **serverbot/**：Django 应用目录，包含业务逻辑
- **data/**：运行时数据目录（自动生成）
  - `profiles/`：浏览器用户配置目录
  - `proxy_ext/`：代理扩展目录
- **logs/**：日志目录（自动生成）
  - `django.log`：Django 服务日志
  - `listener.log`：Telegram 监听器日志
  - `bypass.log`：过盾流程日志

### 运行时目录（自动创建）

- **pids/**：进程 ID 文件目录（由 `start_all.sh` 自动创建）
- **__pycache__/**：Python 缓存目录（可忽略）

## 📝 主要文件说明

### 配置文件
- `config.py`：项目核心配置，包括平台检测、Telegram 配置、浏览器配置等

### 服务脚本
- `menu.sh`：**主要使用**，交互式菜单管理服务
- `start_all.sh`：服务启动/停止脚本
- `检查listener状态.sh`：检查 Listener 服务状态

### 核心代码
- `listener.py`：Telegram 消息监听器，监听频道消息并触发领取任务
- `worker.py`：工作逻辑，处理红包领取任务
- `serverbot/utils.py`：过盾逻辑，处理 Cloudflare 验证

### 数据库
- `db.sqlite3`：SQLite 数据库，存储所有业务数据

## 🚀 快速开始

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 运行数据库迁移
```bash
python manage.py migrate
```

### 3. 启动服务
```bash
# 使用交互式菜单（推荐）
./menu.sh

# 或直接启动
./start_all.sh start
```

## 📋 服务管理

使用 `menu.sh` 可以：
- 启动/停止/重启服务
- 查看日志
- 运行数据库迁移
- 检查服务状态

## ⚠️ 注意事项

1. **数据库文件**：`db.sqlite3` 包含所有业务数据，请定期备份
2. **会话文件**：`stake_listener_session.session` 是 Telegram 登录凭证，请妥善保管
3. **日志目录**：日志文件会持续增长，建议定期清理
4. **数据目录**：`data/` 目录下的文件是运行时生成的，可以删除重建

## 🔧 平台支持

- **Windows**：开发环境
- **Linux**：生产环境（服务器）

通过 `config.py` 中的 `PLATFORM` 配置自动适配不同平台。

