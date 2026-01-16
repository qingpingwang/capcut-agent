from langchain_mcp_adapters.client import MultiServerMCPClient
from pathlib import Path
# 当前工程目录
def dir_to_absolute_path(dir: str) -> str:
    """将相对路径转换为绝对路径（相对于项目根目录）"""
    current_dir = Path(__file__).parent  # 获取项目根目录
    return str(current_dir / dir)

async def load_mcp_tools():
    client = MultiServerMCPClient({
        "jianying_tools": {
            "transport": "stdio",
            "command": "python3",
            "args": [dir_to_absolute_path("jianying_tools.py")]
        }
    })
    return await client.get_tools()  # await!