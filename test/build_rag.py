"""RAG 向量数据库构建工具"""

import os
import sys
os.environ["TRANSFORMERS_NO_TF"] = "1"
os.environ["USE_TF"] = "0"
from dotenv import load_dotenv
from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter

# 导入共享的 embeddings 模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from embeddings import create_embeddings

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


# ===================== 配置 =====================
def load_config():
    load_dotenv()
    return {
        "api_key": os.getenv("OPENAI_API_KEY"),
        "base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "embedding_model": os.getenv("EMBEDDING_MODEL", None),
    }


# ===================== 文档处理 =====================
def load_and_split_document(file_path: str, chunk_size: int = 500, chunk_overlap: int = 50):
    """加载并切分文档"""
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()
    
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", "。", "！", "？", "，"]
    )
    
    chunks = text_splitter.create_documents(
        texts=[text],
        metadatas=[{"chapter": "第一章"}]
    )
    
    print(f"文档切分: {len(text)} 字符 → {len(chunks)} 块")
    return chunks


# ===================== 向量数据库 =====================
def build_vector_db(documents, embeddings, persist_dir: str):
    """构建向量数据库"""
    print(f"构建向量数据库: {persist_dir}")
    
    vector_db = Chroma.from_documents(
        documents=documents,
        embedding=embeddings,
        persist_directory=persist_dir
    )
    
    print(f"✅ 完成: {len(documents)} 个文档块\n")
    return vector_db


# ===================== 主流程 =====================
def main(
    source_file: str = None,
    output_dir: str = None,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    use_local_model: bool = False,
    local_model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
):
    """构建 RAG 向量数据库"""
    if source_file is None:
        source_file = os.path.join(SCRIPT_DIR, "novel.txt")
    if output_dir is None:
        output_dir = os.path.join(SCRIPT_DIR, "long_novel_chroma_db")
    
    print("="*50)
    print("RAG 向量数据库构建")
    print("="*50 + "\n")
    
    if os.path.exists(output_dir):
        import shutil
        shutil.rmtree(output_dir)
    
    config = load_config()
    documents = load_and_split_document(source_file, chunk_size, chunk_overlap)
    embeddings = create_embeddings(
        use_local_model=use_local_model,
        local_model_name=local_model_name,
        config=config
    )
    vector_db = build_vector_db(documents, embeddings, output_dir)


if __name__ == "__main__":
    main(use_local_model=True)