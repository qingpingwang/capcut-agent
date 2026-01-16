"""
RAG 查询工具

功能：
1. 加载已有的向量数据库
2. 支持普通 RAG 查询（快速）
3. 支持 Map-Reduce 查询（完整）
4. 自动选择合适的查询模式

前提：
    需要先运行 build_rag.py 构建向量数据库

使用：
    python query_rag.py
"""

import os
import sys
os.environ["TRANSFORMERS_NO_TF"] = "1"
os.environ["USE_TF"] = "0"
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_community.vectorstores import Chroma
from langchain_core.prompts import PromptTemplate
from langchain_core.tools import Tool
from langchain.agents import create_agent
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import HumanMessage

# 导入共享的 embeddings 模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from embeddings import create_embeddings

# 获取脚本所在目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ===================== 全局配置 =====================
# 是否使用本地模型（True: 本地模型, False: API 模型）
USE_LOCAL_MODEL = True
LOCAL_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


# ===================== 配置加载 =====================
def load_config():
    """加载环境变量配置"""
    load_dotenv()
    return {
        "api_key": os.getenv("OPENAI_API_KEY"),
        "base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "embedding_model": os.getenv("EMBEDDING_MODEL", None),
        "llm_model": os.getenv("OPENAI_MODEL_NAME", "gpt-3.5-turbo-1106")
    }


# ===================== 向量数据库加载 =====================
def load_vector_db(
    config: dict,
    persist_dir: str = None,
    use_local_model: bool = False,
    local_model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
):
    """
    加载已有的向量数据库
    
    Args:
        config: 配置字典
        persist_dir: 持久化目录
        use_local_model: 是否使用本地模型
        local_model_name: 本地模型名称
    
    Returns:
        向量数据库实例
    """
    if persist_dir is None:
        persist_dir = os.path.join(SCRIPT_DIR, "long_novel_chroma_db")
    
    if not os.path.exists(persist_dir):
        raise FileNotFoundError(
            f"向量数据库不存在: {persist_dir}\n"
            f"请先运行 build_rag.py 构建向量数据库"
        )
    
    embeddings = create_embeddings(
        use_local_model=use_local_model,
        local_model_name=local_model_name,
        config=config
    )
    
    vector_db = Chroma(
        persist_directory=persist_dir,
        embedding_function=embeddings
    )
    
    count = vector_db._collection.count()
    print(f"✅ 向量数据库加载完成（{count} 个文档块）\n")
    
    return vector_db


# ===================== RAG 问答链 =====================
def create_rag_chain(llm):
    """创建 RAG 问答链"""
    rag_prompt = PromptTemplate(
        template="""你是一个智能问答助手，请根据以下参考文档回答用户的问题。

参考文档：
{docs}

用户问题：{question}

要求：
1. 基于参考文档内容回答，不要编造信息
2. 如果文档中没有相关信息，明确说明
3. 回答要准确、简洁、有条理

回答：""",
        input_variables=["docs", "question"]
    )
    
    return rag_prompt | llm | StrOutputParser()


def create_map_chain(llm):
    """创建 Map 阶段的链"""
    map_prompt = PromptTemplate(
        template="""请分析以下文档片段，回答用户的问题。

文档片段：
{doc}

用户问题：{question}

要求：
1. 只分析这个片段中的信息
2. 如果片段中没有相关信息，返回"无"
3. 简洁回答，列出要点

回答：""",
        input_variables=["doc", "question"]
    )
    
    return map_prompt | llm | StrOutputParser()


def create_reduce_chain(llm):
    """创建 Reduce 阶段的链"""
    reduce_prompt = PromptTemplate(
        template="""请汇总以下各个文档片段的分析结果，给出完整答案。

各片段的分析结果：
{all_answers}

原始问题：{question}

要求：
1. 合并所有片段的信息
2. 去除重复内容
3. 组织成清晰、完整的答案
4. 如果所有片段都没有信息，明确说明

最终答案：""",
        input_variables=["all_answers", "question"]
    )
    
    return reduce_prompt | llm | StrOutputParser()


# ===================== Map-Reduce 执行器 =====================
def map_reduce_query(vector_db, map_chain, reduce_chain, question: str, 
                     filter_metadata: dict = None, verbose: bool = False):
    """
    使用 Map-Reduce 模式处理全局性问题
    
    Args:
        vector_db: 向量数据库
        map_chain: Map 链
        reduce_chain: Reduce 链
        question: 用户问题
        filter_metadata: 过滤条件
        verbose: 是否显示详细过程
    
    Returns:
        最终汇总答案
    """
    if verbose:
        print("\n" + "="*60)
        print("🗺️  Map-Reduce 模式")
        print("="*60)
        print(f"\n📝 用户问题: {question}")
        if filter_metadata:
            print(f"🔍 过滤条件: {filter_metadata}")
    
    # 获取所有相关文档块
    collection = vector_db._collection
    if filter_metadata:
        results = collection.get(where=filter_metadata, include=["documents"])
        docs = results["documents"]
    else:
        results = collection.get(include=["documents"])
        docs = results["documents"]
    
    if verbose:
        print(f"\n📊 获取到 {len(docs)} 个文档块")
        print(f"\n{'='*60}")
        print("【Map 阶段】对每个文档块分别提问")
        print('='*60)
    
    # Map 阶段
    map_answers = []
    for i, doc in enumerate(docs, 1):
        if verbose:
            print(f"\n处理文档块 {i}/{len(docs)}")
            print(f"内容预览: {doc[:80]}...")
        
        answer = map_chain.invoke({"doc": doc, "question": question})
        
        if verbose:
            print(f"分析结果: {answer}")
        
        if answer.strip() and answer.strip().lower() not in ["无", "none", "无相关信息"]:
            map_answers.append(f"片段{i}: {answer}")
    
    if verbose:
        print(f"\n✅ Map 阶段完成，得到 {len(map_answers)} 个有效答案")
        print(f"\n{'='*60}")
        print("【Reduce 阶段】汇总所有答案")
        print('='*60)
    
    # Reduce 阶段
    if not map_answers:
        final_answer = "所有文档块中都没有找到相关信息。"
    else:
        all_answers_text = "\n\n".join(map_answers)
        final_answer = reduce_chain.invoke({
            "all_answers": all_answers_text,
            "question": question
        })
    
    if verbose:
        print(f"\n✅ Reduce 阶段完成")
        print(f"\n{'='*60}")
        print("💡 最终答案:")
        print('='*60)
        print(final_answer)
        print('='*60 + "\n")
    
    return final_answer


# ===================== 工具封装 =====================
def create_rag_tools(vector_db, rag_chain, map_chain=None, reduce_chain=None, verbose: bool = False):
    """
    创建 RAG 问答工具
    
    Args:
        vector_db: 向量数据库
        rag_chain: RAG 问答链
        map_chain: Map 链
        reduce_chain: Reduce 链
    
    Returns:
        工具列表
    """
    def answer_question(question: str) -> str:
        """基于知识库回答问题（快速模式）"""
        if verbose:
            print(f"  → 快速模式（Top-3 检索）")
        docs_with_scores = vector_db.similarity_search_with_score(question, k=3)
        docs_content = "\n\n".join([doc.page_content for doc, score in docs_with_scores])
        answer = rag_chain.invoke({"docs": docs_content, "question": question})
        return answer
    
    tools = [
        Tool(
            name="KnowledgeBaseQA",
            func=answer_question,
            description="基于知识库回答问题（快速模式）。适合局部性问题，如：某个角色的描写、特定情节等。输入参数为问题文本。"
        )
    ]
    
    if map_chain and reduce_chain:
        def answer_question_comprehensive(question: str) -> str:
            """使用 Map-Reduce 模式全面回答问题"""
            if verbose:
                print(f"  → 完整模式（Map-Reduce）")
            filter_metadata = None
            if "第一章" in question or "第1章" in question:
                filter_metadata = {"chapter": "第一章"}
            
            return map_reduce_query(
                vector_db, map_chain, reduce_chain, question,
                filter_metadata=filter_metadata, verbose=verbose
            )
        
        tools.append(
            Tool(
                name="ComprehensiveKnowledgeQA",
                func=answer_question_comprehensive,
                description="全面的知识库问答（Map-Reduce 模式）。适合需要遍历所有文档的全局性问题，如：'第一章有哪些角色？'、'所有重要情节？'等。输入参数为问题文本。"
            )
        )
    
    return tools


# ===================== Agent 创建 =====================
def create_rag_agent(llm, tools):
    """创建 RAG Agent"""
    return create_agent(model=llm, tools=tools)


def run_query(agent, query: str):
    """执行查询"""
    messages = [HumanMessage(content=query)]
    response = agent.invoke({"messages": messages})
    return response["messages"][-1].content


# ===================== 查询接口 =====================
def query(questions: list[str], verbose: bool = False):
    """
    查询接口 - 由 Agent 自动选择最合适的检索策略
    
    Args:
        question: 用户问题
        verbose: 是否显示详细过程
    
    Returns:
        查询结果
    """
    # 加载配置
    config = load_config()
    
    # 加载向量数据库
    vector_db = load_vector_db(
        config,
        use_local_model=USE_LOCAL_MODEL,
        local_model_name=LOCAL_MODEL_NAME
    )
    
    # 创建 LLM 和链
    llm = ChatOpenAI(model_name=config["llm_model"], temperature=0.1)
    rag_chain = create_rag_chain(llm)
    map_chain = create_map_chain(llm)
    reduce_chain = create_reduce_chain(llm)
    
    # 创建工具和 Agent，让 Agent 自动选择策略
    tools = create_rag_tools(vector_db, rag_chain, map_chain, reduce_chain, verbose)
    agent = create_rag_agent(llm, tools)
    
    for i, question in enumerate(questions, 1):
        print(f"\n【问题 {i}】{question}")
        if verbose:
            print(f"🤖 Agent 正在选择最优策略...")
        result = run_query(agent, question)
        print(f"\n【答案】\n{result}")
        print("=" * 60)
    
    return result


if __name__ == "__main__":
    questions = [
        "萧炎测验结果是什么？",
        "小说第一章讲了什么？",
        "第一章出现了哪些人物？",
        "主要人物有谁？",
    ]
    query(questions, verbose=True)
