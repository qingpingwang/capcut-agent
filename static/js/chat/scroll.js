export function isNearBottom(element, tolerance = 2) {
    return element.scrollHeight - element.scrollTop - element.clientHeight <= tolerance;
}

export class ChatScroll {
    constructor(viewport, content, button) {
        this.viewport = viewport;
        this.button = button;
        this.follow = true;
        this.frame = null;
        this.animation = null;
        this.animationFrame = null;
        this.measure();
        viewport.addEventListener('scroll', () => {
            if (this.suspended || this.disposed) return;
            const top = Math.max(0, Math.min(viewport.scrollTop, viewport.scrollHeight - viewport.clientHeight));
            const layoutChanged = this.height !== viewport.scrollHeight
                || this.clientHeight !== viewport.clientHeight;
            if (!layoutChanged) {
                if (top < this.top) this.pause();
                else if (top > this.top && isNearBottom(viewport)) this.follow = true;
            }
            this.measure();
            // scroll 只读取位置；在这里回写 scrollTop 会和触控板的小幅滚动互相争抢。
            this.updateButton();
        }, { passive: true });
        // 在下一帧的自动跟随之前响应用户向上滚动的意图。
        viewport.addEventListener('wheel', event => {
            if (event.deltaY < 0) this.pause();
        }, { passive: true });
        viewport.addEventListener('keydown', event => {
            if (['ArrowUp', 'PageUp', 'Home'].includes(event.key)
                || (event.key === ' ' && event.shiftKey)) this.pause();
        });
        let touchY = null;
        viewport.addEventListener('touchstart', event => {
            touchY = event.touches[0]?.clientY ?? null;
        }, { passive: true });
        viewport.addEventListener('touchmove', event => {
            const nextY = event.touches[0]?.clientY;
            if (touchY !== null && nextY > touchY) this.pause();
            touchY = nextY ?? null;
        }, { passive: true });
        // 阅读工具详情时保留点击位置；展开/折叠本身不触发自动滚动。
        content.addEventListener('click', event => {
            if (event.target.closest('summary')) this.pause();
        });
        button.addEventListener('click', () => this.bottom(true));
        this.observer = new ResizeObserver(entries => {
            if (entries.some(entry => entry.target === viewport)) this.changed();
            else this.updateButton();
        });
        this.observer.observe(viewport);
        this.observer.observe(content);
        content.addEventListener('load', () => this.changed(), true);
    }

    measure() {
        this.top = Math.max(0, Math.min(this.viewport.scrollTop, this.viewport.scrollHeight - this.viewport.clientHeight));
        this.height = this.viewport.scrollHeight;
        this.clientHeight = this.viewport.clientHeight;
    }

    updateButton() { this.button.hidden = Boolean(this.animation) || isNearBottom(this.viewport); }

    cancelAnimation() {
        if (this.animationFrame !== null) cancelAnimationFrame(this.animationFrame);
        this.animationFrame = null;
        this.animation = null;
    }

    pause() {
        this.cancelAnimation();
        this.follow = false;
    }

    changed() {
        if (this.disposed || this.suspended) return;
        if (this.frame !== null) return;
        this.frame = requestAnimationFrame(() => {
            this.frame = null;
            if (this.follow && !this.animation && !isNearBottom(this.viewport)) {
                this.viewport.scrollTop = this.viewport.scrollHeight;
            }
            this.measure();
            this.updateButton();
        });
    }

    bottom(smooth = false) {
        if (this.disposed || this.suspended) return;
        this.cancelAnimation();
        this.follow = true;
        if (smooth && !isNearBottom(this.viewport)
            && !globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
            const animation = { from: this.viewport.scrollTop, started: null };
            this.animation = animation;
            this.updateButton();
            const tick = timestamp => {
                if (this.animation !== animation) return;
                animation.started ??= timestamp;
                const progress = Math.min(1, (timestamp - animation.started) / 240);
                // 每帧读取目标，快速滑动期间收到的新 token 也能跟上。
                const target = Math.max(0, this.viewport.scrollHeight - this.viewport.clientHeight);
                this.viewport.scrollTop = animation.from + (target - animation.from) * (1 - (1 - progress) ** 3);
                this.measure();
                if (progress < 1) this.animationFrame = requestAnimationFrame(tick);
                else {
                    this.animation = null;
                    this.animationFrame = null;
                    this.updateButton();
                    this.changed();
                }
            };
            this.animationFrame = requestAnimationFrame(tick);
            return;
        }
        this.viewport.scrollTop = this.viewport.scrollHeight;
        this.measure();
        this.updateButton();
        this.changed();
    }

    suspend() {
        this.savedTop = this.viewport.scrollTop;
        this.suspended = true;
        this.cancelAnimation();
        if (this.frame !== null) cancelAnimationFrame(this.frame);
        this.frame = null;
    }

    resume() {
        this.suspended = false;
        if (!this.follow) this.viewport.scrollTop = this.savedTop || 0;
        this.measure();
        this.changed();
    }

    destroy() {
        this.suspend();
        this.disposed = true;
        this.observer.disconnect();
    }
}
