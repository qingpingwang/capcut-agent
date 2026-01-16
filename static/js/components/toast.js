// ==================== Toast 通知组件 ====================

/**
 * Toast 管理器（单例模式）
 * 支持队列管理，多个 Toast 自动堆叠显示
 */
class ToastManager {
    constructor() {
        if (ToastManager.instance) {
            return ToastManager.instance;
        }
        
        this.toasts = [];  // Toast 队列
        this.container = null;
        this.initContainer();
        
        ToastManager.instance = this;
    }
    
    /**
     * 初始化容器
     */
    initContainer() {
        this.container = document.createElement('div');
        this.container.id = 'toast-container';
        this.container.className = 'fixed top-4 right-4 z-[200] flex flex-col gap-2';
        document.body.appendChild(this.container);
    }
    
    /**
     * 显示 Toast
     * @param {string} message - 提示信息
     * @param {string} type - 类型: success, info, warning, error
     * @param {number} duration - 显示时长（毫秒），默认 3000
     */
    show(message, type = 'success', duration = 3000) {
        const toast = this.createToast(message, type);
        
        // 添加到容器
        this.container.appendChild(toast);
        this.toasts.push(toast);
        
        // 触发进入动画
        setTimeout(() => {
            toast.style.opacity = '1';
            toast.style.transform = 'translateX(0)';
        }, 10);
        
        // 定时移除
        setTimeout(() => {
            this.remove(toast);
        }, duration);
        
        return toast;
    }
    
    /**
     * 创建 Toast 元素
     */
    createToast(message, type) {
        const config = {
            success: {
                bg: 'bg-green-500',
                icon: 'check_circle'
            },
            info: {
                bg: 'bg-blue-500',
                icon: 'info'
            },
            warning: {
                bg: 'bg-yellow-500',
                icon: 'warning'
            },
            error: {
                bg: 'bg-red-500',
                icon: 'error'
            }
        };
        
        const { bg, icon } = config[type] || config.success;
        
        const toast = document.createElement('div');
        toast.className = `${bg} text-white px-4 py-3 rounded-lg shadow-lg flex items-center gap-2 min-w-[250px] max-w-[400px] transition-all duration-300`;
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        
        toast.innerHTML = `
            <span class="material-symbols-outlined text-xl flex-shrink-0">${icon}</span>
            <span class="text-sm font-medium flex-1">${this.escapeHtml(message)}</span>
            <button class="toast-close-btn text-white/80 hover:text-white transition-colors flex-shrink-0" title="关闭">
                <span class="material-symbols-outlined text-lg">close</span>
            </button>
        `;
        
        // 绑定关闭按钮
        const closeBtn = toast.querySelector('.toast-close-btn');
        closeBtn.onclick = () => this.remove(toast);
        
        return toast;
    }
    
    /**
     * 移除 Toast
     */
    remove(toast) {
        if (!toast || !toast.parentElement) return;
        
        // 退出动画
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        
        setTimeout(() => {
            if (toast.parentElement) {
                toast.remove();
            }
            
            // 从队列中移除
            const index = this.toasts.indexOf(toast);
            if (index > -1) {
                this.toasts.splice(index, 1);
            }
        }, 300);
    }
    
    /**
     * 清空所有 Toast
     */
    clear() {
        this.toasts.forEach(toast => this.remove(toast));
        this.toasts = [];
    }
    
    /**
     * 转义 HTML
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// 创建全局单例
const toastManager = new ToastManager();

/**
 * 全局 Toast 函数（简化调用）
 */
export function showToast(message, type = 'success', duration = 3000) {
    return toastManager.show(message, type, duration);
}

export function clearToasts() {
    toastManager.clear();
}

// 挂载到 window（兼容 HTML onclick）
window.showToast = showToast;
window.clearToasts = clearToasts;

export default toastManager;


