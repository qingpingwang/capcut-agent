const STORAGE_KEY = 'capcut.composer-height';
export const COMPOSER_HEIGHT = { min: 112, default: 156, max: 480 };

// 高度归输入区所有，textarea 只填满剩余空间，不再与自动增高互相争抢。
export class ComposerResize {
    constructor(root, region, handle) {
        this.root = root;
        this.region = region;
        this.handle = handle;
        this.events = new AbortController();
        const options = { signal: this.events.signal };
        handle.setAttribute('aria-controls', region.id);
        handle.addEventListener('pointerdown', event => {
            if (event.button !== 0) return;
            event.preventDefault();
            handle.focus({ preventScroll: true });
            this.drag = { id: event.pointerId, y: event.clientY, height: region.clientHeight };
            handle.setPointerCapture(event.pointerId);
            handle.classList.add('is-dragging');
        }, options);
        handle.addEventListener('pointermove', event => {
            if (this.drag?.id !== event.pointerId) return;
            this.setHeight(this.drag.height + this.drag.y - event.clientY);
        }, options);
        for (const type of ['pointerup', 'pointercancel', 'lostpointercapture']) {
            handle.addEventListener(type, () => this.stop(), options);
        }
        handle.addEventListener('keydown', event => {
            const { min, max } = this.bounds();
            const heights = {
                ArrowUp: region.clientHeight + 16, ArrowDown: region.clientHeight - 16,
                Home: min, End: max, Enter: COMPOSER_HEIGHT.default,
            };
            if (!(event.key in heights)) return;
            event.preventDefault();
            this.setHeight(heights[event.key]);
            this.save();
        }, options);
        handle.addEventListener('dblclick', () => {
            this.setHeight(COMPOSER_HEIGHT.default);
            this.save();
        }, options);
        this.observer = new ResizeObserver(() => this.layout());
        this.observer.observe(root);
        this.refresh();
    }

    bounds() {
        const height = this.root.clientHeight;
        const approval = this.root.querySelector('.approval-panel')?.getBoundingClientRect().height || 0;
        const header = this.root.querySelector('header')?.clientHeight || 64;
        const max = Math.max(COMPOSER_HEIGHT.min, Math.min(
            COMPOSER_HEIGHT.max, Math.floor(height / 2), height - header - approval - 132,
        ));
        return { min: COMPOSER_HEIGHT.min, max };
    }

    refresh() {
        let stored;
        try { stored = Number(localStorage.getItem(STORAGE_KEY)); } catch { /* 存储不可用时仍可调整 */ }
        this.preferred = Number.isFinite(stored) && stored >= COMPOSER_HEIGHT.min
            ? stored : COMPOSER_HEIGHT.default;
        this.layout();
    }

    setHeight(value) {
        const { min, max } = this.bounds();
        this.preferred = Math.round(Math.max(min, Math.min(max, value)));
        this.layout();
    }

    layout() {
        if (!this.root.clientHeight) return;
        const { min, max } = this.bounds();
        const height = Math.round(Math.max(min, Math.min(max, this.preferred)));
        this.region.style.height = `${height}px`;
        this.handle.setAttribute('aria-valuemin', min);
        this.handle.setAttribute('aria-valuemax', max);
        this.handle.setAttribute('aria-valuenow', height);
        this.handle.setAttribute('aria-valuetext', `${height} 像素`);
    }

    save() {
        try { localStorage.setItem(STORAGE_KEY, this.preferred); } catch { /* 不影响本次调整 */ }
    }

    stop() {
        if (!this.drag) return;
        const { id } = this.drag;
        this.drag = null;
        if (this.handle.hasPointerCapture(id)) this.handle.releasePointerCapture(id);
        this.handle.classList.remove('is-dragging');
        this.save();
    }

    destroy() { this.stop(); this.events.abort(); this.observer.disconnect(); }
}
