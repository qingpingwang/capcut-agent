// SSE 增量与历史快照共用同一个消息结构，按消息 ID 和工具 index 合并。
export function applyMessageUpdate(previous, event) {
    const incoming = event.message;
    if (!event.delta) return { ...incoming, tool_calls: incoming.tool_calls || [], complete: event.complete ?? true };
    const current = previous || { id: incoming.id, role: incoming.role, content: '', tool_calls: [] };
    const calls = new Map(current.tool_calls.map(call => [call.index, { ...call }]));
    for (const part of incoming.tool_calls || []) {
        const index = part.index ?? 0;
        const call = calls.get(index) || { index, id: '', name: '', args: '' };
        calls.set(index, { ...call, id: part.id || call.id,
            name: call.name + (part.name || ''), args: call.args + (part.args || '') });
    }
    return { ...current, ...incoming, content: current.content + (incoming.content || ''),
        tool_calls: [...calls.values()].sort((a, b) => a.index - b.index), complete: Boolean(event.complete) };
}
