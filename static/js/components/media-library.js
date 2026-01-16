// ==================== 媒体库组件 ====================
import { DOM, getUIStateFromURL, saveUIState, API_BASE } from '../utils.js';
import { showToast } from './toast.js';

export class MediaLibrary {
    constructor() {
        this.collapsed = false;
        this.fullscreen = false;
        this.threadId = null;
        this.resources = [];
        this.currentFilter = 'all';  // 当前筛选类型
        this.searchKeyword = '';     // 搜索关键词
        this.chat = null;            // Chat 实例引用，用于访问 isStreaming 状态
    }
    
    /**
     * 获取媒体库相关元素
     */
    getElements() {
        return {
            library: document.getElementById('mediaLibrary'),
            collapseBtn: document.getElementById('mediaLibraryCollapseBtn'),
            fullscreenBtn: document.getElementById('mediaLibraryFullscreenBtn'),
            mediaList: document.querySelector('#mediaLibrary .flex-1.overflow-y-auto'),
            leftSidebar: document.getElementById('leftSidebar'),
            mainContent: document.querySelector('main')
        };
    }
    
    /**
     * 初始化媒体库
     */
    async init(threadId, chat = null) {
        try {
            this.threadId = threadId;
            this.chat = chat;  // 保存 Chat 实例引用
            this.bindEvents();
            
            // 加载素材列表
            await this.loadResources();
            
            // 延迟恢复状态（确保 DOM 完全加载）
            setTimeout(() => {
                this.restoreState();
            }, 100);
        } catch (error) {
            console.error('❌ 媒体库初始化失败:', error);
            // 即使出错也要移除加载动画
            this.removeLoader();
        }
    }
    
    /**
     * 加载素材列表
     */
    async loadResources() {
        if (!this.threadId) {
            this.renderEmptyState();
            return;
        }
        
        try {
            const response = await fetch(`${API_BASE}/thread/${this.threadId}/resources`);
            const data = await response.json();
            
            if (data.success) {
                this.resources = data.resources || [];
                this.renderResources();
            } else {
                this.resources = [];
                this.renderEmptyState();
            }
        } catch (error) {
            console.error('❌ 加载素材失败:', error);
            this.resources = [];
            this.renderEmptyState();
        }
    }
    
    /**
     * 刷新素材列表（用于消息发送后更新）
     */
    async refresh() {
        await this.loadResources();
    }
    
    /**
     * 禁用素材库操作（流式输出时）
     */
    disableOperations() {
        const uploadBtn = document.getElementById('mediaUploadBtn');
        if (uploadBtn) {
            uploadBtn.disabled = true;
            uploadBtn.style.opacity = '0.5';
            uploadBtn.style.cursor = 'not-allowed';
        }
        
        // 禁用所有删除按钮
        const deleteButtons = document.querySelectorAll('.delete-resource-btn');
        deleteButtons.forEach(btn => {
            btn.disabled = true;
            btn.style.opacity = '0.5';
            btn.style.cursor = 'not-allowed';
        });
        
    }
    
    /**
     * 启用素材库操作（流式输出完成）
     */
    enableOperations() {
        const uploadBtn = document.getElementById('mediaUploadBtn');
        if (uploadBtn) {
            uploadBtn.disabled = false;
            uploadBtn.style.opacity = '';
            uploadBtn.style.cursor = '';
        }
        
        // 启用所有删除按钮
        const deleteButtons = document.querySelectorAll('.delete-resource-btn');
        deleteButtons.forEach(btn => {
            btn.disabled = false;
            btn.style.opacity = '';
            btn.style.cursor = '';
        });
        
    }
    
    /**
     * 渲染素材列表
     */
    renderResources() {
        const { mediaList } = this.getElements();
        if (!mediaList) return;
        
        if (this.resources.length === 0) {
            this.renderEmptyState();
            return;
        }
        
        // 使用筛选和渲染
        this.filterAndRenderResources();
    }
    
    /**
     * 创建素材卡片 HTML
     */
    createResourceCard(resource) {
        const typeIcon = {
            'video': 'play_arrow',
            'audio': 'graphic_eq',
            'image': 'image'
        }[resource.resource_type] || 'file_present';
        
        const duration = this.formatDuration(resource.resource_duration);
        const fileSize = this.formatFileSize(resource.resource_size);
        
        // 将 resource 对象序列化为 JSON 字符串，用于点击事件
        const resourceJson = JSON.stringify(resource).replace(/"/g, '&quot;');
        
        // 截断显示的 resource_id (显示前8位)
        const shortId = resource.resource_id ? resource.resource_id.substring(0, 8) : 'unknown';
        
        return `
            <div class="resource-card group bg-[#232948] rounded-lg p-2 border border-slate-700 hover:border-primary transition-all cursor-pointer shadow-sm" 
                 data-resource='${resourceJson}'>
                ${resource.resource_type === 'video' ? this.createVideoPreview(resource, duration) : 
                  resource.resource_type === 'audio' ? this.createAudioPreview(resource, duration) :
                  this.createImagePreview(resource)}
                <div class="flex justify-between items-start gap-2 mb-1.5">
                    <div class="flex-1 min-w-0">
                        <p class="text-xs font-semibold text-slate-200 truncate" title="${resource.resource_name}">${resource.resource_name}</p>
                        <p class="text-[10px] text-slate-400 mt-0.5">${fileSize} • ${resource.resource_resolution || 'N/A'}</p>
                    </div>
                    <button class="delete-resource-btn text-slate-400 hover:text-red-500 transition-colors" 
                            data-resource-id="${resource.resource_id}"
                            title="删除素材">
                        <span class="material-symbols-outlined text-base">delete</span>
                    </button>
                </div>
                <!-- Resource ID 复制按钮 -->
                <div class="resource-id-copy flex items-center gap-1 px-2 py-1 bg-slate-800/50 rounded text-[10px] font-mono text-slate-400 hover:bg-slate-700 transition-colors cursor-pointer" 
                     onclick="event.stopPropagation(); window.copyResourceId('${resource.resource_id}')"
                     title="点击复制完整 ID">
                    <span class="material-symbols-outlined text-xs">content_copy</span>
                    <span class="truncate">${shortId}...</span>
                </div>
            </div>
        `;
    }
    
    /**
     * 创建视频预览
     */
    createVideoPreview(resource, duration) {
        const videoUrl = resource.resource_url || resource.resource_path || '';
        return `
            <div class="aspect-video w-full bg-slate-200 dark:bg-slate-900 rounded overflow-hidden relative mb-2">
                <div class="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity bg-black/30 z-10">
                    <span class="material-symbols-outlined text-white text-3xl drop-shadow-lg">play_arrow</span>
                </div>
                ${videoUrl ? `<video src="${videoUrl}" class="w-full h-full object-cover"></video>` : `<div class="w-full h-full bg-gradient-to-br from-blue-900 to-slate-800 opacity-80"></div>`}
                <span class="absolute bottom-1 right-1 text-[10px] font-mono bg-black/70 text-white px-1.5 py-0.5 rounded z-20">${duration}</span>
            </div>
        `;
    }
    
    /**
     * 创建音频预览
     */
    createAudioPreview(resource, duration) {
        return `
            <div class="aspect-[3/1] w-full bg-slate-100 dark:bg-slate-800 rounded overflow-hidden relative mb-2 flex items-center justify-center">
                <div class="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity bg-black/10 z-10">
                    <span class="material-symbols-outlined text-slate-900 dark:text-white text-2xl drop-shadow-sm">play_arrow</span>
                </div>
                <span class="material-symbols-outlined text-slate-400 text-3xl">graphic_eq</span>
                <span class="absolute bottom-1 right-1 text-[10px] font-mono bg-slate-200 dark:bg-black/70 text-slate-600 dark:text-white px-1.5 py-0.5 rounded">${duration}</span>
            </div>
        `;
    }
    
    /**
     * 创建图片预览
     */
    createImagePreview(resource) {
        const imageUrl = resource.resource_url || resource.resource_path || '';
        return `
            <div class="aspect-video w-full bg-slate-200 dark:bg-slate-900 rounded overflow-hidden relative mb-2">
                <div class="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity bg-black/30 z-10">
                    <span class="material-symbols-outlined text-white text-3xl drop-shadow-lg">zoom_in</span>
                </div>
                ${imageUrl ? `<img src="${imageUrl}" alt="${resource.resource_name}" class="w-full h-full object-cover">` : `<div class="w-full h-full bg-gradient-to-tr from-purple-900 to-indigo-900 opacity-80"></div>`}
            </div>
        `;
    }
    
    /**
     * 渲染空状态
     */
    renderEmptyState() {
        const { mediaList } = this.getElements();
        if (!mediaList) return;
        
        mediaList.innerHTML = `
            <div class="flex flex-col items-center justify-center py-12 text-center">
                <span class="material-symbols-outlined text-slate-300 dark:text-slate-600 text-6xl mb-4">folder_open</span>
                <p class="text-sm text-slate-500 dark:text-slate-400 mb-2">暂无素材</p>
                <p class="text-xs text-slate-400 dark:text-slate-500">开始对话后会自动加载素材</p>
            </div>
        `;
    }
    
    /**
     * 格式化时长（毫秒 -> 时:分:秒）
     */
    formatDuration(ms) {
        if (!ms) return '00:00';
        const totalSeconds = Math.floor(ms / 1000);
        const hours = Math.floor(totalSeconds / 3600);
        const minutes = Math.floor((totalSeconds % 3600) / 60);
        const seconds = totalSeconds % 60;
        
        if (hours > 0) {
            return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
        }
        return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
    }
    
    /**
     * 格式化文件大小（字节 -> KB/MB/GB）
     */
    formatFileSize(size) {
        if (!size || size === 0) return '未知大小';
        
        const units = ['B', 'KB', 'MB', 'GB', 'TB'];
        let index = 0;
        let fileSize = size;
        
        while (fileSize >= 1024 && index < units.length - 1) {
            fileSize /= 1024;
            index++;
        }
        
        return `${fileSize.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
    }
    
    /**
     * 绑定事件
     */
    bindEvents() {
        // 折叠按钮
        const collapseBtn = document.getElementById('mediaLibraryCollapseBtn');
        if (collapseBtn) {
            collapseBtn.onclick = (e) => {
                e.preventDefault();
                e.stopPropagation();
                this.toggle();
            };
        }
        
        // 全屏按钮
        const fullscreenBtn = document.getElementById('mediaLibraryFullscreenBtn');
        if (fullscreenBtn) {
            fullscreenBtn.onclick = (e) => {
                e.preventDefault();
                e.stopPropagation();
                this.toggleFullscreen();
            };
        }
        
        // 搜索框
        const searchInput = document.getElementById('mediaSearchInput');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                this.searchKeyword = e.target.value.trim();
                this.filterAndRenderResources();
            });
        }
        
        // 分类按钮
        const filterBtns = document.querySelectorAll('.media-filter-btn');
        filterBtns.forEach(btn => {
            btn.addEventListener('click', (e) => {
                const type = btn.getAttribute('data-type');
                this.setFilter(type);
            });
        });
        
        // 上传按钮
        const uploadBtn = document.getElementById('mediaUploadBtn');
        const uploadInput = document.getElementById('mediaUploadInput');
        if (uploadBtn && uploadInput) {
            uploadBtn.onclick = () => {
                // 检查是否正在流式输出（点击添加素材时检查）
                if (this.chat && this.chat.isStreaming) {
                    showToast('正在流式输出中，请稍候再试', 'error');
                    return;
                }
                uploadInput.click();
            };
            uploadInput.onchange = (e) => this.handleFileUpload(e);
        }
    }
    
    /**
     * 处理文件上传
     */
    async handleFileUpload(event) {
        const files = event.target.files;
        if (!files || files.length === 0) return;
        
        // 检查是否正在流式输出（在用户点击"打开"确认导入时检查）
        if (this.chat && this.chat.isStreaming) {
            showToast('正在流式输出中，请稍候再试', 'error');
            // 清空文件选择，避免用户再次点击时自动触发
            event.target.value = '';
            return;
        }
        
        const formData = new FormData();
        for (let i = 0; i < files.length; i++) {
            formData.append('files', files[i]);
        }
        
        // 显示上传中状态，保存遮罩层引用
        const uploadingOverlay = this.showUploadingState(files.length);
        
        try {
            const response = await fetch(`${API_BASE}/thread/${this.threadId}/resources/upload`, {
                method: 'POST',
                body: formData
            });
            
            const data = await response.json();
            
            if (data.success) {
                const newCount = data.new_count || 0;
                const skippedCount = data.skipped_count || 0;
                
                // 显示提示信息
                if (skippedCount > 0) {
                    showToast(`已上传 ${newCount} 个文件，跳过 ${skippedCount} 个重复文件`, 'info');
                } else {
                    showToast(`成功上传 ${newCount} 个文件`, 'success');
                }
                
                // 重新加载素材列表
                await this.loadResources();
                
                // 清空文件选择
                event.target.value = '';
            } else {
                console.error('❌ 上传失败:', data.error);
                alert('上传失败: ' + data.error);
            }
        } catch (error) {
            console.error('❌ 上传失败:', error);
            alert('上传失败: ' + error.message);
        } finally {
            // 无论成功还是失败，都要移除遮罩层
            if (uploadingOverlay) {
                uploadingOverlay.remove();
            }
        }
    }
    
    /**
     * 显示上传中状态
     * @returns {HTMLElement|null} 返回遮罩层元素，用于手动移除
     */
    showUploadingState(fileCount) {
        const { mediaList } = this.getElements();
        if (!mediaList) return null;
        
        const uploadingHtml = `
            <div class="flex flex-col items-center justify-center py-12 text-center">
                <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mb-4"></div>
                <p class="text-sm text-slate-600 dark:text-slate-300 font-medium">正在上传 ${fileCount} 个文件...</p>
                <p class="text-xs text-slate-400 dark:text-slate-500 mt-2">请稍候</p>
            </div>
        `;
        
        // 创建遮罩层
        const overlay = document.createElement('div');
        overlay.innerHTML = uploadingHtml;
        overlay.className = 'absolute inset-0 bg-white/80 dark:bg-background-dark/80 backdrop-blur-sm z-50 flex items-center justify-center';
        overlay.id = 'uploadingOverlay';
        
        const library = document.getElementById('mediaLibrary');
        if (library) {
            library.style.position = 'relative';
            library.appendChild(overlay);
        }
        
        return overlay;
    }
    
    /**
     * 设置筛选类型
     */
    setFilter(type) {
        this.currentFilter = type;
        
        // 更新按钮样式
        document.querySelectorAll('.media-filter-btn').forEach(btn => {
            const btnType = btn.getAttribute('data-type');
            if (btnType === type) {
                btn.className = 'media-filter-btn flex-1 py-1.5 text-xs font-medium rounded-md bg-primary text-white shadow-sm';
            } else {
                btn.className = 'media-filter-btn flex-1 py-1.5 text-xs font-medium rounded-md bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors';
            }
        });
        
        // 重新渲染
        this.filterAndRenderResources();
    }
    
    /**
     * 筛选并渲染素材
     */
    filterAndRenderResources() {
        let filtered = this.resources;
        
        // 1. 按类型筛选
        if (this.currentFilter !== 'all') {
            filtered = filtered.filter(res => res.resource_type === this.currentFilter);
        }
        
        // 2. 按搜索关键词筛选
        if (this.searchKeyword) {
            filtered = filtered.filter(res => this.matchSearchKeyword(res, this.searchKeyword));
        }
        
        // 3. 渲染
        const { mediaList } = this.getElements();
        if (!mediaList) return;
        
        if (filtered.length === 0) {
            mediaList.innerHTML = `
                <div class="flex flex-col items-center justify-center py-12 text-center">
                    <span class="material-symbols-outlined text-slate-300 dark:text-slate-600 text-6xl mb-4">search_off</span>
                    <p class="text-sm text-slate-500 dark:text-slate-400 mb-2">未找到素材</p>
                    <p class="text-xs text-slate-400 dark:text-slate-500">尝试调整搜索条件</p>
                </div>
            `;
        } else {
            mediaList.innerHTML = filtered.map(res => this.createResourceCard(res)).join('');
            
            // 强制浏览器重排（确保 DOM 完全更新）
            void mediaList.offsetHeight;
            
            // 根据当前模式应用正确的布局
            // ⚡ 关键优化：直接从 URL 读取状态，而不是依赖 this.fullscreen
            const state = getUIStateFromURL();
            if (state.mediaFullscreen) {
                this.setMediaListLayout(mediaList, true);
            } else {
                // 非全屏模式也需要确保清除可能残留的 inline styles
                this.setMediaListLayout(mediaList, false);
            }
            
            // 绑定卡片点击事件（放在最后）
            this.bindCardClickEvents();
            
            // 如果正在流式输出，应用禁用状态
            if (this.chat && this.chat.isStreaming) {
                this.disableOperations();
            }
        }
    }
    
    /**
     * 绑定卡片点击事件
     */
    bindCardClickEvents() {
        // 绑定卡片预览点击
        const cards = document.querySelectorAll('.resource-card');
        cards.forEach(card => {
            card.onclick = (e) => {
                // 如果点击的是按钮，不触发预览
                if (e.target.closest('button') || e.target.closest('.resource-id-copy')) return;
                
                const resourceData = card.getAttribute('data-resource');
                if (resourceData) {
                    const resource = JSON.parse(resourceData);
                    this.openPreviewModal(resource);
                }
            };
        });
        
        // 绑定删除按钮点击
        const deleteButtons = document.querySelectorAll('.delete-resource-btn');
        deleteButtons.forEach(btn => {
            btn.onclick = async (e) => {
                e.stopPropagation();
                // 检查是否正在流式输出
                if (this.chat && this.chat.isStreaming) {
                    showToast('正在流式输出中，请稍候再试', 'error');
                    return;
                }
                const resourceId = btn.getAttribute('data-resource-id');
                if (resourceId) {
                    await this.deleteResource(resourceId);
                }
            };
        });
    }
    
    /**
     * 删除素材
     */
    async deleteResource(resourceId) {
        // 检查是否正在流式输出
        if (this.chat && this.chat.isStreaming) {
            showToast('正在流式输出中，请稍候再试', 'error');
            return;
        }
        
        try {
            const response = await fetch(`${API_BASE}/thread/${this.threadId}/resources/${resourceId}`, {
                method: 'DELETE'
            });
            
            const data = await response.json();
            
            if (data.success) {
                showToast(`已删除: ${data.deleted_resource?.resource_name || resourceId}`, 'success');
                
                // 重新加载素材列表（会保持当前的全屏/折叠状态）
                await this.loadResources();
            } else {
                console.error('❌ 删除失败:', data.error);
                showToast('删除失败: ' + data.error, 'error');
            }
        } catch (error) {
            console.error('❌ 删除素材失败:', error);
            showToast('删除失败: ' + error.message, 'error');
        }
    }
    
    /**
     * 打开预览模态框
     */
    openPreviewModal(resource) {
        const modalHtml = `
            <div id="mediaPreviewModal" class="fixed inset-0 bg-black/80 backdrop-blur-sm z-[100] flex items-center justify-center p-4" onclick="this.remove()">
                <div class="relative max-w-6xl max-h-[90vh] w-full" onclick="event.stopPropagation()">
                    <!-- 关闭按钮 -->
                    <button onclick="document.getElementById('mediaPreviewModal').remove()" 
                            class="absolute -top-12 right-0 text-white hover:text-red-400 transition-colors">
                        <span class="material-symbols-outlined text-4xl">close</span>
                    </button>
                    
                    <!-- 内容区域 -->
                    <div class="bg-white dark:bg-[#1a2037] rounded-lg overflow-hidden shadow-2xl">
                        ${this.createPreviewContent(resource)}
                        
                        <!-- 底部信息 -->
                        <div class="p-4 border-t border-slate-200 dark:border-slate-700">
                            <h3 class="text-lg font-semibold text-slate-900 dark:text-white mb-2">${resource.resource_name}</h3>
                            <div class="flex gap-4 text-sm text-slate-600 dark:text-slate-400">
                                <span>类型: ${resource.resource_type}</span>
                                ${resource.resource_resolution ? `<span>分辨率: ${resource.resource_resolution}</span>` : ''}
                                ${resource.resource_duration ? `<span>时长: ${this.formatDuration(resource.resource_duration)}</span>` : ''}
                            </div>
                            ${resource.resource_description ? `<p class="text-sm text-slate-500 dark:text-slate-400 mt-2">${resource.resource_description}</p>` : ''}
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        
        // ESC 键关闭
        const escHandler = (e) => {
            if (e.key === 'Escape') {
                document.getElementById('mediaPreviewModal')?.remove();
                document.removeEventListener('keydown', escHandler);
            }
        };
        document.addEventListener('keydown', escHandler);
    }
    
    /**
     * 创建预览内容
     */
    createPreviewContent(resource) {
        const url = resource.resource_url || resource.resource_path || '';
        
        if (resource.resource_type === 'video') {
            return `
                <div class="bg-black flex items-center justify-center" style="max-height: 70vh;">
                    <video src="${url}" controls autoplay class="max-w-full max-h-[70vh] w-auto h-auto">
                        您的浏览器不支持视频播放
                    </video>
                </div>
            `;
        } else if (resource.resource_type === 'audio') {
            return `
                <div class="bg-slate-100 dark:bg-slate-800 flex flex-col items-center justify-center p-12">
                    <span class="material-symbols-outlined text-slate-400 text-8xl mb-6">graphic_eq</span>
                    <audio src="${url}" controls autoplay class="w-full max-w-md">
                        您的浏览器不支持音频播放
                    </audio>
                </div>
            `;
        } else if (resource.resource_type === 'image') {
            return `
                <div class="bg-black flex items-center justify-center" style="max-height: 70vh;">
                    <img src="${url}" alt="${resource.resource_name}" class="max-w-full max-h-[70vh] w-auto h-auto object-contain">
                </div>
            `;
        } else {
            return `
                <div class="p-12 text-center text-slate-500">
                    <span class="material-symbols-outlined text-6xl mb-4">file_present</span>
                    <p>无法预览此文件类型</p>
                </div>
            `;
        }
    }
    
    /**
     * 匹配搜索关键词（遍历所有字段）
     */
    matchSearchKeyword(resource, keyword) {
        const lowerKeyword = keyword.toLowerCase();
        
        // 遍历对象的所有字段
        for (const key in resource) {
            if (resource.hasOwnProperty(key)) {
                const value = resource[key];
                // 转换为字符串并进行匹配
                const strValue = String(value).toLowerCase();
                if (strValue.includes(lowerKeyword)) {
                    return true;
                }
            }
        }
        
        return false;
    }
    
    /**
     * 创建展开按钮
     */
    createExpandButton() {
        const btn = document.createElement('button');
        btn.id = 'expandMediaLibraryBtn';
        btn.className = 'absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-slate-400 hover:text-primary p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5 transition-colors z-10';
        btn.innerHTML = '<span class="material-symbols-outlined text-2xl">keyboard_double_arrow_left</span>';
        btn.onclick = () => this.toggle();
        btn.title = '展开媒体库';
        return btn;
    }
    
    /**
     * 折叠/展开媒体库
     */
    toggle() {
        const { library } = this.getElements();
        if (!library) return;
        
        this.collapsed = !this.collapsed;
        
        if (this.collapsed) {
            // 折叠状态
            DOM.swapClasses(library, 'w-80', 'w-12');
            DOM.toggleElementsDisplay(library.querySelectorAll('.p-4, .flex-1'), false);
            DOM.updateButtonState('mediaLibraryCollapseBtn', 'keyboard_double_arrow_left', '展开库');
            
            // 添加展开按钮
            library.style.position = 'relative';
            library.appendChild(this.createExpandButton());
        } else {
            // 展开状态
            DOM.swapClasses(library, 'w-12', 'w-80');
            DOM.toggleElementsDisplay(library.querySelectorAll('.p-4, .flex-1'), true);
            DOM.updateButtonState('mediaLibraryCollapseBtn', 'keyboard_double_arrow_right', '折叠库');
            
            // 移除展开按钮
            document.getElementById('expandMediaLibraryBtn')?.remove();
        }
        
        this.saveState();
    }
    
    /**
     * 切换折叠按钮显示
     */
    toggleCollapseButton(show) {
        const collapseBtn = document.getElementById('mediaLibraryCollapseBtn');
        if (!collapseBtn) return;
        
        collapseBtn.style.display = show ? '' : 'none';
        
        // 同时切换分隔线
        const divider = collapseBtn.previousElementSibling;
        if (divider && divider.classList.contains('w-px')) {
            divider.style.display = show ? '' : 'none';
        }
    }
    
    /**
     * 设置媒体列表布局
     */
    setMediaListLayout(mediaList, isFlexFlow) {
        if (!mediaList) return;
        
        if (isFlexFlow) {
            // 流式布局（全屏模式）
            mediaList.classList.remove('space-y-3');
            Object.assign(mediaList.style, {
                display: 'flex',
                flexWrap: 'wrap',
                gap: '1rem',
                alignContent: 'flex-start'
            });
            
            // 设置子元素固定宽度，防止内容溢出
            mediaList.querySelectorAll(':scope > *').forEach(card => {
                card.style.flex = '0 0 280px';
                card.style.minWidth = '0';      // 允许 flex 子元素收缩
                card.style.maxWidth = '280px';  // 强制最大宽度
                card.style.margin = '0';
            });
        } else {
            // 垂直布局（默认模式）
            mediaList.classList.add('space-y-3');
            Object.assign(mediaList.style, {
                display: '',
                flexWrap: '',
                gap: '',
                alignContent: ''
            });
            
            // 恢复子元素样式
            mediaList.querySelectorAll(':scope > *').forEach(card => {
                card.style.flex = '';
                card.style.minWidth = '';
                card.style.maxWidth = '';
                card.style.margin = '';
            });
        }
    }
    
    /**
     * 全屏显示媒体库
     */
    toggleFullscreen() {
        const { library, leftSidebar, mainContent, mediaList } = this.getElements();
        
        this.fullscreen = !this.fullscreen;
        
        if (this.fullscreen) {
            // 全屏模式
            DOM.toggleElementsDisplay([leftSidebar, mainContent], false);
            DOM.swapClasses(library, 'w-80', 'w-full');
            this.setMediaListLayout(mediaList, true);
            DOM.updateButtonState('mediaLibraryFullscreenBtn', 'close_fullscreen', '退出全屏');
            this.toggleCollapseButton(false); // 隐藏折叠按钮
        } else {
            // 退出全屏
            DOM.toggleElementsDisplay([leftSidebar, mainContent], true);
            DOM.swapClasses(library, 'w-full', 'w-80');
            this.setMediaListLayout(mediaList, false);
            DOM.updateButtonState('mediaLibraryFullscreenBtn', 'open_in_full', '全屏显示');
            this.toggleCollapseButton(true); // 显示折叠按钮
        }
        
        this.saveState();
    }
    
    /**
     * 保存状态
     */
    saveState() {
        const state = getUIStateFromURL();
        saveUIState({
            ...state,  // 保留其他状态
            mediaCollapsed: this.collapsed,
            mediaFullscreen: this.fullscreen
        });
    }
    
    /**
     * 恢复状态
     */
    restoreState() {
        const state = getUIStateFromURL();
        
        // 同步状态变量
        this.fullscreen = state.mediaFullscreen;
        this.collapsed = state.mediaCollapsed;
        
        const { library, leftSidebar, mainContent, mediaList } = this.getElements();
        
        // 恢复全屏状态
        if (state.mediaFullscreen) {
            [leftSidebar, mainContent].forEach(el => {
                if (el) el.style.display = 'none';
            });
            
            DOM.swapClasses(library, 'w-80', 'w-full');
            this.setMediaListLayout(mediaList, true);
            DOM.updateButtonState('mediaLibraryFullscreenBtn', 'close_fullscreen', '退出全屏');
            this.toggleCollapseButton(false);
        }
        
        // 恢复折叠状态
        if (state.mediaCollapsed && !state.mediaFullscreen) {
            DOM.swapClasses(library, 'w-80', 'w-12');
            DOM.toggleElementsDisplay(library.querySelectorAll('.p-4, .flex-1'), false);
            DOM.updateButtonState('mediaLibraryCollapseBtn', 'keyboard_double_arrow_left', '展开库');
            
            // 创建展开按钮
            if (!document.getElementById('expandMediaLibraryBtn')) {
                library.style.position = 'relative';
                library.appendChild(this.createExpandButton());
            }
        }
        
        // 移除加载动画
        this.removeLoader();
    }
    
    /**
     * 移除加载动画
     */
    removeLoader() {
        const loader = document.getElementById('app-loader');
        if (loader) {
            // 淡出动画
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
}

