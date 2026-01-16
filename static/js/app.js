// ==================== 主应用初始化 ====================
import { generateUUID, API_BASE } from './utils.js';
import { Sidebar } from './components/sidebar.js';
import { Chat } from './components/chat.js';
import { MediaLibrary } from './components/media-library.js';
import { Home } from './components/home.js';
import './components/toast.js';  // Toast 通知组件

/**
 * 应用主类
 */
class App {
    constructor() {
        this.sidebar = new Sidebar();
        this.chat = new Chat();
        this.mediaLibrary = new MediaLibrary();
        this.home = new Home();
        this.threadId = null;
    }
    
    /**
     * 初始化应用
     */
    async init() {
        try {
            // 配置 marked.js
            this.configureMarked();
            
            // 解析 URL，获取或创建 threadId
            const { threadId, isNewChat } = this.parseURL();
            this.threadId = threadId;
            
            // 如果没有 threadId，显示首页（不自动创建会话）
            if (!this.threadId) {
                await this.home.init();
                this.removeLoader();
                return;
            }
            
            // 如果不是新会话，先检查会话是否存在
            if (!isNewChat) {
                const exists = await this.checkThreadExists(this.threadId);
                if (!exists) {
                    this.show404Page();
                    this.removeLoader();
                    return;
                }
            }
            
            // 初始化三个组件
            this.sidebar.init(this.threadId);
            
            // 如果是新会话，先初始化 thread，再加载媒体库
            if (isNewChat) {
                // 先初始化聊天（会创建 thread）
                await this.chat.init(this.threadId, isNewChat, this.mediaLibrary, this.sidebar);
                // 然后初始化媒体库（确保 thread 已存在，并传递 Chat 实例）
                await this.mediaLibrary.init(this.threadId, this.chat);
                // 清空 UI 状态参数
                window.history.replaceState({}, '', `/chat/${this.threadId}`);
            } else {
                // 旧会话：先初始化聊天，再初始化媒体库（需要 Chat 实例引用）
                this.chat.init(this.threadId, isNewChat, this.mediaLibrary, this.sidebar);
                await this.mediaLibrary.init(this.threadId, this.chat);
            }
            
            // 聚焦输入框
            const input = document.getElementById('userInput');
            if (input) input.focus();
            
            // 移除加载动画
            this.removeLoader();
        } catch (error) {
            console.error('❌ 应用初始化失败:', error);
            this.removeLoader();
        }
    }
    
    /**
     * 检查会话是否存在
     */
    async checkThreadExists(threadId) {
        try {
            const response = await fetch(`${API_BASE}/thread/${threadId}/messages`);
            return response.ok;
        } catch (error) {
            console.error('检查会话失败:', error);
            return false;
        }
    }
    
    /**
     * 显示 404 错误页面
     */
    show404Page() {
        // 隐藏所有主要组件
        const leftSidebar = document.getElementById('leftSidebar');
        const mainContent = document.querySelector('main');
        const mediaLibrary = document.getElementById('mediaLibrary');
        
        if (leftSidebar) leftSidebar.style.display = 'none';
        if (mediaLibrary) mediaLibrary.style.display = 'none';
        
        // 清空主内容区并显示 404 页面
        if (mainContent) {
            mainContent.innerHTML = `
                <div class="flex items-center justify-center h-full bg-white dark:bg-background-dark">
                    <div class="text-center max-w-md px-6">
                        <span class="material-symbols-outlined text-slate-300 dark:text-slate-700 mb-6 block" style="font-size: 120px;">
                            chat_error
                        </span>
                        <h1 class="text-3xl font-bold text-slate-900 dark:text-white mb-3">对话不存在</h1>
                        <p class="text-slate-600 dark:text-slate-400 mb-8 leading-relaxed">
                            该会话已被删除或不存在<br>
                            请返回首页创建新对话
                        </p>
                        <div class="flex gap-3 justify-center">
                            <button onclick="window.location.href='/'" class="bg-primary hover:bg-primary/90 text-white px-8 py-3 rounded-lg font-semibold transition-all shadow-lg shadow-primary/30 hover:shadow-xl hover:shadow-primary/40 hover:-translate-y-0.5">
                                返回首页
                            </button>
                        </div>
                    </div>
                </div>
            `;
        }
        
    }
    
    /**
     * 移除加载动画
     */
    removeLoader() {
        const loader = document.getElementById('app-loader');
        if (loader) {
            loader.style.opacity = '0';
            setTimeout(() => {
                loader.remove();
            }, 200);
        }
        
        // 移除预加载样式
        setTimeout(() => {
            document.getElementById('preloadStyles')?.remove();
        }, 300);
    }
    
    /**
     * 配置 Markdown 渲染器
     */
    configureMarked() {
        if (typeof marked !== 'undefined') {
            marked.setOptions({
                breaks: true,
                gfm: true,
                sanitize: false,
                smartLists: true,
                smartypants: true
            });
        }
    }
    
    /**
     * 解析 URL
     */
    parseURL() {
        const pathParts = window.location.pathname.split('/');
        const urlParams = new URLSearchParams(window.location.search);
        const isNewChat = urlParams.get('new') === 'true';
        
        let threadId = null;
        if (pathParts[1] === 'chat' && pathParts[2]) {
            threadId = pathParts[2];
        }
        
        return { threadId, isNewChat };
    }
    
}

// 页面加载完成后初始化应用
window.addEventListener('DOMContentLoaded', async () => {
    try {
        const app = new App();
        await app.init();
    } catch (error) {
        console.error('❌ 应用启动失败:', error);
        // 确保移除加载动画
        const loader = document.getElementById('app-loader');
        if (loader) {
            loader.style.opacity = '0';
            setTimeout(() => loader.remove(), 200);
        }
        document.getElementById('preloadStyles')?.remove();
        
        // 显示错误提示
        document.body.innerHTML = `
            <div class="flex items-center justify-center h-screen bg-background-dark">
                <div class="text-center">
                    <span class="material-symbols-outlined text-red-500 text-6xl mb-4">error</span>
                    <p class="text-white text-xl mb-2">应用加载失败</p>
                    <p class="text-slate-400 text-sm mb-4">${error.message}</p>
                    <button onclick="location.reload()" class="bg-primary hover:bg-primary/90 text-white px-6 py-2 rounded-lg">
                        重新加载
                    </button>
                </div>
            </div>
        `;
    }
});

// 全局错误处理
window.addEventListener('error', (event) => {
    console.error('❌ 全局错误:', event.error);
    // 确保移除加载动画
    const loader = document.getElementById('app-loader');
    if (loader) {
        loader.remove();
    }
});

// 模块加载错误处理
window.addEventListener('unhandledrejection', (event) => {
    console.error('❌ 未处理的 Promise 拒绝:', event.reason);
    // 确保移除加载动画
    const loader = document.getElementById('app-loader');
    if (loader) {
        loader.remove();
    }
});

