"""历史与 SSE 共用原生消息的展示结构；正文和工具调用不互相覆盖。"""
import json
from uuid import uuid4

from langchain_core.messages import BaseMessageChunk, HumanMessage, ToolMessage


def message_text(message):
    return message.content if isinstance(message.content, str) else message.text


def serialize_message(message, *, fallback_id=None):
    role = "human" if isinstance(message, HumanMessage) else "tool" if isinstance(message, ToolMessage) else "ai"
    result = {
        "id": message.id or fallback_id or str(uuid4()),
        "role": role,
        "content": message_text(message),
    }
    chunks = getattr(message, "tool_call_chunks", None)
    if chunks:
        result["tool_calls"] = [
            {"index": call.get("index", index), "id": call.get("id"),
             "name": call.get("name"), "args": call.get("args") or ""}
            for index, call in enumerate(chunks)
        ]
    else:
        calls = [*getattr(message, "tool_calls", []), *getattr(message, "invalid_tool_calls", [])]
        if calls:
            result["tool_calls"] = [
                {"index": index, "id": call.get("id"), "name": call.get("name"),
                 "args": call["args"] if isinstance(call.get("args"), str)
                 else json.dumps(call.get("args", {}), ensure_ascii=False),
                 **({"error": call["error"]} if call.get("error") else {})}
                for index, call in enumerate(calls)
            ]
    if role == "tool":
        result.update(tool_call_id=message.tool_call_id, name=message.name,
                      status=getattr(message, "status", "success"))
    return result


class MessageStream:
    def __init__(self):
        self.fallback_ids = {}

    def feed(self, chunk, namespace=()):
        message, metadata = chunk
        # 子 Agent 的结果通过主 Agent 的 task 工具返回；内部 token 不混入聊天。
        if namespace or metadata.get("lc_source") == "summarization" or isinstance(message, HumanMessage):
            return
        key = (metadata.get("langgraph_step"), metadata.get("langgraph_node"),
               getattr(message, "tool_call_id", None))
        fallback_id = self.fallback_ids.setdefault(key, str(uuid4()))
        delta = isinstance(message, BaseMessageChunk)
        yield {
            "type": "message",
            "message": serialize_message(message, fallback_id=fallback_id),
            "delta": delta,
            # 即使结束块没有文字也必须传递，才能收尾未闭合的 Markdown。
            "complete": not delta or getattr(message, "chunk_position", None) == "last",
        }


def accumulate_message(previous, event):
    """为重新订阅保留本次运行的消息快照，而非永久保留每个 token 事件。"""
    incoming = event["message"]
    if not event.get("delta"):
        return {**incoming, "complete": event.get("complete", True)}
    current = previous or {"content": "", "tool_calls": []}
    calls = {call["index"]: dict(call) for call in current.get("tool_calls", [])}
    for part in incoming.get("tool_calls", []):
        index = part.get("index") or 0
        call = calls.get(index, {"index": index, "id": "", "name": "", "args": ""})
        calls[index] = {**call, "id": part.get("id") or call["id"],
                        "name": call["name"] + (part.get("name") or ""),
                        "args": call["args"] + (part.get("args") or "")}
    return {**current, **incoming, "content": current["content"] + incoming.get("content", ""),
            "tool_calls": [calls[key] for key in sorted(calls)], "complete": event.get("complete", False)}
