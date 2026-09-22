import * as smd from '../../vendor/streaming-markdown.js';

export function safeMarkdownURL(value, image = false, base = 'https://localhost/') {
    try {
        const url = new URL(value, base);
        return (image ? ['http:', 'https:'] : ['http:', 'https:', 'mailto:']).includes(url.protocol);
    } catch { return false; }
}

// 直接增量追加 DOM；不在每个 token 到达时重新生成整段 HTML。
export class StreamingMarkdown {
    constructor(element) {
        this.element = element;
        this.reset();
    }

    reset() {
        this.element.replaceChildren();
        this.content = '';
        this.ended = false;
        const renderer = smd.default_renderer(this.element);
        const setAttribute = renderer.set_attr;
        renderer.set_attr = (data, type, value) => {
            if ((type === smd.HREF || type === smd.SRC) &&
                !safeMarkdownURL(value, type === smd.SRC, window.location.href)) return;
            setAttribute(data, type, value);
            if (type === smd.HREF) {
                data.nodes[data.index].setAttribute('rel', 'noopener noreferrer');
                data.nodes[data.index].setAttribute('target', '_blank');
            }
        };
        this.parser = smd.parser(renderer);
    }

    update(content, complete = false) {
        if (content !== this.content && (this.ended || !content.startsWith(this.content))) this.reset();
        const delta = content.slice(this.content.length);
        if (delta) smd.parser_write(this.parser, delta);
        this.content = content;
        if (complete && !this.ended) {
            smd.parser_end(this.parser);
            this.ended = true;
        }
    }
}
