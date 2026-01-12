// ==UserScript==
// @name         Stake code claim tool
// @namespace    http://tampermonkey.net/
// @version      1.0.0
// @description  
// @author       You
// @match        https://stake.com/*settings/offers*
// @match        https://stake.ac/*settings/offers*
// @match        https://stake.games/*settings/offers*
// @match        https://stake.bet/*settings/offers*
// @match        https://stake.pet/*settings/offers*
// @match        https://stake.mba/*settings/offers*
// @match        https://stake.jp/*settings/offers*
// @match        https://stake.bz/*settings/offers*
// @match        https://stake.ceo/*settings/offers*
// @match        https://stake.krd/*settings/offers*
// @match        https://staketr.com/*settings/offers*
// @match        https://stake1001.com/*settings/offers*
// @match        https://stake1002.com/*settings/offers*
// @match        https://stake1003.com/*settings/offers*
// @match        https://stake1021.com/*settings/offers*
// @match        https://stake1022.com/*settings/offers*
// @match        https://stake.us/settings/offers*
// @match        https://stake.br/settings/offers*
// @grant        none
// @connect      *
// ==/UserScript==

(function() {
    'use strict';

    // ==================== 配置 ====================
    // 注意：HTTPS 页面必须使用 wss:// (加密 WebSocket)，不能使用 ws://
    const WEBSOCKET_URL = 'wss://146.103.42.142:8765';  // 修改为你的服务器地址（使用 wss://）
    const RECONNECT_DELAY = 3000;  // 重连延迟（毫秒）
    const MAX_RECONNECT_ATTEMPTS = 10;  // 最大重连次数
    
    // ==================== 用户标识 ====================
    // 用户唯一标识符（用于区分不同使用者，一个用户可以有多个 Stake 账号）
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
            #stake-ws-panel {
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

            #stake-ws-panel.collapsed {
                width: 40px !important; height: 40px !important; border-radius: 50% !important; padding: 0 !important;
                background: #16191f; border-color: #3a3f4b;
                display: flex; align-items: center; justify-content: center;
            }
            #stake-ws-panel.collapsed .info-group,
            #stake-ws-panel.collapsed #stake-ws-log-container,
            #stake-ws-panel.collapsed #stake-ws-resize-handle,
            #stake-ws-panel.collapsed #stake-ws-username,
            #stake-ws-panel.collapsed #stake-ws-ping-vault-container,
            #stake-ws-panel.collapsed #stake-ws-test-vault-btn { display: none; }
            #stake-ws-panel.collapsed #stake-ws-header {
                background: transparent; border: none; margin: 0; padding: 0;
                width: 100%; height: 100%; justify-content: center;
            }
            #stake-ws-panel.collapsed .header-title { display: none; }

            #stake-ws-header {
                margin: -10px -10px 10px -10px; padding: 8px 12px;
                cursor: move; background: #16191f;
                display: flex; justify-content: space-between; align-items: center;
                border-bottom: 1px solid #23262d;
                position: relative;
                user-select: none;
            }
            #stake-ws-header:active { cursor: grabbing; }
            
            #stake-ws-close-btn {
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
            #stake-ws-close-btn:hover {
                background: rgba(255, 59, 48, 0.3);
                color: #ff6b60;
            }
            #stake-ws-panel.collapsed #stake-ws-close-btn { display: none; }
            
            #stake-ws-resize-handle {
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
            #stake-ws-resize-handle:hover {
                background: rgba(77, 238, 234, 0.2);
            }
            #stake-ws-resize-handle::after {
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

            #stake-ws-username {
                font-size: 12px;
                color: #b0b0b5;
                padding: 4px 8px;
                background: #16191f;
                border: 1px solid #23262d;
                border-radius: 4px;
                font-weight: 600;
                margin-bottom: 8px;
            }
            
            #stake-ws-ping-vault-container {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: 8px;
                gap: 8px;
            }
            #stake-ws-username .username-label {
                color: #8a8d92;
                margin-right: 6px;
            }
            #stake-ws-username .username-value {
                color: #6df5f0;
                font-weight: 700;
            }
            
            #stake-ws-ping {
                font-size: 12px;
                color: #b0b0b5;
                padding: 4px 8px;
                background: #16191f;
                border: 1px solid #23262d;
                border-radius: 4px;
                font-weight: 600;
                white-space: nowrap;
            }
            #stake-ws-ping .ping-label {
                color: #8a8d92;
                margin-right: 6px;
            }
            #stake-ws-ping .ping-value {
                color: #6df5f0;
                font-weight: 700;
            }
            
            #stake-ws-vault-switch {
                display: flex;
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
            #stake-ws-vault-switch:hover {
                background: #1a1d24;
            }
            #stake-ws-vault-switch .switch-label {
                color: #8a8d92;
            }
            #stake-ws-vault-switch .switch-checkbox {
                width: 36px;
                height: 20px;
                position: relative;
                background: #2a2d35;
                border-radius: 10px;
                cursor: pointer;
                transition: background 0.2s;
            }
            #stake-ws-vault-switch .switch-checkbox.active {
                background: #28a745;
            }
            #stake-ws-vault-switch .switch-checkbox::after {
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
            #stake-ws-vault-switch .switch-checkbox.active::after {
                left: 18px;
            }
            
            #stake-ws-test-vault-btn {
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
            #stake-ws-test-vault-btn:hover {
                background: #0056b3;
            }
            #stake-ws-test-vault-btn:active {
                background: #004085;
            }

            #stake-ws-log-container {
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

            #stake-ws-log-container::-webkit-scrollbar { width: 4px; }
            #stake-ws-log-container::-webkit-scrollbar-track { background: transparent; }
            #stake-ws-log-container::-webkit-scrollbar-thumb { background: #4a4d55; border-radius: 2px; }
            #stake-ws-log-container::-webkit-scrollbar-thumb:hover { background: #5a5d65; }
        `;
        document.head.appendChild(style);

        // 创建面板
        statusElement = document.createElement('div');
        statusElement.id = 'stake-ws-panel';
        statusElement.className = 'collapsed';
        statusElement.innerHTML = `
            <div id="stake-ws-header" title="拖动移动位置">
                <span class="header-title">Stake Auto Claim</span>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <div class="status-dot" id="stake-ws-status-dot"></div>
                    <div id="stake-ws-close-btn" title="收起">×</div>
                </div>
            </div>
            <div id="stake-ws-username">
                <span class="username-label">user:</span>
                <span class="username-value" id="stake-ws-username-value">-</span>
            </div>
            <div id="stake-ws-ping-vault-container">
                <div id="stake-ws-vault-switch">
                    <span class="switch-label">存入保险库</span>
                    <div class="switch-checkbox" id="stake-ws-vault-checkbox"></div>
                </div>
                <div id="stake-ws-ping">
                    <span class="ping-label">ping:</span>
                    <span class="ping-value" id="stake-ws-ping-value">-</span>
                </div>
            </div>
            <div id="stake-ws-test-vault-btn">测试存入 1 USDT</div>
            <div id="stake-ws-log-container"></div>
            <div id="stake-ws-resize-handle" title="拖动等比缩放"></div>
        `;
        document.body.appendChild(statusElement);

        logContainer = document.getElementById('stake-ws-log-container');
        statusDot = document.getElementById('stake-ws-status-dot');
        
        // 初始化时获取并显示用户名
        updateUsernameDisplay();
        
        // 初始化存入保险库开关
        initVaultSwitch();
        
        // 初始化测试存入保险库按钮
        initTestVaultButton();

        // 单击展开
        statusElement.addEventListener('click', (e) => {
            // 如果点击的是关闭按钮，不展开
            if (e.target.closest('#stake-ws-close-btn')) return;
            // 如果点击的是调整大小手柄，不展开
            if (e.target.closest('#stake-ws-resize-handle')) return;
            
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
        document.getElementById('stake-ws-close-btn').addEventListener('click', (e) => {
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

        const header = document.getElementById('stake-ws-header');
        header.addEventListener('mousedown', (e) => {
            // 如果点击的是关闭按钮，不拖动
            if (e.target.closest('#stake-ws-close-btn')) return;
            
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

        const resizeHandle = document.getElementById('stake-ws-resize-handle');
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
        const pingElement = document.getElementById('stake-ws-ping-value');
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
        const usernameElement = document.getElementById('stake-ws-username-value');
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
        const checkbox = document.getElementById('stake-ws-vault-checkbox');
        const switchContainer = document.getElementById('stake-ws-vault-switch');
        if (!checkbox || !switchContainer) return;
        
        // 从 localStorage 读取开关状态
        const savedState = localStorage.getItem('stake_vault_auto_deposit');
        const isEnabled = savedState === 'true';
        
        if (isEnabled) {
            checkbox.classList.add('active');
        }
        
        // 点击切换开关
        switchContainer.addEventListener('click', function() {
            const isActive = checkbox.classList.contains('active');
            if (isActive) {
                checkbox.classList.remove('active');
                localStorage.setItem('stake_vault_auto_deposit', 'false');
            } else {
                checkbox.classList.add('active');
                localStorage.setItem('stake_vault_auto_deposit', 'true');
            }
        });
    }

    // 初始化测试存入保险库按钮
    function initTestVaultButton() {
        const testBtn = document.getElementById('stake-ws-test-vault-btn');
        if (!testBtn) return;
        
        testBtn.addEventListener('click', async function() {
            // 禁用按钮，防止重复点击
            testBtn.style.opacity = '0.6';
            testBtn.style.cursor = 'not-allowed';
            testBtn.textContent = '测试中...';
            
            try {
                console.log('[Stake WS] 🧪 测试存入保险库: 1 USDT');
                addLog('🧪 测试存入保险库: 1 USDT', 'info');
                
                const result = await depositToVault(1, 'usdt');
                
                if (result.success) {
                    const depositedAmount = result.data?.amount || '1';
                    addLog(`✅ 测试成功: 存入 ${depositedAmount} USDT`, 'success');
                    console.log('[Stake WS] ✅ 测试存入保险库成功:', result.data);
                } else {
                    addLog(`❌ 测试失败: ${result.error}`, 'error');
                    console.error('[Stake WS] ❌ 测试存入保险库失败:', result.error);
                }
            } catch (e) {
                addLog(`❌ 测试异常: ${e.message}`, 'error');
                console.error('[Stake WS] ❌ 测试存入保险库异常:', e);
            } finally {
                // 恢复按钮状态
                testBtn.style.opacity = '1';
                testBtn.style.cursor = 'pointer';
                testBtn.textContent = '测试存入 1 USDT';
            }
        });
    }

    // 检查是否启用自动存入保险库
    function isVaultAutoDepositEnabled() {
        return localStorage.getItem('stake_vault_auto_deposit') === 'true';
    }

    // 存入保险库
    async function depositToVault(amount, currency) {
        try {
            // 获取 token（使用与领取接口相同的方式）
            const token = getStakeToken();
            if (!token) {
                console.error('[Stake WS] 无法获取 token，无法存入保险库');
                return { success: false, error: '无法获取 token' };
            }

            // 处理金额：向下取整到2位小数
            const originalAmount = parseFloat(amount);
            if (isNaN(originalAmount) || originalAmount <= 0) {
                console.error('[Stake WS] 无效的金额，无法存入保险库');
                return { success: false, error: '无效的金额' };
            }

            // 向下取整到2位小数
            const safeAmount = Math.floor(originalAmount * 100) / 100;
            
            // 如果处理后的金额小于最小值（0.01），则不存入
            if (safeAmount < 0.01) {
                console.warn(`[Stake WS] 金额太小（处理后: ${safeAmount}），跳过存入保险库`);
                return { success: false, error: '金额太小，无法存入' };
            }

            console.log(`[Stake WS] 金额处理: 原始=${originalAmount}, 向下取整=${safeAmount.toFixed(2)}`);

            // 构建 GraphQL mutation
            const mutation = `mutation CreateVaultDeposit($currency: CurrencyEnum!, $amount: Float!) {
                createVaultDeposit(currency: $currency, amount: $amount) {
                    id
                    amount
                    currency
                    user {
                        id
                        balances {
                            available {
                                amount
                                currency
                            }
                            vault {
                                amount
                                currency
                            }
                        }
                    }
                    __typename
                }
            }`;

            const variables = {
                currency: currency.toLowerCase(),
                amount: safeAmount  // 使用处理后的安全金额
            };

            // 发送请求
            const response = await fetch('https://stake.com/_api/graphql', {
                method: 'POST',
                headers: {
                    'accept': '*/*',
                    'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7',
                    'content-type': 'application/json',
                    'origin': 'https://stake.com',
                    'referer': 'https://stake.com/zh/settings/offers',
                    'x-access-token': token,
                    'x-language': 'zh',
                    'x-operation-name': 'CreateVaultDeposit',
                    'x-operation-type': 'query'
                },
                body: JSON.stringify({
                    query: mutation,
                    variables: variables
                })
            });

            const responseData = await response.json();

            if (responseData.data && responseData.data.createVaultDeposit) {
                console.log('[Stake WS] ✅ 存入保险库成功:', responseData.data.createVaultDeposit);
                return { success: true, data: responseData.data.createVaultDeposit };
            } else {
                const error = responseData.errors?.[0]?.message || '未知错误';
                console.error('[Stake WS] ❌ 存入保险库失败:', error);
                return { success: false, error: error };
            }
        } catch (e) {
            console.error('[Stake WS] ❌ 存入保险库异常:', e);
            return { success: false, error: e.message };
        }
    }


    // ==================== WebSocket 连接 ====================
    function connect() {
        if (isConnecting || (ws && ws.readyState === WebSocket.OPEN)) {
            return;
        }

        isConnecting = true;
        updateConnectionStatus('connecting');
        console.log('[Stake WS] 正在连接到服务器...');

        try {
            ws = new WebSocket(WEBSOCKET_URL);

            ws.onopen = function() {
                console.log('[Stake WS] 连接成功');
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
                        console.error('[Stake WS] 发送初始化消息失败:', e);
                    }
                }
                
                // 连接成功后，尝试关闭证书信任页面
                if (certWindow && !certWindow.closed) {
                    try {
                        certWindow.close();
                        console.log('[Stake WS] ✅ 证书已信任，已自动关闭证书页面');
                        certWindow = null;
                        certWindowOpened = false;  // 重置标志，允许下次重新打开
                    } catch (e) {
                        // 如果无法关闭（可能是跨域限制），提示用户手动关闭
                        console.log('[Stake WS] ✅ 证书已信任，请手动关闭证书页面');
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
                    console.error('[Stake WS] 解析消息失败:', e);
                }
            };

            ws.onerror = function(error) {
                const stateNames = {0: 'CONNECTING', 1: 'OPEN', 2: 'CLOSING', 3: 'CLOSED'};
                console.error('[Stake WS] 连接错误:', error);
                console.error('[Stake WS] WebSocket 状态:', ws.readyState, `(${stateNames[ws.readyState]})`);
                console.error('[Stake WS] 连接 URL:', WEBSOCKET_URL);
                console.error('[Stake WS] 错误详情:', {
                    type: error.type,
                    target: error.target,
                    timeStamp: error.timeStamp,
                    isTrusted: error.isTrusted
                });
                
                // 尝试获取更详细的错误信息
                if (ws.readyState === 3) { // CLOSED
                    console.error('[Stake WS] 连接已关闭，可能的原因：');
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
                                const port = urlMatch[2] || '8765';
                                const certUrl = `https://${host}:${port}/`;
                                
                                console.error('[Stake WS] 💡 检测到 SSL 证书问题，正在打开证书信任页面...');
                                console.log('[Stake WS] ⚠️ SSL 证书未信任，正在打开证书页面...');
                                
                                // 标记已打开证书页面
                                certWindowOpened = true;
                                
                                // 延迟打开证书页面，给用户时间看到提示
                                setTimeout(() => {
                                    // 在新标签页打开证书页面，让用户手动信任证书
                                    // 保存窗口引用，以便连接成功后自动关闭
                                    certWindow = window.open(certUrl, '_blank');
                                    
                                    // 显示详细提示（只在 console 中显示）
                                    console.log('[Stake WS] 📋 请在打开的页面中：');
                                    console.log('[Stake WS]    1. 点击"高级"或"Advanced"');
                                    console.log('[Stake WS]    2. 点击"继续访问"或"Proceed"');
                                    console.log('[Stake WS]    3. 信任证书后，页面会自动关闭');
                                    
                                    // 5秒后自动重连
                                    setTimeout(() => {
                                        console.log('[Stake WS] 🔄 5秒后自动重连...');
                                        setTimeout(() => {
                                            connect();
                                        }, 5000);
                                    }, 2000);
                                }, 1000);
                            } else {
                                console.error('[Stake WS] 💡 建议：在浏览器中访问服务器地址并接受证书');
                                console.error('[Stake WS] 连接错误: SSL 证书或网络问题');
                            }
                        } else if (isCertWindowOpen) {
                            // 证书页面已打开，只提示用户操作，不重复打开
                            console.log('[Stake WS] ⚠️ 证书页面已打开，请完成证书信任操作');
                        } else {
                            // 证书页面已关闭但连接仍失败，可能是其他问题
                            console.log('[Stake WS] ⚠️ 证书已信任但连接仍失败，可能是服务器问题');
                        }
                    } else {
                        console.error('[Stake WS] 连接错误: SSL 证书或网络问题');
                    }
                } else {
                    console.error('[Stake WS] WebSocket 连接错误');
                }
                
                updateConnectionStatus('error');
                isConnecting = false;
            };

            ws.onclose = function(event) {
                console.log('[Stake WS] 连接关闭');
                console.log('[Stake WS] 关闭代码:', event.code);
                console.log('[Stake WS] 关闭原因:', event.reason || '无原因');
                console.log('[Stake WS] 是否正常关闭:', event.wasClean);
                
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
                    console.error('[Stake WS] 关闭代码说明:', closeCodeMessages[event.code]);
                }
                
                // 如果是 SSL/TLS 相关错误
                if (event.code === 1015 || event.code === 1006) {
                    console.error('💡 这可能是 SSL 证书问题，请在浏览器中访问 https://146.103.42.142:8765/ 并接受证书');
                    console.error('💡 或者检查服务器端日志，确认 WebSocket 服务器是否正常启动');
                }
                
                isConnecting = false;
                updateConnectionStatus('error');
                console.log(`[Stake WS] 连接关闭 (代码: ${event.code})`);
                
                // 自动重连
                if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
                    reconnectAttempts++;
                    updateConnectionStatus('connecting');
                    console.log(`[Stake WS] 尝试重连 ${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS}...`);
                    addLog('❌ 连接失败，正在尝试重连中...', 'info');
                    setTimeout(connect, RECONNECT_DELAY);
                } else {
                    updateConnectionStatus('error');
                    console.error('[Stake WS] 达到最大重连次数，请刷新页面');
                    addLog('❌ 连接失败，正在尝试重连中...', 'info');
                }
            };

        } catch (e) {
            console.error('[Stake WS] 连接异常:', e);
            console.error('[Stake WS] 异常详情:', e.message, e.stack);
            isConnecting = false;
            updateConnectionStatus('error');
            console.error(`[Stake WS] 连接异常: ${e.message}`);
        }
    }

    // ==================== 消息处理 ====================
    function handleMessage(data) {
        console.log('[Stake WS] 收到消息:', data);

        if (data.type === 'connected') {
            updateConnectionStatus('connected');
            
            // 同步服务器时间
            if (data.server_timestamp_ms) {
                const clientTime = Date.now();
                serverTimeOffset = data.server_timestamp_ms - clientTime;
                console.log('[Stake WS] 时间同步:', {
                    server_time: new Date(data.server_timestamp_ms).toISOString(),
                    client_time: new Date(clientTime).toISOString(),
                    offset_ms: serverTimeOffset,
                    offset_sec: (serverTimeOffset / 1000).toFixed(2)
                });
                console.log(`[Stake WS] 服务器确认连接 (时间已同步，偏移: ${(serverTimeOffset / 1000).toFixed(2)}秒)`);
            } else {
                console.log('[Stake WS] 服务器确认连接');
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
        const code = data.code;
        console.log('[Stake WS] 收到代码，立即领取:', code);
        // 不在这里添加日志，已在 handleMessage 中添加

        // 直接调用 GraphQL 领取接口
        try {
            const startTime = Date.now();
            const result = await claimBonusCodeViaAPI(code);
            const responseTime = Date.now() - startTime;
            
            // 获取用户名（从 API 响应或页面中获取）
            let username = getUsernameFromPage();
            
            if (result.success) {
                const amount = result.data?.amount || 'N/A';
                const currency = result.data?.currency || '';
                const formattedAmount = formatAmount(amount);
                addLog(`✅ 领取成功: ${formattedAmount} ${currency}`, 'success');
                console.log('[Stake WS] 领取成功:', result.data);
                
                // 发送成功结果回服务器（使用服务器时间）
                sendClaimResultToServer({
                    code: code,
                    success: true,
                    status: 'claim_success',
                    amount: amount,
                    currency: currency,
                    username: username,
                    responseTime: responseTime,
                    responseBody: JSON.stringify(result.fullResponse || result.data),
                    errorMessage: null,
                    server_timestamp_ms: getServerTime().getTime()  // 使用服务器时间
                });
                
                // 如果启用了自动存入保险库，则自动存入
                if (isVaultAutoDepositEnabled() && amount && amount !== 'N/A') {
                    const depositAmount = parseFloat(amount);
                    if (!isNaN(depositAmount) && depositAmount > 0) {
                        console.log(`[Stake WS] 💰 自动存入保险库: 原始金额 ${formattedAmount} ${currency}`);
                        depositToVault(depositAmount, currency).then(depositResult => {
                            if (depositResult.success) {
                                const depositedAmount = depositResult.data?.amount || '未知';
                                console.log(`[Stake WS] ✅ 存入保险库成功: ${depositedAmount} ${currency}`);
                            } else {
                                console.error('[Stake WS] ❌ 存入保险库失败:', depositResult.error);
                            }
                        });
                    }
                }
            } else {
                addLog(`❌ 领取失败: ${code} - ${result.error}`, 'error');
                console.error('[Stake WS] 领取失败:', result.error);
                
                // 确定错误状态
                let status = 'error';
                if (result.error.includes('不存在') || result.error.includes('not found') || result.error.includes('notFound')) {
                    status = 'not_found';
                } else if (result.error.includes('已失效') || result.error.includes('unavailable') || result.error.includes('bonusCodeInactive')) {
                    status = 'inactive';
                } else if (result.error.includes('已过期') || result.error.includes('session') || result.error.includes('disabledSession')) {
                    status = 'session_expired';
                } else if (result.error.includes('已领取') || result.error.includes('already') || result.error.includes('codeAlreadyClaimed')) {
                    status = 'already_claimed';
                } else if (result.error.includes('投注额') || result.error.includes('wager') || result.error.includes('weeklyWagerRequirement')) {
                    status = 'weekly_wager_requirement';
                }
                
                // 发送失败结果回服务器（使用服务器时间）
                sendClaimResultToServer({
                    code: code,
                    success: false,
                    status: status,
                    amount: null,
                    currency: null,
                    username: username,
                    responseTime: responseTime,
                    responseBody: JSON.stringify(result.fullResponse || {}),
                    errorMessage: result.error,
                    server_timestamp_ms: getServerTime().getTime()  // 使用服务器时间
                });
            }
        } catch (e) {
            addLog(`❌ 领取异常: ${code} - ${e.message}`, 'error');
            console.error('[Stake WS] 领取异常:', e);
            
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
    }
    
    // 从页面中获取用户名
    function getUsernameFromPage() {
        try {
            // 方式1: 从 GraphQL 响应中提取（最可靠的方式）
            // 查找所有包含 GraphQL 数据的 script 标签
            const graphqlScripts = document.querySelectorAll('script[type="application/json"][data-sveltekit-fetched]');
            for (const script of graphqlScripts) {
                try {
                    const jsonData = JSON.parse(script.textContent);
                    // 检查是否有 user.name 字段
                    if (jsonData.body) {
                        const bodyData = JSON.parse(jsonData.body);
                        if (bodyData.data && bodyData.data.user && bodyData.data.user.name) {
                            const username = bodyData.data.user.name;
                            if (username && username.length > 0 && username.length < 50) {
                                console.log('[Stake WS] 从 GraphQL 响应中提取到用户名:', username);
                                return username;
                            }
                        }
                    }
                } catch (e) {
                    // 跳过解析失败的 script 标签
                    continue;
                }
            }
            
            // 方式2: 从页面的用户信息元素中获取
            const userElements = document.querySelectorAll('[data-username], [class*="username"], [id*="username"]');
            for (const el of userElements) {
                const username = el.textContent?.trim() || el.getAttribute('data-username') || el.getAttribute('data-user');
                if (username && username.length > 0 && username.length < 50) {
                    console.log('[Stake WS] 从页面元素中提取到用户名:', username);
                    return username;
                }
            }
            
            // 方式3: 从 localStorage 中获取
            for (let key of Object.keys(localStorage)) {
                if (key.toLowerCase().includes('user') && !key.toLowerCase().includes('token')) {
                    const value = localStorage.getItem(key);
                    if (value && value.length > 0 && value.length < 50) {
                        console.log('[Stake WS] 从 localStorage 中提取到用户名:', value);
                        return value;
                    }
                }
            }
            
            // 方式4: 从 URL 或页面标题中提取
            const urlMatch = window.location.href.match(/\/user\/([^\/]+)/);
            if (urlMatch) {
                console.log('[Stake WS] 从 URL 中提取到用户名:', urlMatch[1]);
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
                        console.log('[Stake WS] 从 script 内容中提取到用户名:', potentialUsername);
                        return potentialUsername;
                    }
                }
            }
        } catch (e) {
            console.warn('[Stake WS] 获取用户名失败:', e);
        }
        console.warn('[Stake WS] 未能提取到用户名');
        return null;
    }
    
    // 发送领取结果回服务器
    function sendClaimResultToServer(resultData) {
        if (!ws || ws.readyState !== WebSocket.OPEN) {
            console.warn('[Stake WS] WebSocket 未连接，无法发送领取结果');
            return;
        }
        
        try {
            const message = {
                type: 'claim_result',
                user_id: USER_ID,  // 用户标识符（用于区分不同使用者）
                code: resultData.code,
                success: resultData.success,
                status: resultData.status,
                amount: resultData.amount,
                currency: resultData.currency,
                username: resultData.username,  // Stake 账号用户名
                responseTime: resultData.responseTime,
                responseBody: resultData.responseBody,
                errorMessage: resultData.errorMessage,
                timestamp: getServerTime().toISOString(),  // 使用服务器时间
                server_timestamp_ms: resultData.server_timestamp_ms || getServerTime().getTime()  // 确保包含服务器时间戳
            };
            
            ws.send(JSON.stringify(message));
            console.log('[Stake WS] 已发送领取结果到服务器:', message);
        } catch (e) {
            console.error('[Stake WS] 发送领取结果失败:', e);
        }
    }

    // ==================== GraphQL 领取接口（仿照项目逻辑）====================
    async function claimBonusCodeViaAPI(code) {
        try {
            // 1. 获取必要的请求信息
            const headers = getRequestHeaders();
            const currency = 'usdt';  // 默认货币类型

            // 2. 获取 Turnstile Token（从页面中获取或等待页面生成）
            let turnstileToken = await getTurnstileToken(code, currency);
            
            if (!turnstileToken) {
                // 如果获取失败，尝试刷新一次
                console.log('[Stake WS] Token 获取失败，尝试刷新...');
                const refreshedToken = await refreshTurnstileToken();
                if (!refreshedToken) {
                    return {
                        success: false,
                        error: '获取 Turnstile Token 失败，请确保页面已加载完成'
                    };
                }
                // 使用刷新后的 Token
                turnstileToken = refreshedToken;
            }
            
            // 使用 Token 后立即在后台刷新下一个 Token（不阻塞当前请求）
            refreshTurnstileToken().catch(e => {
                console.error('[Stake WS] 后台刷新 Token 失败:', e);
            });

            // 3. 构建 GraphQL mutation（完全仿照项目中的格式）
            const payload = {
                "query": "mutation ClaimConditionBonusCode($code: String!, $currency: CurrencyEnum!, $turnstileToken: String!) {\n  claimConditionBonusCode(\n    code: $code\n    currency: $currency\n    turnstileToken: $turnstileToken\n  ) {\n    bonusCode {\n      id\n      code\n    }\n    amount\n    currency\n    user {\n      id\n      balances {\n        available {\n          amount\n          currency\n        }\n      }\n    }\n  }\n}",
                "variables": {
                    "code": code,
                    "currency": currency.toLowerCase(),  // 使用小写
                    "turnstileToken": turnstileToken
                }
            };

            // 4. 发送请求
            const response = await fetch('https://stake.com/_api/graphql', {
                method: 'POST',
                headers: {
                    ...headers,
                    'referer': `https://stake.com/zh/settings/offers?type=drop&code=${code}`,
                    'x-operation-name': 'ClaimConditionBonusCode'
                },
                credentials: 'include',  // 自动包含 Cookie
                body: JSON.stringify(payload)
            });

            const responseData = await response.json();
            console.log('[Stake WS] API 响应:', responseData);

            // 5. 解析响应（仿照项目中的逻辑）
            if (response.status === 200) {
                const errors = responseData.errors || [];
                
                if (errors.length > 0) {
                    const error = errors[0];
                    const errorType = error.errorType || '';
                    const errorMsg = error.message || '未知错误';
                    
                    // 根据错误类型返回相应状态（完全仿照项目逻辑）
                    let errorStatus = '未知错误';
                    if (errorType === 'notFound' || errorMsg.includes('not found') || errorMsg.includes('cannot be found')) {
                        errorStatus = '代码不存在';
                    } else if (errorType === 'bonusCodeInactive' || errorMsg.includes('unavailable')) {
                        errorStatus = '代码已失效';
                    } else if (errorType === 'disabledSession' || errorMsg.includes('session has expired')) {
                        errorStatus = '会话已过期，请刷新页面';
                    } else if (errorType === 'codeAlreadyClaimed' || errorMsg.includes('already claimed')) {
                        errorStatus = '已领取过';
                    } else if (errorType === 'weeklyWagerRequirement' || errorMsg.includes('not played enough') || errorMsg.includes('wager requirement')) {
                        errorStatus = '周投注额不足';
                    } else {
                        errorStatus = errorMsg;
                    }
                    
                    // 返回完整响应数据
                    return { 
                        success: false, 
                        error: errorStatus,
                        fullResponse: responseData  // 添加完整响应
                    };
                } else {
                    // 领取成功
                    const claimResult = responseData.data?.claimConditionBonusCode;
                    const formattedAmount = formatAmount(claimResult?.amount);
                    return {
                        success: true,
                        data: claimResult,
                        fullResponse: responseData,  // 添加完整响应
                        message: `领取成功！金额: ${formattedAmount} ${claimResult?.currency || ''}`
                    };
                }
            } else {
                // HTTP 状态码不是 200，也返回完整响应
                return {
                    success: false,
                    error: `HTTP ${response.status}`,
                    fullResponse: responseData  // 添加完整响应
                };
            }
        } catch (e) {
            console.error('[Stake WS] API 请求异常:', e);
            return {
                success: false,
                error: e.message || '请求异常',
                fullResponse: null  // 异常时没有响应数据
            };
        }
    }

    // ==================== 获取请求头 ====================
    function getRequestHeaders() {
        // 从页面中获取必要的请求头（仿照项目逻辑）
        const headers = {
            'accept': '*/*',
            'content-type': 'application/json',
            'origin': 'https://stake.com',
            'user-agent': navigator.userAgent,
        };

        // 尝试从页面中获取 token（stake.com 通常存储在 localStorage 或通过 API 获取）
        const token = getStakeToken();
        if (token) {
            headers['x-access-token'] = token;
        } else {
            console.warn('[Stake WS] 未找到 x-access-token，可能影响请求');
        }

        return headers;
    }

    // ==================== 获取 Stake Token ====================
    function getStakeToken() {
        // 尝试多种方式获取 token
        try {
            // 方式1: 从页面的网络请求中拦截（监听 fetch）
            // 如果页面已经发送过请求，可以从拦截的请求中获取
            
            // 方式2: 从 localStorage/sessionStorage
            for (let key of Object.keys(localStorage)) {
                if (key.toLowerCase().includes('token') || key.toLowerCase().includes('access')) {
                    const value = localStorage.getItem(key);
                    if (value && value.length > 20) {  // token 通常比较长
                        return value;
                    }
                }
            }

            // 方式3: 从页面的全局变量中获取
            if (window.__STAKETOKEN__) return window.__STAKETOKEN__;
            if (window.stakeToken) return window.stakeToken;
            if (window.__APOLLO_CLIENT__) {
                // Apollo Client 可能存储了 token
                const client = window.__APOLLO_CLIENT__;
                if (client.defaultOptions && client.defaultOptions.headers) {
                    return client.defaultOptions.headers['x-access-token'];
                }
            }

            // 方式4: 从页面的现有请求头中获取（通过拦截 fetch）
            // 这需要在页面加载时就开始拦截

            return null;
        } catch (e) {
            console.error('[Stake WS] 获取 Token 失败:', e);
            return null;
        }
    }

    // ==================== Turnstile Token 获取器 ====================
    const TURNSTILE_SITE_KEY = '0x4AAAAAAAGD4gMGOTFnvupz';
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
            let container = document.getElementById('stake-ws-turnstile-container');
            if (!container) {
                container = document.createElement('div');
                container.id = 'stake-ws-turnstile-container';
                container.style.cssText = 'position: absolute; left: -9999px; width: 1px; height: 1px; overflow: hidden;';
                document.body.appendChild(container);
            } else {
                // 如果容器已存在但 widget ID 无效，清空容器以便重新渲染
                if (turnstileWidgetId && window.turnstile) {
                    try {
                        window.turnstile.remove(turnstileWidgetId);
                    } catch (e) {
                        // 忽略移除错误，可能 widget 已经不存在
                        console.warn('[Stake WS] 移除旧 widget 时出错（可忽略）:', e.message);
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
                        console.log('[Stake WS] ✅ 成功获取 Turnstile Token:', token.substring(0, 20) + '...');
                        turnstileTokenCache = token;
                        window.__TURNSTILETOKEN__ = token;  // 也存储到全局变量
                        isRefreshingToken = false;
                        tokenRefreshPromise = null;
                    },
                    'error-callback': function(err) {
                        console.error('[Stake WS] ❌ Turnstile 错误:', err);
                        turnstileTokenCache = null;
                        isRefreshingToken = false;
                        tokenRefreshPromise = null;
                        // 错误后自动重试
                        setTimeout(() => {
                            refreshTurnstileToken();
                        }, 2000);
                    },
                    'expired-callback': function() {
                        console.warn('[Stake WS] ⚠️ Turnstile Token 已过期，正在自动刷新...');
                        turnstileTokenCache = null;
                        // 自动重置并重新获取
                        refreshTurnstileToken();
                    }
                });
                console.log('[Stake WS] ✅ Turnstile Token 获取器已初始化');
            }
        } catch (e) {
            console.error('[Stake WS] ❌ 初始化 Turnstile Token 获取器失败:', e);
        }
    }

    // 刷新 Turnstile Token（重置 widget 以获取新 Token）
    async function refreshTurnstileToken() {
        // 如果正在刷新，等待当前刷新完成
        if (isRefreshingToken && tokenRefreshPromise) {
            console.log('[Stake WS] Token 正在刷新中，等待完成...');
            return await tokenRefreshPromise;
        }

        if (!window.turnstile) {
            console.warn('[Stake WS] Turnstile API 未加载，尝试重新初始化...');
            await initTurnstileTokenGrabber();
            if (!window.turnstile) {
                console.error('[Stake WS] ❌ 无法加载 Turnstile API');
                return null;
            }
        }

        // 检查容器是否存在
        const container = document.getElementById('stake-ws-turnstile-container');
        if (!container) {
            console.warn('[Stake WS] Turnstile 容器不存在，重新初始化...');
            turnstileWidgetId = null;
            await initTurnstileTokenGrabber();
            if (!turnstileWidgetId) {
                console.error('[Stake WS] ❌ 无法初始化 Turnstile widget');
                return null;
            }
        }

        // 如果 widget ID 无效，重新初始化
        if (!turnstileWidgetId) {
            console.warn('[Stake WS] Turnstile widget ID 无效，重新初始化...');
            await initTurnstileTokenGrabber();
            if (!turnstileWidgetId) {
                console.error('[Stake WS] ❌ 无法获取 Turnstile widget ID');
                return null;
            }
        }

        isRefreshingToken = true;
        console.log('[Stake WS] 🔄 开始刷新 Turnstile Token...');
        
        // 创建刷新 Promise
        tokenRefreshPromise = new Promise((resolve) => {
            try {
                // 尝试重置 widget
                window.turnstile.reset(turnstileWidgetId);
            } catch (e) {
                // 如果 reset 失败（例如 widget 不存在），尝试重新初始化
                console.warn('[Stake WS] ⚠️ Reset 失败，尝试重新初始化 widget:', e.message);
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
                            console.log('[Stake WS] ✅ Token 通过重新初始化获取成功');
                            resolve(turnstileTokenCache);
                        }
                    }, 500);
                    
                    // 10 秒超时
                    setTimeout(() => {
                        clearInterval(checkInterval);
                        if (!turnstileTokenCache) {
                            isRefreshingToken = false;
                            tokenRefreshPromise = null;
                            console.error('[Stake WS] ❌ 重新初始化后 Token 获取超时');
                            resolve(null);
                        }
                    }, 10000);
                }).catch(err => {
                    console.error('[Stake WS] ❌ 重新初始化失败:', err);
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
                    console.log('[Stake WS] ✅ Token 刷新成功');
                    resolve(turnstileTokenCache);
                }
            }, 500);
            
            // 10 秒超时
            setTimeout(() => {
                clearInterval(checkInterval);
                if (!turnstileTokenCache) {
                    isRefreshingToken = false;
                    tokenRefreshPromise = null;
                    console.error('[Stake WS] ❌ Token 刷新超时');
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
            console.log('[Stake WS] 使用缓存的 Turnstile Token');
            // 使用后立即刷新，确保下次有新的 Token
            refreshTurnstileToken().catch(e => {
                console.error('[Stake WS] 后台刷新 Token 失败:', e);
            });
            return turnstileTokenCache;
        }

        // 方式2: 从全局变量获取
        if (window.__TURNSTILETOKEN__) {
            turnstileTokenCache = window.__TURNSTILETOKEN__;
            // 使用后立即刷新
            refreshTurnstileToken().catch(e => {
                console.error('[Stake WS] 后台刷新 Token 失败:', e);
            });
            return turnstileTokenCache;
        }

        // 方式3: 确保 Turnstile 已初始化
        if (!window.turnstile || !turnstileWidgetId) {
            console.log('[Stake WS] 初始化 Turnstile Token 获取器...');
            await initTurnstileTokenGrabber();
            // 等待 Token 生成（最多等待 10 秒）
            for (let i = 0; i < 20; i++) {
                await new Promise(resolve => setTimeout(resolve, 500));
                if (turnstileTokenCache || window.__TURNSTILETOKEN__) {
                    turnstileTokenCache = turnstileTokenCache || window.__TURNSTILETOKEN__;
                    // 获取到 Token 后，立即在后台刷新下一个
                    refreshTurnstileToken().catch(e => {
                        console.error('[Stake WS] 后台刷新 Token 失败:', e);
                    });
                    return turnstileTokenCache;
                }
            }
        } else {
            // 如果 widget 已存在但 Token 不存在，刷新并等待
            console.log('[Stake WS] 刷新 Turnstile widget 以获取新 Token...');
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
                console.error('[Stake WS] 后台刷新 Token 失败:', e);
            });
            return turnstileTokenCache;
        }

        console.warn('[Stake WS] ⚠️ 无法获取 Turnstile Token');
        return null;
    }

    // ==================== 拦截网络请求获取 Token ====================
    function interceptNetworkRequests() {
        // 拦截 fetch 请求，从请求头和请求体中获取 token 和 turnstile token
        const originalFetch = window.fetch;
        window.fetch = function(...args) {
            const [url, options] = args;
            
            // 获取 x-access-token
            if (options && options.headers) {
                const token = options.headers['x-access-token'] || options.headers['X-Access-Token'];
                if (token) {
                    window.__STAKETOKEN__ = token;
                    console.log('[Stake WS] 从请求中获取到 Token');
                }
            }
            
            // 获取 Turnstile token（从请求体中）
            if (options && options.body) {
                try {
                    const body = typeof options.body === 'string' ? JSON.parse(options.body) : options.body;
                    if (body.variables && body.variables.turnstileToken) {
                        window.__TURNSTILETOKEN__ = body.variables.turnstileToken;
                        console.log('[Stake WS] 从请求中获取到 Turnstile Token');
                    }
                } catch (e) {
                    // 忽略解析错误
                }
            }
            
            return originalFetch.apply(this, args);
        };

        // 拦截 XMLHttpRequest
        const originalSetRequestHeader = XMLHttpRequest.prototype.setRequestHeader;
        XMLHttpRequest.prototype.setRequestHeader = function(header, value) {
            if (header.toLowerCase() === 'x-access-token') {
                window.__STAKETOKEN__ = value;
                console.log('[Stake WS] 从 XHR 请求中获取到 Token');
            }
            return originalSetRequestHeader.apply(this, arguments);
        };
        
        // 拦截 XMLHttpRequest 的 send 方法，获取请求体中的 Turnstile token
        const originalSend = XMLHttpRequest.prototype.send;
        XMLHttpRequest.prototype.send = function(body) {
            if (body) {
                try {
                    const data = typeof body === 'string' ? JSON.parse(body) : body;
                    if (data.variables && data.variables.turnstileToken) {
                        window.__TURNSTILETOKEN__ = data.variables.turnstileToken;
                        console.log('[Stake WS] 从 XHR 请求中获取到 Turnstile Token');
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
        console.log('[Stake WS] 脚本初始化');
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

