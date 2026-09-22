"""Flask API 与真实异步 Deep Agents 状态库的集成测试。"""
import importlib
import io
import json
import tempfile
import unittest
from functools import partial
from pathlib import Path
from unittest.mock import patch

from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from src.agents.runtime import AgentRuntime
from src.agents.workflow import create_jianying_agent
from test_deepagents import ScriptedModel, call


class AgentApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.applied = []

        @tool
        async def copy_project_to_jianying(project_id: str, copy_resource: bool = False) -> dict:
            """同步测试草稿。"""
            self.applied.append((project_id, copy_resource))
            return {"success": True, "jianying_path": "test-draft"}

        self.model = ScriptedModel(responses=[
            call("write_todos", {"todos": [{"content": "准备草稿", "status": "completed"}]}),
            call("write_file", {"file_path": "/workspace/plan.md", "content": "剪辑计划"}, "file"),
            call("copy_project_to_jianying", {"project_id": "draft", "copy_resource": True}, "sync"),
            AIMessage(content="草稿已同步"),
        ])
        self.runtime = AgentRuntime(self.directory.name, agent_factory=partial(
            create_jianying_agent, model=self.model, tools=[copy_project_to_jianying]))
        with patch("src.agents.runtime.AgentRuntime", return_value=self.runtime):
            self.server = importlib.import_module("server")
        self.patchers = [patch.object(self.server, "graph", self.runtime),
                         patch.object(self.server, "DATA_DIR", Path(self.directory.name)),
                         patch.object(self.server, "UPLOAD_DIR", Path(self.directory.name) / "uploads")]
        for item in self.patchers:
            item.start()
        self.client = self.server.app.test_client()

    def tearDown(self):
        for item in reversed(self.patchers):
            item.stop()
        self.runtime.close()
        self.directory.cleanup()

    @staticmethod
    def events(response):
        return [json.loads(line[6:]) for line in response.get_data(as_text=True).splitlines() if line.startswith('data: ')]

    def test_stream_approval_refresh_and_resume(self):
        self.assertEqual(self.client.post('/api/thread/demo/init').status_code, 200)
        response = self.client.post('/api/chat/stream', json={"thread_id": "demo", "message": "交付草稿"})
        events = self.events(response)
        self.assertEqual(events[-1]["type"], "done")
        self.assertTrue(any(e.get("message", {}).get("tool_calls") for e in events))
        self.assertTrue(events[-1]["interrupts"])
        state = self.client.get('/api/thread/demo/agent-state').get_json()
        self.assertTrue(state["interrupts"])
        self.assertFalse(self.applied)
        self.assertEqual(self.client.post('/api/chat/stream', json={"thread_id": "demo", "message": "绕过审批"}).status_code, 409)
        self.assertEqual(self.client.post('/api/thread/demo/resume', json={"decisions": {}}).status_code, 400)
        key = state["interrupts"][0]["id"]
        response = self.client.post('/api/thread/demo/resume', json={"decisions": {key: {"decisions": [{"type": "approve"}]}}})
        self.assertEqual(self.events(response)[-1]["type"], "done")
        self.assertEqual(self.applied, [("draft", True)])
        history = self.client.get('/api/thread/demo/messages').get_json()["messages"]
        self.assertEqual(history[-1]["content"], "草稿已同步")
        self.assertTrue(all(message["id"] for message in history))
        self.assertEqual({event["type"] for event in events}, {"message", "done"})
        self.assertEqual(self.client.get('/api/threads').get_json()["threads"][0]["thread_id"], "demo")

    def test_upload_resource_survives_reinitialization_and_can_be_removed(self):
        self.client.post('/api/thread/media/init')
        with patch.object(self.server, "get_media_info", return_value={"duration": 1000, "resolution": "16x16"}):
            response = self.client.post('/api/thread/media/resources/upload', data={"files": (io.BytesIO(b"test-media"), "clip.mp4")})
        resource = response.get_json()["resources"][0]
        self.client.post('/api/thread/media/init')
        self.assertEqual(len(self.client.get('/api/thread/media/resources').get_json()["resources"]), 1)
        with self.client.get(resource["resource_url"]) as download:
            self.assertEqual(download.status_code, 200)
        self.assertEqual(self.client.delete(f'/api/thread/media/resources/{resource["resource_id"]}').status_code, 200)
        self.assertFalse(list((Path(self.directory.name) / "uploads/media").iterdir()))

    def test_pending_approval_preserves_media_and_rejects_upload(self):
        self.client.post('/api/thread/media/init')
        with patch.object(self.server, "get_media_info", return_value={"duration": 1000, "resolution": "16x16"}):
            response = self.client.post('/api/thread/media/resources/upload', data={"files": (io.BytesIO(b"original"), "clip.mp4")})
            resource = response.get_json()["resources"][0]
            self.events(self.client.post('/api/chat/stream', json={"thread_id": "media", "message": "交付草稿"}))
            self.assertEqual(self.client.delete(f'/api/thread/media/resources/{resource["resource_id"]}').status_code, 409)
            response = self.client.post('/api/thread/media/resources/upload', data={"files": (io.BytesIO(b"new"), "new.mp4")})
            self.assertEqual(response.status_code, 409)
        with self.client.get(resource["resource_url"]) as download:
            self.assertEqual(download.get_data(), b"original")
        self.assertEqual(len(list((Path(self.directory.name) / "uploads/media").iterdir())), 1)
        self.assertEqual(len(self.client.get('/api/thread/media/resources').get_json()["resources"]), 1)


if __name__ == "__main__":
    unittest.main()
