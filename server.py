"""
Flask Server - 提供 SSE 流式对话接口
"""
import os
import logging
import atexit
import subprocess
import json
import uuid
import hashlib
from pathlib import Path
from flask import Flask, request, Response, jsonify, send_from_directory
from flask_cors import CORS
from src.agents.runtime import AgentRuntime, RunConflict, public_state, validate_decisions
from src.agents.events import message_text, serialize_message
from src.agents.models import create_initial_state
from langchain_core.messages import HumanMessage
from typing import List
# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 新版状态单独保存，不读取或迁移旧 checkpoints.db。
DATA_DIR = Path(os.getenv("CAPCUT_DATA_DIR", Path(__file__).parent / "data")).resolve()
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ==================== Flask App ====================
app = Flask(__name__, static_folder='static', static_url_path='/static')
CORS(app)

# 延迟加载模型/MCP；异步运行时同时管理 checkpoint 和跨会话记忆。
graph = AgentRuntime(DATA_DIR)
atexit.register(graph.close)


@app.errorhandler(RunConflict)
def handle_run_conflict(error):
    return jsonify({"success": False, "error": str(error)}), 409


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
    upload_base = UPLOAD_DIR
    return send_from_directory(upload_base, filepath)


def stream_graph_execution(subscription):
    try:
        yield ': connected\n\n'
        for event in graph.consume(subscription):
            if event["type"] == "heartbeat":
                yield ': keep-alive\n\n'
            else:
                yield f'data: {json.dumps(event, ensure_ascii=False)}\n\n'
    except Exception as error:
        logger.error("Agent execution failed", exc_info=True)
        yield f'data: {json.dumps({"type": "error", "error": str(error)}, ensure_ascii=False)}\n\n'


def stream_response(thread_id, input_data=None, *, decisions=None, subscribe=False):
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 200}
    subscription = graph.subscribe(config) if subscribe else graph.start_stream(input_data, config, decisions=decisions)
    def generate():
        yield from stream_graph_execution(subscription)
    return Response(generate(), mimetype="text/event-stream", headers={
        "Cache-Control": "no-cache", "X-Accel-Buffering": "no",
    })


@app.route('/api/chat/stream', methods=['POST'])
def chat_stream():
    data = request.get_json(silent=True) or {}
    thread_id, message = data.get('thread_id'), data.get('message')
    if not isinstance(thread_id, str) or not isinstance(message, str) or not message.strip():
        return jsonify({"error": "missing thread_id or message"}), 400
    message_id = data.get("message_id") or str(uuid.uuid4())
    if not isinstance(message_id, str) or len(message_id) > 128:
        return jsonify({"error": "invalid message_id"}), 400
    snapshot = graph.get_state({"configurable": {"thread_id": thread_id}})
    if snapshot.interrupts:
        return jsonify({"error": "请先处理待审批操作", **public_state(snapshot)}), 409
    return stream_response(thread_id, {"messages": [HumanMessage(content=message, id=message_id)]})


@app.route('/api/thread/<thread_id>/resume', methods=['POST'])
def resume_thread(thread_id):
    decisions = (request.get_json(silent=True) or {}).get("decisions")
    snapshot = graph.get_state({"configurable": {"thread_id": thread_id}})
    try:
        validate_decisions(snapshot, decisions)
    except ValueError as error:
        return jsonify({"success": False, "error": str(error)}), 400
    return stream_response(thread_id, decisions=decisions)


@app.route('/api/thread/<thread_id>/agent-state', methods=['GET'])
def get_agent_state(thread_id):
    snapshot = graph.get_state({"configurable": {"thread_id": thread_id}})
    return jsonify({"success": True, **public_state(snapshot), "run": graph.activity(thread_id)})


@app.route('/api/thread/<thread_id>/events', methods=['GET'])
def subscribe_thread(thread_id):
    return stream_response(thread_id, subscribe=True)


@app.route('/api/thread/<thread_id>/read', methods=['POST'])
def mark_thread_read(thread_id):
    run_id = (request.get_json(silent=True) or {}).get("run_id")
    return jsonify({"success": True, "run": graph.mark_read(thread_id, run_id)})


# ==================== API：初始化会话 ====================
@app.route('/api/thread/<thread_id>/init', methods=['POST'])
def init_thread(thread_id):
    """初始化新会话，创建空的 checkpoint"""
    try:
        config = {"configurable": {"thread_id": thread_id}}
        
        # 检查是否已存在
        state = graph.get_state(config)
        if state and state.values:
            logger.info(f"[INIT] Thread already exists: {thread_id}")
            return jsonify({"success": True, "message": "thread_already_exists"})
        
        # 使用 update_state 创建初始 checkpoint
        graph.update_state(config, create_initial_state())
        
        logger.info(f"[INIT] Thread initialized: {thread_id}")
        return jsonify({"success": True, "thread_id": thread_id})
        
    except RunConflict:
        raise
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
        
        messages = [serialize_message(msg, fallback_id=f"history-{index}")
                    for index, msg in enumerate(state.values.get("messages", []))]
        
        return jsonify({"success": True, "messages": messages})
    except Exception as e:
        logger.error(f"Get history error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== API：删除会话 ====================
@app.route('/api/thread/<thread_id>', methods=['DELETE'])
def delete_thread(thread_id):
    """删除指定会话的所有数据"""
    try:
        graph.delete_thread(thread_id)
        logger.info(f"[DELETE] Thread deleted: {thread_id}")
        return jsonify({"success": True})
    except RunConflict:
        raise
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
        
        # 先通过运行时校验并保存状态，执行中或待审批时保留原文件。
        graph.update_state(config, {"resources": updated_resources})

        # 删除物理文件
        resource_url = resource_to_delete.get('resource_url', '')
        if resource_url.startswith('/uploads/'):
            file_path = DATA_DIR / resource_url.lstrip('/')
            if file_path.exists():
                file_path.unlink()
                logger.info(f"🗑️  已删除文件: {file_path}")
        
        logger.info(f"✅ 已删除素材: {resource_id} (thread: {thread_id})")
        return jsonify({
            "success": True,
            "deleted_resource": resource_to_delete
        })
    
    except RunConflict:
        raise
    except Exception as e:
        logger.error(f"❌ 删除素材失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500



def get_all_thread_ids() -> List[str]:
    return graph.list_threads()


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
    created_paths = []
    
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
            created_paths.append(temp_path)
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
            created_paths.append(file_path)
            
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
        created_paths.clear()
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
    
    except RunConflict:
        raise
    except Exception as e:
        logger.error(f"❌ 上传文件失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        # 状态提交失败（包括待审批/执行冲突）时，不留下未登记的上传文件。
        for path in created_paths:
            path.unlink(missing_ok=True)

# ==================== API：获取所有会话列表 ====================
@app.route('/api/threads', methods=['GET'])
def list_threads():
    """获取所有会话列表（用于侧边栏）"""
    try:
        threads = []
        for thread_id in get_all_thread_ids():
            state = graph.get_state({"configurable": {"thread_id": thread_id}})
            # 获取标题
            history = state.values.get("messages", [])
            title = message_text(history[0]) if history else "新对话"
            if len(title) > 10:
                title = title[:10] + "..."
            
            activity = graph.activity(thread_id)
            updated_at = activity.get("last_chat_at") or activity.get("created_at") or state.created_at
            
            threads.append({
                "thread_id": thread_id,
                "title": title,
                "updated_at": updated_at,
                "run_id": activity.get("run_id"),
                "run_status": activity.get("run_status", "idle"),
                "running": activity.get("running", False),
                "unread": activity.get("unread", False),
            })
        return jsonify({"success": True, "threads": threads})
    except Exception as e:
        logger.error(f"List threads error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== 启动 ====================
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5001, debug=True)
