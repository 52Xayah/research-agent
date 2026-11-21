import unittest
from unittest.mock import Mock

from research_agent.agent.engine import AgentResult, ToolEvent
from research_agent.evaluation.cases import CASES
from research_agent.evaluation.runner import _citation_scores, score_case
from research_agent.llm.base import BaseLLM, ChatResponse, Message, ToolCall
from research_agent.tools.base import ToolFailure, ToolResult


class EvaluationTests(unittest.TestCase):
    def test_invalid_quotes_do_not_reach_the_reviewer(self):
        model = Mock(spec=BaseLLM)
        model.chat.side_effect = [
            ChatResponse(Message("assistant", '{"decisions":[{"number":1,"supported":true}]}'), True),
            ChatResponse(Message("assistant", '{"decisions":[{"number":1,"supported":false}]}'), True),
        ]
        self.assertTrue(all(case["success"] for case in _citation_scores(model)))
        self.assertEqual(model.chat.call_count, 2)

    def test_counts_matches_usage_and_success(self):
        case = next(case for case in CASES if case.id == "division")
        call, = case.calls
        run = AgentResult("completed", "3.0", 2, (), (
            ToolEvent(1, call, ToolResult("calculator", {"value": 3.0})),
        ))
        responses = [ChatResponse(Message("assistant"), True, input_tokens=9, output_tokens=4)]
        scored = score_case(case, run, responses, 1.253)
        self.assertTrue(scored.success)
        self.assertEqual((scored.tool_matches, scored.argument_matches), (1, 1))
        self.assertEqual((scored.input_tokens, scored.output_tokens, scored.measured_responses), (9, 4, 1))

    def test_extra_and_failed_calls_affect_metrics(self):
        case = next(case for case in CASES if case.id == "arithmetic")
        attempted = ToolCall("calculator", {"expression": "1/0"})
        unexpected = ToolCall("nonexistent", {})
        run = AgentResult("completed", "107", 2, (), (
            ToolEvent(1, attempted, ToolResult("calculator", error=ToolFailure("division_by_zero", "zero"))),
            ToolEvent(1, unexpected, ToolResult("nonexistent", error=ToolFailure("unknown_tool", "unknown"))),
        ))
        scored = score_case(case, run, [], 0.0)
        self.assertFalse(scored.success)
        self.assertEqual((scored.expected_or_observed, scored.tool_matches, scored.argument_matches), (2, 1, 0))
        self.assertEqual((scored.calls, scored.failures), (2, 2))

    def test_missing_expected_call_counts_against_accuracy(self):
        case = next(case for case in CASES if case.id == "read")
        result = score_case(case, AgentResult("completed", "teal", 1, (), ()), [], 0.0)
        self.assertEqual((result.expected_or_observed, result.tool_matches), (1, 0))
        self.assertFalse(result.success)
