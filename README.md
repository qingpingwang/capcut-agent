# CapCut Agent — AI 视频剪辑助手

基于 Deep Agents、LangGraph 和 Flask 的本地视频剪辑助手。通过对话管理素材、规划剪辑、调用剪映 MCP 工具生成草稿，并同步到 macOS 剪映工作目录。视频渲染和导出在剪映客户端完成。

## 功能

- **Deep Agents**：任务规划、虚拟文件系统、子 Agent、上下文摘要、人工审批、长期记忆和 Skills。
- **流式聊天**：增量 Markdown；每个工具一张默认折叠的卡片，合并展示调用参数与结果。
- **后台会话**：切换时保留正在执行的页面和 SSE，切回继续看到流式消息；后台结束后释放隐藏页面。
- **状态提醒**：执行中显示呼吸点，后台结束后常亮，打开会话后清除；相对时间每分钟更新。
- **自适应布局**：消息区随面板宽度伸缩，气泡最大占内容区 80%；输入框宽度最多 804px，分割条可调整高度。
- **素材与草稿**：上传、预览、检索媒体素材，操作工程、轨道、片段、字幕和效果，审批后同步草稿。

## 快速开始

需要 Python 3.12+、Git，以及用于读取媒体时长和分辨率的 `ffprobe`（随 FFmpeg 安装）。草稿同步路径目前适配 macOS 剪映专业版。

### 1. 获取代码及子模块

```bash
git clone --recurse-submodules https://github.com/qingpingwang/capcut-agent.git
cd capcut-agent
```

已克隆的仓库可运行 `./init.sh` 初始化子模块。MCP 工具直接加载 `external/jianying-protocol-service/src`，不需要另外启动该子模块的 HTTP 服务。

### 2. 安装依赖

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt

# macOS 缺少 ffprobe 时安装 FFmpeg
brew install ffmpeg
```

前端无需构建步骤。`streaming-markdown 0.2.15` 和 `eventsource-parser 4.1.1` 随仓库提供，许可证见 [static/vendor](static/vendor/README.md)。Tailwind 和字体仍通过页面中的 CDN 加载。

### 3. 配置环境变量

```bash
cp .env.example .env
```

填写 `.env` 中的模型配置。模型需要支持工具调用，服务商 API 需要兼容 `ChatOpenAI`。

| 变量 | 用途 / 默认值 |
| --- | --- |
| `OPENAI_API_KEY` | 模型服务密钥，必填 |
| `OPENAI_BASE_URL` | API 地址，默认 `https://api.openai.com/v1` |
| `OPENAI_MODEL_NAME` | 模型名称，默认 `gpt-4o-mini` |
| `TEMPERATURE` | 默认 `0.7`，需与所用模型支持的参数一致 |
| `MAX_TOKENS` | 单次输出上限，默认 `16384`，需与模型限制一致 |
| `MAX_TOKENS_BEFORE_SUMMARY` | 可选摘要阈值；不设置时由 Deep Agents 根据模型信息选取 |
| `CAPCUT_DATA_DIR` | 状态、记忆、上传素材及剪映工程的存储根目录，默认项目下的 `data/` |
| `OSS_AK`、`OSS_SK`、`PROJECT_REMOTE_PATH` | 第三方剪映协议服务的 OSS / 项目资源配置，按实际资源服务填写 |

从旧版本更新时，检查已有 `.env` 中的输出上限和摘要阈值；旧配置不会被 `.env.example` 自动覆盖。明确指定的摘要阈值应低于模型上下文上限。

### 4. 启动与停止

```bash
./start.sh
# 浏览器打开 http://localhost:5001

./stop.sh
```

也可以在前台运行 `.venv/bin/python server.py`，按 Ctrl+C 停止。`start.sh` 优先使用 `.venv/bin/python`，日志写入项目的 `data/log.log`，进程 ID 写入 `server.pid`；这两个脚本从项目目录执行。

## 使用方式

1. 点击首页“新建剪辑项目”或侧栏“新建”。
2. 通过右侧“添加素材”上传视频、图片或音频，输入剪辑需求。
3. Agent 按需读取剪辑 Skill、查询可用效果、规划任务并调用工具。工具卡片默认折叠，可展开查看参数和结果。
4. 删除工程、轨道、片段或同步到剪映前，界面显示审批卡片，可批准、修改参数或拒绝。
5. 同步成功后在剪映客户端打开草稿，检查效果并导出视频。

记忆和 Skills 不单独占用界面。模型根据稳定偏好、反馈和纠正，自行决定是否通过文件工具更新长期记忆；也可以直接要求它更新或忘记某个偏好。

### 聊天布局与滚动

消息区使用面板实际宽度，左右留白随宽度变化。输入框保持独立的最大宽度，顶部水平分割条控制输入区高度：

- 默认 **156px**，最小 **112px**，最大取面板高度的一半且不超过 **480px**；出现审批面板时还会为消息列表保留空间。
- 高度保存在当前浏览器，切换会话或刷新后恢复；窗口变小时自动限制高度。
- 双击分割条或按 Enter 恢复默认；方向键微调，Home / End 调到最小 / 最大。
- 长输入在框内滚动；Enter 发送，Shift+Enter 换行，Shift+方向键上下切换历史输入。

聊天默认跟随最新消息。向上滚动或展开工具详情时暂停跟随；点击“回到最新”以约 240ms 的动画滑到底部，上滚可以打断动画。

### 会话切换与恢复

站内切换使用 History API。执行中的会话保留原页面、消息视图及 SSE，仅隐藏页面；后台持续接收并渲染消息，切回恢复阅读位置。后台执行结束后释放隐藏页面；当前会话完成后保留页面。

执行中显示呼吸点；后台结束后显示常亮提醒，打开对应会话后清除。结束状态包含完成、失败和等待审批。已读确认绑定本轮 `run_id`，不会清除另一轮新结果的提醒。

SSE 订阅与服务端任务分离，浏览器意外断开不会取消任务。刷新页面后自动重新订阅正在运行的会话，先恢复当前轮快照，再继续接收增量消息。网络异常中断时可刷新恢复连接。

当前运行时为**单进程**，同一会话不能并发执行；服务进程重启会中断正在执行的任务，不会自动重放工具操作。已持久化的消息和审批状态保留，待审批任务可在重启后继续。此应用目前使用本地单用户记忆命名空间，不提供多用户身份隔离。

## Deep Agents 架构

当前固定 `deepagents==0.7.17`，LangGraph 和 SQLite Checkpointer 的版本范围见 [requirements.txt](requirements.txt)。

| 能力 | 接入方式 |
| --- | --- |
| 任务规划 | `TodoListMiddleware` / `write_todos` |
| 虚拟文件系统 | `CompositeBackend`：默认 `StateBackend` 保存会话工作文件和卸载的长工具结果 |
| 子 Agent | 剪辑规划、资源分析、工程检查三个独立上下文子 Agent，只读查询并返回建议；主 Agent 顺序修改工程 |
| 上下文压缩 | Deep Agents 原生摘要及历史卸载 |
| 人工审批 | `interrupt_on` 暂停关键工具；持久化 interrupt，使用 `Command(resume=...)` 继续 |
| 长期记忆 | 模型使用 `read_file` / `edit_file` / `write_file` 管理 `/memories/AGENTS.md`；`StoreBackend` + SQLite 跨会话保存 |
| Skills | `/skills/capcut-editing/SKILL.md` 及按需读取的规划、编辑、效果和交付规则；目录只读 |

### 状态与对话历史

- 前端直接展示原生 `messages`，不维护第二份永久对话历史。工具卡片是按调用 ID 配对的展示映射。
- 当前版本的常规摘要写入 `_summarization_event`，模型请求使用摘要和近期消息，状态中的原生历史仍保留；长工具结果可能被文件引用替换，溢出恢复也可能修改已有工具结果。因此原生 `messages` 不是不可变的对话审计日志。
- 子 Agent 内部消息和摘要生成过程不混入主聊天流，子 Agent 结果通过主 Agent 的 `task` 工具返回。
- 当前轮重连快照只在运行时内存中保存，任务结束后释放；订阅队列有界，慢连接不会阻塞模型执行。
- 会话文件随 thread 保存；长期记忆属于当前本地用户，删除会话不会删除记忆。每轮重新从 Store 读取，避免使用旧会话缓存。
- `StateSnapshot.created_at` 是检查点创建时间，上传素材也会改变它。侧栏使用单独保存的 `last_chat_at`，发送和执行结束时更新，素材变化不更新。应用共用一个 60 秒定时器刷新相对时间。

### 效果资源与上下文边界

第三方 `jianying-protocol-service` 当前提供工程、轨道和片段操作，没有资源目录查询接口。适配层 [resource_catalog.py](src/utils/resource_catalog.py) 复用项目已有的 `rag.get_jianying_res_info()`，运行时读取 `rag/data/*.json`。

- `list_jianying_resource_categories` 返回分类及数量。
- `search_jianying_resources` 按分类和关键词分页返回 `category`、`name`、`desc`，不返回材质配置和下载 URL。
- 效果工具通过分类和名称在内部查找、解析并应用完整渲染 JSON；操作结果仅返回状态和必要标识，资源异常详情留在服务端日志。
- Skill、系统提示词和长期记忆不维护固定的效果资源清单。
- 文件工具只能访问虚拟会话文件、记忆和只读 Skills，不能直接读取 `rag/data`、草稿原始 JSON 或任意本机路径。

新增或更新资源时按现有格式维护 `rag/data/*.json`；如果第三方将来提供目录 API，只需替换适配层的加载入口。

## 项目结构与数据

```text
capcut-agent/
├── server.py                         # Flask API、上传与 SSE
├── requirements.txt
├── .env.example
├── src/
│   ├── agents/
│   │   ├── models.py                 # DeepAgentState 与模型配置
│   │   ├── prompts.py                # 基础角色和摘要提示词
│   │   ├── workflow.py               # Deep Agents、中间件、子 Agent
│   │   ├── runtime.py                # 异步任务、订阅、审批、SQLite
│   │   └── events.py                 # 原生消息序列化及增量快照
│   └── utils/
│       ├── mcp_loader.py
│       ├── jianying_tools.py
│       └── resource_catalog.py
├── agent_skills/capcut-editing/       # SKILL.md 与 references/
├── rag/data/                         # 运行时效果资源目录
├── external/jianying-protocol-service/
├── static/
│   ├── index.html
│   ├── css/chat.css
│   ├── js/app.js                     # 页面实例及站内导航
│   ├── js/chat/                      # 消息、SSE、滚动、分割条、会话状态
│   ├── js/components/                # 聊天、审批、侧栏、首页和素材库
│   └── vendor/                       # 固定版本依赖及许可证
└── test/                             # 离线回归测试及原有 RAG 实验脚本
```

`CAPCUT_DATA_DIR` 默认指向项目的 `data/`：

| 数据 | 用途 |
| --- | --- |
| `deepagents.db` | 原生消息、会话文件、计划、摘要、审批等 checkpoint 状态 |
| `memory.db` | LangGraph Store：长期记忆，以及独立 `("app", "thread_activity")` 命名空间中的最后聊天时间、运行状态和已读标记 |
| `uploads/<thread_id>/` | 上传媒体文件 |

第三方剪映工具也以该目录作为 `JY_Res_Dir` 保存工程资源。旧 `checkpoints.db` 不读取、不迁移，也不主动删除。删除会话会删除对应 checkpoint 和运行元数据；当前上传文件的删除由素材删除接口处理。

## API 与 SSE

| 接口 | 用途 |
| --- | --- |
| `GET /api/threads` | 会话标题、最后聊天时间、运行状态和未读状态 |
| `POST /api/thread/<id>/init` | 初始化新会话，已有会话保持原状态 |
| `GET /api/thread/<id>/messages` | 原生 `messages` 的展示结构 |
| `DELETE /api/thread/<id>` | 删除会话状态，执行中返回 409 |
| `POST /api/chat/stream` | 发送消息并订阅 SSE |
| `GET /api/thread/<id>/events` | 重新订阅当前运行；若已结束，返回结束状态 |
| `GET /api/thread/<id>/agent-state` | 当前 interrupt 和运行元数据 |
| `POST /api/thread/<id>/resume` | 提交审批决定并流式继续 |
| `POST /api/thread/<id>/read` | 通过 `run_id` 确认已查看结束结果 |
| `GET /api/thread/<id>/resources` | 获取素材列表 |
| `POST /api/thread/<id>/resources/upload` | `multipart/form-data`，字段 `files`，支持多文件 |
| `DELETE /api/thread/<id>/resources/<resource_id>` | 删除素材记录和对应上传文件 |

执行中或有待审批操作时，素材修改会返回 409。

发送消息：

```json
{"thread_id":"<id>","message":"使用已上传素材剪一个 15 秒视频","message_id":"<可选的稳定消息 ID>"}
```

SSE 只有 `message`、`done`、`error` 三类业务事件，心跳使用注释：

```text
data: {"type":"message","message":{"id":"answer","role":"ai","content":"正在整理"},"delta":true,"complete":false}

data: {"type":"message","message":{"id":"answer","role":"ai","content":""},"delta":true,"complete":true}

: keep-alive

data: {"type":"done","interrupts":[],"run":{"run_id":"run-1","run_status":"completed","running":false,"unread":true}}

```

`message` 可包含 `tool_calls`，通过调用 index 累积参数，通过调用 ID 配对工具结果。重连快照使用 `delta: false` 替换已有消息。流结束后再从原生 `messages` 校准显示。

审批请求位于 `done.interrupts` 或 `/agent-state`。每个 interrupt 的决定顺序必须对应 `action_requests`；允许的决定由 `review_configs` 提供：

```json
{"decisions":{"<interrupt_id>":{"decisions":[{"type":"approve"}]}}}
```

修改参数使用 `{"type":"edit","edited_action":{"name":"原工具名","args":{}}}`；拒绝使用 `{"type":"reject","message":"拒绝原因"}`。

## 开发与验证

```bash
.venv/bin/python -m unittest discover -s test -p 'test_*.py' -v
node --test test/*.test.mjs
.venv/bin/python -m pip check
```

JavaScript 测试使用支持 ES Modules 和内置 `node:test` 的 Node.js（当前使用 Node 25 验证）。Python 测试使用真实 Deep Agents / SQLite 和脚本模型，不调用付费模型、不修改真实剪映工程；覆盖 Skills、记忆、子 Agent、摘要、文件卸载、审批恢复、素材接口和后台运行。前端测试覆盖 SSE 分帧、Markdown、工具配对、滚动、未读状态及时间刷新。

新增 MCP 工具在 `src/utils/jianying_tools.py` 注册；需要审批的工具同时加入 `workflow.py` 的 `APPROVAL_TOOLS`，允许子 Agent 查询的工具加入 `READ_TOOLS`。剪辑领域规则放在 Skill 中，效果资源数据由目录适配层加载。

原有 `test/build_rag.py` 等属于独立实验脚本，不在上述回归测试范围内，也不是当前 Agent 主流程的依赖。

框架参考：[Deep Agents](https://docs.langchain.com/oss/python/deepagents/overview)、[Memory](https://docs.langchain.com/oss/python/deepagents/memory)、[Skills](https://docs.langchain.com/oss/python/deepagents/skills)、[Human-in-the-loop](https://docs.langchain.com/oss/python/deepagents/human-in-the-loop)。
