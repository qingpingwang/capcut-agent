import { API_BASE } from '../utils.js';
import { showToast } from './toast.js';

const node = (tag, text = '', classes = '') => {
    const el = document.createElement(tag);
    el.textContent = text;
    el.className = classes;
    return el;
};

const actionLabels = {
    delete_project: '删除工程',
    delete_track: '删除轨道',
    delete_segment: '删除片段',
    copy_project_to_jianying: '同步草稿到剪映',
};

// 平时不占用界面，只在工具执行需要人工决定时显示。
export class ApprovalPanel {
    constructor(chat) {
        this.chat = chat;
        this.interrupts = [];
    }

    async init() {
        this.container = node('section', '', 'approval-panel');
        this.container.id = `approvalPanel-${this.chat.threadId}`;
        this.container.hidden = true;
        this.chat.el('composerResizeHandle').before(this.container);
        await this.refresh();
    }

    async refresh() {
        try {
            const response = await fetch(`${API_BASE}/thread/${this.chat.threadId}/agent-state`);
            const data = await response.json();
            if (this.chat.disposed) return;
            if (!response.ok) throw new Error(data.error || '读取待确认操作失败');
            this.update(data);
            return data;
        } catch (error) { showToast(error.message, 'error'); }
    }

    update(state) {
        if (!Array.isArray(state.interrupts)) return;
        if (state.run) this.chat.run = state.run;
        this.interrupts = state.interrupts;
        this.container.hidden = !this.interrupts.length;
        this.render();
        this.chat.composer?.layout();
        this.chat.updateSendButton();
    }

    render() {
        this.container.replaceChildren();
        if (!this.interrupts.length) return;
        const cards = node('div', '', 'approval-cards');
        const controls = [];
        for (const interrupt of this.interrupts) {
            interrupt.action_requests.forEach((action, index) => {
                const label = actionLabels[action.name] || action.name;
                const card = node('section', '', 'approval-card');
                card.append(node('p', `待确认：${label}`, 'approval-title'));
                const choice = node('select', '', 'approval-choice');
                choice.setAttribute('aria-label', `${label} 审批决定`);
                for (const type of interrupt.review_configs[index].allowed_decisions) {
                    const labels = { approve: '批准', edit: '修改参数后批准', reject: '拒绝' };
                    const option = node('option', labels[type] || type);
                    option.value = type;
                    choice.append(option);
                }
                const args = node('textarea', '', 'approval-args');
                args.value = JSON.stringify(action.args, null, 2);
                args.readOnly = true;
                args.setAttribute('aria-label', `${label} 参数`);
                const reason = node('input', '', 'approval-reason');
                reason.placeholder = '拒绝原因（可选）';
                reason.setAttribute('aria-label', `${label} 拒绝原因`);
                reason.hidden = true;
                choice.onchange = () => {
                    args.readOnly = choice.value !== 'edit';
                    reason.hidden = choice.value !== 'reject';
                };
                card.append(choice, args, reason);
                cards.append(card);
                controls.push({ id: interrupt.id, action, choice, args, reason });
            });
        }
        const submit = node('button', '确认并继续', 'approval-submit');
        submit.type = 'button';
        submit.onclick = async () => {
            try {
                const decisions = {};
                for (const item of controls) {
                    const decision = { type: item.choice.value };
                    if (decision.type === 'edit') decision.edited_action = { name: item.action.name, args: JSON.parse(item.args.value) };
                    if (decision.type === 'reject') decision.message = item.reason.value || '用户拒绝了此操作，请调整方案。';
                    (decisions[item.id] ||= { decisions: [] }).decisions.push(decision);
                }
                submit.disabled = true;
                await this.chat.resume(decisions);
            } catch (error) { showToast(error.message, 'error'); }
            finally { submit.disabled = false; }
        };
        this.container.append(cards, submit);
    }
}
