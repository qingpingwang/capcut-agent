import { toolStatus } from './tool-presentation.js';

const node = (tag, className, text = '') => {
    const element = document.createElement(tag);
    element.className = className;
    element.textContent = text;
    return element;
};
const setText = (element, text) => {
    if (element.textContent !== text) element.textContent = text;
};
const pretty = value => {
    try { return JSON.stringify(JSON.parse(value), null, 2); }
    catch { return value || ''; }
};

// 一个调用一张卡；结果到达后更新原卡片，保留用户的展开状态。
export class ToolCallView {
    constructor() {
        this.element = node('details', 'tool-call');
        this.summary = node('summary', 'tool-summary');
        this.icon = node('span', 'material-symbols-outlined tool-icon', 'build');
        this.icon.setAttribute('aria-hidden', 'true');
        this.label = node('span', 'tool-label');
        this.status = node('span', 'tool-status');
        this.summary.append(this.icon, this.label, this.status);
        const content = node('div', 'tool-call-content');
        this.input = node('div', 'tool-section');
        this.args = node('pre', 'tool-content');
        this.input.append(node('p', 'tool-section-label', '输入参数'), this.args);
        const output = node('div', 'tool-section');
        this.result = node('pre', 'tool-content');
        output.append(node('p', 'tool-section-label', '执行结果'), this.result);
        content.append(this.input, output);
        this.element.append(this.summary, content);
    }

    update(tool) {
        const status = toolStatus(tool);
        const name = tool.call?.name || tool.results[0]?.name || '工具执行';
        this.element.dataset.toolCallId = tool.call?.id || tool.results[0]?.tool_call_id || '';
        setText(this.label, name);
        this.label.title = name;
        setText(this.status, status.label);
        setText(this.icon, status.error ? 'error_outline' : status.settled ? 'check_circle' : 'build');
        this.element.classList.toggle('tool-error', status.error);
        this.element.classList.toggle('tool-success', status.settled && !status.error);
        this.input.hidden = !tool.call;
        setText(this.args, pretty(tool.call?.args));
        const result = tool.results.length ? tool.results.map(item => pretty(item.content)).join('\n\n')
            : tool.call?.error || '等待工具返回…';
        setText(this.result, result);
        this.result.classList.toggle('is-pending', !status.settled);
    }
}
