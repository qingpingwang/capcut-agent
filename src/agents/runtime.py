"""为 Flask 提供同步入口，Deep Agents、MCP 和 SQLite 在同一异步循环运行。"""
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4
from contextlib import AsyncExitStack
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Thread

from deepagents.backends.utils import create_file_data
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.store.sqlite.aio import AsyncSqliteStore
from langgraph.types import Command

from .events import MessageStream, accumulate_message
from .workflow import MEMORY_NAMESPACE, MEMORY_PATH, create_jianying_agent

DEFAULT_MEMORY = "# 长期记忆\n\n暂无记录。\n"
ACTIVITY_NAMESPACE = ("app", "thread_activity")
END = object()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


@dataclass
class LiveRun:
    id: str
    thread_id: str
    messages: dict = field(default_factory=dict)
    subscribers: set = field(default_factory=set)
    task: object = None

    def emit(self, event):
        if isinstance(event, dict) and event.get("type") == "message":
            key = event["message"]["id"]
            self.messages[key] = accumulate_message(self.messages.get(key), event)
        for queue in list(self.subscribers):
            try:
                queue.put_nowait(event)
            except Full:
                # 慢连接重新订阅即可获取完整快照，不能让它无限占用内存或阻塞执行。
                self.subscribers.discard(queue)
                while True:
                    try:
                        queue.get_nowait()
                    except Empty:
                        break
                queue.put_nowait({"type": "error", "error": "连接落后，请重新连接"})
                queue.put_nowait(END)


class RunConflict(ValueError):
    """同一会话正在执行，或有待处理审批。"""


def pending_interrupts(snapshot):
    return [{"id": item.id, **item.value} for item in snapshot.interrupts]


def public_state(snapshot):
    return {"interrupts": pending_interrupts(snapshot)}


def validate_decisions(snapshot, decisions):
    """要求每个暂停操作都有且只有一个合法决定，防止过期/错位审批。"""
    pending = pending_interrupts(snapshot)
    if not pending:
        raise ValueError("当前没有待审批操作")
    if not isinstance(decisions, dict) or set(decisions) != {item["id"] for item in pending}:
        raise ValueError("审批已变化，请刷新后重新处理")
    for item in pending:
        response = decisions[item["id"]]
        choices = response.get("decisions") if isinstance(response, dict) else None
        actions = item["action_requests"]
        if not isinstance(choices, list) or len(choices) != len(actions):
            raise ValueError("每个工具调用都需要一个审批决定")
        for action, review, choice in zip(actions, item["review_configs"], choices):
            if not isinstance(choice, dict) or choice.get("type") not in review["allowed_decisions"]:
                raise ValueError("不支持的审批决定")
            if choice["type"] == "edit":
                edited = choice.get("edited_action", {})
                if edited.get("name") != action["name"] or not isinstance(edited.get("args"), dict):
                    raise ValueError("仅允许编辑当前工具的 JSON 参数，不能替换工具")
    return Command(resume=decisions)


class AgentRuntime:
    def __init__(self, data_dir, *, agent_factory=create_jianying_agent):
        self.data_dir = Path(data_dir)
        self.agent_factory = agent_factory
        self.loop = asyncio.new_event_loop()
        self.thread = Thread(target=self.loop.run_forever, name="deepagents-runtime", daemon=True)
        self.thread.start()
        self.graph = None
        self.stack = None
        self._init_lock = asyncio.Lock()
        self._activity_lock = asyncio.Lock()
        self._locks = {}
        self._closed = False
        self._runs = {}

    async def _ready(self):
        async with self._init_lock:
            if self.graph is not None:
                return
            self.data_dir.mkdir(parents=True, exist_ok=True)
            stack = AsyncExitStack()
            try:
                self.checkpointer = await stack.enter_async_context(
                    AsyncSqliteSaver.from_conn_string(str(self.data_dir / "deepagents.db")))
                self.store = await stack.enter_async_context(
                    AsyncSqliteStore.from_conn_string(str(self.data_dir / "memory.db")))
                await self.checkpointer.setup()
                await self.store.setup()
                if await self.store.aget(MEMORY_NAMESPACE, MEMORY_PATH) is None:
                    await self.store.aput(MEMORY_NAMESPACE, MEMORY_PATH, create_file_data(DEFAULT_MEMORY))
                graph = await self.agent_factory(self.checkpointer, self.store)
                # 服务重启不宣称旧进程仍在执行；已保存的原生消息和审批仍可恢复。
                offset = 0
                while items := await self.store.asearch(ACTIVITY_NAMESPACE, limit=100, offset=offset):
                    for item in items:
                        if item.value.get("run_status") == "running":
                            await self.store.aput(ACTIVITY_NAMESPACE, item.key, {
                                **item.value, "run_status": "failed", "error": "服务重启，执行已中断。已完成的内容已保留。",
                            })
                    offset += len(items)
                self.graph = graph
                self.stack = stack
            except BaseException:
                await stack.aclose()
                raise

    def _submit(self, coroutine):
        if self._closed:
            coroutine.close()
            raise RuntimeError("Agent runtime is closed")
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop)

    async def _get_state(self, config):
        await self._ready()
        return await self.graph.aget_state(config)

    def get_state(self, config):
        return self._submit(self._get_state(config)).result()

    def _lock(self, config):
        return self._locks.setdefault(config["configurable"]["thread_id"], asyncio.Lock())

    async def _activity(self, thread_id):
        item = await self.store.aget(ACTIVITY_NAMESPACE, thread_id)
        value = dict(item.value) if item else {}
        value["running"] = value.get("run_status") == "running"
        value["unread"] = bool(value.get("run_id") and not value["running"]
                               and value["run_id"] != value.get("read_run_id"))
        return value

    async def _save_activity(self, thread_id, *, expected_run_id=None, **patch):
        # Store 的 get + put 不是原子更新；已读请求可能和下一轮开始/结束交错。
        async with self._activity_lock:
            item = await self.store.aget(ACTIVITY_NAMESPACE, thread_id)
            value = item.value if item else {}
            if expected_run_id and (value.get("run_id") != expected_run_id or value.get("run_status") == "running"):
                return
            await self.store.aput(ACTIVITY_NAMESPACE, thread_id, {**value, **patch})

    def activity(self, thread_id):
        async def read():
            await self._ready()
            return await self._activity(thread_id)
        return self._submit(read()).result()

    def mark_read(self, thread_id, run_id):
        async def mark():
            await self._ready()
            if run_id:
                await self._save_activity(thread_id, expected_run_id=run_id, read_run_id=run_id)
            return await self._activity(thread_id)
        return self._submit(mark()).result()

    async def _update_state(self, config, values):
        await self._ready()
        lock = self._lock(config)
        if lock.locked():
            raise RunConflict("会话正在执行，请稍后再修改素材或会话")
        async with lock:
            snapshot = await self.graph.aget_state(config)
            if snapshot.interrupts:
                raise RunConflict("请先处理待审批操作")
            result = await self.graph.aupdate_state(config, values, as_node="__start__")
            thread_id = config["configurable"]["thread_id"]
            if not await self.store.aget(ACTIVITY_NAMESPACE, thread_id):
                await self._save_activity(thread_id, created_at=now_iso(), run_status="idle")
            return result

    def update_state(self, config, values):
        return self._submit(self._update_state(config, values)).result()

    async def _list_threads(self):
        await self._ready()
        # 只读 SQLite 主键索引，避免为列出会话解码每个历史 checkpoint 的消息与文件。
        async with self.checkpointer.lock:
            async with self.checkpointer.conn.execute(
                "SELECT DISTINCT thread_id FROM checkpoints WHERE checkpoint_ns = '' ORDER BY thread_id"
            ) as cursor:
                return [row[0] for row in await cursor.fetchall()]

    def list_threads(self):
        return self._submit(self._list_threads()).result()

    async def _delete_thread(self, thread_id):
        await self._ready()
        config = {"configurable": {"thread_id": thread_id}}
        lock = self._lock(config)
        if lock.locked():
            raise RunConflict("会话正在执行，请稍后删除")
        async with lock:
            await self.checkpointer.adelete_thread(thread_id)
            async with self._activity_lock:
                await self.store.adelete(ACTIVITY_NAMESPACE, thread_id)

    def delete_thread(self, thread_id):
        return self._submit(self._delete_thread(thread_id)).result()

    def _subscribe_run(self, run):
        queue = Queue(maxsize=256)
        # 快照放在独立列表中，避免长任务重连时一次填满订阅队列。
        replay = [{"type": "message", "message": message, "delta": False,
                   "complete": message.get("complete", False)} for message in run.messages.values()]
        run.subscribers.add(queue)
        return run, queue, replay

    async def _start(self, input_data, config, decisions):
        await self._ready()
        lock = self._lock(config)
        if lock.locked():
            raise RunConflict("当前会话已有执行中的请求")
        await lock.acquire()
        try:
            snapshot = await self.graph.aget_state(config)
            if decisions is not None:
                payload = validate_decisions(snapshot, decisions)
            elif snapshot.interrupts:
                raise RunConflict("请先处理待审批操作，再发送新消息")
            else:
                payload = input_data
            thread_id = config["configurable"]["thread_id"]
            run = LiveRun(str(uuid4()), thread_id)
            await self._save_activity(thread_id, run_id=run.id, run_status="running", error=None,
                                      last_chat_at=now_iso())
            self._runs[thread_id] = run
            subscription = self._subscribe_run(run)
            run.task = asyncio.create_task(self._produce(run, payload, config, lock))
            return subscription
        except BaseException:
            lock.release()
            raise

    async def _produce(self, run, payload, config, lock):
        failure = None
        snapshot = None
        try:
            messages = MessageStream()
            async for namespace, chunk in self.graph.astream(
                payload, config=config, stream_mode="messages", subgraphs=True,
            ):
                for event in messages.feed(chunk, namespace):
                    run.emit(event)
            snapshot = await self.graph.aget_state(config)
        except asyncio.CancelledError:
            failure = "服务停止，执行已中断。已完成的内容已保留。"
        except Exception as exc:
            failure = str(exc)
        finally:
            try:
                status = "failed" if failure else "interrupted" if snapshot.interrupts else "completed"
                await self._save_activity(run.thread_id, run_status=status, error=failure, last_chat_at=now_iso())
                activity = await self._activity(run.thread_id)
                if failure:
                    run.emit({"type": "error", "error": failure, "run": activity})
                else:
                    run.emit({"type": "done", **public_state(snapshot), "run": activity})
            finally:
                run.emit(END)
                run.messages.clear()
                run.subscribers.clear()
                self._runs.pop(run.thread_id, None)
                lock.release()

    def start_stream(self, input_data, config, *, decisions=None):
        return self._submit(self._start(input_data, config, decisions)).result()

    def subscribe(self, config):
        async def attach():
            await self._ready()
            thread_id = config["configurable"]["thread_id"]
            run = self._runs.get(thread_id)
            if run:
                return self._subscribe_run(run)
            snapshot = await self.graph.aget_state(config)
            queue = Queue()
            queue.put({"type": "done", **public_state(snapshot), "run": await self._activity(thread_id)})
            queue.put(END)
            return None, queue, []
        return self._submit(attach()).result()

    def consume(self, subscription):
        run, queue, replay = subscription
        try:
            yield from replay
            while True:
                try:
                    event = queue.get(timeout=15)
                except Empty:
                    yield {"type": "heartbeat"}
                    continue
                if event is END:
                    break
                yield event
        finally:
            if run and not self._closed:
                async def detach():
                    run.subscribers.discard(queue)
                self._submit(detach()).result()

    def stream(self, input_data, config, *, decisions=None):
        yield from self.consume(self.start_stream(input_data, config, decisions=decisions))

    def close(self):
        if self._closed:
            return

        async def shutdown():
            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if self.stack is not None:
                await self.stack.aclose()

        self._submit(shutdown()).result(timeout=10)
        self._closed = True
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=10)
        self.loop.close()
