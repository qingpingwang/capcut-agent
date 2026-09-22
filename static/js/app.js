import { setNavigator } from './utils.js';
import { Sidebar } from './components/sidebar.js';
import { Chat } from './components/chat.js';
import { MediaLibrary } from './components/media-library.js';
import { Home } from './components/home.js';
import { ThreadStore } from './chat/thread-state.js';
import './components/toast.js';

class App {
    constructor() {
        this.store = new ThreadStore();
        this.sidebar = new Sidebar(this.store);
        this.mediaLibrary = new MediaLibrary();
        this.home = new Home(this.store);
        this.pages = new Map();
        this.current = null;
        this.template = document.querySelector('main');
        this.template.remove();
        this.template.style.display = '';
        setNavigator(url => this.navigate(url));
        window.addEventListener('popstate', () => this.navigate(window.location.href, { history: false }));
    }

    async init() {
        await this.store.refresh();
        await this.navigate(window.location.href, { history: false });
        // 刷新浏览器后恢复仍在服务端执行的会话；正常切换直接复用现有页面和 SSE。
        for (const thread of this.store.values()) {
            if (thread.running && !this.pages.has(thread.thread_id)) this.ensurePage(thread.thread_id);
        }
        this.removeLoader();
    }

    ensurePage(threadId, isNew = false) {
        if (this.pages.has(threadId)) return this.pages.get(threadId);
        const root = this.template.cloneNode(true);
        root.hidden = true;
        root.dataset.threadId = threadId;
        // 多个保留页面使用唯一 DOM ID，组件通过页面内的稳定 data 属性访问元素。
        root.querySelectorAll('[id]').forEach(element => {
            element.dataset.chatElement = element.id;
            element.id = `${element.id}-${threadId}`;
        });
        document.getElementById('mediaLibrary').before(root);
        const chat = new Chat(root, { store: this.store, onSettled: page => this.settled(page).catch(console.error) });
        this.pages.set(threadId, chat);
        chat.ready = chat.init(threadId, isNew, this.mediaLibrary, this.sidebar);
        return chat;
    }

    releaseIdle(page) {
        if (page && page !== this.current && !page.isStreaming && !page.isInitializing) {
            page.destroy();
            this.pages.delete(page.threadId);
        }
    }

    async settled(page) {
        if (page.disposed) return;
        if (page === this.current) await this.store.markRead(page.threadId, page.run?.run_id);
        else this.releaseIdle(page);
    }

    async navigate(value, { history = true } = {}) {
        const url = new URL(value, window.location.origin);
        const threadId = url.pathname.startsWith('/chat/') ? decodeURIComponent(url.pathname.split('/')[2]) : null;
        if (history) {
            const ui = new URL(window.location.href).searchParams.get('ui');
            if (ui && !url.searchParams.has('ui')) url.searchParams.set('ui', ui);
            window.history.pushState({}, '', url);
        }
        if (threadId && this.current?.threadId === threadId) {
            await this.current.activate();
            return;
        }
        const previous = this.current;
        previous?.deactivate();
        this.current = null;
        this.releaseIdle(previous);
        this.home.destroy();
        this.sidebar.init(threadId);
        if (!threadId) {
            this.mediaLibrary.setThread(null);
            await this.home.init();
            this.removeLoader();
            return;
        }
        document.getElementById('leftSidebar').style.display = '';
        document.getElementById('mediaLibrary').style.display = '';
        const page = this.ensurePage(threadId, url.searchParams.get('new') === 'true');
        this.current = page;
        // 页面加载/已读确认期间，素材操作也必须立即切到新会话。
        this.mediaLibrary.setThread(threadId, page);
        await page.activate();
        if (this.current !== page || page.disposed) return;
        await page.ready;
        if (this.current !== page || page.disposed) return;
        await this.mediaLibrary.init(threadId, page);
        if (this.current !== page || page.disposed) return;
        page.updateSendButton();
        page.input.focus();
        url.searchParams.delete('new');
        window.history.replaceState({}, '', url);
        this.removeLoader();
    }

    removeLoader() {
        document.getElementById('app-loader')?.remove();
        document.getElementById('preloadStyles')?.remove();
    }
}

window.addEventListener('DOMContentLoaded', () => {
    const app = new App();
    app.init().catch(error => {
        console.error('应用启动失败:', error);
        app.removeLoader();
        const notice = document.createElement('p');
        notice.className = 'chat-notice';
        notice.textContent = `加载失败：${error.message}，请刷新重试。`;
        document.body.append(notice);
    });
});
