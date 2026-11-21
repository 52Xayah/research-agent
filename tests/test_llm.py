import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from research_agent.config import OllamaSettings
from research_agent.llm.base import (
    LLMProtocolError,
    LLMTimeoutError,
    LLMTransportError,
    Message,
    ToolCall,
    ToolSpec,
)
from research_agent.llm.ollama import OllamaLLM


def frame(content="", **fields):
    return {"message": {"role": "assistant", "content": content}, "done": True, **fields}


def json_body(data):
    return io.BytesIO(json.dumps(data, ensure_ascii=False).encode("utf-8"))


@patch("research_agent.llm.client.urlopen")
class OllamaLLMTests(unittest.TestCase):
    def setUp(self):
        self.llm = OllamaLLM(OllamaSettings(timeout=12))

    def test_normalizes_messages_options_and_usage(self, open_url):
        open_url.return_value = json_body(frame("已连接", prompt_eval_count=8, eval_count=4))
        schema = {"type": "object"}
        result = self.llm.chat([Message("system", "Concise"), Message("user", "你好")],
                               response_format=schema)

        self.assertEqual(result.message, Message("assistant", "已连接"))
        self.assertEqual((result.input_tokens, result.output_tokens), (8, 4))
        request = open_url.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(open_url.call_args.kwargs["timeout"], 12)
        self.assertEqual(request.full_url, "http://localhost:11434/api/chat")
        self.assertEqual(payload["format"], schema)
        self.assertEqual(payload["messages"][1], {"role": "user", "content": "你好"})
        self.assertEqual(payload["options"]["num_ctx"], 4096)
        self.assertFalse(payload["stream"])

    def test_round_trips_tool_call_and_tool_response(self, open_url):
        raw_call = {"type": "function", "function": {"index": 0, "name": "lookup", "arguments": {"id": 7}}}
        item = frame()
        item["message"]["tool_calls"] = [raw_call]
        open_url.side_effect = [json_body(item), json_body(frame("found"))]
        history = [Message("user", "Look up ID 7")]
        spec = ToolSpec("lookup", "Find an ID", {"type": "object"})
        message = self.llm.chat(history, tools=[spec]).message
        self.assertEqual(message.tool_calls, (ToolCall("lookup", {"id": 7}, 0),))
        self.llm.chat([*history, message, Message("tool", "found", tool_name="lookup")])
        first, second = [json.loads(call.args[0].data) for call in open_url.call_args_list]
        self.assertEqual(first["tools"][0]["function"]["parameters"], spec.parameters)
        self.assertEqual(second["messages"][1]["tool_calls"], [raw_call])
        self.assertEqual(second["messages"][2]["tool_name"], "lookup")

    def test_stream_skips_blanks_and_supports_metadata_only_completion(self, open_url):
        text = b'{"message":{"role":"assistant","content":"A"},"done":false}\n'
        final = b'{"done":true,"done_reason":"stop","eval_count":1}\n'
        body = open_url.return_value = io.BytesIO(text + b"\n" + final)
        chunks = list(self.llm.stream([Message("user", "A")]))
        self.assertEqual([chunk.message.content for chunk in chunks], ["A", ""])
        self.assertEqual(chunks[-1].finish_reason, "stop")
        self.assertEqual(chunks[-1].output_tokens, 1)
        self.assertTrue(body.closed)

    def test_closing_stream_releases_response(self, open_url):
        body = open_url.return_value = io.BytesIO(b'{"message":{"role":"assistant","content":"A"},"done":false}\n')
        chunks = self.llm.stream([Message("user", "A")])
        next(chunks)
        chunks.close()
        self.assertTrue(body.closed)

    def test_truncated_stream(self, open_url):
        open_url.return_value = io.BytesIO(b'{"message":{"role":"assistant","content":"A"},"done":false}\n')
        with self.assertLogs("research_agent.llm.client", "WARNING"):
            with self.assertRaisesRegex(LLMProtocolError, "completion frame"):
                list(self.llm.stream([Message("user", "A")]))

    def test_invalid_json_and_error_frame(self, open_url):
        for data in (b"\xff", b"{", b"[]", b'{"error":"invalid request"}'):
            with self.subTest(data=data):
                open_url.return_value = io.BytesIO(data)
                with self.assertLogs("research_agent.llm.client", "WARNING"):
                    with self.assertRaises(LLMProtocolError):
                        self.llm.chat([Message("user", "A")])

    def test_invalid_message_or_tool_call(self, open_url):
        invalid_messages = [
            {"role": "user", "content": "A"},
            {"role": "assistant", "content": 42},
            {"role": "assistant", "tool_calls": [{"function": {"name": "bad", "arguments": "text"}}]},
        ]
        for message in invalid_messages:
            with self.subTest(message=message):
                open_url.return_value = json_body({"done": True, "message": message})
                with self.assertRaises(LLMProtocolError):
                    self.llm.chat([Message("user", "A")])

    def test_timeout_and_transport_errors(self, open_url):
        for reason, expected in (
            (TimeoutError(), LLMTimeoutError),
            (URLError(TimeoutError()), LLMTimeoutError),
            (URLError(ConnectionRefusedError()), LLMTransportError),
        ):
            with self.subTest(reason=reason):
                open_url.side_effect = reason
                with self.assertLogs("research_agent.llm.client", "WARNING"):
                    with self.assertRaises(expected):
                        self.llm.chat([Message("user", "A")])

    def test_http_status_and_logs_do_not_contain_prompt(self, open_url):
        fp = io.BytesIO(b"private response")
        open_url.side_effect = HTTPError("http://localhost", 404, "Not found", {}, fp)
        with self.assertLogs("research_agent.llm.client", "WARNING") as captured:
            with self.assertRaisesRegex(LLMTransportError, "404"):
                self.llm.chat([Message("user", "private prompt")])
        self.assertTrue(fp.closed)
        self.assertNotIn("private", "\n".join(captured.output))
