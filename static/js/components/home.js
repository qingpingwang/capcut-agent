// ==================== 首页组件 ====================
import { generateUUID, API_BASE, createNewChat } from '../utils.js';

export class Home {
    constructor() {
        this.container = null;
    }
    
    /**
     * 初始化首页
     */
    async init() {
        try {
            // 隐藏所有其他组件
            this.hideOtherComponents();
            
            // 创建首页容器
            this.createContainer();
            
            // 加载历史对话
            await this.loadThreads();
            
        } catch (error) {
            console.error('❌ 首页初始化失败:', error);
        }
    }
    
    /**
     * 隐藏其他组件
     */
    hideOtherComponents() {
        const leftSidebar = document.getElementById('leftSidebar');
        const mainContent = document.querySelector('main');
        const mediaLibrary = document.getElementById('mediaLibrary');
        
        if (leftSidebar) leftSidebar.style.display = 'none';
        if (mainContent) mainContent.style.display = 'none';
        if (mediaLibrary) mediaLibrary.style.display = 'none';
    }
    
    /**
     * 创建首页容器
     */
    createContainer() {
        // 创建首页容器
        this.container = document.createElement('div');
        this.container.id = 'homePage';
        // 行业方案：使用极亮的靛蓝/天蓝渐变，显著提升视觉亮度
        this.container.className = 'flex-1 bg-gradient-to-br from-white via-blue-50/40 to-indigo-50/40 dark:from-[#1e2544] dark:via-[#13172e] dark:to-[#1b213e] overflow-y-auto lg:overflow-hidden relative flex flex-col h-full transition-colors duration-500';
        
        this.container.innerHTML = `
            <!-- 背景修饰：显著增强的亮色光晕 -->
            <div class="absolute inset-0 overflow-hidden pointer-events-none opacity-60 dark:opacity-30">
                <div class="absolute -top-32 -left-32 w-[500px] h-[500px] bg-primary/20 rounded-full blur-[120px] animate-pulse"></div>
                <div class="absolute top-1/2 -right-32 w-[400px] h-[400px] bg-indigo-400/20 rounded-full -translate-y-1/2 blur-[100px]"></div>
                <div class="absolute -bottom-32 left-1/2 w-[450px] h-[450px] bg-blue-300/15 rounded-full -translate-x-1/2 blur-[100px]"></div>
            </div>

            <!-- 1. Hero Section: 精简版 (缩减尺寸) -->
            <section class="shrink-0 bg-transparent px-6 py-6 xl:py-8 relative text-center">
                <div class="relative max-w-7xl mx-auto flex flex-col items-center gap-3 xl:gap-4">
                    <div class="flex flex-col items-center gap-2 xl:gap-3">
                        <div class="w-10 h-10 xl:w-14 xl:h-14 bg-primary/10 dark:bg-primary/20 rounded-2xl flex items-center justify-center text-primary transition-all shadow-sm ring-2 ring-white/50 dark:ring-white/5">
                            <span class="material-symbols-outlined text-2xl xl:text-4xl font-bold">movie_edit</span>
                        </div>
                        <div>
                            <h1 class="text-2xl xl:text-3xl font-black text-slate-900 dark:text-white tracking-tight transition-all">视频剪辑助手</h1>
                            <p class="hidden sm:block text-[10px] xl:text-xs text-primary/60 dark:text-indigo-300 font-bold uppercase tracking-[0.2em] mt-1">AI Intelligent Video Editor</p>
                        </div>
                    </div>
                    
                    <button id="homeNewProjectBtn" class="flex items-center gap-2 bg-primary hover:bg-primary/90 text-white font-bold px-8 py-2.5 xl:px-10 xl:py-3.5 rounded-xl shadow-xl shadow-primary/20 hover:shadow-primary/40 hover:-translate-y-0.5 transition-all active:scale-95 text-xs xl:text-sm">
                        <span class="material-symbols-outlined font-bold text-lg xl:text-xl">add_circle</span>
                        <span>新建剪辑项目</span>
                    </button>
                </div>
            </section>
            
            <!-- 2. Main Area: 最近对话 -->
            <section class="flex-[4] flex flex-col min-h-[320px] bg-transparent overflow-hidden">
                <div class="max-w-6xl w-full mx-auto px-6 py-4 xl:py-6 flex flex-col h-full min-h-0 transition-all">
                    <div class="flex items-center justify-between mb-4 xl:mb-6 shrink-0 px-2">
                        <h2 class="text-lg xl:text-2xl font-extrabold text-slate-900 dark:text-white flex items-center gap-3">
                            <span class="material-symbols-outlined text-primary text-xl xl:text-3xl">history</span>
                            最近对话
                        </h2>
                    </div>
                    
                    <!-- 更加通透的极亮磨砂背景 -->
                    <div class="flex-1 bg-white/85 dark:bg-white/10 rounded-[32px] border border-white dark:border-white/20 p-4 xl:p-8 overflow-hidden flex flex-col shadow-2xl shadow-indigo-100 dark:shadow-none backdrop-blur-2xl ring-1 ring-black/[0.02]">
                        <div id="homeThreadList" class="flex-1 overflow-y-auto flex flex-col gap-2 xl:gap-3 pr-1 scroll-smooth">
                            <!-- 动态加载 -->
                        </div>
                    </div>
                </div>
            </section>
            
            <!-- 3. Footer Area: 亮化版页脚 -->
            <section class="shrink-0 py-6 xl:py-8 px-6 border-t border-white/50 dark:border-white/10 bg-white/80 dark:bg-white/5 backdrop-blur-md min-h-fit">
                <div class="max-w-6xl mx-auto w-full shrink-0">
                    <div class="grid grid-cols-1 sm:grid-cols-3 gap-8 xl:gap-20 text-center sm:text-left">
                        <div class="flex items-center sm:items-start gap-3 xl:gap-5">
                            <div class="w-8 h-8 xl:w-14 xl:h-14 bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 rounded-lg xl:rounded-xl flex items-center justify-center shrink-0">
                                <span class="material-symbols-outlined text-lg xl:text-3xl">auto_awesome</span>
                            </div>
                            <div class="min-w-0">
                                <h3 class="text-xs xl:text-xl font-bold text-slate-900 dark:text-white truncate">AI 智能剪辑</h3>
                                <p class="hidden md:block text-[11px] xl:text-sm text-slate-500 dark:text-slate-400 leading-snug">自动完成转场与特效。</p>
                            </div>
                        </div>
                        
                        <div class="flex items-center sm:items-start gap-3 xl:gap-5">
                            <div class="w-8 h-8 xl:w-14 xl:h-14 bg-purple-100 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400 rounded-lg xl:rounded-xl flex items-center justify-center shrink-0">
                                <span class="material-symbols-outlined text-lg xl:text-3xl">folder_open</span>
                            </div>
                            <div class="min-w-0">
                                <h3 class="text-xs xl:text-xl font-bold text-slate-900 dark:text-white truncate">素材管理</h3>
                                <p class="hidden md:block text-[11px] xl:text-sm text-slate-500 dark:text-slate-400 leading-snug">支持一键引用多种格式。</p>
                            </div>
                        </div>
                        
                        <div class="flex items-center sm:items-start gap-3 xl:gap-5">
                            <div class="w-8 h-8 xl:w-14 xl:h-14 bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400 rounded-lg xl:rounded-xl flex items-center justify-center shrink-0">
                                <span class="material-symbols-outlined text-lg xl:text-3xl">speed</span>
                            </div>
                            <div class="min-w-0">
                                <h3 class="text-xs xl:text-xl font-bold text-slate-900 dark:text-white truncate">高效迭代</h3>
                                <p class="hidden md:block text-[11px] xl:text-sm text-slate-500 dark:text-slate-400 leading-snug">对话间转化您的创意。</p>
                            </div>
                        </div>
                    </div>
                </div>
            </section>
        `;
        
        document.body.appendChild(this.container);
        
        // 绑定新建项目按钮事件
        const newProjectBtn = document.getElementById('homeNewProjectBtn');
        if (newProjectBtn) {
            newProjectBtn.onclick = createNewChat;
        }
    }
    
    /**
     * 删除单个对话
     */
    async deleteThread(threadId, event) {
        event.stopPropagation();
        event.preventDefault();
        
        try {
            const response = await fetch(`${API_BASE}/thread/${threadId}`, { method: 'DELETE' });
            const data = await response.json();
            
            if (data.success) {
                // 重新加载列表
                await this.loadThreads();
            } else {
                alert('删除失败: ' + data.error);
            }
        } catch (error) {
            console.error('删除失败:', error);
            alert('删除失败: ' + error.message);
        }
    }
    
    /**
     * 加载历史对话
     */
    async loadThreads() {
        try {
            const response = await fetch(`${API_BASE}/threads`);
            const data = await response.json();
            
            const threadList = document.getElementById('homeThreadList');
            if (!threadList) return;
            
            if (!data.success || !data.threads || data.threads.length === 0) {
                // 显示空状态
                threadList.innerHTML = `
                    <div class="flex flex-col items-center justify-center py-6 text-center">
                        <span class="material-symbols-outlined text-slate-300 dark:text-slate-600 mb-2" style="font-size: 48px;">
                            chat_bubble_outline
                        </span>
                        <p class="text-slate-500 dark:text-slate-400 text-xs">
                            还没有任何对话记录
                        </p>
                    </div>
                `;
                return;
            }
            
            // 排序：最新的在最上面
            const sortedThreads = data.threads.sort((a, b) => {
                const timeA = a.updated_at ? new Date(a.updated_at).getTime() : 0;
                const timeB = b.updated_at ? new Date(b.updated_at).getTime() : 0;
                return timeB - timeA;
            });
            
            // 渲染所有对话（支持大屏缩放的卡片）
            threadList.innerHTML = sortedThreads.map(thread => {
                const displayTitle = thread.title || '新对话';
                const timeText = this.formatTime(thread.updated_at);
                
                return `
                    <div class="group flex items-center gap-4 px-4 py-3 xl:px-6 xl:py-5 rounded-xl xl:rounded-2xl bg-white dark:bg-bubble-agent border border-slate-200/50 dark:border-slate-700/50 shadow-sm hover:shadow-md hover:border-primary/30 transition-all w-full">
                        <!-- 状态图标 -->
                        <div class="flex-shrink-0 w-10 h-10 xl:w-14 xl:h-14 rounded-lg xl:rounded-xl bg-primary/5 dark:bg-primary/20 flex items-center justify-center text-primary group-hover:scale-110 transition-transform">
                            <span class="material-symbols-outlined xl:text-3xl">chat_bubble</span>
                        </div>
                        
                        <!-- 标题区域 -->
                        <div class="flex-1 min-w-0 cursor-pointer" onclick="window.location.href='/chat/${thread.thread_id}'">
                            <h3 class="text-sm xl:text-xl font-bold text-slate-900 dark:text-white truncate group-hover:text-primary transition-colors" title="${thread.title || '新对话'}">
                                ${this.escapeHtml(displayTitle)}
                            </h3>
                            <div class="flex items-center gap-2 mt-0.5 xl:mt-1">
                                <span class="text-[10px] xl:text-xs text-slate-400 dark:text-slate-500 font-medium">
                                    上次修改：${timeText}
                                </span>
                            </div>
                        </div>
                        
                        <!-- 操作栏 -->
                        <div class="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                            <button onclick="window.homeInstance.deleteThread('${thread.thread_id}', event)" 
                                    class="p-2 xl:p-3 text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-all"
                                    title="删除对话">
                                <span class="material-symbols-outlined text-lg xl:text-2xl">delete</span>
                            </button>
                        </div>
                    </div>
                `;
            }).join('');
            
            // 保存实例引用供全局使用
            window.homeInstance = this;
            
        } catch (error) {
            console.error('加载对话列表失败:', error);
        }
    }
    
    
    /**
     * 格式化时间为相对时间
     */
    formatTime(timeStr) {
        if (!timeStr) return '';
        
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
            return `${Math.floor(diff / minute)} 分钟前`;
        } else if (diff < day) {
            return `${Math.floor(diff / hour)} 小时前`;
        } else if (diff < week) {
            return `${Math.floor(diff / day)} 天前`;
        } else {
            return `${createdDate.getFullYear()}年${createdDate.getMonth() + 1}月${createdDate.getDate()}日`;
        }
    }
    
    /**
     * 转义 HTML
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    /**
     * 销毁首页
     */
    destroy() {
        if (this.container) {
            this.container.remove();
            this.container = null;
        }
    }
}

