import test from 'node:test';
import assert from 'node:assert/strict';
import { readChatStream } from '../static/js/chat/sse.js';
import { applyMessageUpdate } from '../static/js/chat/message-state.js';
import { safeMarkdownURL } from '../static/js/chat/markdown.js';
import { ChatScroll } from '../static/js/chat/scroll.js';
import { projectToolMessages, toolStatus } from '../static/js/chat/tool-presentation.js';
import * as smd from '../static/vendor/streaming-markdown.js';

function streamResponse(text, size = 1) {
    const bytes = new TextEncoder().encode(text);
    return new Response(new ReadableStream({
        start(controller) {
            for (let index = 0; index < bytes.length; index += size) controller.enqueue(bytes.slice(index, index + size));
            controller.close();
        },
    }));
}

test('SSE accepts split UTF-8, CRLF, comments and multiline data', async () => {
    const events = [];
    const stream = '\uFEFF: heartbeat\r\n\r\nevent: message\r\ndata: {"type":"message",\r\ndata: "message":{"id":"one","content":"你好，**剪辑**"}}\r\n\r\ndata: {"type":"done","interrupts":[]}\r\n\r\n';
    await readChatStream(streamResponse(stream), event => events.push(event));
    assert.equal(events.length, 2);
    assert.equal(events[0].message.content, '你好，**剪辑**');
    assert.equal(events[1].type, 'done');
});

test('SSE reports errors, malformed payloads and premature EOF', async () => {
    await assert.rejects(readChatStream(streamResponse('data: {"type":"error","error":"模型不可用"}\n\n'), () => {}), /模型不可用/);
    await assert.rejects(readChatStream(streamResponse('data: not-json\n\n'), () => {}), /无法解析/);
    await assert.rejects(readChatStream(streamResponse('data: {"type":"message"}\n\n'), () => {}), /连接已中断/);
});

test('message deltas keep prose and parallel tools, snapshot replaces without duplication', () => {
    let state = applyMessageUpdate(null, { delta: true, message: { id: 'one', role: 'ai', content: '先', tool_calls: [
        { index: 1, id: 'b', name: 'get_tracks', args: '{"project_id":' },
        { index: 0, id: 'a', name: 'get_project_info', args: '{"project_id":' },
    ] } });
    state = applyMessageUpdate(state, { delta: true, message: { id: 'one', role: 'ai', content: '检查', tool_calls: [
        { index: 0, args: '"a"}' }, { index: 1, args: '"b"}' },
    ] } });
    state = applyMessageUpdate(state, { delta: true, complete: true, message: { id: 'one', role: 'ai', content: '' } });
    assert.equal(state.content, '先检查');
    assert.deepEqual(state.tool_calls.map(call => JSON.parse(call.args).project_id), ['a', 'b']);
    assert.equal(state.complete, true);
    const snapshot = applyMessageUpdate(state, { message: { ...state, content: '最终状态' }, delta: false });
    assert.equal(snapshot.content, '最终状态');
    assert.equal(snapshot.tool_calls.length, 2);
});

test('markdown parser accepts character-by-character fences, tables and raw HTML as text', () => {
    const render = content => {
        const events = [];
        const parser = smd.parser({ data: events,
            add_token(data, token) { data.push(['start', token]); },
            end_token(data) { data.push(['end']); },
            add_text(data, text) { data.push(['text', text]); },
            set_attr(data, attr, value) { data.push(['attr', attr, value]); },
        });
        for (const character of content) smd.parser_write(parser, character);
        smd.parser_end(parser);
        return events;
    };
    const markdown = render('## 计划\n\n**清晰**、简短。\n\n|镜头|时长|\n|---|---|\n|开场|3秒|\n\n```js\nconst x = 1;\n```\n\n<script>alert(1)</script>');
    const tokens = markdown.filter(event => event[0] === 'start').map(event => event[1]);
    assert.ok(tokens.includes(smd.TABLE));
    assert.ok(tokens.includes(smd.CODE_FENCE));
    const text = markdown.filter(event => event[0] === 'text').map(event => event[1]).join('');
    assert.ok(text.includes('<script>alert(1)</script>'));
    assert.ok(text.includes('const x = 1;'));
});

test('markdown links cannot execute script URLs', () => {
    assert.equal(safeMarkdownURL('javascript:alert(1)'), false);
    assert.equal(safeMarkdownURL('java\nscript:alert(1)'), false);
    assert.equal(safeMarkdownURL('data:text/html,<script>alert(1)</script>'), false);
    assert.equal(safeMarkdownURL('/uploads/demo.png', true), true);
    assert.equal(safeMarkdownURL('https://example.com'), true);
});

function withScrollHarness(run) {
    const originalRAF = globalThis.requestAnimationFrame;
    const originalCancel = globalThis.cancelAnimationFrame;
    const originalObserver = globalThis.ResizeObserver;
    const frames = [];
    let nextId = 0;
    let clock = 0;
    globalThis.requestAnimationFrame = callback => { const id = ++nextId; frames.push({ id, callback }); return id; };
    globalThis.cancelAnimationFrame = id => {
        const index = frames.findIndex(frame => frame.id === id);
        if (index !== -1) frames.splice(index, 1);
    };
    let resize;
    globalThis.ResizeObserver = class {
        constructor(callback) { resize = callback; }
        observe() {}
        disconnect() {}
    };
    try {
        const viewport = new EventTarget();
        let top = 600;
        Object.assign(viewport, { scrollHeight: 1000, clientHeight: 400 });
        Object.defineProperty(viewport, 'scrollTop', {
            get: () => top,
            set: value => { top = Math.max(0, Math.min(value, viewport.scrollHeight - viewport.clientHeight)); },
        });
        const button = new EventTarget();
        const content = new EventTarget();
        const scroll = new ChatScroll(viewport, content, button);
        const step = () => { clock += 16; frames.shift()?.callback(clock); };
        const paint = () => {
            for (let count = 0; frames.length; count++) {
                assert.ok(count < 100, 'animation frames must settle');
                step();
            }
        };
        run({ viewport, content, button, scroll, paint, step, frames, resize });
    } finally {
        globalThis.requestAnimationFrame = originalRAF;
        globalThis.cancelAnimationFrame = originalCancel;
        globalThis.ResizeObserver = originalObserver;
    }
}

test('scroll follows viewport changes, pauses on user scroll and resumes at the bottom', () => {
    withScrollHarness(({ viewport, button, scroll, paint, resize }) => {
        // Approval opens: the viewport shrinks and fires scroll without user input.
        viewport.clientHeight = 200;
        viewport.dispatchEvent(new Event('scroll'));
        resize([{ target: viewport }]);
        paint();
        assert.equal(scroll.follow, true);
        assert.equal(viewport.scrollTop, 800);
        assert.equal(button.hidden, true);

        viewport.dispatchEvent(Object.assign(new Event('wheel'), { deltaY: -120 }));
        viewport.scrollTop = 500;
        viewport.dispatchEvent(new Event('scroll'));
        viewport.scrollHeight += 300;
        scroll.changed();
        paint();
        assert.equal(viewport.scrollTop, 500);
        assert.equal(button.hidden, false);

        button.dispatchEvent(new Event('click'));
        paint();
        assert.equal(viewport.scrollTop, 1100);
        viewport.scrollHeight += 100;
        scroll.changed();
        paint();
        assert.equal(viewport.scrollTop, 1200);
        assert.equal(scroll.follow, true);
    });
});

test('small upward gestures never snap back or schedule scroll feedback, even during output', () => {
    withScrollHarness(({ viewport, scroll, paint, frames }) => {
        scroll.changed(); // A token already scheduled a frame before the user moved.
        viewport.dispatchEvent(Object.assign(new Event('wheel'), { deltaY: -6 }));
        viewport.scrollTop = 594;
        viewport.dispatchEvent(new Event('scroll'));
        paint();
        assert.equal(viewport.scrollTop, 594);
        assert.equal(scroll.follow, false);
        for (const position of [592.5, 590, 589.5]) {
            viewport.scrollTop = position;
            viewport.dispatchEvent(new Event('scroll'));
            assert.equal(frames.length, 0, 'scroll events must not write scrollTop');
            scroll.changed();
            paint();
            assert.equal(viewport.scrollTop, position);
            assert.equal(scroll.follow, false);
        }
        viewport.scrollHeight += 30;
        scroll.changed();
        paint();
        assert.equal(viewport.scrollTop, 589.5);
        viewport.scrollTop = 630;
        viewport.dispatchEvent(new Event('scroll'));
        assert.equal(scroll.follow, true, 'manually reaching the bottom resumes following');
    });
});

test('tool expansion and collapse preserve the reading position', () => {
    withScrollHarness(({ viewport, content, scroll, paint, resize, frames }) => {
        const click = new Event('click');
        Object.defineProperty(click, 'target', { value: { closest: () => ({ tagName: 'SUMMARY' }) } });
        content.dispatchEvent(click);
        viewport.scrollHeight += 240;
        resize([{ target: content }]);
        assert.equal(frames.length, 0);
        scroll.changed();
        paint();
        assert.equal(viewport.scrollTop, 600);
        assert.equal(scroll.follow, false);
    });
});

test('hidden chat keeps its reading position and resumes following only when appropriate', () => {
    withScrollHarness(({ viewport, scroll, paint, frames }) => {
        viewport.scrollTop = 300;
        viewport.dispatchEvent(new Event('scroll'));
        scroll.suspend();
        // display:none may reset layout and dispatch scroll while tokens keep arriving.
        viewport.scrollHeight = 0;
        viewport.clientHeight = 0;
        viewport.scrollTop = 0;
        viewport.dispatchEvent(new Event('scroll'));
        scroll.changed();
        assert.equal(frames.length, 0);
        viewport.scrollHeight = 1400;
        viewport.clientHeight = 400;
        scroll.resume();
        paint();
        assert.equal(viewport.scrollTop, 300);
        assert.equal(scroll.follow, false);

        scroll.bottom();
        paint();
        scroll.suspend();
        viewport.scrollHeight += 200;
        scroll.changed();
        assert.equal(frames.length, 0);
        scroll.resume();
        paint();
        assert.equal(viewport.scrollTop, 1200);
        assert.equal(scroll.follow, true);
        scroll.destroy();
        scroll.changed();
        assert.equal(frames.length, 0);
    });
});

test('each tool pairs its result by ID and stays in declaration order', () => {
    const messages = [
        { id: 'human', role: 'human', content: '检查草稿' },
        { id: 'ai', role: 'ai', content: '先检查工程和轨道。', tool_calls: [
            { index: 0, id: 'a', name: 'inspect', args: '{"target":"project"}' },
            { index: 1, id: 'b', name: 'inspect', args: '{"target":"tracks"}' },
        ] },
        { id: 'b-result', role: 'tool', tool_call_id: 'b', content: '轨道不存在', status: 'error' },
        { id: 'a-result', role: 'tool', tool_call_id: 'a', content: '{"name":"旅行"}', status: 'success' },
        { id: 'final', role: 'ai', content: '检查完成。' },
    ];
    const original = JSON.stringify(messages);
    const projected = projectToolMessages(messages);
    assert.deepEqual(projected.map(message => message.id), ['human', 'ai', 'final']);
    assert.equal(projected[1].content, '先检查工程和轨道。');
    assert.deepEqual(projected[1].tools.map(tool => tool.results[0].id), ['a-result', 'b-result']);
    assert.equal(toolStatus(projected[1].tools[1]).error, true);
    assert.equal(JSON.stringify(messages), original, 'native messages remain unchanged');
    assert.deepEqual(projectToolMessages(JSON.parse(original)), projected, 'history and live projection agree');
});

test('jump to latest animates quickly, follows a growing target and can be interrupted', () => {
    withScrollHarness(({ viewport, button, scroll, paint, step }) => {
        viewport.scrollTop = 100;
        viewport.dispatchEvent(new Event('scroll'));
        button.dispatchEvent(new Event('click'));
        step();
        step();
        assert.ok(viewport.scrollTop > 100 && viewport.scrollTop < 600, 'move through intermediate positions');
        viewport.scrollHeight += 100;
        scroll.changed();
        paint();
        assert.equal(viewport.scrollTop, 700, 'finish at the latest content');
        assert.equal(scroll.animation, null);
        assert.equal(button.hidden, true);

        viewport.scrollTop = 100;
        viewport.dispatchEvent(new Event('scroll'));
        button.dispatchEvent(new Event('click'));
        step();
        step();
        viewport.dispatchEvent(Object.assign(new Event('wheel'), { deltaY: -4 }));
        const stopped = viewport.scrollTop;
        scroll.changed();
        paint();
        assert.equal(viewport.scrollTop, stopped);
        assert.equal(scroll.follow, false);
        assert.equal(scroll.animation, null);
    });
});

test('unmatched results remain visible, and pending calls keep their slot when IDs arrive', () => {
    const call = { index: 0, name: 'inspect', args: '{' };
    let messages = [
        { id: 'ai', role: 'ai', content: '', tool_calls: [call] },
        { id: 'result', role: 'tool', name: 'inspect', tool_call_id: 'a', content: '结果' },
    ];
    let projected = projectToolMessages(messages);
    assert.equal(projected.length, 2, 'same name is insufficient for pairing');
    assert.equal(toolStatus(projected[0].tools[0]).settled, false);
    messages[0] = { ...messages[0], tool_calls: [{ ...call, id: 'a', args: '{}' }] };
    projected = projectToolMessages(messages);
    assert.equal(projected.length, 1);
    assert.equal(projected[0].tools[0].key, 0);
    assert.equal(projected[0].tools[0].results[0].content, '结果');
    assert.equal(toolStatus(projected[0].tools[0]).settled, true);
});
