// ==================== 左侧栏组件 ====================
import { generateUUID, API_BASE, HTTP, saveUIState, getUIStateFromURL, UI_STATE, DOM, createNewChat } from '../utils.js';

export class Sidebar {
    constructor() {
        this.currentThreadId = null;
        this.collapsed = false;
    }
    
    /**
     * 初始化侧边栏
     */
    init(threadId) {
        this.currentThreadId = threadId;
        this.bindEvents();
        this.loadThreadList();
        this.restoreState();
    }
    
    /**
     * 绑定事件
     */
    bindEvents() {
        // 首页按钮
        const homeBtn = document.getElementById('homeBtn');
        if (homeBtn) {
            homeBtn.onclick = () => this.goHome();
        }
        
        const newChatBtn = document.querySelector('button[onclick="createNewChat()"]');
        if (newChatBtn) {
            newChatBtn.onclick = createNewChat;
        }
        
        // 折叠按钮
        const collapseBtn = document.getElementById('leftSidebarCollapseBtn');
        if (collapseBtn) {
            collapseBtn.onclick = (e) => {
                e.preventDefault();
                e.stopPropagation();
                this.toggle();
            };
        }
    }
    
    /**
     * 返回首页
     */
    goHome() {
        window.location.href = '/';
    }
    
    /**
     * 折叠/展开侧边栏
     */
    toggle() {
        const sidebar = document.getElementById('leftSidebar');
        if (!sidebar) return;
        
        this.collapsed = !this.collapsed;
        
        if (this.collapsed) {
            // 折叠状态
            DOM.swapClasses(sidebar, 'w-64', 'w-12');
            // 隐藏内容
            sidebar.querySelectorAll('.p-4 > *:not(#leftSidebarCollapseBtn)').forEach(el => {
                el.style.display = 'none';
            });
            DOM.updateButtonState('leftSidebarCollapseBtn', 'keyboard_double_arrow_right', '展开侧边栏');
            
            // 创建展开按钮
            this.createExpandButton(sidebar);
        } else {
            // 展开状态
            DOM.swapClasses(sidebar, 'w-12', 'w-64');
            // 显示内容
            sidebar.querySelectorAll('.p-4 > *').forEach(el => {
                el.style.display = '';
            });
            DOM.updateButtonState('leftSidebarCollapseBtn', 'keyboard_double_arrow_left', '折叠侧边栏');
            
            // 移除展开按钮
            document.getElementById('expandLeftSidebarBtn')?.remove();
        }
        
        this.saveState();
    }
    
    /**
     * 创建展开按钮
     */
    createExpandButton(sidebar) {
        if (document.getElementById('expandLeftSidebarBtn')) return;
        
        const btn = document.createElement('button');
        btn.id = 'expandLeftSidebarBtn';
        btn.className = 'absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-slate-400 hover:text-primary p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5 transition-colors z-10';
        btn.innerHTML = '<span class="material-symbols-outlined text-2xl">keyboard_double_arrow_right</span>';
        btn.onclick = () => this.toggle();
        btn.title = '展开侧边栏';
        
        sidebar.style.position = 'relative';
        sidebar.appendChild(btn);
    }
    
    /**
     * 保存状态
     */
    saveState() {
        const state = getUIStateFromURL();
        saveUIState({
            ...state,
            leftSidebarCollapsed: this.collapsed
        });
    }
    
    /**
     * 恢复状态
     */
    restoreState() {
        const state = getUIStateFromURL();
        this.collapsed = state.leftSidebarCollapsed;
        
        if (this.collapsed) {
            const sidebar = document.getElementById('leftSidebar');
            if (!sidebar) return;
            
            DOM.swapClasses(sidebar, 'w-64', 'w-12');
            sidebar.querySelectorAll('.p-4 > *:not(#leftSidebarCollapseBtn)').forEach(el => {
                el.style.display = 'none';
            });
            DOM.updateButtonState('leftSidebarCollapseBtn', 'keyboard_double_arrow_right', '展开侧边栏');
            this.createExpandButton(sidebar);
        }
    }
    
    
    /**
     * 格式化时间为相对时间
     * 支持 ISO 8601 格式：'2026-01-07T03:42:33.875834+00:00'
     */
    formatTime(timeStr) {
        if (!timeStr) return '';
        
        // 解析 ISO 8601 格式的时间字符串
        const createdDate = new Date(timeStr);
        const now = Date.now();
        const diff = now - createdDate.getTime();
        
        const minute = 60 * 1000;
        const hour = 60 * minute;
        const day = 24 * hour;
        const week = 7 * day;
        
        if (diff < minute) {
            return '刚刚';
        } else if (diff < hour) {
            return `${Math.floor(diff / minute)}分钟前`;
        } else if (diff < day) {
            return `${Math.floor(diff / hour)}小时前`;
        } else if (diff < week) {
            return `${Math.floor(diff / day)}天前`;
        } else {
            // 超过一周，显示具体日期
            return `${createdDate.getMonth() + 1}/${createdDate.getDate()}`;
        }
    }
    
    /**
     * 加载会话列表
     */
    async loadThreadList() {
        try {
            const response = await fetch(`${API_BASE}/threads`);
            const data = await response.json();
            
            if (!data.success) return;
            
            const threadItems = document.getElementById('threadItems');
            if (!threadItems) return;
            
            threadItems.innerHTML = '';
            
            // 前端按最后更新时间倒序排序（最新的在最上面）
            const sortedThreads = data.threads.sort((a, b) => {
                const timeA = a.updated_at ? new Date(a.updated_at).getTime() : 0;
                const timeB = b.updated_at ? new Date(b.updated_at).getTime() : 0;
                return timeB - timeA;
            });
            
            sortedThreads.forEach(thread => {
                const isActive = thread.thread_id === this.currentThreadId;
                const displayTitle = thread.title || '新对话';  // 后端已处理长度
                const timeText = this.formatTime(thread.updated_at);
                
                const item = document.createElement('button');
                item.className = `flex items-center gap-3 p-3 w-full rounded-lg ${
                    isActive 
                        ? 'bg-slate-100 dark:bg-[#232948]' 
                        : 'hover:bg-slate-50 dark:hover:bg-white/5'
                } group text-left transition-colors`;
                
                item.innerHTML = `
                    <span class="material-symbols-outlined text-slate-500 dark:text-slate-300 text-[20px]">chat_bubble</span>
                    <div class="flex-1 overflow-hidden min-w-0">
                        <p class="text-sm font-medium truncate ${
                            isActive 
                                ? 'text-slate-900 dark:text-white' 
                                : 'text-slate-700 dark:text-slate-300'
                        }" title="${thread.title || '新对话'}">${displayTitle}</p>
                        <p class="text-xs text-slate-400 dark:text-slate-500 mt-0.5">${timeText}</p>
                    </div>
                `;
                
                item.onclick = () => this.switchThread(thread.thread_id);
                threadItems.appendChild(item);
            });
            
        } catch (error) {
            console.error('Load thread list error:', error);
        }
    }
    
    /**
     * 切换会话
     */
    switchThread(threadId) {
        // 获取当前 UI 状态
        const urlParams = new URLSearchParams(window.location.search);
        const ui = urlParams.get('ui');
        
        // 切换会话时保留 UI 状态
        const url = ui ? `/chat/${threadId}?ui=${ui}` : `/chat/${threadId}`;
        window.location.href = url;
    }
    
    /**
     * 更新标题
     */
    updateTitle(title) {
        const titleEl = document.getElementById('chatTitle');
        if (titleEl) {
            titleEl.textContent = title;
        }
    }
}

