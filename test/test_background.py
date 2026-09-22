import asyncio
import tempfile
import unittest
from functools import partial
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from src.agents.runtime import AgentRuntime, RunConflict
from src.agents.workflow import create_jianying_agent
from test_deepagents import ScriptedModel, call


class BackgroundRunTests(unittest.TestCase):
    def test_concurrent_activity_updates_do_not_overwrite_each_other(self):
        class YieldingStore:
            value = {"run_id": "first", "run_status": "completed"}

            async def aget(self, namespace, key):
                snapshot = SimpleNamespace(value=dict(self.value))
                await asyncio.sleep(0)  # 两次独立读取可在写入前交错。
                return snapshot

            async def aput(self, namespace, key, value):
                await asyncio.sleep(0)
                self.value = value

        with tempfile.TemporaryDirectory() as folder:
            runtime = AgentRuntime(folder, agent_factory=partial(create_jianying_agent, model=ScriptedModel(), tools=[]))
            try:
                async def race():
                    await runtime._ready()
                    store = YieldingStore()
                    with patch.object(runtime, 'store', store):
                        await asyncio.gather(
                            runtime._save_activity('demo', expected_run_id='first', read_run_id='first'),
                            runtime._save_activity('demo', run_id='second', run_status='running'),
                        )
                        return store.value
                value = runtime._submit(race()).result(timeout=5)
                self.assertEqual(value, {"run_id": "second", "run_status": "running", "read_run_id": "first"})
            finally:
                runtime.close()

    def test_detached_run_continues_replays_and_releases_on_completion(self):
        gate = asyncio.Event()

        @tool
        async def wait_for_test() -> str:
            """等待离线测试放行。"""
            await gate.wait()
            return '工具完成'

        model = ScriptedModel(responses=[call('wait_for_test', {}), AIMessage(content='后台完成')])
        with tempfile.TemporaryDirectory() as folder:
            runtime = AgentRuntime(folder, agent_factory=partial(create_jianying_agent, model=model, tools=[wait_for_test]))
            try:
                config = {'configurable': {'thread_id': 'background'}}
                stream = runtime.consume(runtime.start_stream({'messages': [HumanMessage(content='开始')]}, config))
                first = next(stream)
                self.assertEqual(first['type'], 'message')
                stream.close()
                self.assertTrue(runtime.activity('background')['running'])
                with self.assertRaises(RunConflict):
                    runtime.start_stream({'messages': [HumanMessage(content='重复提交')]}, config)

                subscription = runtime.subscribe(config)
                self.assertTrue(subscription[2], 'reconnect receives already streamed messages')
                self.assertFalse(subscription[2][0]['delta'])
                runtime.loop.call_soon_threadsafe(gate.set)
                events = list(runtime.consume(subscription))
                self.assertEqual(events[-1]['type'], 'done')
                self.assertFalse(runtime._runs, 'completed background instances are released')
                self.assertEqual(runtime.get_state(config).values['messages'][-1].content, '后台完成')
                activity = runtime.activity('background')
                self.assertTrue(activity['unread'])
                self.assertEqual(activity['run_status'], 'completed')
                timestamp = activity['last_chat_at']
                runtime.update_state(config, {'resources': [{'resource_name': 'later.mp4'}]})
                self.assertEqual(runtime.activity('background')['last_chat_at'], timestamp)
                self.assertTrue(runtime.mark_read('background', 'stale-run-id')['unread'])
                self.assertFalse(runtime.mark_read('background', activity['run_id'])['unread'])
            finally:
                runtime.close()

            restored = AgentRuntime(folder, agent_factory=partial(create_jianying_agent, model=ScriptedModel(), tools=[]))
            try:
                self.assertEqual(restored.activity('background')['last_chat_at'], timestamp)
                self.assertFalse(restored.activity('background')['unread'])
            finally:
                restored.close()

    def test_stale_read_receipt_cannot_clear_new_completion(self):
        model = ScriptedModel(responses=[AIMessage(content='第一次'), AIMessage(content='第二次')])
        with tempfile.TemporaryDirectory() as folder:
            runtime = AgentRuntime(folder, agent_factory=partial(create_jianying_agent, model=model, tools=[]))
            try:
                config = {'configurable': {'thread_id': 'demo'}}
                list(runtime.stream({'messages': [HumanMessage(content='一')]}, config))
                first = runtime.activity('demo')['run_id']
                list(runtime.stream({'messages': [HumanMessage(content='二')]}, config))
                self.assertTrue(runtime.mark_read('demo', first)['unread'])
                self.assertNotEqual(runtime.activity('demo')['run_id'], first)
                runtime.delete_thread('demo')
                self.assertFalse(runtime.mark_read('demo', first)['unread'])
                self.assertNotIn('run_id', runtime.activity('demo'))
                self.assertEqual(runtime.list_threads(), [])
            finally:
                runtime.close()
