// 仅派生展示结构，不修改原生 messages。工具结果按 call ID 回填声明的位置，
// 并行工具仍按声明顺序排列；找不到声明的结果单独保留，避免历史记录被吞掉。
export function projectToolMessages(messages) {
    const declarations = new Set(messages.flatMap(message =>
        (message.tool_calls || []).map(call => call.id).filter(Boolean)));
    const results = new Map();
    for (const message of messages) {
        if (message.role !== 'tool' || !declarations.has(message.tool_call_id)) continue;
        const group = results.get(message.tool_call_id) || [];
        group.push(message);
        results.set(message.tool_call_id, group);
    }
    return messages.flatMap(message => {
        if (message.role === 'tool') {
            if (declarations.has(message.tool_call_id)) return [];
            return [{ ...message, tools: [{ key: message.id, results: [message] }] }];
        }
        if (!message.tool_calls?.length) return [message];
        return [{ ...message, tools: message.tool_calls.map((call, index) => ({
            key: call.index ?? index, call, results: results.get(call.id) || [],
        })) }];
    });
}

export function toolStatus(tool) {
    if (tool.call?.error) return { label: '参数错误', error: true, settled: true };
    if (tool.results.some(result => result.status === 'error')) {
        return { label: '执行失败', error: true, settled: true };
    }
    if (tool.results.length) return { label: '已完成', error: false, settled: true };
    return { label: '等待结果', error: false, settled: false };
}
