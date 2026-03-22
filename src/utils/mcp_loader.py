import sys
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient


def _jianying_tools_script() -> str:
    """本文件同目录下的 jianying_tools.py 绝对路径。"""
    return str(Path(__file__).resolve().parent / "jianying_tools.py")


async def load_mcp_tools():
    client = MultiServerMCPClient({
        "jianying_tools": {
            "transport": "stdio",
            "command": sys.executable,
            "args": [_jianying_tools_script()],
        }
    })
    return await client.get_tools()  # await!