import { API_BASE, generateUUID, navigateTo } from '../utils.js';
import { ApprovalPanel } from './approval-panel.js';
import { MessageView } from '../chat/message-view.js';
import { applyMessageUpdate } from '../chat/message-state.js';
import { readChatStream } from '../chat/sse.js';
import { ChatScroll } from '../chat/scroll.js';
import { projectToolMessages } from '../chat/tool-presentation.js';
import { ComposerResize } from '../chat/composer-resize.js';

export class Chat {
    constructor(root, { store, onSettled } = {}) {
        this.root = root;
        this.store = store;
        this.onSettled = onSettled;
        this.isActive = false;
        this.disposed = false;
        this.approvalPanel = new ApprovalPanel(this);
        this.isStreaming = false;
        this.isInitializing = true;
        this.messages = new Map();
        this.views = new Map();
        this.historyMessages = [];
        this.currentHistoryIndex = -1;
        this.beforeHistoryInput = '';
    }

    el(id) { return this.root.querySelector(`[data-chat-element="${id}"]`); }

    async activate() {
        this.isActive = true;
        this.root.hidden = false;
        this.composer?.refresh();
        this.scroll?.resume();
        this.updateSendButton();
        if (!this.isInitializing && !this.isStreaming) await this.store?.markRead(this.threadId, this.run?.run_id);
    }

    deactivate() { this.isActive = false; this.composer?.stop(); this.scroll?.suspend(); this.root.hidden = true; }

    destroy() {
        if (this.isStreaming) return;
        this.disposed = true;
        this.scroll?.destroy();
        this.composer?.destroy();
        this.root.remove();
        this.messages.clear();
        this.views.clear();
    }

    async init(threadId, isNewChat = false, mediaLibrary = null, sidebar = null) {
        this.threadId = threadId;
        this.mediaLibrary = mediaLibrary;
        this.sidebar = sidebar;
        this.input = this.el('userInput');
        this.composer = new ComposerResize(this.root, this.el('inputArea'), this.el('composerResizeHandle'));
        this.messagesElement = this.el('chatMessagesInner');
        this.scroll = new ChatScroll(this.el('chatMessages'), this.messagesElement, this.el('scrollToLatest'));
        if (!this.isActive) this.scroll.suspend();
        this.bindEvents();
        try {
            if (isNewChat) {
                const response = await fetch(`${API_BASE}/thread/${threadId}/init`, { method: 'POST' });
                if (!response.ok) throw new Error('创建对话失败，请刷新重试。');
                this.sidebar?.loadThreadList().catch(console.error);
            }
            await this.loadHistoryMessages();
            await this.approvalPanel.init();
            this.scroll.bottom();
            if (this.run?.running) this.runStream(`/thread/${this.threadId}/events`, null);
            else if (this.run?.error) this.addNotice(this.run.error);
        } catch (error) {
            this.addNotice(error.message);
        } finally {
            this.isInitializing = false;
            this.updateSendButton();
            if (!this.isStreaming) this.onSettled?.(this);
        }
    }

    bindEvents() {
        this.el('sendButton').onclick = () => this.sendMessage();
        this.input.addEventListener('keydown', event => {
            if (event.isComposing || event.keyCode === 229) return;
            if (event.shiftKey && ['ArrowUp', 'ArrowDown'].includes(event.key)) {
                event.preventDefault();
                this.navigateHistory(event.key === 'ArrowUp' ? 1 : -1);
                this.updateSendButton();
            } else if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                this.sendMessage();
            }
        });
        this.input.addEventListener('input', () => {
            this.currentHistoryIndex = -1;
            this.updateSendButton();
        });
        this.root.querySelector('button[onclick="deleteCurrentChat()"]').onclick = () => this.deleteCurrentChat();
    }

    updateSendButton() {
        const button = this.el('sendButton');
        if (!button) return;
        const blocked = this.isInitializing || this.isStreaming || this.approvalPanel.interrupts.length > 0;
        button.disabled = blocked || !this.input?.value.trim();
        button.title = this.approvalPanel.interrupts.length ? '请先处理待确认操作' : '发送消息';
        if (this.isActive) {
            if (blocked) this.mediaLibrary?.disableOperations();
            else this.mediaLibrary?.enableOperations();
        }
    }

    applyMessage(event) {
        const message = applyMessageUpdate(this.messages.get(event.message.id), event);
        this.messages.set(message.id, message);
        this.renderMessages();
    }

    renderMessages() {
        const messages = projectToolMessages([...this.messages.values()]);
        const keep = new Set(messages.map(message => message.id));
        for (const [id, view] of this.views) {
            if (!keep.has(id)) { view.element.remove(); this.views.delete(id); }
        }
        messages.forEach((message, index) => {
            let view = this.views.get(message.id);
            if (view) view.update(message);
            else {
                view = new MessageView(message);
                this.views.set(message.id, view);
            }
            if (this.messagesElement.children[index] !== view.element) {
                this.messagesElement.insertBefore(view.element, this.messagesElement.children[index] || null);
            }
        });
        this.scroll.changed();
    }

    reconcileHistory(messages) {
        const viewport = this.scroll.viewport;
        const top = viewport.getBoundingClientRect().top;
        const anchor = [...this.messagesElement.children].find(element => element.getBoundingClientRect().bottom > top);
        const anchorOffset = anchor?.getBoundingClientRect().top;
        const previousTop = viewport.scrollTop;
        const follow = this.scroll.follow;
        this.messages = new Map(messages.map(message => [message.id, { ...message, complete: true }]));
        this.renderMessages();
        this.historyMessages = messages.filter(message => message.role === 'human').map(message => message.content).reverse();
        if (!follow) {
            viewport.scrollTop = anchor?.isConnected
                ? previousTop + anchor.getBoundingClientRect().top - anchorOffset : previousTop;
        }
        this.scroll.follow = follow;
        this.scroll.changed();
    }

    async loadHistoryMessages() {
        const response = await fetch(`${API_BASE}/thread/${this.threadId}/messages`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || '读取对话失败');
        const messages = data.messages || [];
        this.reconcileHistory(messages.length ? messages : [{
            id: 'welcome', role: 'ai', content: '你好，今天想剪一个什么样的视频？\n\n上传素材，告诉我想要的时长和风格，我们就可以开始。',
        }]);
    }

    addNotice(text) {
        const notice = document.createElement('p');
        notice.className = 'chat-notice';
        notice.setAttribute('role', 'alert');
        notice.textContent = text;
        this.messagesElement.append(notice);
        this.scroll.changed();
    }

    showTyping() {
        const indicator = document.createElement('div');
        this.typing = indicator;
        indicator.className = 'typing-indicator';
        indicator.setAttribute('role', 'status');
        indicator.textContent = '正在处理';
        for (let i = 0; i < 3; i++) {
            const dot = document.createElement('span');
            dot.className = 'typing-dot';
            indicator.append(dot);
        }
        this.messagesElement.append(indicator);
        this.scroll.changed();
    }

    hideTyping() { this.typing?.remove(); this.typing = null; }

    async sendMessage() {
        if (this.isInitializing || this.isStreaming || this.approvalPanel.interrupts.length) return;
        const message = this.input.value.trim();
        if (!message) return;
        const id = generateUUID();
        this.messagesElement.querySelectorAll('.chat-notice').forEach(notice => notice.remove());
        this.views.get('welcome')?.element.remove();
        this.views.delete('welcome');
        this.messages.delete('welcome');
        this.applyMessage({ message: { id, role: 'human', content: message }, complete: true });
        this.historyMessages.unshift(message);
        this.input.value = '';
        this.currentHistoryIndex = -1;
        this.beforeHistoryInput = '';
        this.scroll.bottom();
        await this.runStream('/chat/stream', { thread_id: this.threadId, message, message_id: id });
    }

    async resume(decisions) {
        if (this.isStreaming) return;
        await this.runStream(`/thread/${this.threadId}/resume`, { decisions });
    }

    async runStream(path, payload) {
        this.isStreaming = true;
        this.store?.setRunning(this.threadId, true);
        this.updateSendButton();
        this.showTyping();
        let receivedDone = false;
        let failure = null;
        try {
            const response = await fetch(`${API_BASE}${path}`, payload === null ? {} : {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
            });
            this.sidebar?.loadThreadList().catch(console.error);
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || `HTTP ${response.status}`);
            }
            await readChatStream(response, event => {
                if (event.type === 'message') {
                    this.hideTyping();
                    this.applyMessage(event);
                } else if (event.type === 'done') {
                    receivedDone = true;
                    this.approvalPanel.update(event);
                }
            });
        } catch (error) {
            failure = error.message;
        } finally {
            this.hideTyping();
            for (const [id, message] of this.messages) this.messages.set(id, { ...message, complete: true });
            this.renderMessages();
            // 原生 messages 是最终依据，修正重试、工具卸载和中断产生的差异。
            try { await this.loadHistoryMessages(); }
            catch (error) { failure ||= error.message; }
            if (!receivedDone) await this.approvalPanel.refresh();
            if (failure) this.addNotice(failure);
            this.isStreaming = false;
            this.store?.setRunning(this.threadId, false);
            this.updateSendButton();
            if (this.isActive) this.mediaLibrary?.refresh().catch(console.error);
            await this.sidebar?.loadThreadList().catch(console.error);
            this.scroll.changed();
            this.onSettled?.(this);
        }
    }

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
        const input = this.input;
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
            
            // 同步共享列表，站内导航不会再通过整页刷新清除已删除的会话。
            const threads = await this.store.refresh();
            navigateTo(threads.length ? `/chat/${threads[0].thread_id}` : '/');
        } catch (error) {
            console.error('Delete error:', error);
            alert('删除失败: ' + error.message);
        }
    }
}
