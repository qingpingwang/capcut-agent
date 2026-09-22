import { createParser } from '../../vendor/eventsource-parser/index.js';

export async function readChatStream(response, onEvent) {
    if (!response.body) throw new Error('浏览器未提供响应流。');
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let completed = false;
    const parser = createParser({
        onEvent({ data }) {
            let event;
            try { event = JSON.parse(data); }
            catch { throw new Error('收到无法解析的消息流，请刷新查看已保存的记录。'); }
            if (event.type === 'error') throw new Error(event.error || '执行失败');
            if (event.type === 'done') completed = true;
            onEvent(event);
        },
    });
    try {
        while (!completed) {
            const { done, value } = await reader.read();
            if (done) break;
            parser.feed(decoder.decode(value, { stream: true }));
        }
        parser.feed(decoder.decode());
        if (!completed) throw new Error('连接已中断，已完成的内容会保留，可继续对话。');
    } finally {
        try { await reader.cancel(); } catch { /* 连接可能已经关闭。 */ }
        reader.releaseLock();
    }
}
