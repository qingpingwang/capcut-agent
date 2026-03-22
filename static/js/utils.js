// ==================== 公共工具函数 ====================

/**
 * 生成 UUID
 */
export function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
        const r = Math.random() * 16 | 0;
        const v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

/**
 * 创建新对话（统一入口）
 */
export function createNewChat() {
    const newThreadId = generateUUID();
    window.location.href = `/chat/${newThreadId}?new=true`;
}

/**
 * 转义 HTML 并支持 Markdown 渲染
 */
export function escapeHtml(text) {
    if (typeof marked !== 'undefined') {
        try {
            const result = marked.parse(text, { async: false });
            return result;
        } catch (e) {
            console.error('❌ Markdown 解析错误:', e);
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML.replace(/\n/g, '<br>');
        }
    } else {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML.replace(/\n/g, '<br>');
    }
}

/**
 * 滚动到底部
 */
export function scrollToBottom() {
    const messages = document.getElementById('chatMessages');
    if (messages) {
        messages.scrollTo({
            top: messages.scrollHeight,
            behavior: 'smooth'
        });
    }
}

/**
 * DOM 操作工具函数
 */
export const DOM = {
    // 更新按钮状态
    updateButtonState(btnId, icon, title) {
        const btn = document.getElementById(btnId);
        if (!btn) return;

        const iconEl = btn.querySelector('.material-symbols-outlined');
        if (iconEl) iconEl.textContent = icon;
        btn.title = title;
    },

    // 切换元素显示
    toggleElementsDisplay(elements, show) {
        elements.forEach(el => {
            if (el) el.style.display = show ? '' : 'none';
        });
    },

    // 切换 CSS 类
    swapClasses(element, remove, add) {
        if (!element) return;
        element.classList.remove(remove);
        element.classList.add(add);
    },

    // 创建元素
    createElement(tag, className, innerHTML = '') {
        const el = document.createElement(tag);
        if (className) el.className = className;
        if (innerHTML) el.innerHTML = innerHTML;
        return el;
    }
};

/**
 * UI 状态管理
 */
export const UI_STATE = {
    MEDIA_COLLAPSED: 1 << 0,   // bit 0: 媒体库折叠
    MEDIA_FULLSCREEN: 1 << 1,  // bit 1: 媒体库全屏
    SIDEBAR_COLLAPSED: 1 << 2  // bit 2: 左侧边栏折叠（预留）
};

/**
 * 从 URL 读取 UI 状态
 */
export function getUIStateFromURL() {
    const urlParams = new URLSearchParams(window.location.search);
    const ui = parseInt(urlParams.get('ui') || '0', 10);
    return {
        mediaCollapsed: !!(ui & UI_STATE.MEDIA_COLLAPSED),
        mediaFullscreen: !!(ui & UI_STATE.MEDIA_FULLSCREEN),
        leftSidebarCollapsed: !!(ui & UI_STATE.SIDEBAR_COLLAPSED)
    };
}

/**
 * 保存 UI 状态到 URL
 */
export function saveUIState(state) {
    let uiValue = 0;
    if (state.mediaCollapsed) uiValue |= UI_STATE.MEDIA_COLLAPSED;
    if (state.mediaFullscreen) uiValue |= UI_STATE.MEDIA_FULLSCREEN;
    if (state.leftSidebarCollapsed) uiValue |= UI_STATE.SIDEBAR_COLLAPSED;

    const url = new URL(window.location.href);
    if (uiValue > 0) {
        url.searchParams.set('ui', uiValue.toString());
    } else {
        url.searchParams.delete('ui');
    }

    window.history.replaceState({}, '', url.toString());
}

/**
 * 复制 Resource ID 到剪贴板
 */
export function copyResourceId(resourceId) {
    if (!resourceId) return;

    // 使用现代 Clipboard API
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(resourceId).then(() => {
            showCopyToast('已复制 Resource ID', 'success');
        }).catch(err => {
            console.error('复制失败:', err);
            // 降级到传统方法
            fallbackCopy(resourceId);
        });
    } else {
        // 降级到传统方法
        fallbackCopy(resourceId);
    }
}

/**
 * 传统复制方法（兼容旧浏览器）
 */
function fallbackCopy(text) {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();

    try {
        document.execCommand('copy');
        showCopyToast('已复制 Resource ID', 'success');
    } catch (err) {
        console.error('复制失败:', err);
        showCopyToast('复制失败', 'error');
    } finally {
        document.body.removeChild(textarea);
    }
}

/**
 * 显示复制提示（简化版 Toast）
 */
function showCopyToast(message, type = 'success') {
    const bgColor = type === 'success' ? 'bg-green-500' : 'bg-red-500';
    const icon = type === 'success' ? 'check_circle' : 'error';

    const toast = document.createElement('div');
    toast.className = `fixed bottom-4 right-4 ${bgColor} text-white px-4 py-2 rounded-lg shadow-lg flex items-center gap-2 z-[200] animate-slide-in`;
    toast.innerHTML = `
        <span class="material-symbols-outlined text-lg">${icon}</span>
        <span class="text-sm font-medium">${message}</span>
    `;

    document.body.appendChild(toast);

    // 2秒后自动移除
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(20px)';
        toast.style.transition = 'all 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 2000);
}

// 将函数挂载到 window 对象，使其可以在 HTML 的 onclick 中调用
window.copyResourceId = copyResourceId;

/**
 * API 配置
 */
export const API_BASE = 'http://localhost:5001/api';

/**
 * HTTP 请求封装
 */
export const HTTP = {
    async get(url) {
        const response = await fetch(url);
        return await response.json();
    },

    async post(url, data) {
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        return await response.json();
    },

    async delete(url) {
        const response = await fetch(url, {
            method: 'DELETE'
        });
        return await response.json();
    }
};

