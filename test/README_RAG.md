# RAG 示例使用说明

本示例展示了如何使用 RAG (Retrieval Augmented Generation) 技术构建知识库问答系统。

## 📁 文件结构

```
test/
├── embeddings.py          # 共享的 Embeddings 模型创建工具
├── build_rag.py           # 构建向量数据库
├── query_rag.py           # 查询向量数据库
├── novel.txt              # 示例文档
└── long_novel_chroma_db/  # 向量数据库（自动生成）
```

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量（可选）

如果使用 API 模型，需要在 `.env` 文件中配置：

```bash
# API 配置（使用 API 模型时必需）
OPENAI_API_KEY=your-api-key
OPENAI_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
EMBEDDING_MODEL=your-embedding-endpoint-id

# LLM 配置（查询时使用）
OPENAI_MODEL_NAME=gpt-3.5-turbo-1106
```

### 3. 构建向量数据库

```bash
# 方式 1：使用本地模型（推荐，无需 API）
cd test
TRANSFORMERS_NO_TF=1 USE_TF=0 python build_rag.py

# 方式 2：使用 API 模型
# 修改 build_rag.py 最后一行为: main(use_local_model=False)
# 然后运行: python build_rag.py
```

**注意**：
- 本地模型首次运行会自动下载模型文件（约 420MB）
- 必须设置环境变量 `TRANSFORMERS_NO_TF=1` 和 `USE_TF=0` 以避免 Keras 冲突

### 4. 查询向量数据库

```bash
# 交互式查询（推荐）
cd test
TRANSFORMERS_NO_TF=1 USE_TF=0 python query_rag.py

# 单次查询
TRANSFORMERS_NO_TF=1 USE_TF=0 python -c "from query_rag import query; print(query('小说第一章讲了什么？', mode='fast'))"
```

## 📚 核心模块说明

### embeddings.py

提供统一的 Embeddings 模型创建接口：

```python
from embeddings import create_embeddings

# 创建本地模型
embeddings = create_embeddings(use_local_model=True)

# 创建 API 模型
embeddings = create_embeddings(use_local_model=False, config=config)
```

**支持的模型**：
- **本地模型**：`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
  - 优点：无需 API，数据隐私，离线可用
  - 缺点：首次需下载模型，占用内存
- **API 模型**：OpenAI 兼容接口（如火山引擎）
  - 优点：无需本地资源，模型效果可能更好
  - 缺点：需要 API key，数据需发送到外部

### build_rag.py

构建向量数据库的工具：

```python
from build_rag import main

# 使用本地模型
main(
    source_file="novel.txt",
    output_dir="long_novel_chroma_db",
    chunk_size=500,
    chunk_overlap=50,
    use_local_model=True
)

# 使用 API 模型
main(use_local_model=False)
```

**参数说明**：
- `source_file`: 源文档路径
- `output_dir`: 向量数据库输出目录
- `chunk_size`: 文档切分块大小（字符数）
- `chunk_overlap`: 块之间的重叠大小
- `use_local_model`: 是否使用本地模型
- `local_model_name`: 本地模型名称

### query_rag.py

查询向量数据库的工具（由 AI Agent 自动选择最优策略）：

```python
from query_rag import query

# Agent 会自动根据问题类型选择合适的工具
result = query("小说第一章讲了什么？")  # 局部性问题 → KnowledgeBaseQA

result = query("第一章出现了哪些角色？")  # 全局性问题 → ComprehensiveKnowledgeQA

result = query("主要人物有谁？", verbose=True)  # 显示 Agent 决策过程
```

**智能策略选择**：
- AI Agent 会自动分析问题特性
- 对于局部性问题（特定情节、角色描写等），自动选择 `KnowledgeBaseQA` 工具（Top-K 检索）
- 对于全局性问题（列举所有角色、所有情节等），自动选择 `ComprehensiveKnowledgeQA` 工具（Map-Reduce 全文档扫描）
- 无需手动指定模式，完全由 AI 决策

## ⚙️ 配置说明

### 使用本地模型

在 `build_rag.py` 和 `query_rag.py` 中设置：

```python
# build_rag.py
if __name__ == "__main__":
    main(use_local_model=True)

# query_rag.py
USE_LOCAL_MODEL = True
LOCAL_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
```

### 使用 API 模型

在 `build_rag.py` 和 `query_rag.py` 中设置：

```python
# build_rag.py
if __name__ == "__main__":
    main(use_local_model=False)

# query_rag.py
USE_LOCAL_MODEL = False
```

**重要**：构建和查询必须使用相同的 Embedding 模型！

## 🔧 环境变量说明

为避免 TensorFlow/Keras 冲突，必须在运行前设置：

```bash
export TRANSFORMERS_NO_TF=1
export USE_TF=0
export TOKENIZERS_PARALLELISM=false  # 可选，避免 fork 警告
```

或在命令行直接指定：

```bash
TRANSFORMERS_NO_TF=1 USE_TF=0 python build_rag.py
```

## 🎯 使用示例

### 示例 1：构建知识库

```bash
cd test
TRANSFORMERS_NO_TF=1 USE_TF=0 python build_rag.py
```

输出：
```
==================================================
RAG 向量数据库构建
==================================================

文档切分: 1300 字符 → 3 块
📦 本地模型: paraphrase-multilingual-MiniLM-L12-v2
构建向量数据库: /Users/.../long_novel_chroma_db
✅ 完成: 3 个文档块
```

### 示例 2：交互式查询

```bash
TRANSFORMERS_NO_TF=1 USE_TF=0 python query_rag.py
```

输出：
```
============================================================
💬 RAG 交互式查询
============================================================

提示：输入 'exit' 或 'quit' 退出
提示：输入 'mode:fast' 切换到快速模式
提示：输入 'mode:comprehensive' 切换到完整模式
提示：输入 'mode:auto' 切换到自动模式（默认）

[auto] 请输入问题: 小说第一章讲了什么？

⏳ 查询中...
📂 加载向量数据库: /Users/.../long_novel_chroma_db
📦 本地模型: paraphrase-multilingual-MiniLM-L12-v2
✅ 向量数据库加载完成，包含 3 个文档块

============================================================
💡 答案:
============================================================
小说第一章主要讲述了萧炎和萧媚进行斗之气测验的场景...
============================================================
```

### 示例 3：单次查询

```python
from query_rag import query

result = query("小说第一章讲了什么？", mode="fast")
print(result)
```

## 📝 常见问题

### Q1: 遇到 Keras 冲突错误怎么办？

**A**: 确保运行时设置了环境变量：
```bash
TRANSFORMERS_NO_TF=1 USE_TF=0 python your_script.py
```

### Q2: 本地模型下载很慢怎么办？

**A**: 可以使用镜像源：
```bash
export HF_ENDPOINT=https://hf-mirror.com
```

### Q3: 如何切换 Embedding 模型？

**A**: 
1. 修改 `embeddings.py` 中的 `create_local_embeddings` 或 `create_api_embeddings` 函数
2. 删除旧的向量数据库目录
3. 重新运行 `build_rag.py`
4. 确保 `query_rag.py` 使用相同的模型配置

### Q4: 向量数据库可以增量更新吗？

**A**: 当前实现会每次重建数据库。如需增量更新，可以：
1. 修改 `build_rag.py`，移除 `shutil.rmtree(output_dir)` 行
2. 使用 `Chroma.add_documents()` 添加新文档

### Q5: 如何优化查询效果？

**A**: 
1. 调整 `chunk_size` 和 `chunk_overlap` 参数
2. 使用更好的 Embedding 模型
3. 根据问题类型选择合适的查询模式（fast/comprehensive/auto）
4. 优化文档的 metadata（如章节、类别等）

## 📖 扩展阅读

- [LangChain 文档](https://python.langchain.com/)
- [Chroma 向量数据库](https://www.trychroma.com/)
- [Sentence Transformers](https://www.sbert.net/)
- [RAG 技术原理](https://arxiv.org/abs/2005.11401)

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！
