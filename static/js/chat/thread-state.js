export function relativeTime(value, now = Date.now()) {
    const timestamp = Date.parse(value);
    if (!Number.isFinite(timestamp)) return '';
    const minutes = Math.floor(Math.max(0, now - timestamp) / 60000);
    if (minutes < 1) return '刚刚';
    if (minutes < 60) return `${minutes}分钟前`;
    if (minutes < 1440) return `${Math.floor(minutes / 60)}小时前`;
    if (minutes < 10080) return `${Math.floor(minutes / 1440)}天前`;
    const date = new Date(timestamp);
    return `${date.getMonth() + 1}/${date.getDate()}`;
}

export function threadIndicator(thread, active = false) {
    if (thread.running) return 'running';
    if (thread.unread && !active) return 'unread';
    return '';
}

// 应用只有一个时钟；只更新相对时间，不每分钟重建所有会话页面。
export class ThreadStore {
    constructor({ fetcher = (...args) => fetch(...args), schedule = setInterval, unschedule = clearInterval } = {}) {
        this.fetcher = fetcher;
        this.threads = [];
        this.listeners = new Set();
        this.running = new Set();
        this.readRuns = new Map();
        this.request = 0;
        this.timer = schedule(() => this.emit('clock'), 60000);
        this.unschedule = unschedule;
    }

    subscribe(listener) {
        this.listeners.add(listener);
        listener(this.values(), 'data');
        return () => this.listeners.delete(listener);
    }

    values() {
        return this.threads.map(thread => ({ ...thread,
            running: this.running.has(thread.thread_id) || thread.running,
            unread: Boolean(thread.unread && this.readRuns.get(thread.thread_id) !== thread.run_id),
        }));
    }
    emit(reason = 'data') { for (const listener of this.listeners) listener(this.values(), reason); }
    setRunning(id, running) {
        if (running) this.running.add(id);
        else this.running.delete(id);
        this.emit();
    }

    async refresh() {
        const request = ++this.request;
        const response = await this.fetcher('/api/threads');
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || '读取会话列表失败');
        if (request === this.request) {
            this.threads = data.threads.sort((a, b) => (Date.parse(b.updated_at) || 0) - (Date.parse(a.updated_at) || 0));
            this.emit();
        }
        return this.values();
    }

    async markRead(threadId, runId) {
        if (!runId) return;
        try {
            const response = await this.fetcher(`/api/thread/${encodeURIComponent(threadId)}/read`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ run_id: runId }),
            });
            if (!response.ok) return;
            const data = await response.json();
            // 延迟到达的已读响应只能确认对应轮次，不能覆盖下一轮的运行状态。
            if (data.run?.run_id === runId && !data.run.unread && !data.run.running) {
                this.readRuns.set(threadId, runId);
            }
            this.emit();
        } catch (error) {
            // 已读确认失败不阻断导航；再次打开会话时会重试。
            console.warn('更新已读状态失败:', error);
        }
    }

    destroy() { this.unschedule(this.timer); this.listeners.clear(); }
}
