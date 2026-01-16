// ==================== 聊天组件 ====================
import { escapeHtml, scrollToBottom, API_BASE, HTTP } from '../utils.js';

export class Chat {
    constructor() {
        this.threadId = null;
        this.mediaLibrary = null;
        this.sidebar = null;
        this.isStreaming = false;  // 是否正在流式输出
        this.historyMessages = [];  // 历史人类消息（倒序：0=最近）
        this.currentHistoryIndex = -1;  // 当前历史索引（-1 表示未使用历史）
        this.beforeHistoryInput = '';  // 使用历史前的输入内容
    }
    
    /**
     * 初始化聊天组件
     */
    async init(threadId, isNewChat = false, mediaLibrary = null, sidebar = null) {
        this.threadId = threadId;
        this.mediaLibrary = mediaLibrary;
        this.sidebar = sidebar;
        this.bindEvents();
        
        if (isNewChat) {
            await this.initNewChat();
        } else {
            this.loadHistoryMessages();
        }
    }
    
    /**
     * 绑定事件
     */
    bindEvents() {
        // 发送按钮
        const sendBtn = document.getElementById('sendButton');
        if (sendBtn) {
            sendBtn.onclick = () => this.sendMessage();
        }
        
        // 输入框回车发送和历史消息复用
        const input = document.getElementById('userInput');
        if (input) {
            input.addEventListener('keydown', (e) => {
                // 如果正在输入法合成中，不处理特殊键
                if (e.isComposing || e.keyCode === 229) {
                    return;
                }
                
                // Shift+↑/↓：历史消息复用
                if (e.shiftKey && (e.key === 'ArrowUp' || e.key === 'ArrowDown')) {
                    e.preventDefault();
                    // ArrowUp: 向上（更早的消息，index 增大）
                    // ArrowDown: 向下（更新的消息，index 减小）
                    this.navigateHistory(e.key === 'ArrowUp' ? 1 : -1);
                    return;
                }
                
                // Enter 发送
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    // 检查是否正在流式输出
                    if (!this.isStreaming) {
                        this.sendMessage();
                    }
                }
            });
            
            // 监听输入变化，如果用户手动输入，重置历史索引
            input.addEventListener('input', (e) => {
                // 如果用户手动输入（非程序设置），且当前在使用历史，重置状态
                if (this.currentHistoryIndex !== -1 && e.inputType !== null) {
                    // 检查输入是否与当前历史消息不同
                    const currentHistory = this.get_history_message(this.currentHistoryIndex);
                    if (currentHistory !== null && e.target.value !== currentHistory) {
                        // 用户修改了历史消息，重置索引但保留输入
                        this.currentHistoryIndex = -1;
                        this.beforeHistoryInput = e.target.value;
                    }
                }
            });
        }
        
        // 删除对话按钮
        const deleteBtn = document.querySelector('button[onclick="deleteCurrentChat()"]');
        if (deleteBtn) {
            deleteBtn.onclick = () => this.deleteCurrentChat();
        }
        
        // 分隔条拖拽
        this.initResizer();
    }
    
    /**
     * 禁用发送（流式输出时）
     * 注意：输入框保持可编辑，用户可以继续输入下一条消息
     */
    disableInput() {
        const sendButton = document.getElementById('sendButton');
        
        if (sendButton) {
            sendButton.disabled = true;
            // 视觉提示：置灰但保持按钮样式
            sendButton.style.opacity = '0.5';
            sendButton.style.cursor = 'not-allowed';
        }
        
        this.isStreaming = true;
        
        // 同步禁用素材库操作
        if (this.mediaLibrary) {
            this.mediaLibrary.disableOperations();
        }
    }
    
    /**
     * 启用发送（流式输出完成）
     */
    enableInput() {
        const input = document.getElementById('userInput');
        const sendButton = document.getElementById('sendButton');
        
        if (sendButton) {
            sendButton.disabled = false;
            sendButton.style.opacity = '';
            sendButton.style.cursor = '';
        }
        
        // 聚焦输入框
        if (input) {
            input.focus();
        }
        
        this.isStreaming = false;
        
        // 同步启用素材库操作
        if (this.mediaLibrary) {
            this.mediaLibrary.enableOperations();
        }
    }
    
    /**
     * 初始化分隔条拖拽
     */
    initResizer() {
        const resizer = document.getElementById('resizer');
        const chatMessages = document.getElementById('chatMessages');
        const mainContent = document.querySelector('main');
        
        if (!resizer || !chatMessages || !mainContent) return;
        
        let isResizing = false;
        let startY = 0;
        let startMessagesHeight = 0;
        
        const onMouseDown = (e) => {
            isResizing = true;
            startY = e.clientY;
            startMessagesHeight = chatMessages.offsetHeight;
            
            resizer.classList.add('dragging');
            document.body.style.cursor = 'ns-resize';
            document.body.style.userSelect = 'none';
            
            e.preventDefault();
        };
        
        const onMouseMove = (e) => {
            if (!isResizing) return;
            
            const deltaY = e.clientY - startY;
            const newMessagesHeight = startMessagesHeight + deltaY;
            
            // 获取主容器高度
            const headerHeight = mainContent.querySelector('header')?.offsetHeight || 0;
            const resizerHeight = resizer.offsetHeight;
            const mainHeight = mainContent.offsetHeight;
            const availableHeight = mainHeight - headerHeight - resizerHeight;
            
            // 限制高度范围：最小 200px，最大留给输入区域至少 150px
            const minMessagesHeight = 200;
            const maxMessagesHeight = availableHeight - 150;
            
            if (newMessagesHeight >= minMessagesHeight && newMessagesHeight <= maxMessagesHeight) {
                chatMessages.style.height = newMessagesHeight + 'px';
                // 输入框使用 flex-1，会自动调整，无需手动计算 ✅
            }
        };
        
        const onMouseUp = () => {
            if (isResizing) {
                isResizing = false;
                resizer.classList.remove('dragging');
                document.body.style.cursor = '';
                document.body.style.userSelect = '';
            }
        };
        
        resizer.addEventListener('mousedown', onMouseDown);
        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
    }
    
    /**
     * 初始化新会话
     */
    async initNewChat() {
        try {
            await fetch(`${API_BASE}/thread/${this.threadId}/init`, { method: 'POST' });
            this.addWelcomeMessage();
            
            // 刷新侧边栏历史列表
            if (this.sidebar) {
                await this.sidebar.loadThreadList();
            }
        } catch (error) {
            console.error('Init thread error:', error);
        }
    }
    
    /**
     * 添加欢迎消息
     */
    addWelcomeMessage() {
        const welcomeText = `👋 **您好！我是视频剪辑助手**

**我可以帮您：**
• 使用剪映完成视频剪辑
• 管理视频素材和项目
• 智能生成视频内容

**使用示例：**
• "帮我剪辑一个 1 分钟的宣传片"
• "添加转场特效和背景音乐"`;

        this.addMessage(welcomeText, 'ai');
    }
    
    /**
     * 添加消息到 DOM
     */
    addMessage(content, role = 'human') {
        const messagesDiv = document.getElementById('chatMessagesInner');
        if (!messagesDiv) return;
        
        const messageDiv = document.createElement('div');
        
        if (role === 'human') {
            messageDiv.className = 'flex justify-end gap-2 w-full overflow-hidden';
            messageDiv.innerHTML = `
                <div class="flex flex-col items-end gap-1 max-w-[80%] min-w-0">
                    <div class="bg-primary text-white px-4 py-2.5 rounded-2xl rounded-tr-sm shadow-md w-full">
                        <p class="text-sm md:text-base leading-relaxed" style="overflow-wrap: anywhere;">${escapeHtml(content)}</p>
                    </div>
                </div>
                <div class="w-8 h-8 rounded-full bg-slate-200 dark:bg-slate-700 flex items-center justify-center shrink-0">
                    <span class="material-symbols-outlined text-sm">person</span>
                </div>
            `;
        } else {
            messageDiv.className = 'flex justify-start gap-2 w-full overflow-hidden';
            messageDiv.innerHTML = `
                <div class="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shrink-0 shadow-lg shadow-indigo-500/20">
                    <span class="material-symbols-outlined text-white text-sm">smart_toy</span>
                </div>
                <div class="flex flex-col items-start gap-1 max-w-[80%] min-w-0">
                    <div class="bg-white dark:bg-bubble-agent border border-slate-100 dark:border-slate-700/50 text-slate-900 dark:text-slate-100 px-4 py-3 rounded-2xl rounded-tl-sm shadow-sm w-full overflow-hidden">
                        <div class="text-sm md:text-base leading-relaxed message-content" style="overflow-wrap: anywhere;"></div>
                    </div>
                </div>
            `;
        }
        
        messagesDiv.appendChild(messageDiv);
        
        if (role !== 'human') {
            const contentEl = messageDiv.querySelector('.message-content');
            contentEl.innerHTML = escapeHtml(content);
            return contentEl;
        }
        
        scrollToBottom();
    }
    
    /**
     * 显示打字动画
     */
    showTyping() {
        const messagesDiv = document.getElementById('chatMessagesInner');
        if (!messagesDiv) return;
        
        const typingDiv = document.createElement('div');
        typingDiv.id = 'typingIndicator';
        typingDiv.className = 'flex justify-start gap-2 w-full';
        typingDiv.innerHTML = `
            <div class="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shrink-0 shadow-lg shadow-indigo-500/20">
                <span class="material-symbols-outlined text-white text-sm">smart_toy</span>
            </div>
            <div class="flex flex-col items-start gap-1">
                <div class="bg-white dark:bg-bubble-agent border border-slate-100 dark:border-slate-700/50 text-slate-900 dark:text-slate-100 px-4 py-3 rounded-2xl rounded-tl-sm shadow-sm flex items-center gap-3">
                    <div class="flex space-x-1">
                        <div class="w-2 h-2 bg-primary/60 rounded-full typing-dot"></div>
                        <div class="w-2 h-2 bg-primary/60 rounded-full typing-dot"></div>
                        <div class="w-2 h-2 bg-primary/60 rounded-full typing-dot"></div>
                    </div>
                    <p class="text-sm text-slate-500 dark:text-slate-400">正在思考...</p>
                </div>
            </div>
        `;
        messagesDiv.appendChild(typingDiv);
        scrollToBottom();
    }
    
    /**
     * 隐藏打字动画
     */
    hideTyping() {
        const typingDiv = document.getElementById('typingIndicator');
        if (typingDiv) {
            typingDiv.remove();
        }
    }
    
    /**
     * 发送消息
     */
    async sendMessage() {
        // 如果正在流式输出，不允许发送
        if (this.isStreaming) {
            return;
        }
        
        const input = document.getElementById('userInput');
        const message = input.value.trim();
        
        if (!message) return;
        
        // 禁用输入
        this.disableInput();
        
        // 显示用户消息
        this.addMessage(message, 'human');
        
        // 将消息添加到历史（如果不在历史中，或与历史不同）
        if (this.historyMessages.length === 0 || this.historyMessages[0] !== message) {
            this.historyMessages.unshift(message);  // 添加到最前面（最近）
        }
        
        // 重置历史索引
        this.currentHistoryIndex = -1;
        this.beforeHistoryInput = '';
        
        input.value = '';
        
        // 显示打字动画
        this.showTyping();
        
        // ⭐ 用于管理消息结尾的等待状态
        let loadingTimer = null;
        let isWaitingForNextMessage = false;
        
        const cleanupLoadingTimer = () => {
            if (loadingTimer) {
                clearTimeout(loadingTimer);
                loadingTimer = null;
            }
            if (isWaitingForNextMessage) {
                isWaitingForNextMessage = false;
            }
        };
        
        try {
            const response = await fetch(`${API_BASE}/chat/stream`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    thread_id: this.threadId,
                    message: message
                })
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let aiContentEl = null;
            let accumulatedContent = '';
            
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                
                buffer += decoder.decode(value, { stream: true });
                const parts = buffer.split('\n\n');
                buffer = parts.pop();
                
                for (const part of parts) {
                    const line = part.trim();
                    if (!line.startsWith('data:')) continue;
                    
                    const jsonStr = line.slice(5);
                    if (!jsonStr) continue;
                    
                    const evt = JSON.parse(jsonStr);
                    
                    if (evt.type === 'message_change') {
                        // ⭐ 清理加载计时器
                        cleanupLoadingTimer();
                        this.hideTyping();
                        
                        // ⭐ 执行 Markdown 解析（在切换消息前）
                        if (aiContentEl && accumulatedContent) {
                            aiContentEl.innerHTML = escapeHtml(accumulatedContent);
                        }
                        
                        // 重置状态，准备接收新消息
                        aiContentEl = null;
                        accumulatedContent = '';
                        scrollToBottom();
                    }
                    
                    if (evt.type === 'token') {
                        // ⭐ 清理加载计时器（如果正在等待）
                        if (loadingTimer) {
                            clearTimeout(loadingTimer);
                            loadingTimer = null;
                        }
                        
                        this.hideTyping();
                        isWaitingForNextMessage = false;
                        
                        if (!aiContentEl) {
                            aiContentEl = this.addMessage('', 'ai');
                        }
                        
                        accumulatedContent += evt.content;
                        
                        // 流式输出：HTML 转义 + 换行处理
                        const tempDiv = document.createElement('div');
                        tempDiv.textContent = accumulatedContent;
                        aiContentEl.innerHTML = tempDiv.innerHTML.replace(/\n/g, '<br>');
                        scrollToBottom();
                        
                        // ⭐ 检测到最后一个 chunk：执行 Markdown 解析并启动等待计时器
                        if (evt.chunk_position === 'last') {
                            if (aiContentEl && accumulatedContent) {
                                const markdownHtml = escapeHtml(accumulatedContent);
                                aiContentEl.innerHTML = markdownHtml;
                            }
                            // 延迟判断是否有下一条消息
                            loadingTimer = setTimeout(() => {
                                this.showTyping();
                                isWaitingForNextMessage = true;
                            }, 10);
                        }
                    }
                    
                    if (evt.type === 'done') {
                        cleanupLoadingTimer();
                        this.hideTyping();
                        if (aiContentEl && accumulatedContent) {
                            aiContentEl.innerHTML = escapeHtml(accumulatedContent);
                        }
                        // 刷新素材列表
                        if (this.mediaLibrary) {
                            this.mediaLibrary.refresh().catch(err => 
                                console.error('刷新素材列表失败:', err)
                            );
                        }
                        break;
                    }
                    
                    if (evt.type === 'error') {
                        cleanupLoadingTimer();
                        this.hideTyping();
                        this.addMessage(`❌ 错误: ${evt.error}`, 'ai');
                        break;
                    }
                }
            }
        } catch (error) {
            this.hideTyping();
            console.error('Send error:', error);
            this.addMessage(`❌ 发送失败: ${error.message}`, 'ai');
        } finally {
            // 启用输入
            this.enableInput();
        }
    }
    
    /**
     * 加载历史消息
     */
    async loadHistoryMessages() {
        try {
            const response = await fetch(`${API_BASE}/thread/${this.threadId}/messages`);
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.error || '加载失败');
            }
            
            // 总是先显示欢迎消息
            this.addWelcomeMessage();
            
            // 然后加载历史消息（如果有）
            if (data.success && data.messages && data.messages.length > 0) {
                data.messages.forEach(msg => {
                    this.addMessage(msg.content, msg.role);
                    // 存储人类消息到历史数组（只存储 human 角色的消息）
                    if (msg.role === 'human') {
                        this.historyMessages.push(msg.content);
                    }
                });
                // 历史消息倒序存储（0=最近）
                this.historyMessages.reverse();
            }
        } catch (error) {
            console.error('Load history error:', error);
            this.addWelcomeMessage();
        }
    }
    
    /**
     * 获取历史消息
     * @param {number} index - 历史索引（倒序，0=最近一条）
     * @returns {string|null} - 历史消息内容，超出范围返回 null
     */
    get_history_message(index) {
        if (index < 0 || index >= this.historyMessages.length) {
            return null;
        }
        return this.historyMessages[index];
    }
    
    /**
     * 导航历史消息（类似终端）
     * @param {number} direction - 方向：1=向上（更早，index 增大），-1=向下（更新，index 减小）
     */
    navigateHistory(direction) {
        const input = document.getElementById('userInput');
        if (!input) return;
        
        // 如果没有历史消息，直接返回
        if (this.historyMessages.length === 0) {
            return;
        }
        
        // 如果当前没有使用历史，保存当前输入
        if (this.currentHistoryIndex === -1) {
            this.beforeHistoryInput = input.value;
        }
        
        // 计算新索引
        let newIndex = this.currentHistoryIndex + direction;
        
        // 向上导航（更早的消息，index 增大）
        if (direction === 1) {
            if (newIndex >= this.historyMessages.length) {
                // 超出范围，不改变（终端行为：到达最早的消息后不再改变）
                return;
            }
            this.currentHistoryIndex = newIndex;
            const historyMsg = this.get_history_message(newIndex);
            if (historyMsg !== null) {
                input.value = historyMsg;
            }
        }
        // 向下导航（更新的消息，index 减小）
        else {
            if (newIndex < 0) {
                // 超出范围，恢复原始输入（终端行为：回到用户输入的原始内容）
                this.currentHistoryIndex = -1;
                input.value = this.beforeHistoryInput;
                this.beforeHistoryInput = '';
            } else {
                this.currentHistoryIndex = newIndex;
                const historyMsg = this.get_history_message(newIndex);
                if (historyMsg !== null) {
                    input.value = historyMsg;
                }
            }
        }
    }
    
    /**
     * 删除当前对话
     */
    async deleteCurrentChat() {
        if (!confirm('确定要删除当前对话吗？')) return;
        
        try {
            // 1. 删除当前对话
            const response = await fetch(`${API_BASE}/thread/${this.threadId}`, {
                method: 'DELETE'
            });
            const data = await response.json();
            
            if (!data.success) {
                alert('删除失败: ' + data.error);
                return;
            }
            
            // 2. 获取剩余的对话列表
            const threadsResponse = await fetch(`${API_BASE}/threads`);
            const threadsData = await threadsResponse.json();
            
            if (threadsData.success && threadsData.threads && threadsData.threads.length > 0) {
                // 3. 如果有其他对话，跳转到最新的那个（按 updated_at 排序）
                const sortedThreads = threadsData.threads.sort((a, b) => {
                    const timeA = a.updated_at ? new Date(a.updated_at).getTime() : 0;
                    const timeB = b.updated_at ? new Date(b.updated_at).getTime() : 0;
                    return timeB - timeA;
                });
                const latestThread = sortedThreads[0];
                window.location.href = `/chat/${latestThread.thread_id}`;
            } else {
                // 4. 如果没有任何对话了，跳转到首页（会显示欢迎页或创建新对话）
                window.location.href = '/';
            }
        } catch (error) {
            console.error('Delete error:', error);
            alert('删除失败: ' + error.message);
        }
    }
}

