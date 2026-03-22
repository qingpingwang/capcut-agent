import os
import sys
from pathlib import Path
from typing import Optional, Union
import re

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# 加载环境变量（在导入子模块之前，确保 OSS_AK/OSS_SK 等可用）
load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
os.environ["JY_Res_Dir"] = str(PROJECT_ROOT / "data")

# 将项目根目录添加到 Python 搜索路径（确保能导入 rag 模块）
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 将剪映协议服务 src 加入路径（子模块目录名与 .gitmodules 一致）
EXTERNAL_SRC = PROJECT_ROOT / "external" / "jianying-protocol-service" / "src"
if str(EXTERNAL_SRC) not in sys.path:
    sys.path.insert(0, str(EXTERNAL_SRC))

from utils.models import JianYingInternalMaterialInfo

# 导入 TaskManager
from task_manager import TaskManager

# 导入 interface 层的模块和 Request 类型
from interface.task.create_task import handler as create_task_handler, CreateTaskRequest
from interface.task.get_task import handler as get_task_handler
from interface.task.remove_task import handler as remove_task_handler, RemoveTaskRequest

from interface.track.add_track import handler as add_track_handler, AddTrackRequest
from interface.track.remove_track import handler as remove_track_handler, RemoveTrackRequest
from interface.track.get_tracks import handler as get_tracks_handler
from interface.track.get_track import handler as get_track_handler

from interface.segment.add_media_segment import handler as add_media_segment_handler, AddMediaSegmentRequest
from interface.segment.add_text_segment import handler as add_text_segment_handler, AddTextSegmentRequest
from interface.segment.remove_segment import handler as remove_segment_handler, RemoveSegmentRequest
from interface.segment.update_segment_transform import handler as update_segment_transform_handler, UpdateSegmentTransformRequest
from interface.segment.update_text_content import handler as update_text_content_handler, UpdateTextContentRequest
from interface.segment.update_adjust_info import handler as update_adjust_info_handler, UpdateAdjustInfoRequest
from interface.segment.add_internal_material_to_segment import handler as add_internal_material_to_segment_handler, AddInternalMaterialToSegmentRequest
from interface.segment.add_effect_segment import handler as add_effect_segment_handler, AddEffectSegmentRequest
from interface.segment.add_filter_segment import handler as add_filter_segment_handler, AddFilterSegmentRequest
from interface.segment.add_audio_effect_segment import handler as add_audio_effect_segment_handler, AddAudioEffectSegmentRequest
from rag import get_jianying_res_info as load_jianying_res_info
import json
import requests
# FastMCP 服务器
mcp = FastMCP("jianying_tools")

# 全局 TaskManager 实例
_task_manager: Optional[TaskManager] = None
JIANYING_PROJECT_DIR = Path.home() / 'Movies/JianyingPro/User Data/Projects/com.lveditor.draft'

# 在启动时加载所有剪映资源信息
jianying_res_info = load_jianying_res_info()


def get_task_manager() -> TaskManager:
    """获取全局 TaskManager 实例（懒加载）"""
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager


def ensure_request(request_or_dict, request_class):
    """
    确保参数是 Pydantic Request 实例
    
    兼容 MCP 协议传入的 dict 和已实例化的 Request 对象
    
    Args:
        request_or_dict: dict 或 Pydantic 实例
        request_class: 目标 Request 类
    
    Returns:
        Pydantic Request 实例
    """
    if isinstance(request_or_dict, dict):
        return request_class(**request_or_dict)
    elif isinstance(request_or_dict, request_class):
        return request_or_dict
    else:
        # 尝试使用 model_validate（兼容其他类型）
        return request_class.model_validate(request_or_dict)


def unpack_params(first_param, *args, **kwargs):
    """
    解包 MCP 传入的 dict 参数为函数参数
    
    用于处理非 Request 对象的普通函数参数
    
    Args:
        first_param: 第一个参数，可能是 dict（MCP 传入）或正常参数
        *args: 其他位置参数
        **kwargs: 关键字参数
    
    Returns:
        (args_tuple, kwargs_dict): 解包后的参数
    
    示例:
        # 函数定义
        def func(project_id: str, copy_resource: bool = False):
            # MCP 调用时: first_param = {"project_id": "xxx", "copy_resource": False}
            args, kwargs = unpack_params(first_param)
            project_id = kwargs.get('project_id', project_id)
            copy_resource = kwargs.get('copy_resource', copy_resource)
            
        # 或更简洁地：
        def func(project_id: str = None, copy_resource: bool = False):
            if isinstance(project_id, dict):
                return func(**project_id)
            # 正常处理逻辑
    """
    # 如果第一个参数是 dict，且没有其他参数，说明是 MCP 传入的打包参数
    if isinstance(first_param, dict) and not args:
        return (), {**first_param, **kwargs}
    else:
        return (first_param, *args), kwargs


# ==================== 项目管理 ====================

@mcp.tool()
def create_project(request: Union[CreateTaskRequest, dict]) -> dict:
    """
    创建剪映项目
    
    Args:
        request: 创建任务请求
            - name: 项目名称 (必填)
            - width: 画布宽度，像素 (默认 720)
            - height: 画布高度，像素 (默认 1280)
            - fps: 帧率 (默认 30)
            - duration: 初始时长，秒 (默认 0)
    
    Returns:
        dict: {"task_id": "项目ID"}
    """
    request = ensure_request(request, CreateTaskRequest)
    return create_task_handler(request, get_task_manager())


@mcp.tool()
def get_project_info(project_id: str) -> dict:
    """
    获取项目完整信息
    
    Args:
        project_id: 项目ID
    
    Returns:
        dict: 项目详细信息（base_info, materials, tracks, segments）
    """
    # 兼容 MCP 传入的 dict 参数
    if isinstance(project_id, dict):
        return get_project_info(**project_id)
    
    return get_task_handler(project_id, get_task_manager())


@mcp.tool()
def delete_project(request: Union[RemoveTaskRequest, dict]) -> dict:
    """
    删除项目
    
    Args:
        request: 删除任务请求
            - task_id: 项目ID (必填)
    
    Returns:
        dict: {"task_id": "已删除的项目ID"}
    """
    request = ensure_request(request, RemoveTaskRequest)
    return remove_task_handler(request, get_task_manager())


@mcp.tool()
def copy_project_to_jianying(project_id: str, copy_resource: bool = False) -> dict:
    """
    复制项目到剪映工作目录
    
    将项目文件复制到 macOS 剪映工作目录，使其可在剪映中打开。
    
    Args:
        project_id: 项目ID
        copy_resource: 是否复制素材资源文件（默认 False）
            
            ⚠️ **重要参数说明**：
            
            **何时设置为 True**（需要完整复制）：
            - ✅ 添加了新的视频、图片、音频素材
            - ✅ 删除了已有的媒体素材
            - ✅ 替换了素材文件
            - ✅ 首次复制项目到剪映（本地目录不存在）
            
            **何时设置为 False**（仅复制配置，性能更快）：
            - ✅ 仅修改文本内容（如字幕、标题）
            - ✅ 仅调整素材属性（位置、缩放、旋转、透明度）
            - ✅ 仅调整调色参数（亮度、对比度、饱和度等）
            - ✅ 仅修改片段时长或播放速度
            - ✅ 素材文件未变化，仅更新配置
            
            💡 **性能提示**：
            - `False` 时仅复制 JSON 配置文件（秒级完成）
            - `True` 时复制整个项目目录（可能包含 GB 级素材，耗时较长）
            - 建议：仅在必要时设置为 `True`，可大幅提升性能
    
    Returns:
        dict: {
            "success": True,
            "jianying_path": "剪映项目路径"
        }
    """
    # 兼容 MCP 传入的 dict 参数
    if isinstance(project_id, dict):
        return copy_project_to_jianying(**project_id)
    
    import shutil
    from utils.function_utils import get_project_path
    
    project_name = get_project_info(project_id)['data']['name']
    # 获取项目信息
    project_path = Path(get_project_path(project_id))
    
    local_dir = JIANYING_PROJECT_DIR / project_name
    # 如果需要复制资源，或者本地目录不存在，则复制整目录过去
    if copy_resource or not local_dir.exists():
        # 复制整目录过去，先删除旧的(JIANYING_PROJECT_DIR)
        if local_dir.exists():
            shutil.rmtree(local_dir)
        shutil.copytree(project_path, local_dir)
    else:
        # 只复制文件夹下的json文件：
        for file in project_path.glob('*.json'):
            shutil.copy(file, local_dir / file.name)
    
    return {
        "success": True,
        "jianying_path": str(local_dir)
    }


# ==================== 轨道管理 ====================

@mcp.tool()
def add_track(request: Union[AddTrackRequest, dict]) -> dict:
    """
    添加轨道
    
    Args:
        request: 添加轨道请求
            - task_id: 项目ID (必填)
            - track_type: 轨道类型，支持 audio/video/effect/filter/text/sticker/adjust (必填)
            - index: 插入位置，-1 表示追加到末尾 (默认 -1)
    
    Returns:
        dict: {"track_id": "轨道ID"}
    """
    request = ensure_request(request, AddTrackRequest)
    return add_track_handler(request, get_task_manager())


@mcp.tool()
def delete_track(request: Union[RemoveTrackRequest, dict]) -> dict:
    """
    删除轨道
    
    Args:
        request: 删除轨道请求
            - task_id: 项目ID (必填)
            - track_id: 轨道ID (必填)
    
    Returns:
        dict: {"track_id": "已删除的轨道ID"}
    """
    request = ensure_request(request, RemoveTrackRequest)
    return remove_track_handler(request, get_task_manager())


@mcp.tool()
def get_tracks(project_id: str) -> dict:
    """
    获取项目所有轨道
    
    Args:
        project_id: 项目ID
    
    Returns:
        dict: {"tracks": [...]}
    """
    # 兼容 MCP 传入的 dict 参数
    if isinstance(project_id, dict):
        return get_tracks(**project_id)
    
    return get_tracks_handler(project_id, get_task_manager())


@mcp.tool()
def get_track_info(project_id: str, track_id: str) -> dict:
    """
    获取轨道详情
    
    Args:
        project_id: 项目ID
        track_id: 轨道ID
    
    Returns:
        dict: 轨道信息
    """
    # 兼容 MCP 传入的 dict 参数
    if isinstance(project_id, dict):
        return get_track_info(**project_id)
    
    return get_track_handler(project_id, track_id, get_task_manager())


# ==================== 片段管理 ====================

@mcp.tool()
def add_media_segment(request: Union[AddMediaSegmentRequest, dict]) -> dict:
    """
    添加媒体片段（视频/图片/音频）
    
    Args:
        request: 添加媒体片段请求
            - task_id: 项目ID (必填)
            - track_id: 轨道ID (必填)
            - media_material: 媒体素材信息 (必填)，包含:
                - url: 媒体文件路径，本地绝对路径或 URL (必填)
                - media_type: 素材类型，video/photo/audio (默认 video)
                - speed: 播放速度，0.1-10.0 (默认 1.0)
                - mute: 是否静音 (默认 False)
                - from_time: 裁剪开始时间，毫秒 (默认 0)
                - to_time: 裁剪结束时间，毫秒，-1 表示到结尾 (默认 -1)
                - width: 宽度，0 表示自动检测 (默认 0)
                - height: 高度，0 表示自动检测 (默认 0)
                - clip_info: 裁剪信息 (可选)
                - adjust_info: 调节信息 (可选)
                - material_name: 素材名称 (默认 '')
                - category: 素材分类 (默认 '')
                - duration: 素材时长，毫秒 (可选，自动计算，未说明下给None)
            - start_time: 插入时间点，毫秒，None 表示追加到轨道末尾 (默认 None)
            - transform: 变换信息（缩放、旋转、平移）(默认 None)
    
    Returns:
        dict: {"segment_id": "片段ID"}
    """
    request = ensure_request(request, AddMediaSegmentRequest)
    return add_media_segment_handler(request, get_task_manager())


@mcp.tool()
def add_text_segment(request: Union[AddTextSegmentRequest, dict]) -> dict:
    """
    添加文本片段
    
    Args:
        request: 添加文本片段请求
            - task_id: 项目ID (必填)
            - track_id: 轨道ID (必填)
            - text_material: 文本素材信息 (必填)，包含:
                - text: 文本内容 (必填)
                - styles: 样式列表，None 时自动创建默认样式 (可选)
                - background_color: 背景颜色，十六进制 (可选)
                - background_alpha: 背景透明度，0.0-1.0 (默认 1.0)
            - start_time: 插入时间点，毫秒，None 表示追加到轨道末尾 (默认 None)
            - duration: 文本显示时长，毫秒 (默认 5000)
            - transform: 变换信息（缩放、旋转、平移）(默认 None)
    
    Returns:
        dict: {"segment_id": "片段ID"}
    
    提示: 可以使用 JianYingTextMaterialInfo.create_simple() 创建简单文本样式
    """
    request = ensure_request(request, AddTextSegmentRequest)
    return add_text_segment_handler(request, get_task_manager())


@mcp.tool()
def delete_segment(request: Union[RemoveSegmentRequest, dict]) -> dict:
    """
    删除片段
    
    Args:
        request: 删除片段请求
            - task_id: 项目ID (必填)
            - segment_id: 片段ID (必填)
    
    Returns:
        dict: {"segment_id": "已删除的片段ID"}
    """
    request = ensure_request(request, RemoveSegmentRequest)
    return remove_segment_handler(request, get_task_manager())


# ==================== 片段属性修改 ====================

@mcp.tool()
def update_segment_transform(request: Union[UpdateSegmentTransformRequest, dict]) -> dict:
    """
    更新片段变换（位置/缩放/旋转）
    
    Args:
        request: 更新变换请求
            - task_id: 项目ID (必填)
            - segment_id: 片段ID (必填)
            - transform: 变换信息 (必填)，包含:
                - scale_x: X 轴缩放，>0 (默认 1.0)
                - scale_y: Y 轴缩放，>0 (默认 1.0)
                - rotate: 旋转角度，度 (默认 0.0)
                - translate_x: X 轴平移，归一化坐标 -1~1 (默认 0.0)
                - translate_y: Y 轴平移，归一化坐标 -1~1 (默认 0.0)
    
    Returns:
        dict: {"segment_id": "片段ID"}
    """
    request = ensure_request(request, UpdateSegmentTransformRequest)
    return update_segment_transform_handler(request, get_task_manager())


@mcp.tool()
def update_text_content(request: Union[UpdateTextContentRequest, dict]) -> dict:
    """
    更新文本片段的内容（保留原有样式）
    
    Args:
        request: 更新文本内容请求
            - task_id: 项目ID (必填)
            - segment_id: 片段ID (必填)
            - text: 新的文本内容 (必填)
    
    Returns:
        dict: {"segment_id": "片段ID"}
    """
    request = ensure_request(request, UpdateTextContentRequest)
    return update_text_content_handler(request, get_task_manager())


@mcp.tool()
def update_video_adjust(request: Union[UpdateAdjustInfoRequest, dict]) -> dict:
    """
    更新视频片段的调色参数
    
    Args:
        request: 更新调色请求
            - task_id: 项目ID (必填)
            - segment_id: 片段ID (必填)
            - adjust_info: 调节信息 (必填)，包含:
                - temperature: 色温 v3，-50~50 (默认 0)
                - tone: 色调 v3，-50~50 (默认 0)
                - saturation: 饱和度 v1，-50~50 (默认 0)
                - brightness: 亮度 v2，-50~50 (默认 0)
                - contrast: 对比度 v3，-50~50 (默认 0)
                - highlight: 高光 v3，-50~50 (默认 0)
                - shadow: 阴影 v3，-50~50 (默认 0)
                - white: 白色，-50~50 (默认 0)
                - black: 黑色，-50~50 (默认 0)
                - light_sensation: 光感，-50~50 (默认 0)
                - sharpen: 锐化 v1，0~100 (默认 0)
                - clear: 清晰，0~100 (默认 0)
                - particle: 颗粒 v2，0~100 (默认 0)
                - fade: 褪色，0~100 (默认 0)
                - vignetting: 暗角 v1，-50~50 (默认 0)
    
    Returns:
        dict: {"segment_id": "片段ID"}
    """
    request = ensure_request(request, UpdateAdjustInfoRequest)
    return update_adjust_info_handler(request, get_task_manager())


@mcp.tool()
def add_effect_to_track(
    project_id: str, 
    track_id: str, 
    category: str, 
    name: str,
    start_time: Optional[int] = None,
    duration: int = 5000
) -> dict:
    """
    添加剪映内置特效到轨道
    
    将剪映内置的视频特效（如放大镜、马赛克、美肤等）添加到指定轨道上。
    
    Args:
        project_id: 项目ID
        track_id: 特效轨道ID
        category: 资源分类，通常为 "特效"
        name: 特效名称，如 "放大镜"、"马赛克"、"美肤"
        start_time: 插入时间点（毫秒），None 表示追加到轨道末尾（默认 None）
        duration: 特效时长（毫秒），默认 5000
    
    Returns:
        dict: {"segment_id": "片段ID"} 或 {"error": "错误信息"}
    
    示例:
        add_effect_to_track(
            project_id="task-uuid",
            track_id="effect-track-uuid",
            category="特效",
            name="放大镜",
            start_time=0,
            duration=10000
        )
    """
    # 兼容 MCP 传入的 dict 参数
    if isinstance(project_id, dict):
        return add_effect_to_track(**project_id)
    
    try:
        # 获取剪映资源配置
        effect_material, _ = get_jianying_resource(category, name)
        effect_material_dict = json.loads(effect_material)
        # 创建内部材质信息对象
        internal_material = JianYingInternalMaterialInfo(material_info=effect_material_dict)
        # 创建请求对象
        request = AddEffectSegmentRequest(
            task_id=project_id,
            track_id=track_id,
            effect_material=internal_material,
            start_time=start_time,
            duration=duration
        )
        
        return add_effect_segment_handler(request, get_task_manager())
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def add_filter_to_track(
    project_id: str, 
    track_id: str, 
    category: str, 
    name: str,
    start_time: Optional[int] = None,
    duration: int = 5000
) -> dict:
    """
    添加剪映内置滤镜到轨道
    
    将剪映内置的滤镜（如高清增强、美肤、复古等）添加到指定轨道上。
    
    Args:
        project_id: 项目ID
        track_id: 滤镜轨道ID
        category: 资源分类，通常为 "滤镜"
        name: 滤镜名称，如 "高清增强"、"美肤"、"复古"
        start_time: 插入时间点（毫秒），None 表示追加到轨道末尾（默认 None）
        duration: 滤镜时长（毫秒），默认 5000
    
    Returns:
        dict: {"segment_id": "片段ID"} 或 {"error": "错误信息"}
    
    示例:
        add_filter_to_track(
            project_id="task-uuid",
            track_id="filter-track-uuid",
            category="滤镜",
            name="高清增强",
            start_time=0,
            duration=10000
        )
    """
    # 兼容 MCP 传入的 dict 参数
    if isinstance(project_id, dict):
        return add_filter_to_track(**project_id)
    
    try:
        # 获取剪映资源配置
        filter_material, _ = get_jianying_resource(category, name)
        
        filter_material_dict = json.loads(filter_material)
        # 创建内部材质信息对象
        internal_material = JianYingInternalMaterialInfo(material_info=filter_material_dict)
        # 创建请求对象
        request = AddFilterSegmentRequest(
            task_id=project_id,
            track_id=track_id,
            filter_material=internal_material,
            start_time=start_time,
            duration=duration
        )
        
        return add_filter_segment_handler(request, get_task_manager())
    except Exception as e:
        return {"error": str(e)}
   
def download_resource(url: str, local_path: str) -> str:
    """
    下载资源到本地
    """
    if os.path.exists(local_path):
        return local_path
    # 创建本地路径，如果不存在
    Path(local_path).parent.mkdir(parents=True, exist_ok=True)
    # 下载资源
    response = requests.get(url)
    with open(local_path, 'wb') as f:
        f.write(response.content)   
    return local_path

@mcp.tool()
def add_audio_effect_to_track(
    project_id: str, 
    track_id: str,
    category: str, 
    name: str, 
    start_time: Optional[int] = None
) -> dict:
    """
    添加剪映内置音频特效到轨道
    
    Args:
        project_id: 项目ID
        track_id: 音频轨道ID
        category: 资源分类，通常为 "音频特效"
        name: 音频特效名称，如 "电音"、"爵士"
        start_time: 插入时间点（毫秒），None 表示追加到轨道末尾（默认 None）
    
    Returns:
        dict: {"segment_id": "片段ID"} 或 {"error": "错误信息"}
    
    示例:
        add_audio_effect_to_track(
            project_id="task-uuid",
            track_id="audio-track-uuid",
            category="音频特效",
            name="电音",
            start_time=0
        )
    """
    # 兼容 MCP 传入的 dict 参数
    if isinstance(project_id, dict):
        return add_audio_effect_to_track(**project_id)
    
    try:
        supported_categories = ["音效"]
        if category not in supported_categories:
            return {"error": f"不支持的资源分类: {category}, 支持的分类: {supported_categories}"}
        # 获取剪映资源配置
        audio_effect_material_str, url = get_jianying_resource(category, name)
        # 解析 JSON 字符串并下载资源到本地
        audio_material_dict = json.loads(audio_effect_material_str)
        local_path = audio_material_dict['path']
        download_resource(url, local_path)
        
        # 创建请求对象（audio_material 直接传 dict）
        request = AddAudioEffectSegmentRequest(
            task_id=project_id,
            track_id=track_id,
            audio_material=audio_material_dict,
            start_time=start_time
        )
        return add_audio_effect_segment_handler(request, get_task_manager())
    except Exception as e:
        return {"error": str(e)}
    
@mcp.tool()
def add_material_to_segment(project_id: str, segment_id: str, category: str, name: str) -> dict:
    """
    添加剪映内置资源（转场、特效、滤镜、动画等）到片段
    
    Args:
        project_id: 项目ID
        segment_id: 片段ID
        category: 资源分类，如 "转场"、"特效"、"滤镜"、"文字动画"、"画面动画"
        name: 资源名称，如 "推近 II"、"美肤"
    
    Returns:
        dict: {"material_id": "材质ID"} 或 {"error": "错误信息"}
    
    示例:
        add_material_to_segment(
            project_id="task-uuid",
            segment_id="segment-uuid", 
            category="转场",
            name="推近 II"
        )
    """
    # 兼容 MCP 传入的 dict 参数
    if isinstance(project_id, dict):
        return add_material_to_segment(**project_id)
    
    try:
        supported_categories = ["转场", "特效", "滤镜", "文字动画", "画面动画"]
        if category not in supported_categories:
            return {"error": f"不支持的资源分类: {category}, 支持的分类: {supported_categories}"}
        # 获取剪映资源配置
        jianying_res_content, _ = get_jianying_resource(category, name)
        
        # 解析 JSON 字符串为字典
        jianying_res_dict = json.loads(jianying_res_content)
        if category in ["文字动画", "画面动画"]:
            import uuid
            jianying_res_dict = {
                "animations": [jianying_res_dict],
                "id": uuid.uuid4(),
                "type": "sticker_animation"
            }
        
        # 创建内部材质信息对象
        internal_material = JianYingInternalMaterialInfo(material_info=jianying_res_dict)
        
        # 创建请求对象
        request = AddInternalMaterialToSegmentRequest(
            task_id=project_id,
            segment_id=segment_id,
            internal_material=internal_material
        )
        
        return add_internal_material_to_segment_handler(request, get_task_manager())
    except Exception as e:
        return {"error": str(e)}

# ==================== 资源管理 ====================
def get_jianying_resource(category: str, name: str) -> dict:
    """
    获取剪映内置资源的完整配置信息
    
    根据分类和名称获取剪映内置资源（转场、特效、滤镜等）的详细配置。
    会自动将资源配置中的路径替换为当前用户的 home 路径。
    
    Args:
        category: 资源分类，如 "转场"、"特效"、"滤镜"、"文字动画"、"画面动画"、"贴片"、"音效"
        name: 资源名称，如 "推近 II"、"滚动立方"、"美肤"
    
    Returns:
        dict: 资源的完整配置信息，包含 effect_id、resource_id、platform、version 等字段
        
    示例:
        get_jianying_resource(category="转场", name="推近 II")
        → 返回完整的转场效果配置
    """
    res = jianying_res_info[category][name]
    res_content = res['content']
    
    # 获取当前用户的 home 路径并替换资源配置中的路径
    return re.sub(r'/Users/[^/]+/', f'{str(Path.home())}/', res_content), res['url']


# ==================== 启动 MCP 服务 ====================

if __name__ == "__main__":
    mcp.run(transport="stdio")