import { StreamingMarkdown } from './markdown.js';
import { ToolCallView } from './tool-call-view.js';

const node = (tag, className, text = '') => {
    const element = document.createElement(tag);
    element.className = className;
    element.textContent = text;
    return element;
};

export class MessageView {
    constructor(message) {
        this.element = node('article', `chat-message message-${message.role}`);
        this.element.dataset.messageId = message.id;
        this.body = node('div', 'message-body');
        if (message.role === 'ai') {
            const avatar = node('span', 'assistant-avatar material-symbols-outlined', 'movie_edit');
            avatar.setAttribute('aria-hidden', 'true');
            this.element.append(avatar);
        }
        this.text = node('div', message.role === 'human' ? 'user-message-text' : 'message-content');
        this.body.append(this.text);
        this.element.append(this.body);
        this.markdown = message.role === 'ai' ? new StreamingMarkdown(this.text) : null;
        this.tools = new Map();
        this.update(message);
    }

    update(message) {
        if (this.message === message) return;
        this.message = message;
        this.element.classList.toggle('is-streaming', !message.complete);
        this.text.hidden = message.role === 'tool' || !message.content;
        if (message.role !== 'tool') {
            if (this.markdown) this.markdown.update(message.content, message.complete);
            else if (this.text.textContent !== message.content) this.text.textContent = message.content;
        }
        this.element.classList.toggle('has-tools', Boolean(message.tools?.length));
        const keep = new Set((message.tools || []).map(tool => tool.key));
        for (const [key, view] of this.tools) {
            if (!keep.has(key)) { view.element.remove(); this.tools.delete(key); }
        }
        (message.tools || []).forEach((tool, index) => {
            let view = this.tools.get(tool.key);
            if (!view) { view = new ToolCallView(); this.tools.set(tool.key, view); }
            view.update(tool);
            if (this.body.children[index + 1] !== view.element) {
                this.body.insertBefore(view.element, this.body.children[index + 1] || null);
            }
        });
    }
}
