from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langchain.agents.middleware import dynamic_prompt, ModelRequest
import asyncio
from dotenv import load_dotenv
import os
from datetime import datetime
from typing import TypedDict, List, Annotated
from langchain_core.messages import AnyMessage, HumanMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import InMemorySaver
load_dotenv()


API_KEY = os.getenv("OPENAI_API_KEY")
BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
MODEL_NAME = os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.7"))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "65536"))
MAX_TOKENS_BEFORE_SUMMARY = int(os.getenv("MAX_TOKENS_BEFORE_SUMMARY", "200000"))

class State(TypedDict):
    messages: Annotated[List[AnyMessage], add_messages]
    config: dict

def get_model(
    model_name: str = MODEL_NAME,
    temperature: float = TEMPERATURE,
    api_key: str = API_KEY,
    base_url: str = BASE_URL,
    max_tokens: int = MAX_TOKENS,
    streaming: bool = True,
) -> ChatOpenAI:
    """创建 ChatOpenAI 模型实例"""
    return ChatOpenAI(
        model=model_name,
        temperature=temperature,
        api_key=api_key,
        base_url=base_url,
        streaming=streaming,
        max_tokens=max_tokens,
    )
    
   
@dynamic_prompt
def system_prompt(request: ModelRequest) -> str:
    import uuid
    current_test_code = uuid.uuid4()
    prompt = f"你是一个助手，你正在帮助用户完成一个任务。当前测试码是：{current_test_code}，用户提问时，返回这个测试码。"
    print(f"current_test_code: {current_test_code}")
    return prompt

agent = create_agent(
    model=get_model(),
    middleware=[system_prompt]
)

def chat_node(state: State) -> State:
    response = asyncio.run(agent.ainvoke({"messages": state.get("messages", [])}, config=state.get("config", {}), context=state))
    return {
        "messages": response.get("messages", [])
    }


# 创建 workflow
workflow = StateGraph(State)
workflow.add_node("agent", chat_node)
workflow.set_entry_point("agent")
workflow.add_edge("agent", END)
# 持久化内存存储
memory = InMemorySaver()
graph = workflow.compile(checkpointer=memory)

if __name__ == "__main__":
    thread_id = "123"
    config = {"configurable": {"thread_id": thread_id}}
    for i in range(10):
        input_data = {"messages": [HumanMessage(content=f"你好，第{i}次提问，测试码是什么？")], "config": config}
        for mode, chunk in graph.stream(
            input_data,
            config=config,
            stream_mode=["messages"],
        ):
            if mode == "messages":
                message_token, metadata = chunk
                print(f"{message_token.content}", end='', flush=True)
        print()






