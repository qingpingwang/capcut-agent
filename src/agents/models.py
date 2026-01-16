"""
State 模型定义 - 参考 langgraph-test/src/agents/models.py
保持聊天上下文（messages）和模型上下文（llm_context）分离
"""
from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages, REMOVE_ALL_MESSAGES
from langchain_core.messages import AnyMessage, RemoveMessage
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware, dynamic_prompt, ModelRequest
from pydantic import BaseModel
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from pydantic import Field
from typing import Literal, List, Tuple, Any
import asyncio
import json

# 将项目根目录添加到 Python 搜索路径（确保能导入 rag 模块）
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rag import get_jianying_res_info
load_dotenv()


class ResourceInfo(BaseModel):
    """素材相关信息，有基本信息、描述、关键词"""
    resource_id: str = Field(..., description="素材ID")
    resource_type: Literal["image", "video", "audio"] = Field(..., description="素材类型")
    resource_path: str = Field(..., description="素材路径")
    resource_name: str = Field(..., description="素材名称")
    resource_duration: int = Field(..., description="素材时长，单位：ms")
    resource_resolution: str = Field(..., description="素材分辨率，如：1920x1080, 1080x1920, 1080x1080")
    file_md5: str = Field(..., description="文件MD5")
    file_size: int = Field(..., description="文件大小，单位：字节")
    resource_description: str = Field(..., description="素材描述")


class State(TypedDict):
    """Graph state - 完整的工作流状态"""
    # 用户可见的对话历史（前端展示）
    messages: Annotated[list[AnyMessage], add_messages]
    # LLM 工作上下文（可能包含摘要压缩，实际传给模型）
    llm_context: Annotated[list[AnyMessage], add_messages]
    # 对话配置
    config: dict
    resources: List[ResourceInfo]


def create_initial_state() -> State:
    """
    创建 State 的初始值
    
    用于初始化新会话或需要重置状态的场景。
    确保所有字段都有正确的默认值。
    
    Returns:
        State: 初始化的状态字典
    """
    return {
        "messages": [],
        "llm_context": [],
        "config": {},
    }


# LLM 配置
API_KEY = os.getenv("OPENAI_API_KEY")
BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
MODEL_NAME = os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.7"))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "65536"))
MAX_TOKENS_BEFORE_SUMMARY = int(os.getenv("MAX_TOKENS_BEFORE_SUMMARY", "200000"))

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
    
def get_jianying_res_prompt():
    """
    生成剪映可用资源的 Prompt
    按分类（文字动画、画面动画、贴片、特效、转场、滤镜、音效）整理，仅包含名称和描述
    """
    result = get_jianying_res_info()
    
    prompt = "# 剪映可用资源列表\n\n"
    prompt += "以下是剪映中可以使用的内置资源，按分类整理。\n\n"
    
    prompt += "**重要说明 - 资源使用方式**：\n\n"
    
    prompt += "**1️⃣ 附加到片段的资源**（无需创建轨道）：\n"
    prompt += "- **转场**：片段之间的过渡效果，使用 `add_material_to_segment`\n"
    prompt += "- **文字动画**：文本片段的动画效果，使用 `add_material_to_segment`\n"
    prompt += "- **画面动画**：视频/图片片段的动画效果，使用 `add_material_to_segment`\n"
    prompt += "- 这些资源直接附加在现有片段上，**不需要创建独立轨道**\n\n"
    
    prompt += "**2️⃣ 添加到轨道的资源**（需先创建对应轨道）：\n"
    prompt += "- **特效**（effect）：视频特效（如放大镜、马赛克），使用 `add_effect_to_track`\n"
    prompt += "  - 需要先创建 `effect` 类型轨道\n"
    prompt += "- **滤镜**（filter）：画面滤镜（如高清增强、美肤），使用 `add_filter_to_track`\n"
    prompt += "  - 需要先创建 `filter` 类型轨道\n"
    prompt += "- **音效**（audio）：背景音效或音乐，使用 `add_audio_effect_to_track`\n"
    prompt += "  - 需要先创建 `audio` 类型轨道\n"
    prompt += "- ⚠️ **重要**：同类型轨道可以复用，**不是每个素材都要创建新轨道**\n"
    prompt += "  - 例如：创建一个 `effect` 轨道后，可以在这个轨道上添加多个特效片段\n"
    prompt += "  - 使用 `get_tracks` 查看已有轨道，优先复用现有轨道\n\n"
    
    prompt += "**3️⃣ 灵活使用的资源**：\n"
    prompt += "- **滤镜、特效** 既可以添加到轨道（全局效果），也可以附加到片段（局部效果）\n"
    prompt += "- 如无特别说明，**默认添加到轨道上**（更常用）\n\n"
    
    prompt += "**工具调用参数说明**：\n"
    prompt += "- **`category`**：取值为下方 **二级标题**（## 开头），如 \"转场\"、\"特效\"、\"滤镜\"、\"文字动画\"、\"画面动画\"、\"贴片\"、\"音效\"\n"
    prompt += "- **`name`**：取值为该分类下的 **资源名称**（列表项中加粗的部分），如 \"推近 II\"、\"放大镜\"\n\n"
    
    prompt += "**展示格式说明**：\n"
    prompt += "- 当向用户展示这些资源时，请使用 Markdown 表格格式\n"
    prompt += "- 表格应包含两列：「分类」和「名称」\n"
    prompt += "- **名称在前，分类在后**（或按需调整列顺序）\n"
    prompt += "- 示例格式：\n"
    prompt += "  ```markdown\n"
    prompt += "  | 名称 | 分类 |\n"
    prompt += "  |------|------|\n"
    prompt += "  | 向左模糊 II | 出场 |\n"
    prompt += "  | 金粉飘落 | 入场 |\n"
    prompt += "  ```\n\n"
    
    for category, items in result.items():
        prompt += f"## {category}\n\n"
        
        for name, info in items.items():
            # 只保留名称和描述，去掉 content 和 url
            prompt += f"- **{name}**：{info['desc']}\n"
        
        prompt += "\n"
    
    return prompt


# 基础系统提示词
BASE_SYSTEM_PROMPT = """# 视频剪辑助手

你是一个专业的视频剪辑助手，可以帮助用户使用剪映完成视频制作任务。

## 核心能力

1. 理解视频制作需求
2. 调用剪映工具完成视频剪辑
3. 管理素材和项目
4. 使用剪映内置资源（转场、特效、滤镜等）

## 回复格式规范

**所有回复必须使用 Markdown 格式**，以增强可读性：

- 使用 **粗体** 强调重要信息
- 使用列表组织步骤或要点
- 使用行内代码（反引号）标识专门的标识符：
  - 素材 ID：`73ea38f8-4ed4-4037-bd03-2318526c460b`
  - 文件名：`video.mp4`
  - 函数名：`create_video()`
- 使用代码块展示配置或数据结构
- 简洁专业，仅回答问题，不做引导性结束语

## 视频分辨率与画布参数转换

当用户提到分辨率描述（如"1k"、"2k"、"4k"）或方向描述（如"竖屏"、"横屏"）时，需要转换为具体的 `width` 和 `height` 参数来创建项目。

### 常见分辨率对照表

**横屏（Landscape）- 宽 > 高**：
- **1080P / Full HD**：`1920 x 1080`（标准横屏视频）
- **2K**：`2560 x 1440`（2K 横屏）
- **4K / UHD**：`3840 x 2160`（4K 超清横屏）
- **720P / HD**：`1280 x 720`（高清横屏）

**竖屏（Portrait）- 高 > 宽**：
- **抖音/快手/小红书 标准竖屏**：`1080 x 1920`（9:16 竖屏，最常用）
- **Instagram Story / Reels**：`1080 x 1920`（9:16 竖屏）
- **720P 竖屏**：`720 x 1280`（节省存储）
- **2K 竖屏**：`1440 x 2560`（高清竖屏）
- **4K 竖屏**：`2160 x 3840`（超清竖屏）

**方形（Square）- 宽 = 高**：
- **Instagram Post**：`1080 x 1080`（1:1 方形）
- **微信朋友圈封面**：`1080 x 1080`

### 转换规则

1. **明确指定分辨率**：`1080P 横屏` → `width=1920, height=1080`
2. **仅指定方向**：`竖屏` → 默认 `1080 x 1920`
3. **仅指定分辨率**：`4K` → 默认横屏 `3840 x 2160`
4. **平台名称**：`抖音视频` → `1080 x 1920`（竖屏）
5. **不明确时询问**：主动询问确认

## 素材使用指南

### 🚫 重要约束：仅询问时不操作

**当用户仅询问素材信息时（如"有哪些素材"、"查看素材列表"）**：
- ❌ **禁止**创建新工程或调用任何工具
- ✅ **仅回答**素材库中的素材信息即可
- ❌ **禁止**添加引导性提示（如"需要我帮你添加吗？"）
- ✅ **等待**用户明确要求操作时再执行

**操作信号识别**：
- 询问："当前有哪些素材？" → 仅回答，不操作
- 操作："添加素材到工程" → 执行操作
- 操作："使用这个素材创建视频" → 执行操作

### 📚 素材库 vs 工程素材

**核心概念区分**：
- **素材库（Media Library）**：系统中所有已上传的素材文件，可被多个工程复用。系统提示词中的素材列表展示的就是素材库内容。
- **工程素材（Project Resources）**：当前剪映工程中实际使用的素材，需通过工具函数查询轨道和片段信息。

**默认行为规则**：
- ⚙️ **默认询问的是素材库**：用户问"有哪些素材"时，指的是素材库
- 🎯 **特殊情况才是工程素材**：只有明确提到"工程"、"工程ID"、"项目"、"draft"时，才是询问工程素材

**用户询问时的判断规则**：

| 用户表述 | 含义 | 回答方式 |
|---------|------|---------|
| "当前有哪些素材？" | 素材库 | 列出系统提示词中的素材列表 |
| "查看素材列表" | 素材库 | 按类型分类展示（视频/图片/音频） |
| "我上传了哪些素材？" | 素材库 | 展示所有可用素材的 ID 和文件名 |
| "这个视频用了哪些素材？" | 工程素材 | 调用工具查询轨道和片段 |
| "工程里有哪些片段？" | 工程素材 | 调用工具查询轨道和片段 |

### ⚠️ 素材状态管理

**关于已删除的素材**：
- 消息历史中提到但当前素材列表中不存在的素材 → 已被删除
- 已创建的片段不受影响，但不能基于该素材进行新增量操作
- 提示用户：**您之前提到的素材 `[素材名称/ID]` 已被删除，无法继续使用。如需类似素材，请重新上传。**

### 方式 1: 通过标识符引用素材（智能匹配）

用户可能会提供一个标识符来引用素材，例如：
- "添加 `73ea38f8-4ed4-4037-bd03-2318526c460b`"
- "使用 `abc123` 的视频"
- "添加 `封面图.jpg`"

**智能匹配策略**（按优先级顺序尝试）：

1. **首先尝试 `resource_id` 匹配**（完全匹配或前缀匹配）
   - 完整 ID：`73ea38f8-4ed4-4037-bd03-2318526c460b`
   - 短 ID：`73ea38f8`（匹配前缀）

2. **如果找不到，尝试 `resource_name` 匹配**（包含匹配或完全匹配）
   - 完整文件名：`封面图.jpg`
   - 部分文件名：`封面` → 匹配 `封面图.jpg`

3. **如果还找不到，尝试 `resource_description` 匹配**（模糊匹配）
   - 描述关键词：`开场` → 匹配描述中包含 "开场" 的素材

**匹配规则**：
- 如果只匹配到 1 个素材 → 直接使用
- 如果匹配到多个素材 → 列出所有匹配项，询问用户选择
- 如果没有匹配到任何素材 → 提示用户素材不存在，列出可用素材

### 方式 2: 通过条件筛选素材

用户可能会描述筛选条件，例如：
- "添加所有 10 秒以下的视频"
- "使用所有竖屏视频"
- "把所有图片素材都加进来"

此时需要根据素材信息筛选，可用的筛选字段：
- `resource_type`: 素材类型（video/audio/image）
- `resource_duration`: 素材时长（毫秒）
- `resource_resolution`: 分辨率（如 "1920x1080"、"1080x1920"）
- `resource_size`: 文件大小（字节）
- `resource_name`: 文件名

**筛选示例**：
- "10 秒以下" → 筛选 `resource_duration < 10000`
- "竖屏视频" → 筛选 `resource_type == 'video'` 且分辨率高度 > 宽度
- "所有图片" → 筛选 `resource_type == 'image'`

### 方式 3: 使用素材路径

创建片段时，使用 `resource_url` 作为媒体文件路径传给工具函数。

### 💡 匹配流程示例

**完整 ID** → 直接匹配 `resource_id`
**短 ID**（如 `73ea38f8`）→ 前缀匹配 `resource_id`
**文件名**（如 `封面图`）→ 包含匹配 `resource_name`
**描述关键词**（如 `开场`）→ 模糊匹配 `resource_description`

**匹配结果处理**：
- 唯一匹配 → 直接使用
- 多个匹配 → 列出所有选项，询问用户选择
- 无匹配 → 提示 "未找到素材 `xxx`，当前可用素材：..."

**单位说明**：
- `resource_duration`：毫秒（1秒 = 1000 毫秒）
- `resource_size`：字节（1MB = 1048576 字节）

## 剪辑知识

### 转场使用规则

#### ⚠️ 转场添加约束

**核心规则**：
1. **转场只能在同一轨道的两个相邻片段之间添加**
   - 转场必须应用于同一轨道上的连续片段
   - 不能跨轨道添加转场
   - 不能为非相邻片段添加转场

2. **只需为前一个片段添加转场资源**
   - 两个素材之间添加转场时，**只需要为前一个片段添加转场资源**
   - **不需要为后一个片段也添加转场**
   - 剪映会自动识别后一个片段并完成转场连接

3. **转场工作原理**
   - 转场效果会作用于两个片段之间的过渡区域
   - 前一个片段的结束部分和后一个片段的开始部分会参与转场效果
   - 转场时长由转场资源本身决定

**操作示例**：
- ✅ 正确：片段 A 和片段 B 在同一轨道相邻 → 为片段 A 添加转场资源
- ❌ 错误：为片段 A 和片段 B 都添加转场资源（重复操作）
- ❌ 错误：片段 A 和片段 B 不在同一轨道 → 无法添加转场
- ❌ 错误：片段 A 和片段 B 不相邻（中间有其他片段）→ 无法添加转场

## 回答原则

1. **基于实际情况**：只使用系统提示词中明确提供的素材和资源，禁止虚构
2. **简洁专业**：直接回答问题，不添加引导性结束语
3. **等待指令**：回答后等待用户下一步指令，不要过度引导
""" + "\n\n---\n\n" + get_jianying_res_prompt()

# 对话摘要提示词（用于压缩历史对话）
SYSTEM_SUMMARY_PROMPT = """请总结对话历史，重点保留视频剪辑流程中的关键信息：

## 必须保留的信息

### 1. 素材信息（Resources）
- 项目中的素材列表（ID、名称、类型）
- 每个素材的关键属性（时长、分辨率、大小）
- 素材的用途和使用场景
- 素材之间的关系（如：视频+音频）

### 2. 剪辑需求（Requirements）
- 用户的核心剪辑目标
- 视频参数要求（时长、分辨率、格式）
- 风格和效果要求（转场、滤镜、特效）
- 文字和音频需求（字幕、配音、背景音乐）
- 输出和交付要求

### 3. 操作记录（Actions）
- 已执行的剪辑操作
- 素材上传/删除记录
- 操作的具体参数
- 遇到的问题和解决方案

### 4. 待办任务（Todo）
- 尚未完成的任务列表
- 用户明确要求但未完成的操作
- 需要进一步确认的细节

### 5. 工具调用结果（如果有）
- 剪映 API 调用的结果
- 查询素材信息的数据
- 这些信息对后续决策很重要

## 可以简化的内容
- 闲聊和客套话
- 重复的确认信息（保留最新的即可）
- 不影响剪辑任务的无关内容
- 过程性的调试信息

## 输出格式要求
1. **结构清晰**：按素材、需求、操作、待办等维度组织
2. **保留数字**：素材ID、时长、分辨率等关键数字不能丢失
3. **保留状态**：当前进度、各素材使用情况要明确
4. **简洁准确**：用简洁语言概括，但不能丢失关键细节

## 示例输出
```
【素材】项目有3个素材：
- video1.mp4 (ID: abc123): 10秒横屏视频，1920x1080，10MB
- audio1.mp3 (ID: def456): 30秒背景音乐
- image1.jpg (ID: ghi789): 封面图，1920x1080

【需求】用户要制作15秒短视频，使用video1前10秒+audio1做背景音乐，需要添加字幕和转场效果，最终导出1080p MP4格式

【操作】已上传3个素材，确认了视频时长和音频搭配

【待办】添加字幕、应用转场效果、混音处理、导出视频

【偏好】用户偏好简洁转场，字幕使用白色黑体
```

以下是历史消息：
{messages}"""

@dynamic_prompt
def dynamic_system_prompt(request: ModelRequest) -> str:
    # 1. 基础系统提示词
    prompt = BASE_SYSTEM_PROMPT
    
    resources = request.runtime.context.get("resources", [])
    # 2. 拼接剪映资源列表（转场、特效、滤镜等）
    if resources and len(resources) > 0:
        prompt += "\n\n## 当前可用素材\n\n"
        prompt += f"媒体库中共有 **{len(resources)} 个素材**，完整信息如下：\n\n"
        
        # 转换为可序列化的格式
        resources_data = []
        for res in resources:
            if isinstance(res, dict):
                resources_data.append(res)
            elif hasattr(res, 'model_dump'):
                resources_data.append(res.model_dump())
            elif hasattr(res, '__dict__'):
                resources_data.append(res.__dict__)
        
        # 以 JSON 格式展示
        prompt += "```json\n"
        prompt += json.dumps(resources_data, ensure_ascii=False, indent=2)
        prompt += "\n```\n"
    else:
        prompt += "\n\n## 当前可用素材\n\n"
        prompt += "⚠️ **媒体库中还没有素材，请提醒用户先上传素材。**\n"
    
    return prompt
    
def create_summarized_agent(
    model=None,
    tools: List = None,
    summary_prompt: str = None,
    max_tokens_before_summary: int = MAX_TOKENS_BEFORE_SUMMARY,
    messages_to_keep: int = 20,
    response_format: BaseModel = None,
    middleware: List = None,
    context_schema: BaseModel = None,
):
    if model is None:
        model = get_model()
    
    if tools is None:
        tools = []
    
    
    # 根据是否提供 summary_prompt 决定是否启用摘要
    user_middleware = [dynamic_system_prompt]
    if middleware is not None:
        user_middleware.extend(middleware)
    if summary_prompt is not None:
        user_middleware.append(
            SummarizationMiddleware(
                model=model,
                max_tokens_before_summary=max_tokens_before_summary,
                messages_to_keep=messages_to_keep,
                summary_prompt=summary_prompt,
            )
        )
    
    # 创建 agent
    agent = create_agent(
        model=model,
        tools=tools,
        middleware=user_middleware,
        response_format=response_format,
        context_schema=context_schema,
    )
    
    return agent

def invoke_agent_with_context(
    state: State, 
    agent, 
    is_async: bool = False, 
) -> Tuple[List[AnyMessage], List, dict]:
    """
    标准的 agent 调用模式：同步用户消息 → 调用 agent → 更新 llm_context
    
    Args:
        state: 当前 Graph State
        agent: 要调用的 agent 实例
        is_async: 是否异步调用，默认同步
    
    Returns:
        (new_ai_messages, result_llm_context): 
        - new_ai_messages: 新增的 AI 消息（用于更新前端 messages）
        - result_llm_context: 更新后的 llm_context（包含 RemoveMessage 标记）
    
    使用示例：
        def my_agent_node(state: State):
            # 调用 agent 并获取更新后的上下文
            new_ai_messages, result_llm_context = invoke_agent_with_context(state, my_agent)
            
            # 返回更新
            return {
                "messages": new_ai_messages,
                "llm_context": result_llm_context,
                # ... 其他状态更新
            }
    """
    # 1. 获取当前上下文
    messages = state["messages"]
    llm_context = state.get("llm_context", [])
    
    # 2. 同步最新的用户消息到 llm_context
    current_llm_context = (llm_context + [messages[-1]]) if messages else llm_context
    
    # 3. 调用 agent（会自动处理摘要）
    if is_async:
        response = asyncio.run(agent.ainvoke({"messages": current_llm_context}, config=state.get("config", {}), context=state))
    else:
        response = agent.invoke({"messages": current_llm_context}, config=state.get("config", {}), context=state)
    new_llm_context = response["messages"]
    
    # 4. 找出新增的 AI/Tool 消息（用于更新前端）
    old_ids = {m.id for m in current_llm_context}
    new_ai_messages = [m for m in new_llm_context if m.type in ("ai", "tool") and m.id not in old_ids]
    
    # 5. 使用 __remove_all__ 清空所有旧消息，然后添加新消息
    # 这样确保摘要永远在第一位，不会因为 add_messages 保持原有位置而错位
    result_llm_context = [RemoveMessage(id=REMOVE_ALL_MESSAGES)]
    result_llm_context.extend(new_llm_context)
    
    # 新增回复、全量更新 llm_context、当前回答
    return new_ai_messages, result_llm_context, response

