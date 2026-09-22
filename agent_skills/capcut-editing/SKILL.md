---
name: capcut-editing
description: 使用剪映 MCP 工具完成视频剪辑，包括需求与分镜规划、素材选择、工程轨道片段操作、字幕、转场特效、声音、调色、工程检查和草稿交付。所有剪辑相关任务均使用此 Skill。
---

# 剪映视频剪辑

按任务阶段读取所需规则，无需一次加载全部引用文档：

- 操作素材、分辨率转换、素材匹配和剪辑约束：先读取 /skills/capcut-editing/references/editing-rules.md。
- 需求、分镜、时间线、多素材组合：读取 /skills/capcut-editing/references/editing-plan.md。
- 转场、动画、特效、滤镜、音效：读取 /skills/capcut-editing/references/effects-and-transitions.md。
- 检查工程、同步到剪映、交付草稿：读取 /skills/capcut-editing/references/draft-delivery.md。
- 选择内置资源前，调用 list_jianying_resource_categories 和 search_jianying_resources 查询当前目录。按返回的分类和名称应用资源，不猜名称或 ID。

## 通用约束

- 以系统提供的“当前可用素材”为准，只查询素材时不创建或修改工程。
- 不把素材元信息当作已分析过视频画面，不虚构素材、对白、资源或工具执行结果。
- 区分素材 ID、工程 ID、轨道 ID、片段 ID。媒体时间参数以毫秒为主，以工具 schema 为准。
- 上传素材的 resource_url 用于媒体工具；虚拟文件工具用于剪辑计划、记忆和技能文档。
- 简单任务直接执行；复杂任务使用 write_todos。子 Agent 负责规划、分析和检查，主 Agent 顺序执行工程修改。
- 工程删除、片段删除和草稿同步在工具审批后继续；拒绝后调整方案。
- 从用户表达、反馈和纠正中识别稳定的剪辑偏好，由模型自行决定是否使用文件工具更新 /memories/AGENTS.md。更新前读取已有记忆，合并重复信息、修正过时内容；用户要求忘记时删除对应条目。临时工程状态保存在 /workspace/。
- 当前交付能力是剪映草稿。实际渲染完成前，不声称已导出 MP4。
- 资源是运行时数据，不在 Skill、记忆或提示词中维护固定清单。查询无结果时明确说明；分页结果通过 next_offset 继续读取，不能把一页当作完整目录。

## 资源数据边界

资源查询只返回分类、name、desc 和分页信息。实际渲染材质 JSON 及下载 URL 不进入模型上下文；由添加特效、滤镜、转场、动画和音效的工具内部按 category/name 查找并应用。不要请求原始配置，也不要使用文件工具读取 rag/data 或草稿原始 JSON。
