"""Deep Agents 会话状态与 OpenAI 兼容模型配置。"""
import os
from typing import NotRequired

from deepagents.graph import DeepAgentState
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()


class State(DeepAgentState):
    # messages、files、todos、摘要和记忆缓存由 Deep Agents 管理。
    resources: NotRequired[list[dict]]


def create_initial_state() -> State:
    return {"messages": [], "resources": []}


def get_model() -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini"),
        temperature=float(os.getenv("TEMPERATURE", "0.7")),
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        streaming=True,
        max_tokens=int(os.getenv("MAX_TOKENS", "16384")),
    )
