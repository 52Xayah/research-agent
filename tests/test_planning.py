import json
import unittest
from unittest.mock import Mock

from research_agent.agent.executor import Executor, TaskFailure, TaskState
from research_agent.agent.planning import PLAN_SCHEMA, Planner, Task, TaskManager
from research_agent.llm.base import BaseLLM, ChatResponse, Message


class PlanningTests(unittest.TestCase):
    def test_validation_rejects_missing_edges_duplicates_and_cycles(self):
        for tasks in (
            (Task("a", "A", depends_on=("b",)),),
            (Task("a", "A"), Task("a", "B")),
            (Task("a", "A", depends_on=("b",)), Task("b", "B", depends_on=("a",))),
        ):
            with self.subTest(tasks=tasks), self.assertRaises(ValueError):
                TaskManager(tasks)

    def test_model_schema_and_priority_with_dependencies(self):
        plan = TaskManager((Task("blocked", "C", 5, ("a",)), Task("a", "A", 1), Task("b", "B", 2)))
        llm = Mock(spec=BaseLLM)
        llm.chat.return_value = ChatResponse(Message("assistant", json.dumps(plan.as_dict())), True)
        self.assertEqual([item.id for item in Planner(llm).plan("Compare A and B").tasks],
                         ["b", "a", "blocked"])
        self.assertEqual(llm.chat.call_args.kwargs["response_format"], PLAN_SCHEMA)

    def test_retry_and_pass_prerequisite_data(self):
        plan = TaskManager((Task("a", "A"), Task("b", "B", depends_on=("a",))))
        handler = Mock(side_effect=[TaskFailure("temporary", retryable=True), {"fact": 4}, {"value": 8}])
        saved = Mock()
        states = Executor().run(plan, handler, checkpoint=saved)
        self.assertEqual(states["a"], TaskState("succeeded", 2, {"fact": 4}))
        self.assertEqual(states["b"], TaskState("succeeded", 1, {"value": 8}))
        self.assertEqual(handler.call_args.args[1], {"a": {"fact": 4}})
        self.assertEqual(saved.call_args_list[0].args, ("a", TaskState("running", 1)))

    def test_failed_dependency_blocks_only_its_descendants(self):
        plan = TaskManager((Task("a", "A"), Task("b", "B", depends_on=("a",)), Task("c", "C")))
        handler = Mock(side_effect=[TaskFailure("denied"), {"found": True}])
        states = Executor().run(plan, handler)
        self.assertEqual([states[key].status for key in ("a", "b", "c")], ["failed", "blocked", "succeeded"])
        self.assertEqual(handler.call_count, 2)
