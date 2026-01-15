// ==UserScript==
// @name         Winna code claim tool
// @namespace    http://tampermonkey.net/
// @version      1.0.0
// @description  Winna 代码自动领取工具（支持自动更新）
// @author       You
// @match        https://winna.com/*
// @grant        none
// @connect      *
// @updateURL    http://146.103.42.142:8000/scripts/winna.user.js
// @downloadURL  http://146.103.42.142:8000/scripts/winna.user.js
// ==/UserScript==

(function() {
    'use strict';

    // ==================== 配置 ====================
    // 注意：HTTPS 页面必须使用 wss:// (加密 WebSocket)，不能使用 ws://
    const WEBSOCKET_URL = 'wss://146.103.42.142:8766';  // Winna 使用端口 8766（与 Stake 的 8765 区分）
    const RECONNECT_DELAY = 3000;  // 重连延迟（毫秒）
    const MAX_RECONNECT_ATTEMPTS = 10;  // 最大重连次数
    
    // ==================== 用户标识 ====================
    // 用户唯一标识符（用于区分不同使用者，一个用户可以有多个 Winna 账号）
    // 注意：为每个用户生成脚本时，需要修改此值
    const USER_ID = 'KK';  // 请修改为实际的用户标识符

    // ==================== 状态管理 ====================
    let ws = null;
    let reconnectAttempts = 0;
    let isConnecting = false;
    let lastPingTime = null;  // 记录最后一次发送 ping 的时间戳
    let statusElement = null;
    let certWindow = null;  // 保存打开的证书窗口引用，用于自动关闭
    let certWindowOpened = false;  // 标记是否已经打开过证书页面，避免重复打开
    let serverTimeOffset = 0;  // 服务器时间偏移量（服务器时间 - 客户端时间，毫秒）

    // ==================== UI 状态显示（终端风格）====================
    let logContainer = null;
    let statusDot = null;
    let isPanelCollapsed = true;

    function createStatusUI() {
        // 注入 CSS 样式
        const style = document.createElement('style');
        style.textContent = `
            #winna-ws-panel {
                position: fixed; top: 60px; left: 20px; z-index: 9999;
                width: 288px; height: 432px;
                background: #0f1115;
                border: 1px solid #2a2d35;
                border-radius: 8px;
                font-family: 'SF Mono', 'Roboto Mono', Consolas, monospace;
                color: #ececed;
                box-shadow: 0 8px 24px rgba(0,0,0,0.5);
                transition: left 0.2s ease-out, right 0.2s ease-out;
                overflow: hidden; display: flex; flex-direction: column;
                padding: 10px; box-sizing: border-box;
            }

            #winna-ws-panel.collapsed {
                width: 40px !important; height: 40px !important; border-radius: 50% !important; padding: 0 !important;
                background: #16191f; border-color: #3a3f4b;
                display: flex; align-items: center; justify-content: center;
            }
            #winna-ws-panel.collapsed .info-group,
            #winna-ws-panel.collapsed #winna-ws-log-container,
            #winna-ws-panel.collapsed #winna-ws-resize-handle,
            #winna-ws-panel.collapsed #winna-ws-username,
            #winna-ws-panel.collapsed #winna-ws-ping-vault-container,
            #winna-ws-panel.collapsed #winna-ws-test-vault-btn,
            #winna-ws-panel.collapsed #winna-ws-test-buttons { display: none; }
            #winna-ws-panel.collapsed #winna-ws-header {
                background: transparent; border: none; margin: 0; padding: 0;
                width: 100%; height: 100%; justify-content: center;
            }
            #winna-ws-panel.collapsed .header-title { display: none; }

            #winna-ws-header {
                margin: -10px -10px 10px -10px; padding: 8px 12px;
                cursor: move; background: #16191f;
                display: flex; justify-content: space-between; align-items: center;
                border-bottom: 1px solid #23262d;
                position: relative;
                user-select: none;
            }
            #winna-ws-header:active { cursor: grabbing; }
            
            #winna-ws-close-btn {
                width: 18px; height: 18px;
                display: flex; align-items: center; justify-content: center;
                cursor: pointer;
                color: #b0b0b5;
                font-size: 14px;
                line-height: 1;
                border-radius: 3px;
                transition: all 0.2s;
                margin-left: 8px;
            }
            #winna-ws-close-btn:hover {
                background: rgba(255, 59, 48, 0.3);
                color: #ff6b60;
            }
            #winna-ws-panel.collapsed #winna-ws-close-btn { display: none; }
            
            #winna-ws-resize-handle {
                position: absolute;
                bottom: 0;
                right: 0;
                width: 12px;
                height: 12px;
                cursor: nwse-resize;
                background: transparent;
                z-index: 10;
                user-select: none;
            }
            #winna-ws-resize-handle:hover {
                background: rgba(77, 238, 234, 0.2);
            }
            #winna-ws-resize-handle::after {
                content: '';
                position: absolute;
                bottom: 2px;
                right: 2px;
                width: 0;
                height: 0;
                border-style: solid;
                border-width: 0 0 8px 8px;
                border-color: transparent transparent #b0b0b5 transparent;
            }
            .header-title { font-size: 10px; font-weight: 700; color: #b0b0b5; text-transform: uppercase; letter-spacing: 1px; }

            .status-dot {
                width: 8px; height: 8px; background: #ff3b30; border-radius: 50%;
                box-shadow: 0 0 8px rgba(255,59,48,0.4); transition: all 0.3s;
            }
            .status-dot.connected { background: #34c759; box-shadow: 0 0 8px rgba(52,199,89,0.4); }
            .status-dot.connecting { background: #ffcc00; box-shadow: 0 0 8px rgba(255,204,0,0.4); }

            .info-group { display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 10px; color: #8a8d92; }
            .info-value { font-weight: 600; color: #ffffff; margin-left: 8px; }

            #winna-ws-username {
                font-size: 12px;
                color: #b0b0b5;
                padding: 4px 8px;
                background: #16191f;
                border: 1px solid #23262d;
                border-radius: 4px;
                font-weight: 600;
                margin-bottom: 8px;
            }
            
            #winna-ws-ping-vault-container {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: 8px;
                gap: 8px;
            }
            #winna-ws-username .username-label {
                color: #8a8d92;
                margin-right: 6px;
            }
            #winna-ws-username .username-value {
                color: #6df5f0;
                font-weight: 700;
            }
            
            #winna-ws-ping {
                font-size: 12px;
                color: #b0b0b5;
                padding: 4px 8px;
                background: #16191f;
                border: 1px solid #23262d;
                border-radius: 4px;
                font-weight: 600;
                white-space: nowrap;
            }
            #winna-ws-ping .ping-label {
                color: #8a8d92;
                margin-right: 6px;
            }
            #winna-ws-ping .ping-value {
                color: #6df5f0;
                font-weight: 700;
            }
            
            #winna-ws-vault-switch {
                display: none; /* Winna 暂不支持保险库功能 */
                align-items: center;
                gap: 6px;
                padding: 4px 8px;
                background: #16191f;
                border: 1px solid #23262d;
                border-radius: 4px;
                font-size: 12px;
                cursor: pointer;
                user-select: none;
                white-space: nowrap;
                flex-shrink: 0;
            }
            #winna-ws-vault-switch:hover {
                background: #1a1d24;
            }
            #winna-ws-vault-switch .switch-label {
                color: #8a8d92;
            }
            #winna-ws-vault-switch .switch-checkbox {
                width: 36px;
                height: 20px;
                position: relative;
                background: #2a2d35;
                border-radius: 10px;
                cursor: pointer;
                transition: background 0.2s;
            }
            #winna-ws-vault-switch .switch-checkbox.active {
                background: #28a745;
            }
            #winna-ws-vault-switch .switch-checkbox::after {
                content: '';
                position: absolute;
                width: 16px;
                height: 16px;
                border-radius: 50%;
                background: #fff;
                top: 2px;
                left: 2px;
                transition: left 0.2s;
            }
            #winna-ws-vault-switch .switch-checkbox.active::after {
                left: 18px;
            }
            
            #winna-ws-test-vault-btn {
                display: none; /* 隐藏测试按钮 */
                padding: 6px 12px;
                margin-bottom: 8px;
                background: #007bff;
                border: 1px solid #0056b3;
                border-radius: 4px;
                font-size: 12px;
                color: #fff;
                text-align: center;
                cursor: pointer;
                user-select: none;
                transition: background 0.2s;
            }
            #winna-ws-test-vault-btn:hover {
                background: #0056b3;
            }
            #winna-ws-test-vault-btn:active {
                background: #004085;
            }

            #winna-ws-test-buttons {
                display: flex;
                flex-direction: column;
                gap: 6px;
                margin-bottom: 8px;
            }
            #winna-ws-test-buttons button {
                padding: 6px 12px;
                background: #007bff;
                border: 1px solid #0056b3;
                border-radius: 4px;
                font-size: 12px;
                color: #fff;
                text-align: center;
                cursor: pointer;
                user-select: none;
                transition: background 0.2s;
            }
            #winna-ws-test-buttons button:hover {
                background: #0056b3;
            }
            #winna-ws-test-buttons button:active {
                background: #004085;
            }
            #winna-ws-test-buttons button:disabled {
                opacity: 0.6;
                cursor: not-allowed;
            }
            #winna-ws-panel.collapsed #winna-ws-test-buttons {
                display: none;
            }

            #winna-ws-log-container {
                flex-grow: 1;
                background: #08090c;
                border: 1px solid #23262d;
                border-radius: 4px; padding: 8px;
                overflow-y: auto; display: flex; flex-direction: column;
                user-select: text;
                cursor: text;
            }

            .log-item {
                font-size: 12px;
                line-height: 1.3; margin-bottom: 3px;
                color: #b0b0b5;
                word-break: break-all;
                user-select: text;
            }
            .log-success { color: #6df5f0; }
            .log-info { color: #a0a0a5; }
            .log-error { color: #ff6b60; }
            .log-code { color: #ffdd44; font-weight: 700; }
            .log-warning { color: #ffdd44; }

            #winna-ws-log-container::-webkit-scrollbar { width: 4px; }
            #winna-ws-log-container::-webkit-scrollbar-track { background: transparent; }
            #winna-ws-log-container::-webkit-scrollbar-thumb { background: #4a4d55; border-radius: 2px; }
            #winna-ws-log-container::-webkit-scrollbar-thumb:hover { background: #5a5d65; }
        `;
        document.head.appendChild(style);

        // 创建面板
        statusElement = document.createElement('div');
        statusElement.id = 'winna-ws-panel';
        statusElement.className = 'collapsed';
        statusElement.innerHTML = `
            <div id="winna-ws-header" title="拖动移动位置">
                <span class="header-title">Winna Auto Claim</span>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <div class="status-dot" id="winna-ws-status-dot"></div>
                    <div id="winna-ws-close-btn" title="收起">×</div>
                </div>
            </div>
            <div id="winna-ws-username">
                <span class="username-label">user:</span>
                <span class="username-value" id="winna-ws-username-value">-</span>
            </div>
            <div id="winna-ws-ping-vault-container">
                <div id="winna-ws-vault-switch">
                    <span class="switch-label">存入保险库</span>
                    <div class="switch-checkbox" id="winna-ws-vault-checkbox"></div>
                </div>
                <div id="winna-ws-ping">
                    <span class="ping-label">ping:</span>
                    <span class="ping-value" id="winna-ws-ping-value">-</span>
                </div>
            </div>
            <div id="winna-ws-test-vault-btn">测试存入 1 USDT</div>
            <div id="winna-ws-test-buttons">
                <button id="winna-ws-test-turnstile-btn">测试获取 Turnstile Token</button>
                <button id="winna-ws-test-claim-btn">测试领取接口 (pinex6)</button>
            </div>
            <div id="winna-ws-log-container"></div>
            <div id="winna-ws-resize-handle" title="拖动等比缩放"></div>
        `;
        document.body.appendChild(statusElement);

        logContainer = document.getElementById('winna-ws-log-container');
        statusDot = document.getElementById('winna-ws-status-dot');
        
        // 初始化时获取并显示用户名
        updateUsernameDisplay();
        
        // Winna 暂不支持保险库功能，已隐藏相关 UI
        // initVaultSwitch();
        // initTestVaultButton();
        
        // 初始化测试按钮
        initTestButtons();

        // 单击展开
        statusElement.addEventListener('click', (e) => {
            // 如果点击的是关闭按钮，不展开
            if (e.target.closest('#winna-ws-close-btn')) return;
            // 如果点击的是调整大小手柄，不展开
            if (e.target.closest('#winna-ws-resize-handle')) return;
            
            if (isPanelCollapsed) {
                isPanelCollapsed = false;
                statusElement.className = '';
                // 清除收起时的强制尺寸，恢复之前的状态
                // 如果之前调整过大小，保留调整后的尺寸；否则使用默认尺寸
                if (!statusElement.dataset.hasCustomSize) {
                    statusElement.style.width = '';
                    statusElement.style.height = '';
                }
                // 确保展开时至少恢复默认尺寸
                if (!statusElement.style.width || statusElement.style.width === '40px') {
                    statusElement.style.width = '288px';
                    statusElement.style.height = '432px';
                }
            }
        });

        // 关闭按钮点击收起
        document.getElementById('winna-ws-close-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            isPanelCollapsed = true;
            statusElement.className = 'collapsed';
            // 强制重置尺寸，确保圆形
            statusElement.style.width = '40px';
            statusElement.style.height = '40px';
            // 延迟一下确保样式已应用，然后自动吸附
            setTimeout(() => {
                checkAndSnapToEdge();
            }, 10);
        });

        // 拖动功能（展开状态）
        let isDragging = false;
        let dragStartX = 0;
        let dragStartY = 0;
        let panelStartX = 0;
        let panelStartY = 0;

        const header = document.getElementById('winna-ws-header');
        header.addEventListener('mousedown', (e) => {
            // 如果点击的是关闭按钮，不拖动
            if (e.target.closest('#winna-ws-close-btn')) return;
            
            if (isPanelCollapsed) {
                // 收起状态：拖动移动
                isDragging = true;
                dragStartX = e.clientX;
                dragStartY = e.clientY;
                const rect = statusElement.getBoundingClientRect();
                panelStartX = rect.left;
                panelStartY = rect.top;
                e.preventDefault();
            } else {
                // 展开状态：拖动移动
                isDragging = true;
                dragStartX = e.clientX;
                dragStartY = e.clientY;
                const rect = statusElement.getBoundingClientRect();
                panelStartX = rect.left;
                panelStartY = rect.top;
                e.preventDefault();
            }
        });

        document.addEventListener('mousemove', (e) => {
            if (isDragging) {
                const deltaX = e.clientX - dragStartX;
                const deltaY = e.clientY - dragStartY;
                statusElement.style.left = (panelStartX + deltaX) + 'px';
                statusElement.style.top = (panelStartY + deltaY) + 'px';
                statusElement.style.right = 'auto';
            }
        });

        document.addEventListener('mouseup', () => {
            if (isDragging) {
                isDragging = false;
                if (isPanelCollapsed) {
                    checkAndSnapToEdge();
                }
            }
        });

        // 边缘吸附（只在收起状态，左右两侧，自动吸附到最近的边缘）
        function checkAndSnapToEdge() {
            if (!isPanelCollapsed) return;
            
            const rect = statusElement.getBoundingClientRect();
            const windowWidth = window.innerWidth;
            const centerX = rect.left + rect.width / 2;
            
            // 计算到左右边缘的距离
            const distanceToLeft = centerX;
            const distanceToRight = windowWidth - centerX;
            
            // 自动吸附到最近的边缘
            if (distanceToLeft < distanceToRight) {
                // 靠近左边，吸附到左边缘
                statusElement.style.left = '0px';
                statusElement.style.right = 'auto';
            } else {
                // 靠近右边，吸附到右边缘
                statusElement.style.right = '0px';
                statusElement.style.left = 'auto';
            }
        }

        // 调整大小功能（展开状态，右下角等比缩放）
        let isResizing = false;
        let resizeStartX = 0;
        let resizeStartY = 0;
        let panelStartWidth = 0;
        let panelStartHeight = 0;
        const aspectRatio = 288 / 432; // 初始宽高比

        const resizeHandle = document.getElementById('winna-ws-resize-handle');
        resizeHandle.addEventListener('mousedown', (e) => {
            if (!isPanelCollapsed) {
                isResizing = true;
                resizeStartX = e.clientX;
                resizeStartY = e.clientY;
                panelStartWidth = statusElement.offsetWidth;
                panelStartHeight = statusElement.offsetHeight;
                e.preventDefault();
                e.stopPropagation();
            }
        });

        document.addEventListener('mousemove', (e) => {
            if (isResizing && !isPanelCollapsed) {
                const deltaX = e.clientX - resizeStartX;
                const deltaY = e.clientY - resizeStartY;
                
                // 计算新的宽度和高度（保持宽高比）
                const newWidth = Math.max(200, Math.min(600, panelStartWidth + deltaX));
                const newHeight = newWidth / aspectRatio;
                
                // 确保高度也在合理范围内
                const finalHeight = Math.max(300, Math.min(900, newHeight));
                const finalWidth = finalHeight * aspectRatio;
                
                statusElement.style.width = finalWidth + 'px';
                statusElement.style.height = finalHeight + 'px';
                statusElement.dataset.hasCustomSize = 'true'; // 标记已自定义尺寸
            }
        });

        document.addEventListener('mouseup', () => {
            if (isResizing) {
                isResizing = false;
            }
        });

        // 初始日志
        addLog('系统初始化...', 'info');
        
        // 初始化时自动吸附到最近的边缘
        setTimeout(() => {
            checkAndSnapToEdge();
        }, 100);
    }

    // 获取服务器时间（基于时间偏移量）
    function getServerTime() {
        return new Date(Date.now() + serverTimeOffset);
    }
    
    // 格式化服务器时间
    function formatServerTime(date) {
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        const seconds = String(date.getSeconds()).padStart(2, '0');
        const milliseconds = String(date.getMilliseconds()).padStart(3, '0');
        return `${hours}:${minutes}:${seconds}.${milliseconds}`;
    }
    
    function addLog(message, type = 'info', useServerTime = true) {
        if (!logContainer) return;
        
        const logItem = document.createElement('div');
        logItem.className = `log-item log-${type}`;
        
        // 使用服务器时间格式化时间戳
        const timeDate = useServerTime ? getServerTime() : new Date();
        const timeStr = formatServerTime(timeDate);
        
        // 高亮代码
        let formattedMessage = message;
        const codeMatch = message.match(/([A-Za-z0-9]{8,})/);
        if (codeMatch) {
            formattedMessage = message.replace(codeMatch[0], `<span class="log-code">${codeMatch[0]}</span>`);
        }
        
        logItem.innerHTML = `[${timeStr}] ${formattedMessage}`;
        logContainer.appendChild(logItem);
        
        // 自动滚动到底部
        logContainer.scrollTop = logContainer.scrollHeight;
        
        // 限制日志条数（保留最后 100 条）
        const logs = logContainer.querySelectorAll('.log-item');
        if (logs.length > 100) {
            logs[0].remove();
        }
    }

    // 更新连接状态（只更新状态点，不更新文本）
    function updateConnectionStatus(status) {
        // status: 'connected' | 'connecting' | 'error'
        if (!statusDot) return;
        
        statusDot.className = 'status-dot';
        if (status === 'connected') {
            statusDot.classList.add('connected');
        } else if (status === 'connecting') {
            statusDot.classList.add('connecting');
            updatePingDisplay(null);  // 连接中时重置 ping 显示
        } else {
            // error 状态保持默认红色，不需要添加类
            updatePingDisplay(null);  // 错误时重置 ping 显示
        }
    }
    
    // 更新 ping 延迟显示
    function updatePingDisplay(pingMs) {
        const pingElement = document.getElementById('winna-ws-ping-value');
        if (!pingElement) return;
        
        if (pingMs !== null && pingMs !== undefined) {
            pingElement.textContent = `${pingMs}ms`;
            // 根据延迟设置颜色：绿色(<100ms), 黄色(100-300ms), 红色(>300ms)
            if (pingMs < 100) {
                pingElement.style.color = '#34c759';  // 绿色
            } else if (pingMs < 300) {
                pingElement.style.color = '#ffcc00';  // 黄色
            } else {
                pingElement.style.color = '#ff6b60';  // 红色
            }
        } else {
            pingElement.textContent = '-';
            pingElement.style.color = '#6df5f0';  // 默认青色
        }
    }
    
    // 处理 pong 响应，计算延迟
    function handlePong(data) {
        if (lastPingTime) {
            const now = Date.now();
            const pingMs = now - lastPingTime;
            updatePingDisplay(pingMs);
            lastPingTime = null;  // 清除时间戳
        }
    }

    // 更新用户名显示
    function updateUsernameDisplay() {
        const usernameElement = document.getElementById('winna-ws-username-value');
        if (!usernameElement) return;
        
        const username = getUsernameFromPage();
        if (username) {
            usernameElement.textContent = username;
        } else {
            usernameElement.textContent = '-';
        }
    }

    // 格式化金额（保留两位小数）
    function formatAmount(amount) {
        if (amount === null || amount === undefined || amount === 'N/A') {
            return 'N/A';
        }
        try {
            const num = parseFloat(amount);
            if (isNaN(num)) {
                return amount;  // 如果不是数字，返回原值
            }
            return num.toFixed(2);  // 保留两位小数
        } catch (e) {
            return amount;  // 如果转换失败，返回原值
        }
    }

    // 初始化存入保险库开关
    function initVaultSwitch() {
        const checkbox = document.getElementById('winna-ws-vault-checkbox');
        const switchContainer = document.getElementById('winna-ws-vault-switch');
        if (!checkbox || !switchContainer) return;
        
        // 从 localStorage 读取开关状态
        const savedState = localStorage.getItem('winna_vault_auto_deposit');
        const isEnabled = savedState === 'true';
        
        if (isEnabled) {
            checkbox.classList.add('active');
        }
        
        // 点击切换开关
        switchContainer.addEventListener('click', function() {
            const isActive = checkbox.classList.contains('active');
            if (isActive) {
                checkbox.classList.remove('active');
                localStorage.setItem('winna_vault_auto_deposit', 'false');
            } else {
                checkbox.classList.add('active');
                localStorage.setItem('winna_vault_auto_deposit', 'true');
            }
        });
    }

    // 初始化测试存入保险库按钮
    function initTestVaultButton() {
        const testBtn = document.getElementById('winna-ws-test-vault-btn');
        if (!testBtn) return;
        
        testBtn.addEventListener('click', async function() {
            // 禁用按钮，防止重复点击
            testBtn.style.opacity = '0.6';
            testBtn.style.cursor = 'not-allowed';
            testBtn.textContent = '测试中...';
            
            try {
                console.log('[Winna WS] 🧪 测试存入保险库: 1 USDT');
                addLog('🧪 测试存入保险库: 1 USDT', 'info');
                
                const result = await depositToVault(1, 'usdt');
                
                if (result.success) {
                    const depositedAmount = result.data?.amount || '1';
                    addLog(`✅ 测试成功: 存入 ${depositedAmount} USDT`, 'success');
                    console.log('[Winna WS] ✅ 测试存入保险库成功:', result.data);
                } else {
                    addLog(`❌ 测试失败: ${result.error}`, 'error');
                    console.error('[Winna WS] ❌ 测试存入保险库失败:', result.error);
                }
            } catch (e) {
                addLog(`❌ 测试异常: ${e.message}`, 'error');
                console.error('[Winna WS] ❌ 测试存入保险库异常:', e);
            } finally {
                // 恢复按钮状态
                testBtn.style.opacity = '1';
                testBtn.style.cursor = 'pointer';
                testBtn.textContent = '测试存入 1 USDT';
            }
        });
    }

    // Winna 暂不支持保险库功能，相关函数已移除

    // ==================== 初始化测试按钮 ====================
    function initTestButtons() {
        // 测试获取 Turnstile Token
        const testTurnstileBtn = document.getElementById('winna-ws-test-turnstile-btn');
        if (testTurnstileBtn) {
            testTurnstileBtn.addEventListener('click', async function() {
                testTurnstileBtn.disabled = true;
                testTurnstileBtn.textContent = '测试中...';
                
                try {
                    addLog('🔍 开始测试获取 Turnstile Token...', 'info');
                    
                    // 先检查是否有缓存的 token
                    if (turnstileTokenCache) {
                        addLog(`✅ 缓存的 Turnstile Token: ${turnstileTokenCache.substring(0, 30)}...`, 'success');
                        console.log('[Winna WS] ✅ 缓存的 Turnstile Token:', turnstileTokenCache);
                    } else if (window.__TURNSTILETOKEN__) {
                        addLog(`✅ 全局 Turnstile Token: ${window.__TURNSTILETOKEN__.substring(0, 30)}...`, 'success');
                        console.log('[Winna WS] ✅ 全局 Turnstile Token:', window.__TURNSTILETOKEN__);
                    } else {
                        addLog('⚠️ 未找到缓存的 Token，尝试获取新 Token...', 'warning');
                        console.log('[Winna WS] 未找到缓存的 Token，尝试获取新 Token...');
                        
                        // 尝试获取新 token
                        const token = await getTurnstileToken('test', 'usdt');
                        if (token) {
                            addLog(`✅ 获取到 Turnstile Token: ${token.substring(0, 30)}...`, 'success');
                            console.log('[Winna WS] ✅ 获取到 Turnstile Token:', token);
                        } else {
                            addLog('❌ 无法获取 Turnstile Token', 'error');
                            console.error('[Winna WS] ❌ 无法获取 Turnstile Token');
                            console.log('[Winna WS] 提示: 请确保 Turnstile widget 已初始化');
                        }
                    }
                } catch (e) {
                    addLog(`❌ 测试异常: ${e.message}`, 'error');
                    console.error('[Winna WS] ❌ 测试 Turnstile Token 异常:', e);
                } finally {
                    testTurnstileBtn.disabled = false;
                    testTurnstileBtn.textContent = '测试获取 Turnstile Token';
                }
            });
        }

        // 测试领取接口
        const testClaimBtn = document.getElementById('winna-ws-test-claim-btn');
        if (testClaimBtn) {
            testClaimBtn.addEventListener('click', async function() {
                testClaimBtn.disabled = true;
                testClaimBtn.textContent = '测试中...';
                
                try {
                    const testCode = 'pinex6';
                    addLog(`🔍 开始测试领取接口: ${testCode}...`, 'info');
                    console.log('[Winna WS] 🧪 测试领取接口:', testCode);
                    
                    // 使用DOM操作领取代码
                    const startTime = Date.now();
                    console.log('[Winna WS] 🧪 开始调用 claimBonusCodeViaDOM...');
                    const result = await claimBonusCodeViaDOM(testCode);
                    const responseTime = Date.now() - startTime;
                    
                    console.log('[Winna WS] 🧪 claimBonusCodeViaDOM 返回，结果:', result);
                    console.log('[Winna WS] 🧪 响应时间:', responseTime, 'ms');
                    
                    // 统一显示：已经尝试领取该code
                    addLog(`📝 已经尝试领取该code: ${testCode}`, 'info');
                    if (responseTime) {
                        addLog(`⏱️ 响应时间: ${responseTime}ms`, 'info');
                    }
                    console.log('[Winna WS] 📝 已经尝试领取该code:', testCode);
                    console.log('[Winna WS] 领取结果:', result);
                    if (result.errorMessage) {
                        addLog(`❌ 错误: ${result.errorMessage}`, 'error');
                        console.log('[Winna WS] 错误信息:', result.errorMessage);
                    } else if (result.success) {
                        if (result.amount) {
                            addLog(`✅ 领取成功: ${result.amount} ${result.currency || 'USDT'}`, 'success');
            } else {
                            addLog(`✅ 领取成功`, 'success');
                        }
                    }
                    
                    // 发送结果回服务器
                    console.log('[Winna WS] 🧪 准备发送测试结果到服务器...');
                    const username = getUsernameFromPage();
                    const dataToSend = {
                        code: testCode,
                        success: result.success || false,
                        status: result.status || 'error',
                        amount: result.amount || null,
                        currency: result.currency || null,
                        username: username,
                        responseTime: responseTime,
                        responseBody: JSON.stringify(result.responseBody || {}),
                        errorMessage: result.errorMessage || null,
                        server_timestamp_ms: getServerTime().getTime()
                    };
                    console.log('[Winna WS] 🧪 测试数据准备完成:', dataToSend);
                    sendClaimResultToServer(dataToSend);
                    console.log('[Winna WS] 🧪 测试结果已发送到服务器');
                    
                    /* ========== 原来的API调用逻辑（已注释） ==========
                    // 调用领取接口
                    const result = await claimBonusCodeViaAPI(testCode);
                    
                    // 统一显示：已经尝试领取该code
                    addLog(`📝 已经尝试领取该code: ${testCode}`, 'info');
                    if (result.responseTime) {
                        addLog(`⏱️ 响应时间: ${result.responseTime}ms`, 'info');
                    }
                    console.log('[Winna WS] 📝 已经尝试领取该code:', testCode);
                    console.log('[Winna WS] API 响应:', result.fullResponse);
                    if (result.error) {
                        console.log('[Winna WS] 错误信息:', result.error);
                    }
                    ========== 原来的API调用逻辑（已注释） ========== */
        } catch (e) {
                    addLog(`❌ 测试异常: ${e.message}`, 'error');
                    console.error('[Winna WS] ❌ 测试领取接口异常:', e);
                } finally {
                    testClaimBtn.disabled = false;
                    testClaimBtn.textContent = '测试领取接口 (pinex6)';
                }
            });
        }
    }


    // ==================== WebSocket 连接 ====================
    function connect() {
        if (isConnecting || (ws && ws.readyState === WebSocket.OPEN)) {
            return;
        }

        isConnecting = true;
        updateConnectionStatus('connecting');
        console.log('[Winna WS] 正在连接到服务器...');

        try {
            ws = new WebSocket(WEBSOCKET_URL);

            ws.onopen = function() {
                console.log('[Winna WS] 连接成功');
                isConnecting = false;
                reconnectAttempts = 0;
                updateConnectionStatus('connected');
                addLog('✅ 连接成功', 'success');
                
                // 连接成功后，发送初始化消息（包含 username）
                const username = getUsernameFromPage();
                if (ws.readyState === WebSocket.OPEN) {
                    try {
                        ws.send(JSON.stringify({
                            type: 'init',
                            username: username || '-',
                            user_id: USER_ID
                        }));
                    } catch (e) {
                        console.error('[Winna WS] 发送初始化消息失败:', e);
                    }
                }
                
                // 连接成功后，尝试关闭证书信任页面
                if (certWindow && !certWindow.closed) {
                    try {
                        certWindow.close();
                        console.log('[Winna WS] ✅ 证书已信任，已自动关闭证书页面');
                        certWindow = null;
                        certWindowOpened = false;  // 重置标志，允许下次重新打开
                    } catch (e) {
                        // 如果无法关闭（可能是跨域限制），提示用户手动关闭
                        console.log('[Winna WS] ✅ 证书已信任，请手动关闭证书页面');
                        certWindow = null;
                        certWindowOpened = false;  // 重置标志
                    }
                } else if (certWindowOpened) {
                    // 证书页面已关闭，重置标志
                    certWindowOpened = false;
                }
            };

            ws.onmessage = function(event) {
                try {
                    const data = JSON.parse(event.data);
                    handleMessage(data);
                } catch (e) {
                    console.error('[Winna WS] 解析消息失败:', e);
                }
            };

            ws.onerror = function(error) {
                const stateNames = {0: 'CONNECTING', 1: 'OPEN', 2: 'CLOSING', 3: 'CLOSED'};
                console.error('[Winna WS] 连接错误:', error);
                console.error('[Winna WS] WebSocket 状态:', ws.readyState, `(${stateNames[ws.readyState]})`);
                console.error('[Winna WS] 连接 URL:', WEBSOCKET_URL);
                console.error('[Winna WS] 错误详情:', {
                    type: error.type,
                    target: error.target,
                    timeStamp: error.timeStamp,
                    isTrusted: error.isTrusted
                });
                
                // 尝试获取更详细的错误信息
                if (ws.readyState === 3) { // CLOSED
                    console.error('[Winna WS] 连接已关闭，可能的原因：');
                    console.error('  1. SSL 证书问题（自签名证书需要浏览器接受）');
                    console.error('  2. 服务器未启动或端口未开放');
                    console.error('  3. 防火墙阻止连接');
                    console.error('  4. 证书中的 IP 地址不匹配');
                    
                    // 检测是否为证书问题（通常是 SSL/TLS 错误）
                    const isCertError = error.type === 'error' || 
                                       (error.target && error.target.readyState === 3);
                    
                    if (isCertError) {
                        // 检查是否已经打开过证书页面，避免重复打开
                        const isCertWindowOpen = certWindow && !certWindow.closed;
                        
                        if (!certWindowOpened && !isCertWindowOpen) {
                            // 从 WEBSOCKET_URL 提取服务器地址（wss://host:port -> https://host:port）
                            const urlMatch = WEBSOCKET_URL.match(/wss?:\/\/([^:]+)(?::(\d+))?/);
                            if (urlMatch) {
                                const host = urlMatch[1];
                                const port = urlMatch[2] || '8766';  // Winna 使用端口 8766
                                const certUrl = `https://${host}:${port}/`;
                                
                                console.error('[Winna WS] 💡 检测到 SSL 证书问题，正在打开证书信任页面...');
                                console.log('[Winna WS] ⚠️ SSL 证书未信任，正在打开证书页面...');
                                
                                // 标记已打开证书页面
                                certWindowOpened = true;
                                
                                // 延迟打开证书页面，给用户时间看到提示
                                setTimeout(() => {
                                    // 在新标签页打开证书页面，让用户手动信任证书
                                    // 保存窗口引用，以便连接成功后自动关闭
                                    certWindow = window.open(certUrl, '_blank');
                                    
                                    // 显示详细提示（只在 console 中显示）
                                    console.log('[Winna WS] 📋 请在打开的页面中：');
                                    console.log('[Winna WS]    1. 点击"高级"或"Advanced"');
                                    console.log('[Winna WS]    2. 点击"继续访问"或"Proceed"');
                                    console.log('[Winna WS]    3. 信任证书后，页面会自动关闭');
                                    
                                    // 5秒后自动重连
                                    setTimeout(() => {
                                        console.log('[Winna WS] 🔄 5秒后自动重连...');
                                        setTimeout(() => {
                                            connect();
                                        }, 5000);
                                    }, 2000);
                                }, 1000);
                            } else {
                                console.error('[Winna WS] 💡 建议：在浏览器中访问服务器地址并接受证书');
                                console.error('[Winna WS] 连接错误: SSL 证书或网络问题');
                            }
                        } else if (isCertWindowOpen) {
                            // 证书页面已打开，只提示用户操作，不重复打开
                            console.log('[Winna WS] ⚠️ 证书页面已打开，请完成证书信任操作');
                        } else {
                            // 证书页面已关闭但连接仍失败，可能是其他问题
                            console.log('[Winna WS] ⚠️ 证书已信任但连接仍失败，可能是服务器问题');
                        }
                    } else {
                        console.error('[Winna WS] 连接错误: SSL 证书或网络问题');
                    }
                } else {
                    console.error('[Winna WS] WebSocket 连接错误');
                }
                
                updateConnectionStatus('error');
                isConnecting = false;
            };

            ws.onclose = function(event) {
                console.log('[Winna WS] 连接关闭');
                console.log('[Winna WS] 关闭代码:', event.code);
                console.log('[Winna WS] 关闭原因:', event.reason || '无原因');
                console.log('[Winna WS] 是否正常关闭:', event.wasClean);
                
                // WebSocket 关闭代码说明
                const closeCodeMessages = {
                    1000: '正常关闭',
                    1001: '端点离开（如服务器关闭或浏览器导航）',
                    1002: '协议错误',
                    1003: '不支持的数据类型',
                    1006: '异常关闭（无关闭帧）- 通常是 SSL/TLS 或网络问题',
                    1007: '数据格式错误',
                    1008: '策略违规',
                    1009: '消息过大',
                    1010: '扩展协商失败',
                    1011: '服务器错误',
                    1012: '服务重启',
                    1013: '稍后重试',
                    1014: '网关错误',
                    1015: 'TLS 握手失败 - SSL 证书问题'
                };
                
                if (closeCodeMessages[event.code]) {
                    console.error('[Winna WS] 关闭代码说明:', closeCodeMessages[event.code]);
                }
                
                // 如果是 SSL/TLS 相关错误
                if (event.code === 1015 || event.code === 1006) {
                    // 从 WEBSOCKET_URL 提取服务器地址
                    const urlMatch = WEBSOCKET_URL.match(/wss?:\/\/([^:]+)(?::(\d+))?/);
                    if (urlMatch) {
                        const host = urlMatch[1];
                        const port = urlMatch[2] || '8766';  // Winna 使用端口 8766
                        const certUrl = `https://${host}:${port}/`;
                        console.error(`💡 这可能是 SSL 证书问题，请在浏览器中访问 ${certUrl} 并接受证书`);
                    } else {
                        console.error('💡 这可能是 SSL 证书问题，请在浏览器中访问服务器地址并接受证书');
                    }
                    console.error('💡 或者检查服务器端日志，确认 WebSocket 服务器是否正常启动');
                }
                
                isConnecting = false;
                updateConnectionStatus('error');
                console.log(`[Winna WS] 连接关闭 (代码: ${event.code})`);
                
                // 自动重连
                if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
                    reconnectAttempts++;
                    updateConnectionStatus('connecting');
                    console.log(`[Winna WS] 尝试重连 ${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS}...`);
                    addLog('❌ 连接失败，正在尝试重连中...', 'info');
                    setTimeout(connect, RECONNECT_DELAY);
                } else {
                    updateConnectionStatus('error');
                    console.error('[Winna WS] 达到最大重连次数，请刷新页面');
                    addLog('❌ 连接失败，正在尝试重连中...', 'info');
                }
            };

        } catch (e) {
            console.error('[Winna WS] 连接异常:', e);
            console.error('[Winna WS] 异常详情:', e.message, e.stack);
            isConnecting = false;
            updateConnectionStatus('error');
            console.error(`[Winna WS] 连接异常: ${e.message}`);
        }
    }

    // ==================== 消息处理 ====================
    function handleMessage(data) {
        console.log('[Winna WS] 收到消息:', data);

        if (data.type === 'connected') {
            updateConnectionStatus('connected');
            
            // 同步服务器时间
            if (data.server_timestamp_ms) {
                const clientTime = Date.now();
                serverTimeOffset = data.server_timestamp_ms - clientTime;
                console.log('[Winna WS] 时间同步:', {
                    server_time: new Date(data.server_timestamp_ms).toISOString(),
                    client_time: new Date(clientTime).toISOString(),
                    offset_ms: serverTimeOffset,
                    offset_sec: (serverTimeOffset / 1000).toFixed(2)
                });
                console.log(`[Winna WS] 服务器确认连接 (时间已同步，偏移: ${(serverTimeOffset / 1000).toFixed(2)}秒)`);
            } else {
                console.log('[Winna WS] 服务器确认连接');
            }
            
            // 连接成功后更新用户名显示
            updateUsernameDisplay();
            // 连接成功后立即发送一次 ping 测试延迟
            if (ws && ws.readyState === WebSocket.OPEN) {
                lastPingTime = Date.now();
                ws.send(JSON.stringify({ type: 'ping' }));
            }
        } else if (data.type === 'code_detected') {
            // 如果消息包含服务器时间戳，更新时间偏移（用于更精确的时间同步）
            if (data.server_timestamp_ms) {
                const clientTime = Date.now();
                const newOffset = data.server_timestamp_ms - clientTime;
                // 平滑更新偏移量（避免网络延迟导致的抖动）
                serverTimeOffset = serverTimeOffset === 0 ? newOffset : (serverTimeOffset * 0.7 + newOffset * 0.3);
            }
            addLog(`收到代码: ${data.code}`, 'info');
            handleCodeReceived(data);
        } else if (data.type === 'pong') {
            // 心跳响应，计算延迟
            handlePong(data);
        }
    }

    // ==================== 代码领取逻辑 ====================
    async function handleCodeReceived(data) {
        console.log('[Winna WS] ========== handleCodeReceived 开始 ==========');
        const code = data.code;
        console.log('[Winna WS] 收到代码，立即领取:', code);
        console.log('[Winna WS] 完整数据:', JSON.stringify(data, null, 2));
        // 不在这里添加日志，已在 handleMessage 中添加

        // 新逻辑：通过DOM操作自动填写并点击领取
        console.log('[Winna WS] 🚀 开始处理代码领取:', code);
        try {
            const startTime = Date.now();
            console.log('[Winna WS] ⏳ 调用 claimBonusCodeViaDOM...');
            const result = await claimBonusCodeViaDOM(code);
            const responseTime = Date.now() - startTime;
            
            console.log('[Winna WS] ✅ claimBonusCodeViaDOM 返回');
            console.log('[Winna WS] 📋 DOM操作完成，结果:', result);
            console.log('[Winna WS] 📋 响应时间:', responseTime, 'ms');
            
            // 检查结果是否有效
            if (!result) {
                console.error('[Winna WS] ❌ claimBonusCodeViaDOM 返回了 null 或 undefined');
                throw new Error('领取函数返回了无效结果');
            }
            
            // 获取用户名
            let username = getUsernameFromPage();
            console.log('[Winna WS] 📋 用户名:', username);
            
            // 统一显示文案：已经尝试领取该code
            addLog(`📝 已经尝试领取该code: ${code}`, 'info');
            console.log('[Winna WS] 已经尝试领取该code:', code);
            
            // 构建要发送的数据
            const dataToSend = {
                    code: code,
                success: result.success || false,
                status: result.status || 'error',
                amount: result.amount || null,
                currency: result.currency || null,
                    username: username,
                    responseTime: responseTime,
                responseBody: JSON.stringify(result.responseBody || {}),
                errorMessage: result.errorMessage || null,
                server_timestamp_ms: getServerTime().getTime()
            };
            
            console.log('[Winna WS] 📤 准备发送到服务器的数据:', dataToSend);
            console.log('[Winna WS] 📤 数据详情:', JSON.stringify(dataToSend, null, 2));
            
            // 发送结果回服务器
            console.log('[Winna WS] 📤 调用 sendClaimResultToServer...');
            console.log('[Winna WS] 📤 准备发送的数据对象:', dataToSend);
            console.log('[Winna WS] 📤 数据对象类型:', typeof dataToSend);
            console.log('[Winna WS] 📤 数据对象键:', Object.keys(dataToSend));
            sendClaimResultToServer(dataToSend);
            console.log('[Winna WS] ✅ sendClaimResultToServer 调用完成');
            console.log('[Winna WS] ========== handleCodeReceived 正常完成 ==========');
        } catch (e) {
            console.error('[Winna WS] ========== handleCodeReceived 发生异常 ==========');
            addLog(`❌ 领取异常: ${code} - ${e.message}`, 'error');
            console.error('[Winna WS] 领取异常:', e);
            console.error('[Winna WS] 异常堆栈:', e.stack);
            
            // 发送异常结果回服务器
            console.log('[Winna WS] 📤 准备发送异常结果到服务器...');
                sendClaimResultToServer({
                    code: code,
                    success: false,
                status: 'error',
                    amount: null,
                    currency: null,
                username: getUsernameFromPage(),
                responseTime: null,
                responseBody: null,
                errorMessage: e.message,
                server_timestamp_ms: getServerTime().getTime()
            });
            console.log('[Winna WS] ✅ 异常结果已发送到服务器');
            console.log('[Winna WS] ========== handleCodeReceived 异常处理完成 ==========');
        }

        /* ========== 原来的API调用逻辑（已注释） ==========
        // 直接调用 GraphQL 领取接口
        try {
            const startTime = Date.now();
            const result = await claimBonusCodeViaAPI(code);
            const responseTime = Date.now() - startTime;
            
            // 获取用户名（从 API 响应或页面中获取）
            let username = getUsernameFromPage();
            
            // 统一显示文案：已经尝试领取该code
            addLog(`📝 已经尝试领取该code: ${code}`, 'info');
            console.log('[Winna WS] 已经尝试领取该code:', code);
            console.log('[Winna WS] API 响应:', result.fullResponse);
            
            // 从 Winna API 响应中提取金额和货币（如果有）
            const amount = result.data?.amount || result.data?.bonus || result.data?.bonusAmount || null;
            const currency = result.data?.currency || null;
            
            // 确定状态（从 result 中获取，如果没有则根据 success 判断）
            let finalStatus = result.status || (result.success ? 'claim_success' : 'error');
            let errorMessage = result.error || null;
            
            // 发送结果回服务器（无论成功失败都回传）
            sendClaimResultToServer({
                code: code,
                success: result.success || false,
                status: finalStatus,
                amount: amount,
                currency: currency,
                    username: username,
                responseTime: result.responseTime || responseTime,  // 使用 API 返回的响应时间
                responseBody: JSON.stringify(result.fullResponse || result.data || {}),
                errorMessage: errorMessage,
                    server_timestamp_ms: getServerTime().getTime()  // 使用服务器时间
                });
        } catch (e) {
            addLog(`❌ 领取异常: ${code} - ${e.message}`, 'error');
            console.error('[Winna WS] 领取异常:', e);
            
            // 发送异常结果回服务器（使用服务器时间）
            sendClaimResultToServer({
                code: code,
                success: false,
                status: 'error',
                amount: null,
                currency: null,
                username: getUsernameFromPage(),
                responseTime: null,
                responseBody: null,
                errorMessage: e.message,
                server_timestamp_ms: getServerTime().getTime()  // 使用服务器时间
            });
        }
        ========== 原来的API调用逻辑（已注释） ========== */
    }
    
    // ==================== 通过DOM操作领取代码 ====================
    async function claimBonusCodeViaDOM(code) {
        try {
            console.log('[Winna WS] 开始通过DOM操作领取代码:', code);
            
            // 1. 查找输入框（通过多个特征确保准确性）
            const inputSelector = 'input[id="_r_2_"], input[name="promoCode"], input[placeholder*="Promo code" i], input[placeholder*="promo" i]';
            let input = await waitForElement(inputSelector, 5000);
            
            if (!input) {
                throw new Error('未找到输入框，请确保在正确的页面');
            }
            
            console.log('[Winna WS] ✅ 找到输入框:', input);
            
            // 2. 使用浏览器原生方法模拟真实输入
            input.focus();
            
            // 先删除现有内容（如果有的话）
            const currentValue = input.value || '';
            if (currentValue.length > 0) {
                console.log('[Winna WS] 检测到输入框有内容，先删除:', currentValue);
                // 选中所有文本
                input.select();
                input.setSelectionRange(0, currentValue.length);
                
                // 使用 execCommand 删除（更接近真实操作）
                try {
                    document.execCommand('delete', false, null);
                } catch (e) {
                    // 如果 execCommand 不支持，使用 Backspace 键
                    input.dispatchEvent(new KeyboardEvent('keydown', { 
                        key: 'Backspace',
                        keyCode: 8,
                        which: 8,
                        bubbles: true,
                        cancelable: true
                    }));
                    input.value = '';
                    input.dispatchEvent(new InputEvent('input', { 
                        bubbles: true, 
                        cancelable: true,
                        inputType: 'deleteContentBackward'
                    }));
                }
                
                await new Promise(resolve => setTimeout(resolve, 200));
            }
            
            // 使用 execCommand('insertText') 逐个字符插入（最接近真实输入）
            console.log('[Winna WS] 开始使用 execCommand 插入代码:', code);
            input.focus();
            
            for (let i = 0; i < code.length; i++) {
                const char = code[i];
                
                // 设置光标位置
                input.setSelectionRange(i, i);
                
                // 使用 execCommand 插入字符（这是浏览器原生方法，最接近真实输入）
                try {
                    const success = document.execCommand('insertText', false, char);
                    if (!success) {
                        // 如果 execCommand 失败，回退到键盘事件
                        console.warn('[Winna WS] execCommand 失败，使用键盘事件:', char);
                        input.value = code.substring(0, i + 1);
                        input.dispatchEvent(new InputEvent('input', {
                            bubbles: true,
                            cancelable: true,
                            inputType: 'insertText',
                            data: char
                        }));
                    }
                } catch (e) {
                    // execCommand 可能不支持，使用键盘事件
                    console.warn('[Winna WS] execCommand 异常，使用键盘事件:', e);
                    input.value = code.substring(0, i + 1);
                    input.dispatchEvent(new InputEvent('input', {
                        bubbles: true,
                        cancelable: true,
                        inputType: 'insertText',
                        data: char
                    }));
                }
                
                // 每个字符之间稍微延迟，模拟真实输入速度
                await new Promise(resolve => setTimeout(resolve, 100));
            }
            
            // 确保值正确
            if (input.value !== code) {
                console.warn('[Winna WS] 输入值不匹配，修正为:', code);
                input.value = code;
                input.dispatchEvent(new InputEvent('input', {
                    bubbles: true,
                    cancelable: true,
                    inputType: 'insertText',
                    data: code
                }));
            }
            
            // 触发 change 事件
            input.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
            
            console.log('[Winna WS] ✅ 已填写代码到输入框（使用 execCommand）');
            console.log('[Winna WS] 当前输入框值:', input.value);
            
            // 等待并检查按钮是否启用
            let buttonCheckCount = 0;
            while (buttonCheckCount < 30) {
                await new Promise(resolve => setTimeout(resolve, 100));
                const testButton = document.querySelector('button[type="submit"]');
                if (testButton) {
                    const text = testButton.textContent?.toLowerCase().trim();
                    if ((text === 'apply' || text.includes('apply'))) {
                        if (!testButton.disabled) {
                            console.log('[Winna WS] ✅ 按钮已启用');
                            break;
                        } else {
                            console.log('[Winna WS] ⏳ 按钮仍禁用，继续等待...', buttonCheckCount + 1);
                        }
                    }
                }
                buttonCheckCount++;
            }
            
            // 等待一下，让页面处理输入并启用按钮
            await new Promise(resolve => setTimeout(resolve, 300));
            
            // 等待一下，让页面处理输入
            await new Promise(resolve => setTimeout(resolve, 300));
            
            // 3. 查找领取按钮（通过多个特征确保准确性）
            // 优先查找 type="submit" 的按钮，且包含 "apply" 文本
            let button = null;
            
            // 方式1: 查找所有 submit 按钮，然后筛选包含 "apply" 文本的
            const submitButtons = document.querySelectorAll('button[type="submit"]');
            for (const btn of submitButtons) {
                const text = btn.textContent?.toLowerCase().trim();
                if (text === 'apply' || text.includes('apply')) {
                    button = btn;
                    break;
                }
            }
            
            // 方式2: 如果没找到，查找所有按钮，筛选包含 "apply" 文本且是 submit 类型
            if (!button) {
                const allButtons = document.querySelectorAll('button');
                for (const btn of allButtons) {
                    const text = btn.textContent?.toLowerCase().trim();
                    if ((text === 'apply' || text.includes('apply')) && btn.type === 'submit') {
                        button = btn;
                        break;
                    }
                }
            }
            
            // 方式3: 如果还是没找到，等待按钮出现（可能页面还在加载）
            if (!button) {
                let waitCount = 0;
                while (!button && waitCount < 50) {
                    await new Promise(resolve => setTimeout(resolve, 100));
                    const allButtons = document.querySelectorAll('button[type="submit"]');
                    for (const btn of allButtons) {
                        const text = btn.textContent?.toLowerCase().trim();
                        if (text === 'apply' || text.includes('apply')) {
                            button = btn;
                            break;
                        }
                    }
                    waitCount++;
                }
            }
            
            if (!button) {
                throw new Error('未找到领取按钮，请确保在正确的页面');
            }
            
            console.log('[Winna WS] ✅ 找到领取按钮:', button);
            
            // 检查按钮是否被禁用
            if (button.disabled) {
                console.log('[Winna WS] ⚠️ 按钮当前被禁用，等待启用...');
                // 等待按钮启用（最多等待3秒）
                let waitCount = 0;
                while (button.disabled && waitCount < 30) {
                    await new Promise(resolve => setTimeout(resolve, 100));
                    waitCount++;
                }
                
                if (button.disabled) {
                    throw new Error('按钮一直处于禁用状态，可能代码格式不正确或页面未准备好');
                }
            }
            
            // 4. 点击按钮
            console.log('[Winna WS] 点击领取按钮...');
            button.click();
            
            // 5. 等待领取结果（监听网络请求或页面变化）
            console.log('[Winna WS] ⏳ 开始等待领取结果...');
            const result = await waitForClaimResult(code, 15000);
            
            console.log('[Winna WS] ✅ 领取结果已返回:', result);
            console.log('[Winna WS] 结果详情:', {
                success: result.success,
                status: result.status,
                errorMessage: result.errorMessage,
                responseBody: result.responseBody
            });
            return result;
            
        } catch (e) {
            console.error('[Winna WS] DOM操作领取失败:', e);
            return {
                success: false,
                status: 'error',
                errorMessage: e.message,
                responseBody: null
            };
        }
    }
    
    // 等待元素出现
    async function waitForElement(selector, timeout = 5000) {
        const startTime = Date.now();
        
        // 先尝试直接查找
        let element = document.querySelector(selector);
        if (element) {
            return element;
        }
        
        // 如果没找到，等待并轮询
        return new Promise((resolve) => {
            const checkInterval = setInterval(() => {
                element = document.querySelector(selector);
                if (element) {
                    clearInterval(checkInterval);
                    resolve(element);
                } else if (Date.now() - startTime > timeout) {
                    clearInterval(checkInterval);
                    resolve(null);
                }
            }, 100);
        });
    }
    
    // 等待领取结果（通过监听网络请求或页面变化）
    async function waitForClaimResult(code, timeout = 15000) {
        const startTime = Date.now();
        
        return new Promise((resolve) => {
            let requestIntercepted = false;
            
            // 方式1: 拦截 fetch 请求
            const originalFetch = window.fetch;
            window.fetch = function(...args) {
                const [url, options] = args;
                const urlStr = typeof url === 'string' ? url : url.toString();
                
                // 检查是否是领取API请求，且请求体包含 turnstileToken（第二次请求）
                if (urlStr.includes('/v2/bonus') && options?.method === 'POST') {
                    // 检查请求体是否包含 turnstileToken
                    let hasToken = false;
                    if (options?.body) {
                        try {
                            const bodyStr = typeof options.body === 'string' ? options.body : JSON.stringify(options.body);
                            if (bodyStr.includes('turnstileToken') || bodyStr.includes('turnstile')) {
                                hasToken = true;
                            }
                        } catch (e) {
                            // 忽略解析错误
                        }
                    }
                    
                    // 只有包含 turnstileToken 的请求才拦截（第二次请求）
                    if (hasToken) {
                        requestIntercepted = true;
                        console.log('[Winna WS] ✅ 检测到 fetch 领取API请求（包含 turnstileToken）:', urlStr);
                        
                        // 恢复原始fetch（只拦截一次）
                        window.fetch = originalFetch;
                        
                        // 调用原始fetch并监听响应
                        return originalFetch.apply(this, args).then(async (response) => {
                        console.log('[Winna WS] 领取API响应状态:', response.status, response.statusText);
                        
                        // 克隆响应，这样原始响应仍然可以被页面使用
                        const clonedResponse = response.clone();
                        
                        // 无论状态码是什么，都尝试解析响应体
                        let responseData = {};
                        try {
                            const responseText = await clonedResponse.text();
                            if (responseText) {
                                responseData = JSON.parse(responseText);
                            }
                        } catch (e) {
                            console.warn('[Winna WS] 无法解析响应体:', e);
                            responseData = { error: `HTTP ${response.status}: ${response.statusText}` };
                        }
                        
                        console.log('[Winna WS] 领取API响应数据:', responseData);
                        
                        // 解析响应（无论状态码是什么，都解析响应体）
                        const result = parseClaimResponse(responseData, response.status);
                        console.log('[Winna WS] 解析后的结果:', result);
                        resolve(result);
                        
                            // 返回原始响应（页面可以正常使用）
                            return response;
                        }).catch((error) => {
                            console.error('[Winna WS] 领取API请求失败:', error);
                            resolve({
                                success: false,
                                status: 'error',
                                errorMessage: error.message,
                                responseBody: null
                            });
                            throw error;
                        });
                    } else {
                        // 第一次请求（不包含 token），不拦截，继续执行
                        console.log('[Winna WS] 检测到第一次请求（不包含 turnstileToken），跳过拦截');
                    }
                }
                
                return originalFetch.apply(this, args);
            };
            
            // 方式2: 拦截 XMLHttpRequest（某些页面可能使用 XHR）
            const originalXHROpen = XMLHttpRequest.prototype.open;
            const originalXHRSend = XMLHttpRequest.prototype.send;
            
            XMLHttpRequest.prototype.open = function(method, url, ...rest) {
                this._url = url;
                this._method = method;
                return originalXHROpen.apply(this, [method, url, ...rest]);
            };
            
            XMLHttpRequest.prototype.send = function(...args) {
                if (this._url && this._url.includes('/v2/bonus') && this._method === 'POST') {
                    // 检查请求体是否包含 turnstileToken
                    let hasToken = false;
                    if (args[0]) {
                        try {
                            const bodyStr = typeof args[0] === 'string' ? args[0] : JSON.stringify(args[0]);
                            if (bodyStr.includes('turnstileToken') || bodyStr.includes('turnstile')) {
                                hasToken = true;
                            }
                        } catch (e) {
                            // 忽略解析错误
                        }
                    }
                    
                    // 只有包含 turnstileToken 的请求才拦截（第二次请求）
                    if (hasToken) {
                        requestIntercepted = true;
                        console.log('[Winna WS] ✅ 检测到 XMLHttpRequest 领取API请求（包含 turnstileToken）:', this._url);
                        
                        // 恢复原始方法（只拦截一次）
                        XMLHttpRequest.prototype.open = originalXHROpen;
                        XMLHttpRequest.prototype.send = originalXHRSend;
                        
                        // 监听响应
                        this.addEventListener('load', function() {
                        console.log('[Winna WS] XMLHttpRequest 响应状态:', this.status, this.statusText);
                        
                        let responseData = {};
                        try {
                            const responseText = this.responseText;
                            if (responseText) {
                                responseData = JSON.parse(responseText);
                            }
                        } catch (e) {
                            console.warn('[Winna WS] 无法解析 XMLHttpRequest 响应体:', e);
                            responseData = { error: `HTTP ${this.status}: ${this.statusText}` };
                        }
                        
                            console.log('[Winna WS] XMLHttpRequest 响应数据:', responseData);
                            
                            // 解析响应
                            const result = parseClaimResponse(responseData, this.status);
                            console.log('[Winna WS] 解析后的结果:', result);
                            resolve(result);
                        });
                        
                        this.addEventListener('error', function() {
                            console.error('[Winna WS] XMLHttpRequest 请求失败');
                            resolve({
                                success: false,
                                status: 'error',
                                errorMessage: 'XMLHttpRequest 请求失败',
                                responseBody: null
                            });
                        });
                    } else {
                        // 第一次请求（不包含 token），不拦截，继续执行
                        console.log('[Winna WS] 检测到第一次 XMLHttpRequest 请求（不包含 turnstileToken），跳过拦截');
                    }
                }
                
                return originalXHRSend.apply(this, args);
            };
            
            // 方式3: 超时处理
            setTimeout(() => {
                if (!requestIntercepted) {
                    // 恢复原始方法
                    window.fetch = originalFetch;
                    XMLHttpRequest.prototype.open = originalXHROpen;
                    XMLHttpRequest.prototype.send = originalXHRSend;
                    
                    console.warn('[Winna WS] ⚠️ 等待领取结果超时（未拦截到请求）');
                    console.warn('[Winna WS] 提示：页面可能使用了其他方式发送请求，或请求已被其他拦截器处理');
                    resolve({
                        success: false,
                        status: 'error',
                        errorMessage: '等待领取结果超时',
                        responseBody: null
                    });
                }
            }, timeout);
        });
    }
    
    // 解析领取响应
    function parseClaimResponse(responseData, httpStatus = 200) {
        // 检查是否有错误（Winna API 错误格式: { "message": { "key": "...", "value": ... } }）
        if (responseData.message && typeof responseData.message === 'object' && responseData.message.key) {
            const errorKey = responseData.message.key;
            const errorValue = responseData.message.value;
            
            let status = 'error';
            let errorMessage = '未知错误';
            
            if (errorKey === 'BONUS_CODE_ERROR_INVALID' || errorKey.includes('INVALID')) {
                status = 'not_found';
                errorMessage = '代码不存在';
            } else if (errorKey === 'BONUS_CODE_ERROR_MINIMUM_WAGER' || errorKey.includes('WAGER')) {
                status = 'weekly_wager_requirement';
                errorMessage = errorValue ? `投注额不足（需要 ${errorValue}）` : '投注额不足';
            } else if (errorKey.includes('EXPIRED') || errorKey.includes('SESSION')) {
                status = 'session_expired';
                errorMessage = '会话已过期';
            } else if (errorKey.includes('ALREADY') || errorKey.includes('CLAIMED')) {
                status = 'already_claimed';
                errorMessage = '已领取过';
            } else if (errorKey.includes('INACTIVE')) {
                status = 'inactive';
                errorMessage = '代码已失效';
            } else {
                errorMessage = errorKey;
            }
            
            console.log('[Winna WS] 解析错误响应:', { status, errorMessage, httpStatus });
            
            return {
                success: false,
                status: status,
                errorMessage: errorMessage,
                responseBody: responseData
            };
        }
        
        // 如果 HTTP 状态码不是 2xx，但响应体没有错误格式，也当作错误处理
        if (httpStatus < 200 || httpStatus >= 300) {
            console.log('[Winna WS] HTTP 状态码错误:', httpStatus);
            return {
                success: false,
                status: 'error',
                errorMessage: `HTTP ${httpStatus}: ${responseData.error || responseData.message || '请求失败'}`,
                responseBody: responseData
            };
        }
        
        // 成功情况（HTTP 2xx 且没有错误消息）
        const amount = responseData.amount || responseData.bonus || responseData.bonusAmount || null;
        const currency = responseData.currency || null;
        
        console.log('[Winna WS] 解析成功响应:', { amount, currency });
        
        return {
            success: true,
            status: 'claim_success',
            amount: amount,
            currency: currency,
            responseBody: responseData
        };
    }
    
    // 从页面中获取用户名（适配 Winna）
    function getUsernameFromPage() {
        try {
            // 方式1: 从页面的用户信息元素中获取
            const userElements = document.querySelectorAll('[data-username], [class*="username"], [class*="user"], [id*="username"], [id*="user"]');
            for (const el of userElements) {
                const username = el.textContent?.trim() || el.getAttribute('data-username') || el.getAttribute('data-user');
                if (username && username.length > 0 && username.length < 50) {
                    console.log('[Winna WS] 从页面元素中提取到用户名:', username);
                    return username;
                }
            }
            
            // 方式2: 从 localStorage 中获取
            for (let key of Object.keys(localStorage)) {
                if (key.toLowerCase().includes('user') && !key.toLowerCase().includes('token')) {
                    const value = localStorage.getItem(key);
                    if (value && value.length > 0 && value.length < 50) {
                        console.log('[Winna WS] 从 localStorage 中提取到用户名:', value);
                        return value;
                    }
                }
            }
            
            // 方式4: 从 URL 或页面标题中提取
            const urlMatch = window.location.href.match(/\/user\/([^\/]+)/);
            if (urlMatch) {
                console.log('[Winna WS] 从 URL 中提取到用户名:', urlMatch[1]);
                return urlMatch[1];
            }
            
            // 方式5: 从所有 script 标签中搜索用户名（备用方案）
            const allScripts = document.querySelectorAll('script');
            for (const script of allScripts) {
                const content = script.textContent || script.innerHTML;
                // 搜索 "name":"用户名" 的模式
                const nameMatch = content.match(/"name"\s*:\s*"([^"]{1,50})"/);
                if (nameMatch && nameMatch[1]) {
                    const potentialUsername = nameMatch[1];
                    // 过滤掉明显不是用户名的值（如 "足球"、"新游戏" 等）
                    if (potentialUsername.length >= 3 && 
                        potentialUsername.length <= 20 && 
                        /^[a-zA-Z0-9_-]+$/.test(potentialUsername)) {
                        console.log('[Winna WS] 从 script 内容中提取到用户名:', potentialUsername);
                        return potentialUsername;
                    }
                }
            }
        } catch (e) {
            console.warn('[Winna WS] 获取用户名失败:', e);
        }
        console.warn('[Winna WS] 未能提取到用户名');
        return null;
    }
    
    // 发送领取结果回服务器
    function sendClaimResultToServer(resultData) {
        console.log('[Winna WS] ========== sendClaimResultToServer 开始 ==========');
        console.log('[Winna WS] 📤 准备发送领取结果到服务器:', resultData);
        console.log('[Winna WS] 📤 数据代码:', resultData.code);
        console.log('[Winna WS] 📤 数据状态:', resultData.status);
        
        // 检查 WebSocket 对象
        if (!ws) {
            console.error('[Winna WS] ❌ WebSocket 对象不存在');
            console.error('[Winna WS] ❌ 无法发送数据，WebSocket 未初始化');
            addLog('❌ WebSocket 未连接，无法发送领取结果', 'error');
            return;
        }
        
        // 检查 WebSocket 连接状态
        const wsState = ws.readyState;
        console.log('[Winna WS] 🔍 WebSocket 状态检查:', wsState);
        console.log('[Winna WS] 🔍 WebSocket 状态说明: 0=CONNECTING, 1=OPEN, 2=CLOSING, 3=CLOSED');
        
        if (wsState !== WebSocket.OPEN) {
            console.error('[Winna WS] ❌ WebSocket 未连接，当前状态:', wsState);
            console.error('[Winna WS] ❌ 无法发送数据，WebSocket 状态不是 OPEN');
            addLog(`❌ WebSocket 未连接（状态: ${wsState}），无法发送领取结果`, 'error');
            return;
        }
        
        console.log('[Winna WS] ✅ WebSocket 连接正常，准备构建消息...');
        
        try {
            const message = {
                type: 'claim_result',
                user_id: USER_ID,  // 用户标识符（用于区分不同使用者）
                code: resultData.code,
                success: resultData.success,
                status: resultData.status,
                amount: resultData.amount,
                currency: resultData.currency,
                username: resultData.username || getUsernameFromPage(),  // Winna 账号用户名
                responseTime: resultData.responseTime,  // 服务器端会转换为 response_time_ms
                responseBody: resultData.responseBody,
                errorMessage: resultData.errorMessage,
                timestamp: getServerTime().toISOString(),  // 使用服务器时间
                server_timestamp_ms: resultData.server_timestamp_ms || getServerTime().getTime()  // 确保包含服务器时间戳
            };
            
            console.log('[Winna WS] 📦 构建的消息对象:', message);
            
            const messageStr = JSON.stringify(message);
            console.log('[Winna WS] 📤 准备发送的消息JSON:', messageStr);
            console.log('[Winna WS] 📤 消息长度:', messageStr.length, '字节');
            
            // 发送消息
            console.log('[Winna WS] 📤 调用 ws.send()...');
            ws.send(messageStr);
            console.log('[Winna WS] ✅ ws.send() 调用成功');
            console.log('[Winna WS] ✅ 已发送领取结果到服务器');
            console.log('[Winna WS] ========== sendClaimResultToServer 完成 ==========');
        } catch (e) {
            console.error('[Winna WS] ❌ 发送领取结果失败:', e);
            console.error('[Winna WS] ❌ 错误类型:', e.name);
            console.error('[Winna WS] ❌ 错误消息:', e.message);
            console.error('[Winna WS] ❌ 错误堆栈:', e.stack);
            addLog(`❌ 发送领取结果失败: ${e.message}`, 'error');
        }
    }

    // ==================== Winna 领取接口（两阶段流程）====================
    async function claimBonusCodeViaAPI(code) {
        const totalStartTime = performance.now();
        
        try {
            // 获取必要的请求信息
            const headers = getRequestHeaders();
            const apiUrl = 'https://api2.winna.com/v2/bonus';
            
            // ========== 第一阶段：检查代码有效性（不包含 turnstileToken）==========
            console.log('[Winna WS] 📋 第一阶段：检查代码有效性...');
            const checkStartTime = performance.now();
            
            const checkPayload = {
                "code": code
                // 不包含 turnstileToken
            };
            
            console.log('[Winna WS] 发送检查请求到:', apiUrl);
            console.log('[Winna WS] 请求体（第一阶段）:', checkPayload);
            
            const checkResponse = await fetch(apiUrl, {
                method: 'POST',
                headers: headers,
                credentials: 'include',
                body: JSON.stringify(checkPayload)
            });
            
            const checkResponseTime = Math.round(performance.now() - checkStartTime);
            console.log('[Winna WS] 第一阶段响应状态:', checkResponse.status, checkResponse.statusText);
            
            // 解析第一阶段响应（无论状态码是什么，都要先解析响应体）
            let checkResponseData = {};
            try {
                const responseText = await checkResponse.text();
                if (responseText) {
                    checkResponseData = JSON.parse(responseText);
                }
            } catch (e) {
                console.warn('[Winna WS] 无法解析第一阶段响应:', e);
                checkResponseData = { error: `HTTP ${checkResponse.status}: ${checkResponse.statusText}` };
            }
            
            console.log('[Winna WS] 第一阶段响应:', checkResponseData);
            
            // 检查是否需要 Token（即使返回 403，如果响应体包含 requiresToken: true，也要继续）
            if (checkResponseData.requiresToken === true) {
                // 代码有效，需要 Token，进入第二阶段
                console.log('[Winna WS] ✅ 代码有效，需要 Turnstile Token，进入第二阶段...');
                if (checkResponse.status === 403) {
                    console.log('[Winna WS] ℹ️ 注意：虽然返回 403，但响应包含 requiresToken: true，继续流程');
                }
            } else {
                // 处理非 200 状态码且没有 requiresToken 的情况
                if (!checkResponse.ok) {
                    console.error('[Winna WS] 第一阶段错误响应:', checkResponseData);
                    
                    // 403 错误且没有 requiresToken，通常是认证问题
                    if (checkResponse.status === 403) {
                        const authInfo = getWinnaAuthInfo();
                        console.error('[Winna WS] ❌ 403 Forbidden - 认证失败');
                        console.error('[Winna WS] 当前 Cookie 长度:', authInfo.cookie ? authInfo.cookie.length : 0);
                        
                        return {
                            success: false,
                            status: 'error_403',
                            error: '403 Forbidden - 认证失败，请检查 Cookie',
                            errorKey: checkResponseData.message?.key || 'HTTP_403',
                            fullResponse: checkResponseData,
                            responseTime: checkResponseTime
                        };
                    }
                    
                    // 其他 HTTP 错误
                    return {
                        success: false,
                        status: 'error',
                        error: `HTTP ${checkResponse.status}: ${checkResponse.statusText}`,
                        errorKey: checkResponseData.message?.key || `HTTP_${checkResponse.status}`,
                        fullResponse: checkResponseData,
                        responseTime: checkResponseTime
                    };
                }
                
                // 200 状态码但没有 requiresToken，检查是否有错误信息
                // 检查是否有错误信息（代码无效的情况）
                if (checkResponseData.message && typeof checkResponseData.message === 'object') {
                    const errorKey = checkResponseData.message.key;
                    const errorValue = checkResponseData.message.value;
                    
                    // 映射错误状态
                    let status = 'error';
                    let errorStatus = '未知错误';
                    
                    if (errorKey === 'BONUS_CODE_ERROR_INVALID' || errorKey.includes('INVALID')) {
                        status = 'not_found';
                        errorStatus = '代码不存在';
                    } else if (errorKey === 'BONUS_CODE_ERROR_MINIMUM_WAGER' || errorKey.includes('WAGER')) {
                        status = 'weekly_wager_requirement';
                        errorStatus = errorValue ? `投注额不足（需要 ${errorValue}）` : '投注额不足';
                    } else if (errorKey.includes('EXPIRED') || errorKey.includes('SESSION')) {
                        status = 'session_expired';
                        errorStatus = '会话已过期';
                    } else if (errorKey.includes('ALREADY') || errorKey.includes('CLAIMED')) {
                        status = 'already_claimed';
                        errorStatus = '已领取过';
                    } else if (errorKey.includes('INACTIVE')) {
                        status = 'inactive';
                        errorStatus = '代码已失效';
                    } else {
                        errorStatus = errorKey;
                    }
                    
                    console.error('[Winna WS] ❌ 代码无效:', errorStatus);
                    
                    return {
                        success: false,
                        status: status,
                        error: errorStatus,
                        errorKey: errorKey,
                        errorValue: errorValue,
                        fullResponse: checkResponseData,
                        responseTime: checkResponseTime
                    };
                }
                
                // 未知响应格式
                console.warn('[Winna WS] ⚠️ 未知的响应格式:', checkResponseData);
                return {
                    success: false,
                    status: 'error',
                    error: '未知的响应格式',
                    fullResponse: checkResponseData,
                    responseTime: checkResponseTime
                };
            }
            
            // ========== 第二阶段：获取 Token 并完成领取 ==========
            console.log('[Winna WS] 🔐 第二阶段：获取 Turnstile Token 并完成领取...');
            const claimStartTime = performance.now();
            
            // 获取 Turnstile Token
            const currency = 'usdt';  // 默认货币类型
            let turnstileToken = await getTurnstileToken(code, currency);
            
            if (!turnstileToken) {
                // 如果获取失败，尝试刷新一次
                console.log('[Winna WS] Token 获取失败，尝试刷新...');
                const refreshedToken = await refreshTurnstileToken();
                if (!refreshedToken) {
                    return {
                        success: false,
                        status: 'error',
                        error: '获取 Turnstile Token 失败，请确保页面已加载完成',
                        fullResponse: checkResponseData,
                        responseTime: checkResponseTime
                    };
                }
                turnstileToken = refreshedToken;
            }
            
            console.log('[Winna WS] ✅ Turnstile Token 获取成功');
            
            // 等待一下，确保Turnstile验证完成，Cookie中的cf_clearance已更新
            // 检查Cookie中是否包含cf_clearance，如果没有则等待
            let waitCount = 0;
            const maxWait = 50; // 最多等待50次（约10秒）
            while (waitCount < maxWait && !document.cookie.includes('cf_clearance')) {
                await new Promise(resolve => setTimeout(resolve, 200)); // 等待200ms
                waitCount++;
            }
            
            if (document.cookie.includes('cf_clearance')) {
                console.log('[Winna WS] ✅ cf_clearance Cookie 已更新');
            } else {
                console.warn('[Winna WS] ⚠️ 等待后仍未检测到 cf_clearance，继续发送请求');
            }
            
            // 重新获取请求头（确保使用最新的Cookie，包括更新后的cf_clearance）
            const updatedHeaders = getRequestHeaders();
            
            // 使用 Token 后立即在后台刷新下一个 Token（不阻塞当前请求）
            refreshTurnstileToken().catch(e => {
                console.error('[Winna WS] 后台刷新 Token 失败:', e);
            });
            
            // 构建包含 Token 的请求体
            const claimPayload = {
                    "code": code,
                    "turnstileToken": turnstileToken
            };
            
            console.log('[Winna WS] 发送领取请求到:', apiUrl);
            console.log('[Winna WS] 请求体（第二阶段）:', { code: code, turnstileToken: '***' });
            
            // 发送领取请求（使用更新后的请求头）
            const claimResponse = await fetch(apiUrl, {
                method: 'POST',
                headers: updatedHeaders,
                credentials: 'include',
                body: JSON.stringify(claimPayload)
            });
            
            const claimResponseTime = Math.round(performance.now() - claimStartTime);
            const totalResponseTime = Math.round(performance.now() - totalStartTime);
            console.log('[Winna WS] 第二阶段响应状态:', claimResponse.status, claimResponse.statusText);
            
            // 处理非 200 状态码
            if (!claimResponse.ok) {
                let responseData = {};
                try {
                    const responseText = await claimResponse.text();
                    if (responseText) {
                        responseData = JSON.parse(responseText);
                    }
                } catch (e) {
                    responseData = { error: `HTTP ${claimResponse.status}: ${claimResponse.statusText}` };
                }
                
                console.error('[Winna WS] 第二阶段错误响应:', responseData);
                
                if (claimResponse.status === 403) {
                    return {
                        success: false,
                        status: 'error_403',
                        error: '403 Forbidden - 认证失败',
                        errorKey: responseData.message?.key || 'HTTP_403',
                        fullResponse: responseData,
                        responseTime: totalResponseTime
                    };
                }
                
                return {
                    success: false,
                    status: 'error',
                    error: `HTTP ${claimResponse.status}: ${claimResponse.statusText}`,
                    errorKey: responseData.message?.key || `HTTP_${claimResponse.status}`,
                    fullResponse: responseData,
                    responseTime: totalResponseTime
                };
            }
            
            // 解析第二阶段响应（实际领取结果）
            const claimResponseData = await claimResponse.json();
            console.log('[Winna WS] 第二阶段响应（领取结果）:', claimResponseData);
            
            // 解析领取结果（Winna API 格式）
            // Winna 错误格式: { "message": { "key": "BONUS_CODE_ERROR_INVALID" } }
            // 或: { "message": { "key": "BONUS_CODE_ERROR_MINIMUM_WAGER", "value": 9000 } }
            
            // 检查是否有错误（Winna 的错误格式）
            let hasError = false;
            let errorKey = null;
            let errorValue = null;
            
            if (claimResponseData.message && typeof claimResponseData.message === 'object') {
                // Winna 错误格式: { message: { key: "...", value: ... } }
                if (claimResponseData.message.key) {
                    hasError = true;
                    errorKey = claimResponseData.message.key;
                    errorValue = claimResponseData.message.value;
                }
            } else if (claimResponseData.error || claimResponseData.message) {
                // 其他错误格式
                hasError = true;
                errorKey = claimResponseData.message || claimResponseData.error || '未知错误';
            }
            
            // 根据错误 key 映射状态
            let status = 'error';
                    let errorStatus = '未知错误';
            
            if (hasError && errorKey) {
                // 映射 Winna 错误 key 到状态
                if (errorKey === 'BONUS_CODE_ERROR_INVALID' || errorKey.includes('INVALID')) {
                    status = 'not_found';
                        errorStatus = '代码不存在';
                } else if (errorKey === 'BONUS_CODE_ERROR_MINIMUM_WAGER' || errorKey.includes('WAGER')) {
                    status = 'weekly_wager_requirement';
                    errorStatus = errorValue ? `投注额不足（需要 ${errorValue}）` : '投注额不足';
                } else if (errorKey.includes('EXPIRED') || errorKey.includes('SESSION')) {
                    status = 'session_expired';
                    errorStatus = '会话已过期';
                } else if (errorKey.includes('ALREADY') || errorKey.includes('CLAIMED')) {
                    status = 'already_claimed';
                        errorStatus = '已领取过';
                } else if (errorKey.includes('INACTIVE')) {
                    status = 'inactive';
                    errorStatus = '代码已失效';
                    } else {
                    errorStatus = errorKey;
                    }
                    
                console.error('[Winna WS] ❌ 领取失败:', errorStatus);
                
                    return { 
                        success: false, 
                    status: status,
                        error: errorStatus,
                    errorKey: errorKey,
                    errorValue: errorValue,
                    fullResponse: claimResponseData,
                    responseTime: totalResponseTime
                    };
                } else {
                // 没有错误，可能是成功
                // 从响应中提取金额和货币（如果有）
                const amount = claimResponseData.amount || claimResponseData.bonus || claimResponseData.bonusAmount || null;
                const currency = claimResponseData.currency || null;
                
                console.log('[Winna WS] ✅ 领取成功（或已尝试）');
                if (amount) {
                    console.log('[Winna WS] 金额:', amount, currency || 'USDT');
                }
                
                // 所有响应都回传到服务端，让服务端判断
                return {
                    success: true,  // 暂时标记为成功，实际由服务端判断
                    data: claimResponseData,
                    fullResponse: claimResponseData,
                    responseTime: totalResponseTime,
                    message: '已经尝试领取该code'  // 统一显示文案
                };
            }
        } catch (e) {
            const totalResponseTime = Math.round(performance.now() - totalStartTime);
            console.error('[Winna WS] API 请求异常:', e);
            return {
                success: false,
                status: 'error',
                error: e.message || '请求异常',
                fullResponse: null,  // 异常时没有响应数据
                responseTime: totalResponseTime
            };
        }
    }

    // ==================== 获取请求头 ====================
    function getRequestHeaders() {
        // 从页面中获取必要的请求头
        const authInfo = getWinnaAuthInfo();
        
        // 从浏览器获取 Cookie（必须从 document.cookie 获取，不能硬编码）
        // 每次获取最新的Cookie，因为Turnstile验证后cf_clearance会更新
        const cookie = document.cookie;
        
        // 生成Sentry trace ID（用于错误监控）
        const sentryTraceId = generateSentryTraceId();
        const sentryTrace = `${sentryTraceId}-${generateShortId()}-1`;
        const baggage = `sentry-environment=production,sentry-trace_id=${sentryTraceId},sentry-sample_rate=0.6,sentry-sampled=true`;
        
        const headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-encoding': 'gzip, deflate, br, zstd',
            'content-type': 'application/json',
            'origin': 'https://winna.com',
            'referer': 'https://winna.com/',
            'user-agent': navigator.userAgent,
            'sec-ch-ua-platform': '"Windows"',
            'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-fetch-site': 'same-site',
            'sec-fetch-mode': 'cors',
            'sec-fetch-dest': 'empty',
            'accept-language': navigator.language || 'zh-CN,zh;q=0.9',
            'priority': 'u=1, i',
            // Sentry监控头（正常请求包含这些）
            'baggage': baggage,
            'sentry-trace': sentryTrace
        };

        // 显式添加 Cookie（从浏览器本地获取，每次获取最新的）
        if (cookie) {
            headers['cookie'] = cookie;
            console.log('[Winna WS] 使用浏览器 Cookie（长度:', cookie.length, '）');
            // 检查是否包含cf_clearance（Turnstile验证后的Cookie）
            if (cookie.includes('cf_clearance')) {
                console.log('[Winna WS] ✅ Cookie 包含 cf_clearance（Turnstile验证已通过）');
        } else {
                console.warn('[Winna WS] ⚠️ Cookie 不包含 cf_clearance，可能需要等待Turnstile验证');
            }
        } else {
            console.warn('[Winna WS] ⚠️ 未找到 Cookie，可能影响请求');
        }

        // 添加 x-auth-uid
        if (authInfo.authUid) {
            headers['x-auth-uid'] = authInfo.authUid;
            console.log('[Winna WS] 使用 x-auth-uid:', authInfo.authUid);
        } else {
            console.warn('[Winna WS] ⚠️ 未找到 x-auth-uid，可能影响请求');
        }

        return headers;
    }

    // 生成Sentry Trace ID（32位十六进制字符串）
    function generateSentryTraceId() {
        return Array.from(crypto.getRandomValues(new Uint8Array(16)))
            .map(b => b.toString(16).padStart(2, '0'))
            .join('');
    }
    
    // 生成短ID（16位十六进制字符串）
    function generateShortId() {
        return Array.from(crypto.getRandomValues(new Uint8Array(8)))
            .map(b => b.toString(16).padStart(2, '0'))
            .join('');
    }

    // ==================== 获取 Winna 认证信息 ====================
    function getWinnaAuthInfo() {
        try {
            // 获取 x-auth-uid（从页面获取）
            let authUid = null;
            
            // 方式1: 从页面的全局变量中获取
            if (!authUid && window.winnaUid) {
                authUid = window.winnaUid;
                console.log('[Winna WS] 从全局变量获取到 uid:', authUid);
            }
            
            // 方式3: 从 localStorage/sessionStorage 中查找
            if (!authUid) {
            for (let key of Object.keys(localStorage)) {
                    if (key.toLowerCase().includes('uid') || key.toLowerCase().includes('userid')) {
                    const value = localStorage.getItem(key);
                        if (value && !isNaN(value)) {
                            authUid = value;
                            console.log('[Winna WS] 从 localStorage 获取到 uid:', authUid);
                            break;
                        }
                    }
                }
            }
            
            // 方式4: 从 Cookie 中解析 connect.sid（尝试提取用户ID，但通常无法直接解析）
            if (!authUid) {
                const cookies = document.cookie.split(';');
                for (let cookie of cookies) {
                    const [name, value] = cookie.trim().split('=');
                    if (name === 'connect.sid') {
                        // connect.sid 格式: s%3A... 需要解码
                        try {
                            const decoded = decodeURIComponent(value);
                            console.log('[Winna WS] 找到 connect.sid:', decoded.substring(0, 50) + '...');
                            // 注意：通常无法直接从 session 中提取用户ID，需要服务器端解析
                        } catch (e) {
                            console.warn('[Winna WS] 解析 connect.sid 失败:', e);
                        }
                    }
                }
            }
            
            // 获取完整 Cookie（从浏览器本地获取，这是最重要的）
            // document.cookie 会自动包含当前域名下的所有 Cookie
            const fullCookie = document.cookie;
            
            if (!fullCookie) {
                console.warn('[Winna WS] ⚠️ 未找到任何 Cookie，请确保已登录');
            } else {
                console.log('[Winna WS] 获取到 Cookie（长度:', fullCookie.length, '）');
                // 检查是否包含关键 Cookie
                if (fullCookie.includes('connect.sid')) {
                    console.log('[Winna WS] ✅ 找到 connect.sid Cookie');
                }
                if (fullCookie.includes('chat.jwt')) {
                    console.log('[Winna WS] ✅ 找到 chat.jwt Cookie');
                }
            }
            
            return {
                authUid: authUid,
                cookie: fullCookie
            };
        } catch (e) {
            console.error('[Winna WS] 获取认证信息失败:', e);
            return {
                authUid: null,
                cookie: document.cookie || ''
            };
        }
    }

    // ==================== Turnstile Token 获取器 ====================
    const TURNSTILE_SITE_KEY = '0x4AAAAAACHcU3E6UUbmv3p-';  // Winna 的 Turnstile Site Key
    let turnstileTokenCache = null;
    let turnstileWidgetId = null;
    let isRefreshingToken = false;  // 防止重复刷新
    let tokenRefreshPromise = null;  // 刷新 Promise，避免并发刷新

    // 初始化 Turnstile Token 获取器
    async function initTurnstileTokenGrabber() {
        try {
            // 加载 Cloudflare Turnstile API
            if (!window.turnstile) {
                await new Promise((resolve, reject) => {
                    const script = document.createElement('script');
                    script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
                    script.async = true;
                    script.defer = true;
                    script.onload = resolve;
                    script.onerror = reject;
                    document.head.appendChild(script);
                });
            }

            // 创建隐藏的渲染容器
            let container = document.getElementById('winna-ws-turnstile-container');
            if (!container) {
                container = document.createElement('div');
                container.id = 'winna-ws-turnstile-container';
                container.style.cssText = 'position: absolute; left: -9999px; width: 1px; height: 1px; overflow: hidden;';
                document.body.appendChild(container);
            } else {
                // 如果容器已存在但 widget ID 无效，清空容器以便重新渲染
                if (turnstileWidgetId && window.turnstile) {
                    try {
                        window.turnstile.remove(turnstileWidgetId);
                    } catch (e) {
                        // 忽略移除错误，可能 widget 已经不存在
                        console.warn('[Winna WS] 移除旧 widget 时出错（可忽略）:', e.message);
                    }
                }
                // 清空容器内容
                container.innerHTML = '';
                turnstileWidgetId = null;
            }

            // 渲染 Turnstile widget
            if (window.turnstile && !turnstileWidgetId) {
                turnstileWidgetId = window.turnstile.render(container, {
                    sitekey: TURNSTILE_SITE_KEY,
                    callback: function(token) {
                        console.log('[Winna WS] ✅ 成功获取 Turnstile Token:', token.substring(0, 20) + '...');
                        turnstileTokenCache = token;
                        window.__TURNSTILETOKEN__ = token;  // 也存储到全局变量
                        isRefreshingToken = false;
                        tokenRefreshPromise = null;
                    },
                    'error-callback': function(err) {
                        console.error('[Winna WS] ❌ Turnstile 错误:', err);
                        turnstileTokenCache = null;
                        isRefreshingToken = false;
                        tokenRefreshPromise = null;
                        // 错误后自动重试
                        setTimeout(() => {
                            refreshTurnstileToken();
                        }, 2000);
                    },
                    'expired-callback': function() {
                        console.warn('[Winna WS] ⚠️ Turnstile Token 已过期，正在自动刷新...');
                        turnstileTokenCache = null;
                        // 自动重置并重新获取
                        refreshTurnstileToken();
                    }
                });
                console.log('[Winna WS] ✅ Turnstile Token 获取器已初始化');
            }
        } catch (e) {
            console.error('[Winna WS] ❌ 初始化 Turnstile Token 获取器失败:', e);
        }
    }

    // 刷新 Turnstile Token（重置 widget 以获取新 Token）
    async function refreshTurnstileToken() {
        // 如果正在刷新，等待当前刷新完成
        if (isRefreshingToken && tokenRefreshPromise) {
            console.log('[Winna WS] Token 正在刷新中，等待完成...');
            return await tokenRefreshPromise;
        }

        if (!window.turnstile) {
            console.warn('[Winna WS] Turnstile API 未加载，尝试重新初始化...');
            await initTurnstileTokenGrabber();
            if (!window.turnstile) {
                console.error('[Winna WS] ❌ 无法加载 Turnstile API');
                return null;
            }
        }

        // 检查容器是否存在
        const container = document.getElementById('winna-ws-turnstile-container');
        if (!container) {
            console.warn('[Winna WS] Turnstile 容器不存在，重新初始化...');
            turnstileWidgetId = null;
            await initTurnstileTokenGrabber();
            if (!turnstileWidgetId) {
                console.error('[Winna WS] ❌ 无法初始化 Turnstile widget');
                return null;
            }
        }

        // 如果 widget ID 无效，重新初始化
        if (!turnstileWidgetId) {
            console.warn('[Winna WS] Turnstile widget ID 无效，重新初始化...');
            await initTurnstileTokenGrabber();
            if (!turnstileWidgetId) {
                console.error('[Winna WS] ❌ 无法获取 Turnstile widget ID');
                return null;
            }
        }

        isRefreshingToken = true;
        console.log('[Winna WS] 🔄 开始刷新 Turnstile Token...');
        
        // 创建刷新 Promise
        tokenRefreshPromise = new Promise((resolve) => {
            try {
                // 尝试重置 widget
                window.turnstile.reset(turnstileWidgetId);
            } catch (e) {
                // 如果 reset 失败（例如 widget 不存在），尝试重新初始化
                console.warn('[Winna WS] ⚠️ Reset 失败，尝试重新初始化 widget:', e.message);
                turnstileWidgetId = null;
                turnstileTokenCache = null;
                
                // 重新初始化
                initTurnstileTokenGrabber().then(() => {
                    // 等待新 widget 生成 token
                    const checkInterval = setInterval(() => {
                        if (turnstileTokenCache) {
                            clearInterval(checkInterval);
                            isRefreshingToken = false;
                            tokenRefreshPromise = null;
                            console.log('[Winna WS] ✅ Token 通过重新初始化获取成功');
                            resolve(turnstileTokenCache);
                        }
                    }, 500);
                    
                    // 10 秒超时
                    setTimeout(() => {
                        clearInterval(checkInterval);
                        if (!turnstileTokenCache) {
                            isRefreshingToken = false;
                            tokenRefreshPromise = null;
                            console.error('[Winna WS] ❌ 重新初始化后 Token 获取超时');
                            resolve(null);
                        }
                    }, 10000);
                }).catch(err => {
                    console.error('[Winna WS] ❌ 重新初始化失败:', err);
                    isRefreshingToken = false;
                    tokenRefreshPromise = null;
                    resolve(null);
                });
                return;
            }
            
            // 等待新 Token 生成（最多等待 10 秒）
            const checkInterval = setInterval(() => {
                if (turnstileTokenCache) {
                    clearInterval(checkInterval);
                    isRefreshingToken = false;
                    tokenRefreshPromise = null;
                    console.log('[Winna WS] ✅ Token 刷新成功');
                    resolve(turnstileTokenCache);
                }
            }, 500);
            
            // 10 秒超时
            setTimeout(() => {
                clearInterval(checkInterval);
                if (!turnstileTokenCache) {
                    isRefreshingToken = false;
                    tokenRefreshPromise = null;
                    console.error('[Winna WS] ❌ Token 刷新超时');
                    resolve(null);
                }
            }, 10000);
        });

        return await tokenRefreshPromise;
    }

    // ==================== 获取 Turnstile Token ====================
    async function getTurnstileToken(code, currency) {
        // 方式1: 从缓存中获取（如果已有）
        if (turnstileTokenCache) {
            console.log('[Winna WS] 使用缓存的 Turnstile Token');
            // 使用后立即刷新，确保下次有新的 Token
            refreshTurnstileToken().catch(e => {
                console.error('[Winna WS] 后台刷新 Token 失败:', e);
            });
            return turnstileTokenCache;
        }

        // 方式2: 从全局变量获取
        if (window.__TURNSTILETOKEN__) {
            turnstileTokenCache = window.__TURNSTILETOKEN__;
            // 使用后立即刷新
            refreshTurnstileToken().catch(e => {
                console.error('[Winna WS] 后台刷新 Token 失败:', e);
            });
            return turnstileTokenCache;
        }

        // 方式3: 确保 Turnstile 已初始化
        if (!window.turnstile || !turnstileWidgetId) {
            console.log('[Winna WS] 初始化 Turnstile Token 获取器...');
            await initTurnstileTokenGrabber();
            // 等待 Token 生成（最多等待 10 秒）
            for (let i = 0; i < 20; i++) {
                await new Promise(resolve => setTimeout(resolve, 500));
                if (turnstileTokenCache || window.__TURNSTILETOKEN__) {
                    turnstileTokenCache = turnstileTokenCache || window.__TURNSTILETOKEN__;
                    // 获取到 Token 后，立即在后台刷新下一个
                    refreshTurnstileToken().catch(e => {
                        console.error('[Winna WS] 后台刷新 Token 失败:', e);
                    });
                    return turnstileTokenCache;
                }
            }
        } else {
            // 如果 widget 已存在但 Token 不存在，刷新并等待
            console.log('[Winna WS] 刷新 Turnstile widget 以获取新 Token...');
            const newToken = await refreshTurnstileToken();
            if (newToken) {
                return newToken;
            }
        }

        // 方式4: 从拦截的网络请求中获取（如果页面已经发送过请求）
        if (window.__TURNSTILETOKEN__) {
            turnstileTokenCache = window.__TURNSTILETOKEN__;
            // 使用后立即刷新
            refreshTurnstileToken().catch(e => {
                console.error('[Winna WS] 后台刷新 Token 失败:', e);
            });
            return turnstileTokenCache;
        }

        console.warn('[Winna WS] ⚠️ 无法获取 Turnstile Token');
        return null;
    }

    // ==================== 拦截网络请求获取 Token ====================
    function interceptNetworkRequests() {
        // 拦截 fetch 请求，从请求头和请求体中获取 token 和 turnstile token
        const originalFetch = window.fetch;
        window.fetch = function(...args) {
            const [url, options] = args;
            
            // 获取 Turnstile token（从请求体中，Winna 格式）
            if (options && options.body) {
                try {
                    const body = typeof options.body === 'string' ? JSON.parse(options.body) : options.body;
                    // Winna 格式: { code: "...", turnstileToken: "..." }
                    if (body.turnstileToken) {
                        window.__TURNSTILETOKEN__ = body.turnstileToken;
                        console.log('[Winna WS] 从请求中获取到 Turnstile Token');
                    }
                } catch (e) {
                    // 忽略解析错误
                }
            }
            
            return originalFetch.apply(this, args);
        };

        // 拦截 XMLHttpRequest 的 send 方法，获取请求体中的 Turnstile token（Winna 格式）
        const originalSend = XMLHttpRequest.prototype.send;
        XMLHttpRequest.prototype.send = function(body) {
            if (body) {
                try {
                    const data = typeof body === 'string' ? JSON.parse(body) : body;
                    // Winna 格式: { code: "...", turnstileToken: "..." }
                    if (data.turnstileToken) {
                        window.__TURNSTILETOKEN__ = data.turnstileToken;
                        console.log('[Winna WS] 从 XHR 请求中获取到 Turnstile Token');
                    }
                } catch (e) {
                    // 忽略解析错误
                }
            }
            return originalSend.apply(this, arguments);
        };
    }

    // ==================== 初始化 ====================
    function init() {
        console.log('[Winna WS] 脚本初始化');
        createStatusUI();
        
        // 拦截网络请求以获取 Token
        interceptNetworkRequests();
        
        // 初始化 Turnstile Token 获取器
        initTurnstileTokenGrabber();
        
        // 等待页面加载完成
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => {
                setTimeout(connect, 1000);
            });
        } else {
            setTimeout(connect, 1000);
        }

        // 定期发送心跳
        setInterval(() => {
            if (ws && ws.readyState === WebSocket.OPEN) {
                lastPingTime = Date.now();  // 记录发送时间
                ws.send(JSON.stringify({ type: 'ping' }));
            }
        }, 30000);  // 每30秒发送一次心跳
    }

    // 启动脚本
    init();
})();

