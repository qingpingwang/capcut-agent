"""
Flask Server - 提供 SSE 流式对话接口
"""
import os
import logging
import sqlite3
import subprocess
import json
import uuid
import hashlib
from pathlib import Path
from flask import Flask, request, Response, jsonify, send_from_directory
from flask_cors import CORS
from src.agents.workflow import workflow
from src.agents.models import create_initial_state
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from typing import List
# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# SQLite 数据库路径
DB_PATH = Path(__file__).parent / "data" / "checkpoints.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# 上传文件存储路径
UPLOAD_DIR = Path(__file__).parent / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ==================== Flask App ====================
app = Flask(__name__, static_folder='static', static_url_path='/static')
CORS(app)

# 初始化 checkpointer 和 graph
conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
checkpointer = SqliteSaver(conn)
graph = workflow.compile(checkpointer=checkpointer)

# ==================== 路由：静态页面 ====================
@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/chat/<thread_id>')
def chat_page(thread_id):
    return send_from_directory('static', 'index.html')

# ==================== 路由：上传文件服务 ====================
@app.route('/uploads/<path:filepath>')
def serve_upload(filepath):
    """提供上传文件的访问"""
    upload_base = Path(__file__).parent / "data" / "uploads"
    return send_from_directory(upload_base, filepath)


def get_message_role(message) -> str:
    """判断消息角色类型"""
    # 检查工具调用
    if (hasattr(message, "tool_call_chunks") and message.tool_call_chunks and len(message.tool_call_chunks) > 0) or \
       (hasattr(message, "tool_calls") and message.tool_calls and len(message.tool_calls) > 0):
        return "tool_call"
    # 检查工具结果
    elif isinstance(message, ToolMessage):
        return "tool_result"
    # 普通消息
    else:
        return "human" if isinstance(message, HumanMessage) else "ai"


def stream_graph_execution(input_data, config):
    """
    通用的 graph 流式执行处理函数
    
    Args:
        input_data: 输入数据
        config: LangGraph 配置
    
    Yields:
        SSE 格式的数据字符串
    """
    import json
    
    message_id = None
    message_role = None
    
    try:
        for mode, chunk in graph.stream(
            input_data,
            config=config,
            stream_mode=["messages"],
        ):
            if mode == "messages":
                message_token, metadata = chunk
                
                # ⭐ 提取 chunk_position（用于标识消息流的最后一个 chunk）
                chunk_position = message_token.chunk_position if hasattr(message_token, "chunk_position") and message_token.chunk_position else None
                
                # 处理 message_id 变化
                if message_id != message_token.id:
                    message_role = get_message_role(message_token)
                    if message_role == "ai" and message_token.content == "":
                        continue
                    yield f'data: {json.dumps({"type": "message_change", "role": message_role})}\n\n'
                    message_id = message_token.id
                
                # 处理不同类型的消息
                if message_role == "tool_call":
                    tool_call_content = ""
                    for tool_call in message_token.tool_call_chunks:
                        tool_call_id = "" if tool_call.get("id") is None else f"🔧 Tool Call({tool_call['id']}):\n"
                        tool_call_name = "" if tool_call.get("name") is None else f"name: {tool_call['name']}\nargs: "
                        tool_call_args = tool_call['args']
                        tool_call_content += f"{tool_call_id}{tool_call_name}{tool_call_args}"
                    yield f'data: {json.dumps({"type": "token", "content": tool_call_content, "chunk_position": chunk_position})}\n\n'
                elif message_role == "tool_result":
                    if not message_token.tool_call_id and message_token.content:
                        continue
                    yield f'data: {json.dumps({"type": "token", "content": f"✅ Tool Result({message_token.tool_call_id}):\nresult: {message_token.content}", "chunk_position": chunk_position})}\n\n'
                else:
                    yield f'data: {json.dumps({"type": "token", "content": message_token.content, "chunk_position": chunk_position})}\n\n'
        
        # 流式结束
        yield f'data: {json.dumps({"type": "done"})}\n\n'
    
    except Exception as stream_error:
        logger.error(f"Stream error: {stream_error}", exc_info=True)
        yield f'data: {json.dumps({"type": "error", "error": str(stream_error)})}\n\n'


# ==================== API：流式对话 ====================
@app.route('/api/chat/stream', methods=['POST'])
def chat_stream():
    data = request.json
    thread_id = data.get('thread_id')
    message = data.get('message')
    
    if not thread_id or not message:
        return jsonify({"error": "missing thread_id or message"}), 400
    
    def generate():
        try:
            # 发送 thread_id
            yield f'data: {{"type": "thread_id", "thread_id": "{thread_id}"}}\n\n'
            
            config = {"configurable": {"thread_id": thread_id}}
            input_data = {"messages": [HumanMessage(content=message)], "config": config}
            
            yield from stream_graph_execution(input_data, config)
        
        except Exception as e:
            logger.error(f"Stream error: {e}", exc_info=True)
            yield f'data: {{"type": "error", "error": "{str(e)}"}}\n\n'
    
    return Response(generate(), mimetype='text/event-stream')


# ==================== API：初始化会话 ====================
@app.route('/api/thread/<thread_id>/init', methods=['POST'])
def init_thread(thread_id):
    """初始化新会话，创建空的 checkpoint"""
    try:
        config = {"configurable": {"thread_id": thread_id}}
        
        # 检查是否已存在
        state = graph.get_state(config)
        if state and state.values.get("messages"):
            logger.info(f"[INIT] Thread already exists: {thread_id}")
            return jsonify({"success": True, "message": "thread_already_exists"})
        
        # 使用 update_state 创建初始 checkpoint
        graph.update_state(config, create_initial_state())
        
        logger.info(f"[INIT] Thread initialized: {thread_id}")
        return jsonify({"success": True, "thread_id": thread_id})
        
    except Exception as e:
        logger.error(f"[INIT] Init thread error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== API：获取历史消息 ====================
@app.route('/api/thread/<thread_id>/messages', methods=['GET'])
def get_history(thread_id):
    try:
        config = {"configurable": {"thread_id": thread_id}}
        state = graph.get_state(config)
        
        if not state or len(state.values) == 0:
            return jsonify({"success": False, "error": "thread_not_found"}), 404
        
        messages = []
        for msg in state.values["messages"]:
            role = get_message_role(msg)
            if role == "tool_call":
                message_content = ""
                for tool_call in msg.tool_calls:
                    if tool_call['id'] == None or tool_call['name'] == None or tool_call['args'] == None:
                        continue
                    message_content += f"🔧 Tool Call({tool_call['id']}):\nname: {tool_call['name']}\nargs: {tool_call['args']}\n\n"
                messages.append({
                    "role": "tool_call",
                    "content": message_content.strip()
                })
            elif role == "tool_result":
                messages.append({
                    "role": role,
                    "content": f"✅ Tool Result({msg.tool_call_id}):\nresult: {msg.content}"
                })
            else:
                messages.append({
                    "role": role,
                    "content": msg.content
                })
        
        return jsonify({"success": True, "messages": messages})
    except Exception as e:
        logger.error(f"Get history error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== API：删除会话 ====================
@app.route('/api/thread/<thread_id>', methods=['DELETE'])
def delete_thread(thread_id):
    """删除指定会话的所有数据"""
    try:
        # SqliteSaver 没有直接的删除方法，需要手动操作数据库
        checkpointer.delete_thread(thread_id)
        logger.info(f"[DELETE] Thread deleted: {thread_id}")
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"[DELETE] Delete thread error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== API：获取素材列表 ====================
@app.route('/api/thread/<thread_id>/resources', methods=['GET'])
def get_resources(thread_id):
    """获取指定会话的素材列表"""
    try:
        # 从 checkpointer 获取最新状态
        config = {"configurable": {"thread_id": thread_id}}
        state = graph.get_state(config)
        
        if not state or not state.values:
            return jsonify({"success": True, "resources": []})
        
        # 获取 resources 字段
        resources = state.values.get("resources", [])
        
        # 转换为 JSON 可序列化格式
        resources_data = []
        for res in resources:
            if isinstance(res, dict):
                resources_data.append(res)
            elif hasattr(res, 'model_dump'):  # Pydantic model
                resources_data.append(res.model_dump())
            elif hasattr(res, '__dict__'):
                resources_data.append(res.__dict__)
        
        logger.info(f"[RESOURCES] Thread {thread_id} has {len(resources_data)} resources")
        return jsonify({"success": True, "resources": resources_data})
    except Exception as e:
        logger.error(f"[RESOURCES] Get resources error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== API：删除素材 ====================
@app.route('/api/thread/<thread_id>/resources/<resource_id>', methods=['DELETE'])
def delete_resource(thread_id, resource_id):
    """删除指定素材"""
    try:
        # 获取当前 state
        config = {"configurable": {"thread_id": thread_id}}
        state = graph.get_state(config)
        
        if not state or not state.values:
            return jsonify({"success": False, "error": "Thread not found"}), 404
        
        # 获取现有素材
        current_resources = state.values.get("resources", [])
        
        # 查找要删除的资源
        resource_to_delete = None
        updated_resources = []
        
        for res in current_resources:
            res_dict = res if isinstance(res, dict) else (res.model_dump() if hasattr(res, 'model_dump') else res.__dict__)
            if res_dict.get('resource_id') == resource_id:
                resource_to_delete = res_dict
            else:
                updated_resources.append(res)
        
        if not resource_to_delete:
            return jsonify({"success": False, "error": "Resource not found"}), 404
        
        # 删除物理文件
        resource_url = resource_to_delete.get('resource_url', '')
        if resource_url.startswith('/uploads/'):
            file_path = Path(__file__).parent / "data" / resource_url.lstrip('/')
            if file_path.exists():
                file_path.unlink()
                logger.info(f"🗑️  已删除文件: {file_path}")
        
        # 更新 state
        graph.update_state(config, {"resources": updated_resources})
        
        logger.info(f"✅ 已删除素材: {resource_id} (thread: {thread_id})")
        return jsonify({
            "success": True,
            "deleted_resource": resource_to_delete
        })
    
    except Exception as e:
        logger.error(f"❌ 删除素材失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500



def get_all_thread_ids() -> List[str]:
    """获取所有 thread_id 列表"""
    thread_ids = []
    for info in checkpointer.list(config=None):
        thread_id = info.config["configurable"]["thread_id"]
        if thread_id in thread_ids:
            continue
        thread_ids.append(thread_id)
    return thread_ids


def calculate_file_md5(file_path: str) -> str:
    """计算文件的 MD5 哈希值"""
    md5_hash = hashlib.md5()
    with open(file_path, "rb") as f:
        # 分块读取，避免大文件占用过多内存
        for chunk in iter(lambda: f.read(8192), b""):
            md5_hash.update(chunk)
    return md5_hash.hexdigest()


def find_resource_by_md5(resources: list, md5: str):
    """在资源列表中查找相同 MD5 的资源"""
    for resource in resources:
        if isinstance(resource, dict) and resource.get('resource_md5') == md5:
            return resource
    return None


# ==================== 媒体文件信息提取 ====================
def get_media_info(file_path: str) -> dict:
    """
    使用 ffprobe 获取媒体文件的详细信息
    返回: {
        "duration": int,  # 时长（毫秒）
        "resolution": str,  # 分辨率 (如 "1920x1080")
        "width": int,
        "height": int,
        "format": str,  # 格式名称
        "error": str  # 错误信息（如果有）
    }
    """
    result = {
        "duration": 0,
        "resolution": "",
        "width": 0,
        "height": 0,
        "format": "",
        "error": None
    }
    
    try:
        # 1. 获取视频流信息（分辨率）
        cmd_video = [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'v:0',  # 选择第一个视频流
            '-show_entries', 'stream=width,height',
            '-of', 'json',
            file_path
        ]
        
        video_output = subprocess.run(
            cmd_video,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if video_output.returncode == 0:
            video_data = json.loads(video_output.stdout)
            if 'streams' in video_data and len(video_data['streams']) > 0:
                stream = video_data['streams'][0]
                result['width'] = stream.get('width', 0)
                result['height'] = stream.get('height', 0)
                if result['width'] and result['height']:
                    result['resolution'] = f"{result['width']}x{result['height']}"
        
        # 2. 获取格式信息（时长、格式名称）
        cmd_format = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration,format_name',
            '-of', 'json',
            file_path
        ]
        
        format_output = subprocess.run(
            cmd_format,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if format_output.returncode == 0:
            format_data = json.loads(format_output.stdout)
            if 'format' in format_data:
                fmt = format_data['format']
                # 时长（转换为整数毫秒）
                duration_str = fmt.get('duration', '0')
                try:
                    result['duration'] = int(float(duration_str) * 1000)
                except (ValueError, TypeError):
                    result['duration'] = 0
                
                # 格式名称
                result['format'] = fmt.get('format_name', '')
        
    except subprocess.TimeoutExpired:
        result['error'] = "ffprobe 超时"
        logger.error(f"❌ ffprobe 超时: {file_path}")
    except json.JSONDecodeError as e:
        result['error'] = f"JSON 解析失败: {str(e)}"
        logger.error(f"❌ JSON 解析失败: {file_path}")
    except FileNotFoundError:
        result['error'] = "ffprobe 未安装"
        logger.error(f"❌ ffprobe 未安装，请安装 ffmpeg")
    except Exception as e:
        result['error'] = str(e)
        logger.error(f"❌ 获取媒体信息失败: {file_path}")
    
    return result


# ==================== API：上传素材 ====================
@app.route('/api/thread/<thread_id>/resources/upload', methods=['POST'])
def upload_resource(thread_id):
    """批量上传文件"""
    import time
    start_time = time.time()
    
    try:
        if 'files' not in request.files:
            return jsonify({"success": False, "error": "No file provided"}), 400
        
        files = request.files.getlist('files')
        if not files:
            return jsonify({"success": False, "error": "No file provided"}), 400
        
        logger.info(f"📤 开始上传 {len(files)} 个文件到 thread {thread_id}")
        
        # 创建线程专属目录
        thread_dir = UPLOAD_DIR / thread_id
        thread_dir.mkdir(parents=True, exist_ok=True)
        
        # 获取当前 state
        config = {"configurable": {"thread_id": thread_id}}
        state = graph.get_state(config)
        if not state or not state.values:
            return jsonify({"success": False, "error": "Thread not found"}), 404
        
        # 获取现有素材
        current_resources = state.values.get("resources", [])
        uploaded_resources = []
        
        skipped_count = 0  # 跳过的重复文件数
        
        for idx, file in enumerate(files, 1):
            if file.filename == '':
                continue
            
            # 生成临时资源ID
            temp_id = str(uuid.uuid4())
            ext = Path(file.filename).suffix.lower().lstrip('.')
            
            # 判断文件类型
            if ext in ['mp4', 'mov', 'avi', 'mkv', 'flv', 'webm', 'm4v']:
                resource_type = 'video'
            elif ext in ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'svg']:
                resource_type = 'image'
            elif ext in ['mp3', 'wav', 'aac', 'flac', 'ogg', 'm4a']:
                resource_type = 'audio'
            else:
                resource_type = 'video'  # 默认
            
            # 先保存到临时文件
            temp_path = thread_dir / f"{temp_id}_temp.{ext}"
            file.save(str(temp_path))
            
            # 计算 MD5
            file_md5 = calculate_file_md5(str(temp_path))
            
            # 检查是否已存在相同 MD5 的资源
            existing_resource = find_resource_by_md5(current_resources, file_md5)
            if existing_resource:
                # 删除临时文件，跳过上传
                temp_path.unlink()
                logger.info(f"⏭️  跳过重复文件: {file.filename}")
                skipped_count += 1
                uploaded_resources.append({
                    **existing_resource,
                    "resource_name": file.filename
                })
                continue
            
            # 不存在重复，移动到正式位置
            resource_id = str(uuid.uuid4())
            file_path = thread_dir / f"{resource_id}.{ext}"
            temp_path.rename(file_path)
            
            # 获取文件大小和媒体信息
            file_size = file_path.stat().st_size
            media_info = get_media_info(str(file_path))
            
            # 构建资源对象
            resource = {
                "resource_id": resource_id,
                "resource_type": resource_type,
                "resource_url": f"/uploads/{thread_id}/{resource_id}.{ext}",
                "resource_name": file.filename,
                "resource_md5": file_md5,
                "resource_size": file_size,
                "resource_duration": 5000 if resource_type == 'image' else media_info['duration'],
                "resource_resolution": media_info['resolution'] or 'N/A',
                "resource_description": f"用户上传的{resource_type}素材 ({file.filename})"
            }
            
            uploaded_resources.append(resource)
            logger.info(f"✅ 新增文件: {file.filename} ({file_size} bytes)")
        
        # 更新 state 中的 resources（只添加新资源）
        update_start = time.time()
        new_resources = [r for r in uploaded_resources if not find_resource_by_md5(current_resources, r.get('resource_md5'))]
        updated_resources = current_resources + new_resources
        graph.update_state(config, {"resources": updated_resources})
        update_time = time.time() - update_start
        
        total_time = time.time() - start_time
        logger.info(f"✅ 上传完成: 总计 {len(files)} 个文件, 新增 {len(new_resources)} 个, 跳过 {skipped_count} 个重复 (总耗时: {total_time:.2f}s, 更新state: {update_time:.2f}s)")
        
        return jsonify({
            "success": True,
            "resources": uploaded_resources,
            "total": len(uploaded_resources),
            "new_count": len(new_resources),
            "skipped_count": skipped_count
        })
    
    except Exception as e:
        logger.error(f"❌ 上传文件失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

# ==================== API：获取所有会话列表 ====================
@app.route('/api/threads', methods=['GET'])
def list_threads():
    """获取所有会话列表（用于侧边栏）"""
    try:
        threads = []
        for thread_id in get_all_thread_ids():
            state = graph.get_state({"configurable": {"thread_id": thread_id}})
            # 获取标题
            title = "新对话" if not state.values.get("messages") else state.values.get("messages")[0].content
            if len(title) > 10:
                title = title[:10] + "..."
            
            updated_at = state.created_at
            
            threads.append({
                "thread_id": thread_id,
                "title": title,
                "updated_at": updated_at
            })
        return jsonify({"success": True, "threads": threads})
    except Exception as e:
        logger.error(f"List threads error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== 启动 ====================
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)