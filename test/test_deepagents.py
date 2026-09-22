"""离线集成测试：使用真实 Deep Agents/SQLite 和脚本模型，不调用付费模型。"""
import asyncio
import json
import os
import tempfile
import unittest
from contextlib import AsyncExitStack
from functools import partial
from unittest.mock import patch

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.store.sqlite.aio import AsyncSqliteStore
from langgraph.types import Command
from pydantic import Field

from src.agents.events import MessageStream, serialize_message
from src.agents.runtime import AgentRuntime, RunConflict, validate_decisions
from src.agents.workflow import create_jianying_agent
from src.utils import resource_catalog


class ScriptedModel(BaseChatModel):
    responses: list[AIMessage] = Field(default_factory=list)
    calls: list = Field(default_factory=list)
    bound_tools: list = Field(default_factory=list)
    index: int = 0

    @property
    def _llm_type(self):
        return "capcut-offline-test"

    def bind_tools(self, tools, **kwargs):
        self.bound_tools.append([t.name if hasattr(t, "name") else t.get("name") for t in tools])
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.calls.append(messages)
        if len(messages) == 1 and "请总结对话历史" in messages[0].content:
            message = AIMessage(content="已完成旧任务，保留工程信息继续新任务。")
        else:
            if self.index >= len(self.responses):
                raise AssertionError("Unexpected model call")
            message = self.responses[self.index]
            self.index += 1
        return ChatResult(generations=[ChatGeneration(message=message)])


def call(name, args, id="call-1"):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": id}])


class DeepAgentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.stack = AsyncExitStack()
        self.saver = await self.stack.enter_async_context(AsyncSqliteSaver.from_conn_string(":memory:"))
        self.store = await self.stack.enter_async_context(AsyncSqliteStore.from_conn_string(":memory:"))
        await self.store.setup()
        self.config = {"configurable": {"thread_id": "test"}, "recursion_limit": 100}

    async def asyncTearDown(self):
        await self.stack.aclose()

    async def agent(self, model, tools=(), **kwargs):
        kwargs.setdefault("summary_trigger", ("tokens", 1000000))
        return await create_jianying_agent(self.saver, self.store, model=model, tools=list(tools), **kwargs)

    async def test_planning_files_skills_and_resource_context(self):
        model = ScriptedModel(responses=[
            call("write_todos", {"todos": [{"content": "剪辑开场", "status": "in_progress"}]}),
            call("write_file", {"file_path": "/workspace/plan.md", "content": "开场三秒"}, "file"),
            call("read_file", {"file_path": "/skills/capcut-editing/SKILL.md"}, "skill"),
            AIMessage(content="计划已保存"), AIMessage(content="当前素材已更新"),
        ])
        graph = await self.agent(model)
        await graph.ainvoke({"messages": [HumanMessage(content="规划剪辑")],
                             "resources": [{"resource_name": "before.mp4"}]}, self.config)
        state = (await graph.aget_state(self.config)).values
        self.assertEqual(state["todos"][0]["content"], "剪辑开场")
        self.assertIn("/workspace/plan.md", state["files"])
        self.assertEqual([s["name"] for s in state["skills_metadata"]], ["capcut-editing"])
        self.assertTrue(any("# 剪映视频剪辑" in m.content for m in state["messages"] if isinstance(m, ToolMessage)))
        self.assertIn("before.mp4", str(model.calls[0][0].content))
        await graph.aupdate_state(self.config, {"resources": [{"resource_name": "after.mp4"}]})
        await graph.ainvoke({"messages": [HumanMessage(content="再看素材")]}, self.config)
        self.assertIn("after.mp4", str(model.calls[-1][0].content))
        self.assertNotIn("before.mp4", str(model.calls[-1][0].content))
        other = await graph.aget_state({"configurable": {"thread_id": "other"}})
        self.assertFalse(other.values)

    async def test_subagent_isolated_context_and_read_only_tools(self):
        @tool
        def delete_project(project_id: str) -> str:
            """删除测试工程。"""
            raise AssertionError("Subagent must not delete projects")

        model = ScriptedModel(responses=[
            call("task", {"subagent_type": "resource-analyst", "description": "分析素材组合"}),
            AIMessage(content="子 Agent 建议先开场再结尾"),
            AIMessage(content="主 Agent 整理结果"),
        ])
        graph = await self.agent(model, [delete_project])
        result = await graph.ainvoke({"messages": [HumanMessage(content="父会话专属文字")],
                                      "resources": [{"resource_name": "clip.mp4"}]}, self.config)
        self.assertEqual(result["messages"][-1].content, "主 Agent 整理结果")
        child = model.calls[1]
        self.assertNotIn("父会话专属文字", str(child))
        self.assertIn("clip.mp4", str(child[0].content))
        self.assertNotIn("delete_project", model.bound_tools[1])

    async def test_summary_keeps_history_and_offloads_to_files(self):
        model = ScriptedModel(responses=[AIMessage(content="继续执行")])
        graph = await self.agent(model, summary_trigger=("messages", 4), summary_keep=("messages", 2))
        history = [HumanMessage(content="旧请求一"), AIMessage(content="旧答复一"),
                   HumanMessage(content="旧请求二"), AIMessage(content="旧答复二"), HumanMessage(content="继续")]
        await graph.ainvoke({"messages": history}, self.config)
        state = (await graph.aget_state(self.config)).values
        self.assertTrue(state["_summarization_event"])
        self.assertTrue(any("conversation_history" in p for p in state["files"]))
        self.assertIn("旧请求一", [m.content for m in state["messages"]])
        self.assertEqual([m.content for m in state["messages"]],
                         ["旧请求一", "旧答复一", "旧请求二", "旧答复二", "继续", "继续执行"])
        self.assertNotIn("旧请求一", [m.content for m in model.calls[-1]])

    async def test_large_tool_result_is_offloaded(self):
        @tool
        def get_project_info() -> str:
            """返回较长的测试工程描述。"""
            return "large-result-marker " * 10000

        model = ScriptedModel(responses=[call("get_project_info", {}), AIMessage(content="检查完成")])
        graph = await self.agent(model, [get_project_info])
        await graph.ainvoke({"messages": [HumanMessage(content="检查工程")]}, self.config)
        state = (await graph.aget_state(self.config)).values
        self.assertTrue(any("large_tool_results" in p for p in state["files"]))
        result = next(m for m in model.calls[-1] if isinstance(m, ToolMessage))
        self.assertLess(len(result.content), 25000)

    async def test_approval_edit_and_reject(self):
        applied = []

        @tool
        def delete_project(project_id: str) -> str:
            """删除测试工程。"""
            applied.append(project_id)
            return "删除成功"

        model = ScriptedModel(responses=[call("delete_project", {"project_id": "original"}),
                                        AIMessage(content="已处理"),
                                        call("delete_project", {"project_id": "rejected"}, "second"),
                                        AIMessage(content="遵循拒绝")])
        graph = await self.agent(model, [delete_project])
        await graph.ainvoke({"messages": [HumanMessage(content="删除工程")]}, self.config)
        state = await graph.aget_state(self.config)
        self.assertFalse(applied)
        self.assertEqual(len(state.interrupts), 1)
        with self.assertRaises(ValueError):
            validate_decisions(state, {})
        id = state.interrupts[0].id
        command = validate_decisions(state, {id: {"decisions": [{"type": "edit", "edited_action": {
            "name": "delete_project", "args": {"project_id": "edited"}}}]}})
        await graph.ainvoke(command, self.config)
        self.assertEqual(applied, ["edited"])
        await graph.ainvoke({"messages": [HumanMessage(content="再次删除")]}, self.config)
        state = await graph.aget_state(self.config)
        await graph.ainvoke(Command(resume={state.interrupts[0].id: {"decisions": [
            {"type": "reject", "message": "保留工程"}]}}), self.config)
        self.assertEqual(applied, ["edited"])
        self.assertFalse((await graph.aget_state(self.config)).interrupts)


class RuntimeTests(unittest.TestCase):
    def test_memory_files_and_pending_approval_survive_restart(self):
        applied = []

        @tool
        async def delete_project(project_id: str) -> str:
            """删除测试工程。"""
            applied.append(project_id)
            return "ok"

        with tempfile.TemporaryDirectory() as directory:
            first = ScriptedModel(responses=[
                call("write_file", {"file_path": "/workspace/plan.md", "content": "计划"}),
                call("edit_file", {"file_path": "/memories/AGENTS.md", "old_string": "暂无记录。",
                                   "new_string": "偏好竖屏、自然转场"}, "memory"),
                call("delete_project", {"project_id": "draft"}, "delete"),
            ])
            config = {"configurable": {"thread_id": "one"}}
            runtime = AgentRuntime(directory, agent_factory=partial(create_jianying_agent, model=first, tools=[delete_project]))
            try:
                events = list(runtime.stream({"messages": [HumanMessage(content="我一直偏好竖屏、自然转场。删除这个草稿。")]}, config))
                self.assertEqual(events[-1]["type"], "done")
                self.assertTrue(runtime.get_state(config).interrupts)
                memory_result = next(m for m in runtime.get_state(config).values["messages"]
                                     if isinstance(m, ToolMessage) and m.tool_call_id == "memory")
                self.assertNotEqual(memory_result.status, "error")
            finally:
                runtime.close()
            second = ScriptedModel(responses=[
                AIMessage(content="恢复完成"), AIMessage(content="新会话读取记忆"),
                call("edit_file", {"file_path": "/memories/AGENTS.md", "old_string": "偏好竖屏",
                                   "new_string": "偏好横屏"}, "update-memory"),
                AIMessage(content="偏好已更新"), AIMessage(content="原会话读取更新后的偏好"),
                AIMessage(content="删除会话后仍保留偏好"),
                call("edit_file", {"file_path": "/memories/AGENTS.md", "old_string": "偏好横屏、自然转场",
                                   "new_string": ""}, "forget-memory"),
                AIMessage(content="偏好已删除"), AIMessage(content="已不再使用旧偏好"),
            ])
            runtime = AgentRuntime(directory, agent_factory=partial(create_jianying_agent, model=second, tools=[delete_project]))
            try:
                snapshot = runtime.get_state(config)
                self.assertIn("/workspace/plan.md", snapshot.values["files"])
                self.assertFalse(applied)
                with self.assertRaises(RunConflict):
                    list(runtime.stream({"messages": [HumanMessage(content="绕过审批")]}, config))
                decisions = {snapshot.interrupts[0].id: {"decisions": [{"type": "approve"}]}}
                list(runtime.stream(None, config, decisions=decisions))
                self.assertEqual(applied, ["draft"])
                other = {"configurable": {"thread_id": "two"}}
                list(runtime.stream({"messages": [HumanMessage(content="我的偏好")]}, other))
                self.assertIn("偏好竖屏", str(second.calls[-1][0].content))
                self.assertNotIn("/workspace/plan.md", runtime.get_state(other).values.get("files", {}))
                list(runtime.stream({"messages": [HumanMessage(content="以后统一用横屏，转场风格不变")]}, other))
                # 原会话也重新读取 Store，不继续使用 checkpoint 里的旧 memory_contents。
                list(runtime.stream({"messages": [HumanMessage(content="再读偏好")]}, config))
                self.assertIn("偏好横屏", str(second.calls[-1][0].content))
                self.assertNotIn("偏好竖屏", str(second.calls[-1][0].content))
                runtime.delete_thread("one")
                third = {"configurable": {"thread_id": "three"}}
                list(runtime.stream({"messages": [HumanMessage(content="我的偏好")]}, third))
                self.assertIn("偏好横屏", str(second.calls[-1][0].content))
                list(runtime.stream({"messages": [HumanMessage(content="忘记我的画幅和转场偏好")]}, other))
                list(runtime.stream({"messages": [HumanMessage(content="还有旧偏好吗")]}, third))
                self.assertNotIn("偏好横屏", str(second.calls[-1][0].content))
                self.assertNotIn("自然转场", str(second.calls[-1][0].content))
            finally:
                runtime.close()


class CatalogAndStreamTests(unittest.TestCase):
    def test_catalog_is_dynamic_metadata_only_and_paginated(self):
        catalog = {"特效": {"柔光": {"desc": "柔和画面", "content": "RAW_RENDER_JSON", "url": "PRIVATE_URL"},
                            "锐化": {"desc": "清晰画面", "content": "OTHER_JSON", "url": "OTHER_URL"}}}
        with patch.object(resource_catalog, "load_catalog", side_effect=lambda: catalog):
            result = resource_catalog.search_resources(limit=1)
            self.assertEqual(result["total"], 2)
            self.assertEqual(result["next_offset"], 1)
            self.assertEqual(set(result["items"][0]), {"category", "name", "desc"})
            self.assertNotIn("RAW_RENDER_JSON", json.dumps(result))
            self.assertNotIn("PRIVATE_URL", json.dumps(result))
            del catalog["特效"]["柔光"]
            self.assertEqual(resource_catalog.search_resources()["total"], 1)
            with self.assertRaises(ValueError):
                resource_catalog.get_resource("特效", "柔光")
            self.assertIn("error", resource_catalog.search_resources(limit=101))

    def test_stream_filters_internal_messages_and_keeps_text_with_tools(self):
        stream = MessageStream()
        self.assertEqual(list(stream.feed((AIMessage(content="内部摘要"), {"lc_source": "summarization"}))), [])
        child = list(stream.feed((AIMessage(content="子 Agent 建议"), {}), ("tools:child",)))
        self.assertEqual(child, [])
        message = AIMessage(id="answer", content="先规划，再执行。", tool_calls=[
            {"name": "write_todos", "args": {"todos": []}, "id": "plan"}])
        main = list(stream.feed((message, {})))
        self.assertEqual(main[0]["message"], serialize_message(message))
        self.assertEqual(main[0]["message"]["content"], "先规划，再执行。")
        self.assertEqual(main[0]["message"]["tool_calls"][0]["name"], "write_todos")
        self.assertFalse(main[0]["delta"])

    def test_stream_preserves_empty_end_and_interleaved_tool_indexes(self):
        stream = MessageStream()
        chunk = AIMessageChunk(id="parallel", content="**检查**", tool_call_chunks=[
            {"index": 1, "id": "track", "name": "get_tracks", "args": '{"project_id":'},
            {"index": 0, "id": "project", "name": "get_project_info", "args": '{"project_id":'},
        ])
        event = list(stream.feed((chunk, {})))[0]
        self.assertTrue(event["delta"])
        self.assertEqual([call["index"] for call in event["message"]["tool_calls"]], [1, 0])
        self.assertEqual(event["message"]["content"], "**检查**")
        ending = list(stream.feed((AIMessageChunk(id="parallel", content="", chunk_position="last"), {})))[0]
        self.assertTrue(ending["complete"])
        self.assertEqual(ending["message"]["id"], "parallel")
        error = list(stream.feed((ToolMessage(id="failed", tool_call_id="track", content="没有找到", status="error"), {})))[0]
        self.assertEqual(error["message"]["status"], "error")


if __name__ == "__main__":
    unittest.main()
