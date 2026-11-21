import json
import unittest
from unittest.mock import Mock

from research_agent.function_demo import EXAMPLES, SPECS, run_example
from research_agent.llm.base import BaseLLM, ChatResponse, Message, ToolCall
from research_agent.parameters import InvalidArguments, Parameter, parameter_schema, validate_arguments


class ArgumentTests(unittest.TestCase):
    def setUp(self):
        self.fields = {
            "name": Parameter("string", "Name", min_length=1, max_length=4),
            "count": Parameter("integer", "Count", minimum=1, maximum=5),
            "ratio": Parameter("number", "Ratio", required=False),
            "enabled": Parameter("boolean", "Enabled", required=False),
        }

    def test_generated_schema_matches_accepted_fields(self):
        schema = parameter_schema(self.fields)
        self.assertEqual(schema["required"], ["name", "count"])
        self.assertEqual(schema["properties"]["count"]["maximum"], 5)
        self.assertFalse(schema["additionalProperties"])
        validate_arguments(self.fields, {"name": "蘭花", "count": 5})
        validate_arguments(self.fields, {"name": "test", "count": 1, "ratio": 0.2, "enabled": True})

    def test_rejects_invalid_parameters(self):
        for args in (
            [], {}, {"name": "x", "count": 1, "other": 2}, {"name": "", "count": 1},
            {"name": "xxxxx", "count": 1}, {"name": "x", "count": 0},
            {"name": "x", "count": 6}, {"name": "x", "count": True},
            {"name": "x", "count": 1.0}, {"name": "x", "count": 1, "ratio": float("nan")},
            {"name": "x", "count": 1, "enabled": 1},
        ):
            with self.subTest(args=args), self.assertRaises(InvalidArguments):
                validate_arguments(self.fields, args)


class FunctionDemoTests(unittest.TestCase):
    def test_appends_tool_result_to_history(self):
        model = Mock(spec=BaseLLM)
        request = Message("assistant", tool_calls=(ToolCall("lookup_project", {"code": "R-27"}),))
        model.chat.side_effect = [ChatResponse(request, True), ChatResponse(Message("assistant", "amber"), True)]
        result = run_example(model, EXAMPLES[0])
        self.assertTrue(result.answer_matches)
        first, second = model.chat.call_args_list
        self.assertEqual(first.kwargs["tools"], SPECS)
        self.assertEqual([message.role for message in first.args[0]], ["system", "user"])
        self.assertEqual(second.args[0][-2], request)
        tool_result = second.args[0][-1]
        self.assertEqual((tool_result.role, tool_result.tool_name), ("tool", "lookup_project"))
        self.assertEqual(json.loads(tool_result.content), {"status": "amber"})

    def test_invalid_call_is_not_executed_or_sent_back(self):
        model = Mock(spec=BaseLLM)
        request = Message("assistant", tool_calls=(ToolCall("lookup_inventory", {"sku": "381"}),))
        model.chat.return_value = ChatResponse(request, True)
        result = run_example(model, EXAMPLES[1])
        self.assertTrue(result.selected)
        self.assertFalse(result.arguments_match)
        self.assertEqual(model.chat.call_count, 1)
