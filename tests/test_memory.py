import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from research_agent.agent.executor import Executor, TaskState
from research_agent.agent.planning import Task, TaskManager
from research_agent.llm.base import Message, ToolCall
from research_agent.memory import TaskMemory


class MemoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "memory.sqlite3"
        self.memory = TaskMemory(self.path)
        self.plan = TaskManager((Task("a", "First"), Task("b", "Second", depends_on=("a",))))
        self.run_id = self.memory.create("SQLite", self.plan, {"local": True})

    def test_messages_and_checkpoints_round_trip(self):
        history = (Message("user", "中文"), Message("assistant", tool_calls=(ToolCall("lookup", {"id": 7}),)))
        state = TaskState("succeeded", 1, {"fact": "A"})
        self.memory.checkpoint(self.run_id, "a", state, messages=history)
        reopened = TaskMemory(self.path)
        self.assertEqual(reopened.load(self.run_id).options, {"local": True})
        self.assertEqual(reopened.states(self.run_id), {"a": state})
        self.assertEqual(reopened.messages(self.run_id), history)
        self.assertEqual(reopened.list_runs()[0]["finished"], 1)

    def test_resumes_interrupted_task_without_replaying_completed_task(self):
        handler = Mock(side_effect=[{"fact": "A"}, KeyboardInterrupt()])
        with self.assertRaises(KeyboardInterrupt), self.memory.claim(self.run_id):
            Executor().run(self.plan, handler, checkpoint=lambda key, state: self.memory.checkpoint(
                self.run_id, key, state))
        resumed = TaskMemory(self.path)
        next_handler = Mock(return_value={"fact": "B"})
        with resumed.claim(self.run_id):
            result = Executor().run(resumed.load(self.run_id).plan, next_handler,
                                    previous=resumed.states(self.run_id),
                                    checkpoint=lambda key, state: resumed.checkpoint(self.run_id, key, state))
        next_handler.assert_called_once_with(self.plan.tasks[1], {"a": {"fact": "A"}})
        self.assertEqual(result["b"], TaskState("succeeded", 2, {"fact": "B"}))
        self.assertEqual(resumed.list_runs()[0]["finished"], 2)

    def test_same_run_cannot_be_claimed_twice(self):
        with self.memory.claim(self.run_id), self.assertRaisesRegex(ValueError, "already active"):
            with TaskMemory(self.path).claim(self.run_id):
                self.fail("duplicate runner")
        with self.memory.claim(self.run_id):
            self.assertTrue(self.path.is_file())

    def test_exhausted_interrupted_attempt_is_terminal(self):
        self.memory.checkpoint(self.run_id, "a", TaskState("running", 2))
        handler = Mock()
        states = Executor().run(self.plan, handler, previous=self.memory.states(self.run_id))
        self.assertEqual((states["a"].status, states["b"].status), ("failed", "blocked"))
        handler.assert_not_called()
