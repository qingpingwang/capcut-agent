"""组装剪辑 Deep Agent：规划、工作文件、子 Agent、压缩、审批、记忆和 Skills。"""
import json
import os
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend, StateBackend, StoreBackend
from deepagents.middleware.memory import MemoryMiddleware
from deepagents.middleware.filesystem import FilesystemPermission
from deepagents.middleware.summarization import SummarizationMiddleware, create_summarization_middleware
from langchain.agents.middleware import AgentMiddleware, TodoListMiddleware
from langchain_core.messages import SystemMessage

from .models import State, get_model
from .prompts import BASE_SYSTEM_PROMPT, SYSTEM_SUMMARY_PROMPT
from ..utils.mcp_loader import load_mcp_tools

SKILLS_DIR = Path(__file__).resolve().parents[2] / "agent_skills"
MEMORY_NAMESPACE = ("capcut", "local-user", "memories")
MEMORY_PATH = "/AGENTS.md"
APPROVAL_TOOLS = {"delete_project", "delete_track", "delete_segment", "copy_project_to_jianying"}
READ_TOOLS = {"get_project_info", "get_tracks", "get_track_info",
              "list_jianying_resource_categories", "search_jianying_resources"}
SUBAGENTS = [
    ("general-purpose", "剪辑规划", "分析剪辑需求、分镜、时间线和执行步骤，输出可执行方案。"),
    ("resource-analyst", "资源分析", "根据当前素材元信息和资源目录分析素材搭配、转场和音效选择。"),
    ("project-reviewer", "工程检查", "读取工程、轨道和片段，核对时间线、分辨率、素材及交付要求。"),
]

DEEP_AGENT_PROMPT = """
## 工作方式
- 复杂剪辑使用 write_todos 规划和更新进度；简单问答直接回答。
- 需要领域知识时读取 /skills/ 中对应的 SKILL.md，并遵循其中的剪辑规则。
- 可委派规划、资源分析、工程检查给专用子 Agent。它们只查询和提出建议；
  主 Agent 负责执行剪辑工具。同一工程的修改按依赖顺序串行执行。
- 在会话工作文件中保存分镜、剪辑计划、工程 ID、操作记录；这些文件随当前会话保存。
- /memories/AGENTS.md 保存跨会话的稳定偏好和可复用经验。根据用户表达、反馈和纠正，
  自行判断是否值得长期保留，并使用 read_file、edit_file 或 write_file 更新；无需用户明确说“记住”。
  更新前读取现有内容，合并重复信息、替换过时偏好；用户要求忘记时删除对应记录。
  不记录一次性需求、临时工程 ID、素材路径、完整渲染 JSON 或未经证实的推测。
- 素材以“当前可用素材”为准，文件工具的虚拟工作区不是上传素材所在的真实文件系统。
- 关键工具可能暂停等待用户审批，收到拒绝后调整方案，不绕过审批。
- 交付物是剪映草稿工程；只有实际完成视频渲染才可以声称已导出 MP4。
"""


class ResourceContextMiddleware(AgentMiddleware):
    """追加实时素材信息，保留 Deep Agents 注入的工具、Skills 和记忆提示。"""

    def _request(self, request):
        resources = request.state.get("resources", [])
        context = "\n\n## 当前可用素材\n" + json.dumps(resources, ensure_ascii=False)
        if not resources:
            context += "\n当前会话没有上传素材；需要媒体素材的操作应先请用户上传。"
        content = request.system_message.content if request.system_message else ""
        if isinstance(content, str):
            content += context
        else:
            content = [*content, {"type": "text", "text": context}]
        return request.override(system_message=SystemMessage(content=content))

    def wrap_model_call(self, request, handler):
        return handler(self._request(request))

    async def awrap_model_call(self, request, handler):
        return await handler(self._request(request))


class FreshMemoryMiddleware(MemoryMiddleware):
    """每轮重新读取共享记忆，使模型在其他会话中的更新立即生效。"""

    def before_agent(self, state, runtime, config):
        return super().before_agent({k: v for k, v in state.items() if k != "memory_contents"}, runtime, config)

    async def abefore_agent(self, state, runtime, config):
        return await super().abefore_agent({k: v for k, v in state.items() if k != "memory_contents"}, runtime, config)


async def create_jianying_agent(checkpointer, store, *, model=None, tools=None,
                               summary_trigger=None, summary_keep=("messages", 20)):
    model = model if model is not None else get_model()
    tools = await load_mcp_tools() if tools is None else tools
    backend = CompositeBackend(
        default=StateBackend(),
        routes={
            "/memories/": StoreBackend(store=store, namespace=lambda _: MEMORY_NAMESPACE),
            "/skills/": FilesystemBackend(root_dir=SKILLS_DIR, virtual_mode=True),
        },
    )
    threshold = os.getenv("MAX_TOKENS_BEFORE_SUMMARY", "").strip()
    if summary_trigger is None and threshold:
        summary_trigger = ("tokens", int(threshold))
    if summary_trigger is None:
        summary = create_summarization_middleware(model, backend, summary_prompt=SYSTEM_SUMMARY_PROMPT)
    else:
        summary = SummarizationMiddleware(
            model=model, backend=backend, trigger=summary_trigger, keep=summary_keep,
            summary_prompt=SYSTEM_SUMMARY_PROMPT, trim_tokens_to_summarize=None,
        )
    permissions = [FilesystemPermission(operations=["write"], paths=["/skills/**"], mode="deny")]
    subagents = [
        {
            "name": name,
            "description": description,
            "system_prompt": BASE_SYSTEM_PROMPT + "\n" + description +
                "\n只做分析和查询，不执行工程修改。不要把素材元信息当作已经看过视频画面。",
            "tools": [tool for tool in tools if tool.name in READ_TOOLS],
            "middleware": [ResourceContextMiddleware(),
                           FreshMemoryMiddleware(backend=backend, sources=["/memories/AGENTS.md"])],
            "skills": ["/skills/"],
            "permissions": [
                FilesystemPermission(operations=["write"], paths=["/skills/**", "/memories/**"], mode="deny"),
            ],
        }
        for name, _, description in SUBAGENTS
    ]
    return create_deep_agent(
        model=model, tools=tools, system_prompt=BASE_SYSTEM_PROMPT + DEEP_AGENT_PROMPT,
        state_schema=State, backend=backend, store=store, checkpointer=checkpointer,
        skills=["/skills/"], permissions=permissions, subagents=subagents,
        middleware=[
            TodoListMiddleware(), ResourceContextMiddleware(), summary,
            FreshMemoryMiddleware(backend=backend, sources=["/memories/AGENTS.md"]),
        ],
        interrupt_on={
            tool.name: {"allowed_decisions": ["approve", "edit", "reject"]}
            for tool in tools if tool.name in APPROVAL_TOOLS
        },
        name="capcut-deep-agent",
    )
