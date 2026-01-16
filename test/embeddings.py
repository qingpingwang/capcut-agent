"""
Embeddings 模型创建工具

提供统一的 Embeddings 模型创建接口，支持：
1. 本地模型（sentence-transformers）
2. API 模型（OpenAI 兼容接口）
"""

from langchain_openai import OpenAIEmbeddings


def create_local_embeddings(
    model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
):
    """
    创建本地 Embeddings 模型（无需 API）
    
    优点：
        - 无需 API key
        - 数据不会发送到外部服务器
        - 首次使用会自动下载模型（约 420MB）
    
    参数：
        model_name: HuggingFace 模型名称
    
    返回：
        HuggingFaceEmbeddings 实例
    """
    try:
        from langchain_huggingface import HuggingFaceEmbeddings
    except ImportError:
        raise ImportError(
            "使用本地模型需要安装依赖:\n"
            "  pip install sentence-transformers langchain-huggingface\n\n"
            "或使用 API 模型（设置 use_local_model=False）"
        )
    
    print(f"📦 本地模型: {model_name.split('/')[-1]}")
    return HuggingFaceEmbeddings(model_name=model_name)


def create_api_embeddings(config: dict):
    """
    创建 API Embeddings 模型（OpenAI 兼容接口）
    
    支持：
        - OpenAI 官方 API
        - 火山引擎等兼容接口
    
    参数：
        config: 配置字典，需包含：
            - api_key: API 密钥
            - base_url: API 基础 URL
            - embedding_model: 模型名称/端点 ID
    
    返回：
        OpenAIEmbeddings 实例
    """
    print(f"🌐 API 模型: {config['embedding_model']}")
    return OpenAIEmbeddings(
        api_key=config["api_key"],
        base_url=config["base_url"],
        model=config["embedding_model"]
    )


def create_embeddings(
    use_local_model: bool = False,
    local_model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    config: dict = None
):
    """
    统一的 Embeddings 创建接口
    
    参数：
        use_local_model: 是否使用本地模型
        local_model_name: 本地模型名称（仅当 use_local_model=True 时有效）
        config: API 配置（仅当 use_local_model=False 时需要）
    
    返回：
        Embeddings 实例
    """
    if use_local_model:
        return create_local_embeddings(model_name=local_model_name)
    else:
        if config is None:
            raise ValueError("使用 API 模型时必须提供 config 参数")
        return create_api_embeddings(config)

