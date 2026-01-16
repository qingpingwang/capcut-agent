"""
LangGraph workflow - 单 agent 处理视频剪辑请求
"""
from langgraph.graph import StateGraph, END
from .models import *
from langchain_core.messages import AIMessage
from ..utils.mcp_loader import load_mcp_tools
from langchain.agents.middleware import TodoListMiddleware
import asyncio



jianying_agent = create_summarized_agent(
    model=get_model(),
    tools=asyncio.run(load_mcp_tools()),
    summary_prompt=SYSTEM_SUMMARY_PROMPT,
    middleware=[TodoListMiddleware()]
)

def agent_node(state: State) -> State:
    try:
        new_ai_messages, result_llm_context, _ = invoke_agent_with_context(state, jianying_agent, is_async=True)
        return {
            "messages": new_ai_messages,  # 添加到前端消息
            "llm_context": result_llm_context  # 更新 LLM 上下文
        }
    except Exception as e:
        message = AIMessage(content=f"发生错误: {e}")
        last_messages = state.get("messages", [])[-1]
        return {
            "messages": [message],
            "llm_context": [last_messages, message]
        }   


# 创建 workflow
workflow = StateGraph(State)
# 添加节点
workflow.add_node("agent", agent_node)
# 设置入口
workflow.set_entry_point("agent")
# 设置边（简单流程：agent -> END）
workflow.add_edge("agent", END)

