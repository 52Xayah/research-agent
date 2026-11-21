import unittest
from unittest.mock import Mock, patch

from research_agent.agent.engine import AgentEngine
from research_agent.llm.base import BaseLLM, ChatResponse, LLMTimeoutError, LLMTransportError, Message, ToolCall
from research_agent.tools.calculator import Calculator
from research_agent.tools.registry import ToolRegistry


def response(*calls, text=""):
    return ChatResponse(Message("assistant", text, calls), True)


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.model = Mock(spec=BaseLLM)
        self.tools = ToolRegistry()
        self.tools.register(Calculator())
        self.request = (Message("user", "Calculate"),)
        self.call = ToolCall("calculator", {"expression": "2 + 3"})

    def test_batches_and_subsequent_calls_are_returned_to_model(self):
        unknown = ToolCall("unknown", {})
        self.model.chat.side_effect = [response(unknown, self.call), response(self.call), response(text="5")]
        run = AgentEngine(self.model, self.tools).run(self.request)
        self.assertEqual((run.reason, run.answer, run.steps), ("completed", "5", 3))
        self.assertEqual([event.step for event in run.events], [1, 1, 2])
        self.assertEqual(run.events[0].result.error.code, "unknown_tool")
        sent = self.model.chat.call_args_list[1].args[0]
        self.assertEqual([(msg.role, msg.tool_name) for msg in sent[-2:]],
                         [("tool", "unknown"), ("tool", "calculator")])

    def test_repeated_calls_stop_at_round_limit(self):
        self.model.chat.return_value = response(self.call)
        run = AgentEngine(self.model, self.tools, max_steps=3).run(self.request)
        self.assertEqual((run.reason, run.steps, len(run.events)), ("max_steps", 3, 2))

    def test_oversized_batch_is_not_dispatched(self):
        self.model.chat.return_value = response(self.call, self.call)
        run = AgentEngine(self.model, self.tools, max_tool_calls=1).run(self.request)
        self.assertEqual((run.reason, run.events), ("max_tool_calls", ()))

    @patch("research_agent.agent.engine.monotonic", side_effect=[0, 1, 3])
    def test_discards_response_after_deadline(self, _clock):
        self.model.chat.return_value = response(self.call)
        run = AgentEngine(self.model, self.tools, timeout=2).run(self.request)
        self.assertEqual((run.reason, run.events), ("timeout", ()))
        self.assertEqual(self.model.chat.call_args.kwargs["timeout"], 1)

    def test_model_failure_is_classified(self):
        for error, reason in ((LLMTimeoutError("late"), "timeout"), (LLMTransportError("down"), "model_error")):
            with self.subTest(error=error):
                self.model.chat.side_effect = error
                run = AgentEngine(self.model, self.tools).run(self.request)
                self.assertEqual(run.reason, reason)
