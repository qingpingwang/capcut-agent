// ==================== 左侧栏组件 ====================
import { saveUIState, getUIStateFromURL, DOM, createNewChat, navigateTo } from '../utils.js';
import { relativeTime, threadIndicator } from '../chat/thread-state.js';

export class Sidebar {
    constructor(store) {
        this.store = store;
        this.currentThreadId = null;
        this.collapsed = false;
        this.unsubscribe = store.subscribe((threads, reason) => {
            if (reason === 'clock') this.updateTimes();
            else this.renderThreads(threads);
        });
    }
    
    /**
     * 初始化侧边栏
     */
    init(threadId) {
        this.currentThreadId = threadId;
        if (!this.initialized) {
            this.bindEvents();
            this.restoreState();
            this.initialized = true;
        }
        this.renderThreads(this.store.values());
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
        navigateTo('/');
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
        return relativeTime(timeStr);
    }

    updateTimes() {
        document.querySelectorAll('#threadItems time').forEach(element => {
            element.textContent = relativeTime(element.dateTime);
        });
    }
    
    /**
     * 加载会话列表
     */
    async loadThreadList() { return this.store.refresh(); }

    renderThreads(threads) {
        const container = document.getElementById('threadItems');
        if (!container) return;
        const items = threads.map(thread => {
            const active = thread.thread_id === this.currentThreadId;
            const item = document.createElement('button');
            item.className = `thread-item ${active ? 'is-active' : ''}`;
            item.dataset.threadId = thread.thread_id;
            if (active) item.setAttribute('aria-current', 'page');
            const icon = document.createElement('span');
            icon.className = 'material-symbols-outlined thread-icon';
            icon.textContent = 'chat_bubble';
            icon.setAttribute('aria-hidden', 'true');
            const body = document.createElement('div');
            body.className = 'thread-item-body';
            const title = document.createElement('p');
            title.className = 'thread-item-title';
            title.textContent = thread.title || '新对话';
            title.title = title.textContent;
            const time = document.createElement('time');
            time.dateTime = thread.updated_at || '';
            time.textContent = relativeTime(thread.updated_at);
            body.append(title, time);
            item.append(icon, body);
            const status = threadIndicator(thread, active);
            if (status) {
                const dot = document.createElement('span');
                dot.className = `thread-dot is-${status}`;
                dot.setAttribute('role', 'img');
                dot.setAttribute('aria-label', status === 'running' ? '聊天中' : '有新的完成结果');
                dot.title = status === 'running' ? '聊天中' : '已结束，点击查看';
                item.append(dot);
            }
            item.onclick = () => this.switchThread(thread.thread_id);
            return item;
        });
        container.replaceChildren(...items);
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
        navigateTo(url);
    }
    
    /**
     * 更新标题
     */
    updateTitle(title) {
        const titleEl = document.querySelector('main:not([hidden]) [data-chat-element="chatTitle"]');
        if (titleEl) {
            titleEl.textContent = title;
        }
    }
}
