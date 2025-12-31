@echo off
chcp 65001 >nul
echo ========================================
echo    Stake 服务启动脚本 (Windows)
echo ========================================
echo.

REM 检查 Python 是否可用
where python >nul 2>&1
if errorlevel 1 (
    where py >nul 2>&1
    if errorlevel 1 (
        echo [错误] 未找到 Python，请先安装 Python 3.10+
        echo.
        echo 安装方法：
        echo 1. 访问 https://www.python.org/downloads/
        echo 2. 下载并安装 Python 3.10 或更高版本
        echo 3. 安装时勾选 "Add Python to PATH"
        echo.
        pause
        exit /b 1
    )
    set "PYTHON_CMD=py"
) else (
    set "PYTHON_CMD=python"
)

REM 检查虚拟环境
if not exist "venv\Scripts\activate.bat" (
    echo [警告] 虚拟环境不存在，正在创建...
    echo.
    %PYTHON_CMD% -m venv venv
    if errorlevel 1 (
        echo [错误] 虚拟环境创建失败
        echo 请检查 Python 是否正确安装
        echo.
        echo 尝试手动创建：
        echo   %PYTHON_CMD% -m venv venv
        echo.
        pause
        exit /b 1
    )
    echo [成功] 虚拟环境已创建
    echo.
)

REM 激活虚拟环境
call venv\Scripts\activate.bat

REM 检查依赖
echo [1/4] 检查依赖...
cd config
venv\Scripts\python.exe -c "import django" 2>nul
if errorlevel 1 (
    echo [警告] Django 未安装，正在安装依赖...
    venv\Scripts\pip.exe install -r requirements.txt
    if errorlevel 1 (
        echo [错误] 依赖安装失败
        cd ..
        pause
        exit /b 1
    )
)
cd ..

REM 检查数据库
echo [2/4] 检查数据库...
if not exist "db\db.sqlite3" (
    echo [信息] 数据库不存在，运行迁移...
    cd config
    ..\venv\Scripts\python.exe manage.py migrate
    cd ..
)

REM 获取脚本所在目录的父目录（项目根目录）
set "PROJECT_ROOT=%~dp0"

REM 启动 Django
echo [3/4] 启动 Django 服务...
start "Django Server" cmd /k "title Django Server && cd /d %PROJECT_ROOT% && call venv\Scripts\activate.bat && cd config && venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000"
timeout /t 3 /nobreak >nul

REM 启动 Listener
echo [4/4] 启动 Telegram Listener...
start "Telegram Listener" cmd /k "title Telegram Listener && cd /d %PROJECT_ROOT% && call venv\Scripts\activate.bat && cd core && ..\venv\Scripts\python.exe listener.py"

echo.
echo ========================================
echo    ✅ 服务启动完成！
echo ========================================
echo.
echo 📋 访问地址：
echo    Django Admin: http://localhost:8000/admin
echo.
echo 📊 查看日志：
echo    Django:   db\logs\django.log
echo    Listener: db\logs\listener.log
echo    Bypass:   db\logs\bypass.log
echo.
echo 💡 停止服务：关闭对应的命令行窗口
echo.
pause

