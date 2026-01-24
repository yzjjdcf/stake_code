// ==UserScript==
// @name         Stake code claim tool
// @namespace    http://tampermonkey.net/
// @version      1.0.0
// @description  Stake 代码自动领取工具
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
// @updateURL    https://stakefav.xyz/scripts/stake.user.js
// @downloadURL  https://stakefav.xyz/scripts/stake.user.js
// ==/UserScript==

(function() {
    'use strict';

    // ==================== 防止脚本多次执行（火狐浏览器兼容性）====================
    // 使用顶层窗口（window.top）存储标志，实现跨 iframe 的防重复检查
    const SCRIPT_FLAG_KEY = '__STAKE_WS_SCRIPT_INSTANCE__';
    const WS_INSTANCE_KEY = '__STAKE_WS_INSTANCE__';
    
    // 获取顶层窗口对象（跨 iframe 共享）
    let topWindow = null;
    try {
        // 尝试访问顶层窗口（如果当前窗口就是顶层窗口，window.top === window）
        if (typeof window !== 'undefined' && window.top) {
            topWindow = window.top;
        } else if (typeof window !== 'undefined') {
            topWindow = window;
        }
    } catch (e) {
        // 如果无法访问顶层窗口（跨域限制），使用当前窗口
        if (typeof window !== 'undefined') {
            topWindow = window;
        }
    }
    
    // 如果无法获取顶层窗口，使用当前窗口
    if (!topWindow && typeof window !== 'undefined') {
        topWindow = window;
    }
    
    // 检查顶层窗口是否已有脚本实例运行（包括 WebSocket 连接）
    let foundExistingInstance = false;
    if (topWindow) {
        try {
            // 检查脚本标志
            if (topWindow[SCRIPT_FLAG_KEY]) {
                console.warn('[Stake WS] 检测到已有脚本实例运行，跳过重复执行（火狐浏览器兼容性）');
                foundExistingInstance = true;
            }
            // 检查是否有活跃的 WebSocket 连接
            const existingWs = topWindow[WS_INSTANCE_KEY];
            if (!foundExistingInstance && existingWs && (existingWs.readyState === WebSocket.OPEN || existingWs.readyState === WebSocket.CONNECTING)) {
                console.warn('[Stake WS] 检测到已有活跃 WebSocket 连接，跳过重复执行（火狐浏览器兼容性）');
                foundExistingInstance = true;
            }
        } catch (e) {
            // 忽略访问错误（可能是跨域限制）
            console.warn('[Stake WS] 无法访问顶层窗口，继续执行:', e.message);
        }
    }
    
    // 如果发现已有实例，立即退出
    if (foundExistingInstance) {
        return;
    }
    
    // 在顶层窗口上设置标志（防止后续实例运行）
    if (topWindow) {
        try {
            topWindow[SCRIPT_FLAG_KEY] = true;
        } catch (e) {
            // 如果无法设置到顶层窗口，尝试设置到当前窗口
            if (typeof window !== 'undefined') {
                try {
                    window[SCRIPT_FLAG_KEY] = true;
                } catch (e2) {
                    // 忽略设置失败
                }
            }
        }
    }
    
    // 获取所有可能的全局对象（用于备用检查）
    const globalObjects = [
        topWindow,
        typeof window !== 'undefined' ? window : null,
        typeof self !== 'undefined' ? self : null,
        typeof globalThis !== 'undefined' ? globalThis : null,
        typeof document !== 'undefined' ? document : null
    ].filter(obj => obj !== null && obj !== topWindow); // 排除重复的 topWindow

    // ==================== 版本信息 ====================
    // 注意：版本号现在在需要的地方直接获取（使用局部变量），避免混淆工具破坏全局变量引用

    // ==================== 配置 ====================
    // 注意：HTTPS 页面必须使用 wss:// (加密 WebSocket)，不能使用 ws://
    const WEBSOCKET_URL = 'wss://stakefav.xyz';  // 使用域名（通过 nginx 反向代理）
    const RECONNECT_DELAY = 5000;  // 重连延迟（毫秒）
    const MAX_RECONNECT_ATTEMPTS = 10;  // 最大重连次数
    
    // ==================== 调试模式开关 ====================
    // true: debug 模式，打印所有日志
    // false: release 模式，只打印 WebSocket 传输相关日志
    const DEBUG_MODE = false;  // 修改此值切换模式
    
    // ==================== 动态域名获取 ====================
    /**
     * 获取当前访问的 Stake 域名（支持所有 Stake 域名）
     * @returns {string} 当前域名，例如：stake.com, stake.ac, stake.games 等
     */
    function getCurrentDomain() {
        return window.location.hostname;
    }
    
    /**
     * 获取当前域名的完整 URL（包含协议）
     * @returns {string} 例如：https://stake.com, https://stake.ac 等
     */
    function getCurrentOrigin() {
        return window.location.origin;
    }
    
    /**
     * 获取 GraphQL API 的完整 URL（根据当前域名动态构建）
     * @returns {string} 例如：https://stake.com/_api/graphql
     */
    function getGraphQLApiUrl() {
        return `${getCurrentOrigin()}/_api/graphql`;
    }
    
    // ==================== 用户标识 ====================
    // 用户唯一标识符（用于区分不同使用者，一个用户可以有多个 Stake 账号）
    // 注意：为每个用户生成脚本时，需要修改此值
    const USER_ID = 'KK';  // 请修改为实际的用户标识符
    
    // 用户名缓存（避免 CSP 错误后无法获取用户名）
    let usernameCache = null;
    
    // ==================== 日志函数 ====================
    // WebSocket 相关日志（release 模式下也打印）
    function wsLog(...args) {
        console.log('[Stake WS]', ...args);
    }
    
    // WebSocket 相关警告（release 模式下也打印）
    function wsWarn(...args) {
        console.warn('[Stake WS]', ...args);
    }
    
    // WebSocket 相关错误（release 模式下也打印）
    function wsError(...args) {
        console.error('[Stake WS]', ...args);
    }
    
    // 通用日志（只在 debug 模式下打印）
    function debugLog(...args) {
        if (DEBUG_MODE) {
            console.log(...args);
        }
    }
    
    // 通用警告（只在 debug 模式下打印）
    function debugWarn(...args) {
        if (DEBUG_MODE) {
            console.warn(...args);
        }
    }
    
    // 通用错误（只在 debug 模式下打印）
    function debugError(...args) {
        if (DEBUG_MODE) {
            console.error(...args);
        }
    }

    // ==================== 状态管理 ====================
    let ws = null;
    let reconnectAttempts = 0;
    let isConnecting = false;
    let lastPingTime = null;  // 记录最后一次发送 ping 的时间戳
    let statusElement = null;
    let serverTimeOffset = 0;  // 服务器时间偏移量（服务器时间 - 客户端时间，毫秒）
    let sessionCache = null;  // session 缓存（只获取一次，和登录绑定，不变）
    let lastConnectionStatus = null;  // 上一次的连接状态（'connected', 'disconnected', 'error'），用于判断状态变化
    
    // 全局 WebSocket 实例检查（火狐浏览器兼容性）
    // 使用顶层窗口（window.top）存储 WebSocket 实例，实现跨 iframe 共享
    // 辅助函数：获取全局 WebSocket 实例（优先从顶层窗口获取）
    function getGlobalWebSocketInstance() {
        // 优先从顶层窗口获取（跨 iframe 共享）
        if (topWindow) {
            try {
                const wsInstance = topWindow[WS_INSTANCE_KEY];
                if (wsInstance && (wsInstance.readyState === WebSocket.OPEN || wsInstance.readyState === WebSocket.CONNECTING)) {
                    return wsInstance;
                }
            } catch (e) {
                // 忽略访问错误
            }
        }
        
        // 备用：检查其他全局对象
        for (const globalObj of globalObjects) {
            try {
                const wsInstance = globalObj[WS_INSTANCE_KEY];
                if (wsInstance && (wsInstance.readyState === WebSocket.OPEN || wsInstance.readyState === WebSocket.CONNECTING)) {
                    return wsInstance;
                }
            } catch (e) {
                // 忽略访问错误
            }
        }
        return null;
    }
    
    // 辅助函数：设置全局 WebSocket 实例（优先设置到顶层窗口）
    function setGlobalWebSocketInstance(wsInstance) {
        // 优先设置到顶层窗口（跨 iframe 共享）
        if (topWindow) {
            try {
                topWindow[WS_INSTANCE_KEY] = wsInstance;
            } catch (e) {
                // 如果无法设置到顶层窗口，尝试设置到当前窗口
                if (typeof window !== 'undefined') {
                    try {
                        window[WS_INSTANCE_KEY] = wsInstance;
                    } catch (e2) {
                        // 忽略设置失败
                    }
                }
            }
        }
        
        // 备用：设置到其他全局对象
        for (const globalObj of globalObjects) {
            try {
                globalObj[WS_INSTANCE_KEY] = wsInstance;
            } catch (e) {
                // 忽略设置失败
            }
        }
    }
    
    // 辅助函数：清除全局 WebSocket 实例
    function clearGlobalWebSocketInstance(targetInstance) {
        // 优先清除顶层窗口上的实例
        if (topWindow) {
            try {
                if (topWindow[WS_INSTANCE_KEY] === targetInstance) {
                    topWindow[WS_INSTANCE_KEY] = null;
                }
            } catch (e) {
                // 忽略清除失败
            }
        }
        
        // 备用：清除其他全局对象上的实例
        for (const globalObj of globalObjects) {
            try {
                if (globalObj[WS_INSTANCE_KEY] === targetInstance) {
                    globalObj[WS_INSTANCE_KEY] = null;
                }
            } catch (e) {
                // 忽略清除失败
            }
        }
    }

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
            .header-title .header-version { font-size: 9px; font-weight: 600; color: #8a8d92 !important; margin-left: 8px; text-transform: none !important; letter-spacing: 0.5px; opacity: 0.9; display: inline-block; }

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
            .log-time { color: #8a8d92; }
            .log-success { color: #6df5f0; }
            .log-info { color: #8a8d92; }
            .log-error { color: #b0b0b5; }
            .log-error-prefix { color: #8a8d92; }
            .log-error-text { color: #ff6b60; }
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
        
        // 直接使用 GM_info.script.version 获取版本号（混淆安全）
        var versionStr = 'v' + (typeof GM_info !== 'undefined' && GM_info.script && GM_info.script.version ? GM_info.script.version : '1.0.0');
        statusElement.innerHTML = 
            '<div id="stake-ws-header" title="拖动移动位置">' +
                '<span class="header-title">Stake Auto Claim<span class="header-version">' + versionStr + '</span></span>' +
                '<div style="display: flex; align-items: center; gap: 8px;">' +
                    '<div class="status-dot" id="stake-ws-status-dot"></div>' +
                    '<div id="stake-ws-close-btn" title="收起">×</div>' +
                '</div>' +
            '</div>' +
            '<div id="stake-ws-username">' +
                '<span class="username-label">user:</span>' +
                '<span class="username-value" id="stake-ws-username-value">-</span>' +
            '</div>' +
            '<div id="stake-ws-ping-vault-container">' +
                '<div id="stake-ws-vault-switch">' +
                    '<span class="switch-label">存入保险库</span>' +
                    '<div class="switch-checkbox" id="stake-ws-vault-checkbox"></div>' +
                '</div>' +
                '<div id="stake-ws-ping">' +
                    '<span class="ping-label">ping:</span>' +
                    '<span class="ping-value" id="stake-ws-ping-value">-</span>' +
                '</div>' +
            '</div>' +
            '<div id="stake-ws-test-vault-btn">测试存入 1 USDT</div>' +
            '<div id="stake-ws-log-container"></div>' +
            '<div id="stake-ws-resize-handle" title="拖动等比缩放"></div>';
        
        // 确保 document.body 存在后再添加元素
        if (document.body) {
            document.body.appendChild(statusElement);
        } else {
            wsError('❌ 无法添加 UI 元素：document.body 不存在，等待 body 准备好...');
            // 等待 body 准备好
            const checkBody = setInterval(function() {
                if (document.body) {
                    document.body.appendChild(statusElement);
                    clearInterval(checkBody);
                    wsLog('✅ UI 元素已添加到页面');
                }
            }, 100);
            // 10秒后停止尝试
            setTimeout(function() {
                clearInterval(checkBody);
                if (!document.body) {
                    wsError('❌ 10秒后 document.body 仍不存在');
                }
            }, 10000);
        }

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
        const timeSpan = `<span class="log-time">[${timeStr}]</span>`;
        
        // 处理错误类型的特殊格式（前缀灰色，错误文字红色）
        let formattedMessage = message;
        if (type === 'error' && message.includes('领取失败:')) {
            // 匹配格式：❌ 领取失败: <code> - <error>
            const errorMatch = message.match(/^(.*?领取失败:\s*)([A-Za-z0-9]{8,})(\s*-\s*)(.+)$/);
            if (errorMatch) {
                const prefix = errorMatch[1];  // "❌ 领取失败: "
                const code = errorMatch[2];     // 代码
                const separator = errorMatch[3]; // " - "
                const errorText = errorMatch[4]; // 错误信息
                formattedMessage = `<span class="log-error-prefix">${prefix}</span><span class="log-code">${code}</span><span class="log-error-prefix">${separator}</span><span class="log-error-text">${errorText}</span>`;
            } else {
                // 如果格式不匹配，尝试匹配其他错误格式
                const codeMatch = message.match(/([A-Za-z0-9]{8,})/);
                if (codeMatch) {
                    formattedMessage = message.replace(codeMatch[0], `<span class="log-code">${codeMatch[0]}</span>`);
                }
                formattedMessage = formattedMessage.replace(/领取失败:\s*/g, '<span class="log-error-prefix">领取失败: </span>');
                // 将错误信息部分（冒号后的内容）设置为红色
                formattedMessage = formattedMessage.replace(/:\s*([^<]+)$/, ': <span class="log-error-text">$1</span>');
            }
        } else {
            // 高亮代码（非错误类型）
            const codeMatch = message.match(/([A-Za-z0-9]{8,})/);
            if (codeMatch) {
                formattedMessage = message.replace(codeMatch[0], `<span class="log-code">${codeMatch[0]}</span>`);
            }
        }
        
        logItem.innerHTML = `${timeSpan} ${formattedMessage}`;
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
                wsLog('🧪 测试存入保险库: 1 USDT');
                addLog('🧪 测试存入保险库: 1 USDT', 'info');
                
                const result = await depositToVault(1, 'usdt');
                
                if (result.success) {
                    const depositedAmount = result.data?.amount || '1';
                    addLog(`✅ 测试成功: 存入 ${depositedAmount} USDT`, 'success');
                    wsLog('✅ 测试存入保险库成功:', result.data);
                } else {
                    addLog(`❌ 测试失败: ${result.error}`, 'error');
                    wsError('❌ 测试存入保险库失败:', result.error);
                }
            } catch (e) {
                addLog(`❌ 测试异常: ${e.message}`, 'error');
                wsError('❌ 测试存入保险库异常:', e);
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
            // 获取 session
            const session = getSession();
            if (!session) {
                wsError('无法获取 session，无法存入保险库');
                return { success: false, error: '无法获取 session' };
            }

            // 处理金额：向下取整到2位小数
            const originalAmount = parseFloat(amount);
            if (isNaN(originalAmount) || originalAmount <= 0) {
                wsError('无效的金额，无法存入保险库');
                return { success: false, error: '无效的金额' };
            }

            // 向下取整到2位小数
            const safeAmount = Math.floor(originalAmount * 100) / 100;
            
            // 如果处理后的金额小于最小值（0.01），则不存入
            if (safeAmount < 0.01) {
                wsWarn(`金额太小（处理后: ${safeAmount}），跳过存入保险库`);
                return { success: false, error: '金额太小，无法存入' };
            }

            debugLog(`[Stake WS] 金额处理: 原始=${originalAmount}, 向下取整=${safeAmount.toFixed(2)}`);

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
            const response = await fetch(getGraphQLApiUrl(), {
                method: 'POST',
                headers: {
                    'accept': '*/*',
                    'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7',
                    'content-type': 'application/json',
                    'origin': getCurrentOrigin(),
                    'referer': `${getCurrentOrigin()}/zh/settings/offers`,
                    'x-access-token': session,
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
                wsLog('✅ 存入保险库成功:', responseData.data.createVaultDeposit);
                return { success: true, data: responseData.data.createVaultDeposit };
            } else {
                const error = responseData.errors?.[0]?.message || '未知错误';
                wsError('❌ 存入保险库失败:', error);
                return { success: false, error: error };
            }
        } catch (e) {
            wsError('❌ 存入保险库异常:', e);
            return { success: false, error: e.message };
        }
    }


    // ==================== WebSocket 连接 ====================
    function connect() {
        // 首先检查是否已有活跃连接（包括全局实例和当前实例）
        const globalWs = getGlobalWebSocketInstance();
        if (globalWs && globalWs !== ws) {
            wsWarn('⚠️ 检测到已有活跃连接，跳过重复连接（火狐浏览器兼容性）');
            ws = globalWs;  // 使用已有的全局实例
            // 同步当前实例的状态
            if (globalWs.readyState === WebSocket.OPEN) {
                isConnecting = false;
                reconnectAttempts = 0;
                updateConnectionStatus('connected');
            }
            // 直接返回，不创建新连接
            return;
        }
        
        // 检查当前实例是否正在连接或已连接
        if (isConnecting || (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING))) {
            wsWarn('⚠️ 正在连接或已连接，跳过重复连接');
            return;
        }
        
        // 再次检查全局连接（防止在检查后、创建前有新的连接建立）
        const doubleCheckWs = getGlobalWebSocketInstance();
        if (doubleCheckWs && doubleCheckWs !== ws) {
            wsWarn('⚠️ 检测到新的活跃连接，跳过重复连接（二次检查）');
            ws = doubleCheckWs;
            if (doubleCheckWs.readyState === WebSocket.OPEN) {
                isConnecting = false;
                reconnectAttempts = 0;
                updateConnectionStatus('connected');
            }
            return;
        }

        // 先获取 session 和用户名，如果 session 没获取到，不进行连接
        const session = getSession();
        const preUsername = getUsernameFromPage();
        
        if (!session) {
            wsWarn('⚠️ 未获取到 session，无法建立 WebSocket 连接');
            wsWarn('⚠️ 请确保已登录并刷新页面');
            updateConnectionStatus('error');
            addLog('❌ 未获取到 session，请确保已登录', 'error');
            return;
        }
        
        if (preUsername && isValidUsername(preUsername)) {
            wsLog('已获取到用户名:', preUsername);
        } else {
            wsWarn('⚠️ 未获取到有效用户名，将在连接后继续尝试');
        }

        isConnecting = true;
        updateConnectionStatus('connecting');
        wsLog('正在连接到服务器...');

        try {
            ws = new WebSocket(WEBSOCKET_URL);
            // 将 WebSocket 实例保存到所有全局变量（火狐浏览器兼容性）
            setGlobalWebSocketInstance(ws);

            ws.onopen = function() {
                wsLog('连接成功');
                isConnecting = false;
                reconnectAttempts = 0;
                updateConnectionStatus('connected');
                // 只在状态变化时添加日志
                if (lastConnectionStatus !== 'connected') {
                    addLog('✅ 连接成功', 'success');
                    lastConnectionStatus = 'connected';
                }
                
                // 如果连接前已经获取到用户名，立即发送
                if (preUsername && isValidUsername(preUsername)) {
                    try {
                        ws.send(JSON.stringify({
                            type: 'init',
                            username: preUsername,
                            user_id: USER_ID
                        }));
                        wsLog('已发送初始化消息，用户名:', preUsername);
                    } catch (e) {
                        wsError('发送初始化消息失败:', e);
                    }
                } else {
                    // 如果连接前未获取到用户名，延迟发送初始化消息，等待页面完全加载后再获取
                    // 延迟 2 秒，确保页面数据已加载完成（火狐浏览器可能需要更长时间）
                    setTimeout(function() {
                        if (ws && ws.readyState === WebSocket.OPEN) {
                            // 多次尝试获取用户名（最多尝试 5 次，每次间隔 1 秒，兼容火狐浏览器）
                            let attempts = 0;
                            const maxAttempts = 5;
                            
                            function trySendInit() {
                                attempts++;
                                const username = getUsernameFromPage();
                                
                                if (username && isValidUsername(username)) {
                                    // 获取到有效用户名，立即发送
                                    try {
                                        ws.send(JSON.stringify({
                                            type: 'init',
                                            username: username,
                                            user_id: USER_ID
                                        }));
                                        wsLog('已发送初始化消息，用户名:', username);
                                    } catch (e) {
                                        wsError('发送初始化消息失败:', e);
                                    }
                                } else if (attempts < maxAttempts) {
                                    // 未获取到有效用户名，继续尝试
                                    wsWarn(`⚠️ 第 ${attempts} 次尝试获取用户名失败，继续尝试...`);
                                    setTimeout(trySendInit, 1000);
                                } else {
                                    // 达到最大尝试次数，发送默认值
                                    wsWarn('⚠️ 达到最大尝试次数，未能获取到有效用户名，发送默认值');
                                    try {
                                        ws.send(JSON.stringify({
                                            type: 'init',
                                            username: '-',
                                            user_id: USER_ID
                                        }));
                                        wsLog('未能获取到有效用户名，已发送默认值');
                                    } catch (e) {
                                        wsError('发送初始化消息失败:', e);
                                    }
                                }
                            }
                            
                            trySendInit();
                        }
                    }, 2000);  // 延迟 2 秒开始获取用户名
                }
            };

            ws.onmessage = function(event) {
                try {
                    const data = JSON.parse(event.data);
                    handleMessage(data);
                } catch (e) {
                    wsError('解析消息失败:', e);
                }
            };

            ws.onerror = function(error) {
                // 简化错误处理，只记录基本日志，不触发任何操作
                wsLog('连接错误，将自动重连');
                updateConnectionStatus('error');
                isConnecting = false;
            };

            ws.onclose = function(event) {
                wsLog('连接关闭');
                wsLog('关闭代码:', event.code);
                // 清除全局 WebSocket 实例（火狐浏览器兼容性）
                clearGlobalWebSocketInstance(ws);
                wsLog('关闭原因:', event.reason || '无原因');
                wsLog('是否正常关闭:', event.wasClean);
                
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
                    wsError('关闭代码说明:', closeCodeMessages[event.code]);
                }
                
                // 如果是 SSL/TLS 相关错误
                if (event.code === 1015 || event.code === 1006) {
                    // 从 WEBSOCKET_URL 提取域名
                    const urlMatch = WEBSOCKET_URL.match(/wss?:\/\/([^:]+)/);
                    const host = urlMatch ? urlMatch[1] : 'stakefav.xyz';
                    wsError(`💡 这可能是 SSL 证书问题，请检查服务器端 SSL 证书配置`);
                    wsError(`💡 WebSocket 地址: ${WEBSOCKET_URL}`);
                    wsError('💡 或者检查服务器端日志，确认 WebSocket 服务器是否正常启动');
                }
                
                isConnecting = false;
                updateConnectionStatus('error');
                wsLog(`连接关闭 (代码: ${event.code})`);
                
                // 只在状态变化时添加日志（从连接成功变为失败）
                if (lastConnectionStatus === 'connected') {
                    addLog('❌ 连接失败，正在尝试重连中...', 'info');
                    lastConnectionStatus = 'disconnected';
                }
                
                // 自动重连
                if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
                    reconnectAttempts++;
                    updateConnectionStatus('connecting');
                    wsLog(`尝试重连 ${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS}...`);
                    // 不添加日志，因为状态没有变化（仍然是失败状态）
                    setTimeout(connect, RECONNECT_DELAY);
                } else {
                    updateConnectionStatus('error');
                    wsError('达到最大重连次数，请刷新页面');
                    addLog('❌ 连接失败，联系管理员', 'info');
                    // 不添加日志，因为状态没有变化
                }
            };

        } catch (e) {
            wsError('连接异常:', e);
            wsError('异常详情:', e.message, e.stack);
            isConnecting = false;
            updateConnectionStatus('error');
            wsError(`连接异常: ${e.message}`);
        }
    }

    // ==================== 消息处理 ====================
    function handleMessage(data) {
        wsLog('收到消息:', data);

        if (data.type === 'connected') {
            updateConnectionStatus('connected');
            
            // 同步服务器时间
            if (data.server_timestamp_ms) {
                const clientTime = Date.now();
                serverTimeOffset = data.server_timestamp_ms - clientTime;
                wsLog('时间同步:', {
                    server_time: new Date(data.server_timestamp_ms).toISOString(),
                    client_time: new Date(clientTime).toISOString(),
                    offset_ms: serverTimeOffset,
                    offset_sec: (serverTimeOffset / 1000).toFixed(2)
                });
                wsLog(`服务器确认连接 (时间已同步，偏移: ${(serverTimeOffset / 1000).toFixed(2)}秒)`);
            } else {
                wsLog('服务器确认连接');
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
        wsLog('收到代码，立即领取:', code);
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
                wsLog('领取成功:', result.data);
                
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
                        debugLog(`[Stake WS] 💰 自动存入保险库: 原始金额 ${formattedAmount} ${currency}`);
                        depositToVault(depositAmount, currency).then(depositResult => {
                            if (depositResult.success) {
                                const depositedAmount = depositResult.data?.amount || '未知';
                                debugLog(`[Stake WS] ✅ 存入保险库成功: ${depositedAmount} ${currency}`);
                            } else {
                                wsError('❌ 存入保险库失败:', depositResult.error);
                            }
                        });
                    }
                }
            } else {
                addLog(`❌ 领取失败: ${code} - ${result.error}`, 'error');
                wsError('领取失败:', result.error);
                
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
                } else if (result.error.includes('7天内不能领代码') || result.error.includes('dropUnavailable') || result.error.includes('drop_unavailable')) {
                    status = 'drop_unavailable';
                } else if (result.error.includes('Unexpected token') && result.error.includes('<!DOCTYPE')) {
                    // JSON 解析错误，通常是 Cloudflare 验证页面（HTML 而非 JSON），需要手动刷新
                    status = 'error_403';
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
            wsError('领取异常:', e);
            
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
    
    // 验证用户名是否有效
    function isValidUsername(username) {
        if (!username || typeof username !== 'string') {
            return false;
        }
        const trimmed = username.trim();
        if (trimmed.length < 1 || trimmed.length > 50) {
            return false;
        }
        // 过滤无效的用户名模式
        const invalidPatterns = ['user:', 'user:user', 'user:user:user', 'user:user:user:user'];
        const lower = trimmed.toLowerCase();
        for (let pattern of invalidPatterns) {
            if (lower.includes(pattern)) {
                return false;
            }
        }
        // 检查是否只是重复的 "user:" 或 "-"
        const cleaned = lower.replace(/user:/g, '').replace(/-/g, '').replace(/\s/g, '');
        if (cleaned === '') {
            return false;
        }
        // 不能只是 "user" 或 "-"
        if (trimmed === 'user' || trimmed === '-' || trimmed === 'user:') {
            return false;
        }
        return true;
    }
    
    // 从页面中获取用户名（懒加载：延迟获取，等待页面完全加载）
    function getUsernameFromPage() {
        // 如果缓存中有用户名，直接返回（避免 CSP 错误后无法获取）
        if (usernameCache) {
            return usernameCache;
        }
        
        try {
            // 方式1: 从 GraphQL 响应中提取（最可靠的方式）
            // 查找所有包含 GraphQL 数据的 script 标签（支持多种格式，兼容火狐浏览器）
            const graphqlScripts = document.querySelectorAll('script[type="application/json"][data-sveltekit-fetched], script[type="application/json"]');
            for (const script of graphqlScripts) {
                try {
                    const scriptText = script.textContent || script.innerHTML;
                    if (!scriptText || scriptText.trim().length === 0) {
                        continue;
                    }
                    
                    let jsonData;
                    try {
                        jsonData = JSON.parse(scriptText);
                    } catch (e) {
                        continue;
                    }
                    
                    // 检查是否有 user.name 字段（支持多种数据结构）
                    let userData = null;
                    
                    // 结构1: jsonData.body -> bodyData.data.user.name
                    if (jsonData.body) {
                        try {
                            const bodyData = typeof jsonData.body === 'string' ? JSON.parse(jsonData.body) : jsonData.body;
                            if (bodyData.data && bodyData.data.user && bodyData.data.user.name) {
                                userData = bodyData.data.user;
                            }
                        } catch (e) {
                            // 忽略解析错误
                        }
                    }
                    
                    // 结构2: jsonData.data.user.name（直接结构）
                    if (!userData && jsonData.data && jsonData.data.user && jsonData.data.user.name) {
                        userData = jsonData.data.user;
                    }
                    
                    // 结构3: jsonData.user.name（更直接的结构）
                    if (!userData && jsonData.user && jsonData.user.name) {
                        userData = jsonData.user;
                    }
                    
                    if (userData && userData.name) {
                        const username = userData.name;
                        if (isValidUsername(username)) {
                            usernameCache = username;  // 缓存用户名
                            wsLog('从 GraphQL 响应中提取到用户名:', username);
                            return username;
                        }
                    }
                } catch (e) {
                    // 跳过解析失败的 script 标签
                    continue;
                }
            }


            // 方式2: 从所有 script 标签中搜索用户名（备用方案，增强火狐浏览器兼容性）
            const allScripts = document.querySelectorAll('script:not([type="application/json"])');
            for (const script of allScripts) {
                const content = script.textContent || script.innerHTML;
                if (!content || content.length < 10) {
                    continue;  // 跳过太短的内容
                }
                
                // 搜索多种用户名模式
                const patterns = [
                    /"name"\s*:\s*"([^"]{1,50})"/,  // "name":"用户名"
                    /'name'\s*:\s*'([^']{1,50})'/,  // 'name':'用户名'
                    /user\.name\s*=\s*["']([^"']{1,50})["']/,  // user.name = "用户名"
                    /username\s*:\s*["']([^"']{1,50})["']/,  // username: "用户名"
                ];
                
                for (const pattern of patterns) {
                    const match = content.match(pattern);
                    if (match && match[1]) {
                        const potentialUsername = match[1].trim();
                        // 过滤掉明显不是用户名的值
                        if (isValidUsername(potentialUsername) && 
                            potentialUsername.length >= 3 && 
                            potentialUsername.length <= 20 && 
                            /^[a-zA-Z0-9_-]+$/.test(potentialUsername)) {
                            usernameCache = potentialUsername;  // 缓存用户名
                            wsLog('从 script 内容中提取到用户名:', potentialUsername);
                            return potentialUsername;
                        }
                    }
                }
            }
            

            // 方式3: 从 window 全局对象中获取（如果 Stake 页面有暴露）
            try {
                if (window.__STAKE_USER__ && window.__STAKE_USER__.name && isValidUsername(window.__STAKE_USER__.name)) {
                    usernameCache = window.__STAKE_USER__.name;  // 缓存用户名
                    wsLog('从 window.__STAKE_USER__ 中提取到用户名:', window.__STAKE_USER__.name);
                    return window.__STAKE_USER__.name;
                }
                if (window.stakeUser && window.stakeUser.name && isValidUsername(window.stakeUser.name)) {
                    usernameCache = window.stakeUser.name;  // 缓存用户名
                    wsLog('从 window.stakeUser 中提取到用户名:', window.stakeUser.name);
                    return window.stakeUser.name;
                }
                if (window.user && window.user.name && isValidUsername(window.user.name)) {
                    usernameCache = window.user.name;  // 缓存用户名
                    wsLog('从 window.user 中提取到用户名:', window.user.name);
                    return window.user.name;
                }
            } catch (e) {
                // 忽略访问 window 属性的错误
            }
            
            // 方式4: 从页面的用户信息元素中获取（过滤掉包含 "user:" 标签的元素）
            const userElements = document.querySelectorAll('[data-username], [class*="username"], [id*="username"]');
            for (const el of userElements) {
                // 优先使用 data 属性，避免获取到标签文本
                let username = el.getAttribute('data-username') || el.getAttribute('data-user');
                if (!username) {
                    // 如果 data 属性不存在，才使用 textContent，但要过滤掉 "user:" 这样的标签文本
                    const text = el.textContent?.trim();
                    if (text && !text.toLowerCase().includes('user:') && text.length > 0 && text.length < 50) {
                        username = text;
                    }
                }
                if (isValidUsername(username)) {
                    usernameCache = username;  // 缓存用户名
                    wsLog('从页面元素中提取到用户名:', username);
                    return username;
                }
            }
            
       
        } catch (e) {
            wsWarn('获取用户名失败:', e);
        }
        wsWarn('未能提取到有效用户名');
        return null;
    }
    
    // 发送领取结果回服务器
    function sendClaimResultToServer(resultData) {
        if (!ws || ws.readyState !== WebSocket.OPEN) {
            wsWarn('WebSocket 未连接，无法发送领取结果');
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
            wsLog('已发送领取结果到服务器:', message);
        } catch (e) {
            wsError('发送领取结果失败:', e);
        }
    }

    // ==================== GraphQL 领取接口（仿照项目逻辑）====================
    async function claimBonusCodeViaAPI(code) {
        try {
            // 1. 获取必要的请求信息（带重试机制）
            let headers = getRequestHeaders();
            let retryCount = 0;
            const maxRetries = 5;
            
            // 检查 session 是否存在，如果不存在则等待并重试（可能页面还在加载）
            while (!headers['x-access-token'] && retryCount < maxRetries) {
                retryCount++;
                wsWarn(`⚠️ 未找到 session，等待 ${retryCount * 500}ms 后重试 (${retryCount}/${maxRetries})...`);
                await new Promise(resolve => setTimeout(resolve, retryCount * 500));
                
                // 重新获取 headers（会重新从 cookie 中读取 session）
                headers = getRequestHeaders();
            }
            
            if (!headers['x-access-token']) {
                wsError('❌ 无法获取 session，请确保已登录并刷新页面');
                return {
                    success: false,
                    error: '无法获取 session，请确保已登录并刷新页面'
                };
            }
            
            const currency = 'usdt';  // 默认货币类型

            // 2. 获取 Turnstile Token（从页面中获取或等待页面生成）
            let turnstileToken = await getTurnstileToken(code, currency);
            
            if (!turnstileToken) {
                // 如果获取失败，尝试刷新一次
                wsLog('Turnstile Token 获取失败，尝试刷新...');
                const refreshedToken = await refreshTurnstileToken();
                if (!refreshedToken) {
                    return {
                        success: false,
                        error: '获取 Turnstile Token 失败，请确保页面已加载完成'
                    };
                }
                // 使用刷新后的 Turnstile Token
                turnstileToken = refreshedToken;
            }
            
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
            const response = await fetch(getGraphQLApiUrl(), {
                method: 'POST',
                headers: {
                    ...headers,
                    'referer': `${getCurrentOrigin()}/zh/settings/offers?type=drop&code=${code}`,
                    'x-operation-name': 'ClaimConditionBonusCode'
                },
                credentials: 'include',  // 自动包含 Cookie
                body: JSON.stringify(payload)
            });
            
            // 5. 使用 Turnstile Token 后，清空缓存和全局变量，并立即在后台获取新的（不阻塞当前请求）
            turnstileTokenCache = null;
            turnstileTokenExpireTime = null;
            window.__TURNSTILETOKEN__ = null;  // 清空全局变量，确保下次从 widget 获取并触发 callback
            // 后台刷新，确保下次有新的 Turnstile Token 可用（会触发 callback 输出日志）
            wsLog('🔄 使用 Token 后，开始后台刷新 Turnstile Token...');
            refreshTurnstileToken(3).then(token => {
                if (token) {
                    wsLog('✅ 后台刷新 Turnstile Token 成功');
                } else {
                    wsWarn('⚠️ 后台刷新 Turnstile Token 失败，将在下次使用时重试');
                }
            }).catch(e => {
                wsError('❌ 后台刷新 Turnstile Token 异常:', e);
            });

            const responseData = await response.json();
            wsLog('API 响应:', responseData);

            // 6. 解析响应（仿照项目中的逻辑）
            if (response.status === 200) {
                const errors = responseData.errors || [];
                
                if (errors.length > 0) {
                    const error = errors[0];
                    const errorType = error.errorType || '';
                    const errorMsg = error.message || '未知错误';
                    
                    // 检查是否是 invalid_turnstile 错误，如果是则自动刷新 token 并重试一次
                    if (errorType === 'invalidTurnstile' || errorMsg.includes('invalid_turnstile') || errorMsg.includes('invalid turnstile')) {
                        wsWarn('⚠️ 检测到 invalid_turnstile 错误，自动刷新 Turnstile Token 并重试...');
                        
                        // 强制刷新 Turnstile Token
                        turnstileTokenCache = null;
                        turnstileTokenExpireTime = null;
                        window.__TURNSTILETOKEN__ = null;
                        
                        const newToken = await refreshTurnstileToken(3);
                        if (newToken) {
                            wsLog('✅ Turnstile Token 刷新成功，重新发送请求...');
                            // 使用新的 token 重新发送请求（只重试一次）
                            const retryPayload = {
                                "query": "mutation ClaimConditionBonusCode($code: String!, $currency: CurrencyEnum!, $turnstileToken: String!) {\n  claimConditionBonusCode(\n    code: $code\n    currency: $currency\n    turnstileToken: $turnstileToken\n  ) {\n    bonusCode {\n      id\n      code\n    }\n    amount\n    currency\n    user {\n      id\n      balances {\n        available {\n          amount\n          currency\n        }\n      }\n    }\n  }\n}",
                                "variables": {
                                    "code": code,
                                    "currency": currency.toLowerCase(),
                                    "turnstileToken": newToken
                                }
                            };
                            
                            const retryResponse = await fetch(getGraphQLApiUrl(), {
                                method: 'POST',
                                headers: {
                                    ...headers,
                                    'referer': `${getCurrentOrigin()}/zh/settings/offers?type=drop&code=${code}`,
                                    'x-operation-name': 'ClaimConditionBonusCode'
                                },
                                credentials: 'include',
                                body: JSON.stringify(retryPayload)
                            });
                            
                            // 使用新 token 后，清空缓存并后台刷新
                            turnstileTokenCache = null;
                            turnstileTokenExpireTime = null;
                            window.__TURNSTILETOKEN__ = null;
                            refreshTurnstileToken().catch(e => {
                                wsError('后台刷新 Turnstile Token 失败:', e);
                            });
                            
                            const retryResponseData = await retryResponse.json();
                            wsLog('重试 API 响应:', retryResponseData);
                            
                            // 处理重试后的响应
                            if (retryResponse.status === 200) {
                                const retryErrors = retryResponseData.errors || [];
                                if (retryErrors.length > 0) {
                                    // 重试后仍有错误，按正常错误处理
                                    const retryError = retryErrors[0];
                                    const retryErrorType = retryError.errorType || '';
                                    const retryErrorMsg = retryError.message || '未知错误';
                                    return { 
                                        success: false, 
                                        error: retryErrorMsg,
                                        fullResponse: retryResponseData
                                    };
                                } else {
                                    // 重试成功
                                    const claimResult = retryResponseData.data?.claimConditionBonusCode;
                                    const formattedAmount = formatAmount(claimResult?.amount);
                                    return {
                                        success: true,
                                        data: claimResult,
                                        fullResponse: retryResponseData,
                                        message: `领取成功！金额: ${formattedAmount} ${claimResult?.currency || ''}`
                                    };
                                }
                            } else {
                                return {
                                    success: false,
                                    error: `HTTP ${retryResponse.status}`,
                                    fullResponse: retryResponseData
                                };
                            }
                        } else {
                            wsError('❌ Turnstile Token 刷新失败，无法重试');
                            return { 
                                success: false, 
                                error: 'Turnstile Token 无效且刷新失败',
                                fullResponse: responseData
                            };
                        }
                    }
                    
                    // 根据错误类型返回相应状态（与 STATUS_CHOICES 中的显示文案保持一致）
                    let errorStatus = '未知错误';
                    if (errorType === 'notFound' || errorMsg.includes('not found') || errorMsg.includes('cannot be found')) {
                        errorStatus = '代码不存在';
                    } else if (errorType === 'dropUnavailable' || errorMsg.includes('drop_unavailable')) {
                        errorStatus = '7天内不能领代码';
                    } else if (errorType === 'bonusCodeInactive' || errorMsg.includes('unavailable')) {
                        errorStatus = '代码已失效';
                    } else if (errorType === 'disabledSession' || errorMsg.includes('session has expired')) {
                        errorStatus = '会话已过期，请刷新页面';
                    } else if (errorType === 'codeAlreadyClaimed' || errorType === 'already_claimed' || errorMsg.includes('already claimed') || errorMsg.includes('already_claimed')) {
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
            wsError('API 请求异常:', e);
            // 如果是 JSON 解析错误（通常是 Cloudflare 验证页面），转换为友好的错误信息
            let errorMsg = e.message || '请求异常';
            if (errorMsg.includes('Unexpected token') && errorMsg.includes('<!DOCTYPE')) {
                errorMsg = '403错误，请刷新手动验证后重试';
            }
            return {
                success: false,
                error: errorMsg,
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
            'origin': getCurrentOrigin(),
            'user-agent': navigator.userAgent,
        };

        // 获取 session
        const session = getSession();
        if (session) {
            headers['x-access-token'] = session;
        } else {
            wsWarn('未找到 session，可能影响请求');
        }

        return headers;
    }

    // ==================== 获取 session ====================
    // 从 cookie 中获取 session（只获取一次，和登录绑定，不变）
    function getSession() {
        // 如果缓存中有值，直接返回
        if (sessionCache) {
            return sessionCache;
        }
        
        try {
            // 从 cookie 中获取 session 字段（精确匹配，避免匹配到 session_info 等）
            const cookies = document.cookie.split('; ');
            const sessionCookie = cookies.find(row => {
                const [name] = row.split('=');
                return name === 'session';
            });
            
            if (sessionCookie) {
                const value = sessionCookie.split('=')[1];
                if (value) {
                    // 缓存 session，只获取一次，和登录绑定，不变
                    sessionCache = value;
                    debugLog('[session] 获取成功，已缓存');
                    return sessionCache;
                }
            }
            
            // 如果没找到 session cookie
            wsWarn('⚠️ 未找到 session，请确保已登录');
            return null;
        } catch (e) {
            wsError('获取 session 失败:', e);
            return null;
        }
    }

    // ==================== Turnstile Token 获取器 ====================
    const TURNSTILE_SITE_KEY = '0x4AAAAAAAGD4gMGOTFnvupz';
    const TURNSTILE_TOKEN_EXPIRE_TIME = 1 * 60 * 1000;  // Turnstile Token 过期时间（1分钟，毫秒）
    
    let turnstileTokenCache = null;  // Turnstile Token 缓存
    let turnstileTokenExpireTime = null;  // Turnstile Token 过期时间戳
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
                        wsWarn('移除旧 widget 时出错（可忽略）:', e.message);
                    }
                }
                // 清空容器内容
                container.innerHTML = '';
                turnstileWidgetId = null;
            }

            // 渲染 Turnstile widget
            if (window.turnstile && !turnstileWidgetId) {
                try {
                    turnstileWidgetId = window.turnstile.render(container, {
                        sitekey: TURNSTILE_SITE_KEY,
                        callback: function(token) {
                            wsLog('✅ 成功获取 Turnstile Token:', token.substring(0, 20) + '...');
                            // 缓存 Turnstile Token 和过期时间
                            turnstileTokenCache = token;
                            turnstileTokenExpireTime = Date.now() + TURNSTILE_TOKEN_EXPIRE_TIME;
                            window.__TURNSTILETOKEN__ = token;  // 也存储到全局变量
                            isRefreshingToken = false;
                            tokenRefreshPromise = null;
                        },
                        'error-callback': function(err) {
                            wsError('❌ Turnstile 错误:', err);
                            turnstileTokenCache = null;
                            turnstileTokenExpireTime = null;
                            isRefreshingToken = false;
                            tokenRefreshPromise = null;
                            // 自动重试
                            setTimeout(() => {
                                refreshTurnstileToken();
                            }, 2000);
                        },
                        'expired-callback': function() {
                            wsWarn('⚠️ Turnstile Token 已过期，正在自动刷新...');
                            turnstileTokenCache = null;
                            turnstileTokenExpireTime = null;
                            // 自动重置并重新获取
                            refreshTurnstileToken();
                        }
                    });
                    
                    wsLog('✅ Turnstile Token 获取器已初始化');
                } catch (e) {
                    wsError('❌ 初始化 Turnstile Token 获取器失败:', e);
                    throw e;
                }
            }
        } catch (e) {
            wsError('❌ 初始化 Turnstile Token 获取器失败:', e);
        }
    }

    // 刷新 Turnstile Token（重置 widget 以获取新 Token，带重试机制）
    async function refreshTurnstileToken(maxRetries = 3) {
        wsLog(`🔄 refreshTurnstileToken 被调用 (maxRetries=${maxRetries})`);
        
        // 如果正在刷新，等待当前刷新完成
        if (isRefreshingToken && tokenRefreshPromise) {
            wsLog('⏳ Token 正在刷新中，等待当前刷新完成...');
            try {
                const result = await tokenRefreshPromise;
                wsLog('✅ 等待刷新完成，返回结果');
                return result;
            } catch (e) {
                wsWarn('⚠️ 等待刷新时出错，将继续执行新的刷新:', e);
                // 继续执行，不阻塞
            }
        }

        wsLog(`🚀 开始执行 refreshTurnstileToken (将重试最多 ${maxRetries} 次)`);
        let lastError = null;
        for (let attempt = 1; attempt <= maxRetries; attempt++) {
            try {
                if (!window.turnstile) {
                    wsWarn(`Turnstile API 未加载，尝试重新初始化... (尝试 ${attempt}/${maxRetries})`);
                    await initTurnstileTokenGrabber();
                    if (!window.turnstile) {
                        lastError = '无法加载 Turnstile API';
                        if (attempt < maxRetries) {
                            await new Promise(resolve => setTimeout(resolve, 1000 * attempt));
                            continue;
                        }
                        wsError('❌ 无法加载 Turnstile API');
                        return null;
                    }
                }

                // 检查容器是否存在
                let container = document.getElementById('stake-ws-turnstile-container');
                if (!container) {
                    wsWarn(`Turnstile 容器不存在，重新初始化... (尝试 ${attempt}/${maxRetries})`);
                    turnstileWidgetId = null;
                    await initTurnstileTokenGrabber();
                    container = document.getElementById('stake-ws-turnstile-container');
                    if (!container || !turnstileWidgetId) {
                        lastError = '无法初始化 Turnstile widget';
                        if (attempt < maxRetries) {
                            await new Promise(resolve => setTimeout(resolve, 1000 * attempt));
                            continue;
                        }
                        wsError('❌ 无法初始化 Turnstile widget');
                        return null;
                    }
                }

                // 如果 widget ID 无效，重新初始化
                if (!turnstileWidgetId) {
                    wsWarn(`Turnstile widget ID 无效，重新初始化... (尝试 ${attempt}/${maxRetries})`);
                    await initTurnstileTokenGrabber();
                    if (!turnstileWidgetId) {
                        lastError = '无法获取 Turnstile widget ID';
                        if (attempt < maxRetries) {
                            await new Promise(resolve => setTimeout(resolve, 1000 * attempt));
                            continue;
                        }
                        wsError('❌ 无法获取 Turnstile widget ID');
                        return null;
                    }
                }

                isRefreshingToken = true;
                wsLog(`🔄 开始刷新 Turnstile Token... (尝试 ${attempt}/${maxRetries})`);
                
                // 创建刷新 Promise
                tokenRefreshPromise = new Promise((resolve) => {
                    try {
                        // 尝试重置 widget
                        wsLog(`🔄 调用 window.turnstile.reset(${turnstileWidgetId})`);
                        window.turnstile.reset(turnstileWidgetId);
                        wsLog('✅ reset 调用成功，等待新 Token 生成...');
                    } catch (e) {
                        // 如果 reset 失败（例如 widget 不存在），尝试重新初始化
                        wsWarn(`⚠️ Reset 失败，尝试重新初始化 widget: ${e.message}`);
                        turnstileWidgetId = null;
                        turnstileTokenCache = null;
                        window.__TURNSTILETOKEN__ = null;
                        
                        // 重新初始化
                        wsLog('🔄 开始重新初始化 widget...');
                        initTurnstileTokenGrabber().then(() => {
                            wsLog('✅ 重新初始化完成，等待新 Token...');
                            // 等待新 widget 生成 Turnstile Token
                            const checkInterval = setInterval(() => {
                                if (turnstileTokenCache) {
                                    clearInterval(checkInterval);
                                    isRefreshingToken = false;
                                    tokenRefreshPromise = null;
                                    wsLog('✅ Turnstile Token 通过重新初始化获取成功');
                                    resolve(turnstileTokenCache);
                                }
                            }, 500);
                            
                            // 15 秒超时
                            setTimeout(() => {
                                clearInterval(checkInterval);
                                if (!turnstileTokenCache) {
                                    isRefreshingToken = false;
                                    tokenRefreshPromise = null;
                                    wsWarn('⚠️ 重新初始化后 Turnstile Token 获取超时');
                                    resolve(null);
                                }
                            }, 15000);
                        }).catch(err => {
                            wsError('❌ 重新初始化失败:', err);
                            isRefreshingToken = false;
                            tokenRefreshPromise = null;
                            resolve(null);
                        });
                        return;
                    }
                    
                    // 等待新 Turnstile Token 生成（最多等待 15 秒）
                    wsLog('⏳ 等待 widget callback 生成新 Token...');
                    const checkInterval = setInterval(() => {
                        if (turnstileTokenCache) {
                            clearInterval(checkInterval);
                            isRefreshingToken = false;
                            tokenRefreshPromise = null;
                            wsLog('✅ 检测到新 Token，刷新成功');
                            resolve(turnstileTokenCache);
                        }
                    }, 500);
                    
                    // 15 秒超时
                    setTimeout(() => {
                        clearInterval(checkInterval);
                        if (!turnstileTokenCache) {
                            isRefreshingToken = false;
                            tokenRefreshPromise = null;
                            wsWarn('⚠️ Turnstile Token 刷新超时（15秒内未生成）');
                            resolve(null);
                        }
                    }, 15000);
                });
                
                const refreshResult = await tokenRefreshPromise;

                if (refreshResult) {
                    tokenRefreshPromise = null;
                    return refreshResult;
                } else {
                    lastError = 'Turnstile Token 刷新超时';
                    if (attempt < maxRetries) {
                        wsWarn(`⚠️ 刷新失败，${1000 * attempt}ms 后重试... (尝试 ${attempt}/${maxRetries})`);
                        // 清空状态以便重试
                        turnstileTokenCache = null;
                        turnstileTokenExpireTime = null;
                        window.__TURNSTILETOKEN__ = null;
                        await new Promise(resolve => setTimeout(resolve, 1000 * attempt));
                        continue;
                    }
                }
            } catch (e) {
                lastError = e.message;
                wsError(`❌ 刷新 Turnstile Token 异常 (尝试 ${attempt}/${maxRetries}):`, e);
                if (attempt < maxRetries) {
                    turnstileTokenCache = null;
                    turnstileTokenExpireTime = null;
                    window.__TURNSTILETOKEN__ = null;
                    await new Promise(resolve => setTimeout(resolve, 1000 * attempt));
                }
            } finally {
                isRefreshingToken = false;
                tokenRefreshPromise = null;
            }
        }

        wsError(`❌ Turnstile Token 刷新失败（已重试 ${maxRetries} 次）: ${lastError}`);
        return null;
    }

    // ==================== 获取 Turnstile Token ====================
    async function getTurnstileToken(code, currency) {
        // 方式1: 从缓存中获取（检查是否过期）
        if (turnstileTokenCache && turnstileTokenExpireTime) {
            const now = Date.now();
            if (now < turnstileTokenExpireTime) {
                // Token 未过期，直接返回
                debugLog('[Turnstile Token] 使用缓存的 Token');
                return turnstileTokenCache;
            } else {
                // Token 已过期，清空缓存
                wsWarn('⚠️ Turnstile Token 已过期，重新获取...');
                turnstileTokenCache = null;
                turnstileTokenExpireTime = null;
            }
        }

        // 方式2: 从全局变量获取
        if (window.__TURNSTILETOKEN__) {
            turnstileTokenCache = window.__TURNSTILETOKEN__;
            turnstileTokenExpireTime = Date.now() + TURNSTILE_TOKEN_EXPIRE_TIME;
            debugLog('[Turnstile Token] 从全局变量获取');
            return turnstileTokenCache;
        }

        // 方式3: 确保 Turnstile 已初始化
        if (!window.turnstile || !turnstileWidgetId) {
            wsLog('初始化 Turnstile Token 获取器...');
            await initTurnstileTokenGrabber();
            // 等待 Turnstile Token 生成（最多等待 10 秒）
            for (let i = 0; i < 20; i++) {
                await new Promise(resolve => setTimeout(resolve, 500));
                if (turnstileTokenCache || window.__TURNSTILETOKEN__) {
                    const token = turnstileTokenCache || window.__TURNSTILETOKEN__;
                    turnstileTokenCache = token;
                    turnstileTokenExpireTime = Date.now() + TURNSTILE_TOKEN_EXPIRE_TIME;
                    return turnstileTokenCache;
                }
            }
        } else {
            // 如果 widget 已存在但 Turnstile Token 不存在，刷新并等待
            wsLog('刷新 Turnstile widget 以获取新 Turnstile Token...');
            const newToken = await refreshTurnstileToken();
            if (newToken) {
                return newToken;
            }
        }

        // 方式4: 从拦截的网络请求中获取（如果页面已经发送过请求）
        if (window.__TURNSTILETOKEN__) {
            turnstileTokenCache = window.__TURNSTILETOKEN__;
            turnstileTokenExpireTime = Date.now() + TURNSTILE_TOKEN_EXPIRE_TIME;
            return turnstileTokenCache;
        }

        wsWarn('⚠️ 无法获取 Turnstile Token');
        return null;
    }

    // ==================== 拦截网络请求获取 Token ====================
    function interceptNetworkRequests() {
        // 拦截 fetch 请求，从请求头和请求体中获取 token 和 turnstile token
        const originalFetch = window.fetch;
        window.fetch = function(...args) {
            const [url, options] = args;
            
            // 获取 Turnstile token（从请求体中）
            if (options && options.body) {
                try {
                    const body = typeof options.body === 'string' ? JSON.parse(options.body) : options.body;
                    if (body.variables && body.variables.turnstileToken) {
                        window.__TURNSTILETOKEN__ = body.variables.turnstileToken;
                        wsLog('从请求中获取到 Turnstile Token');
                    }
                } catch (e) {
                    // 忽略解析错误
                }
            }
            
            return originalFetch.apply(this, args);
        };

        // 拦截 XMLHttpRequest 的 send 方法，获取请求体中的 Turnstile token
        const originalSend = XMLHttpRequest.prototype.send;
        XMLHttpRequest.prototype.send = function(body) {
            if (body) {
                try {
                    const data = typeof body === 'string' ? JSON.parse(body) : body;
                    if (data.variables && data.variables.turnstileToken) {
                        const token = data.variables.turnstileToken;
                        window.__TURNSTILETOKEN__ = token;
                        if (!turnstileTokenCache) {
                            turnstileTokenCache = token;
                            turnstileTokenExpireTime = Date.now() + TURNSTILE_TOKEN_EXPIRE_TIME;
                        }
                        debugLog('[Turnstile Token] 从 XHR 请求中获取');
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
        wsLog('脚本初始化');
        
        // 确保 document.body 存在后再创建 UI
        function ensureBodyAndCreateUI() {
            if (document.body) {
                try {
                    createStatusUI();
                    wsLog('✅ UI 创建成功');
                } catch (e) {
                    // 使用原始 console.error 输出，避免被拦截
                    originalConsoleError('[Stake WS] ❌ UI 创建失败:', e);
                }
            } else {
                wsWarn('⚠️ document.body 尚未准备好，等待...');
                // 如果 body 还没准备好，等待
                if (document.readyState === 'loading') {
                    document.addEventListener('DOMContentLoaded', function() {
                        if (document.body) {
                            try {
                                createStatusUI();
                                wsLog('✅ UI 创建成功（DOMContentLoaded）');
                            } catch (e) {
                                originalConsoleError('[Stake WS] ❌ UI 创建失败:', e);
                            }
                        } else {
                            setTimeout(ensureBodyAndCreateUI, 100);
                        }
                    });
                } else {
                    setTimeout(ensureBodyAndCreateUI, 100);
                }
            }
        }
        
        ensureBodyAndCreateUI();
        
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

