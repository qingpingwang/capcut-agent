"""
RAG 模块 - 剪映资源信息获取

公共 API:
- get_jianying_res_info: 从本地 JSON 文件加载剪映资源信息
"""

from .get_res_from_feishu import get_jianying_res_info

__all__ = ["get_jianying_res_info"]

