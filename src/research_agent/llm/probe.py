"""Repeatable capability checks against the configured local model."""

import json
import re
from collections.abc import Callable
from time import perf_counter

from research_agent.llm.base import LLMError, Message, ToolSpec
from research_agent.llm.ollama import OllamaLLM

PROFILE_TOOL = ToolSpec(
    name="lookup_project",
    description="Look up the status of a project by its code.",
    parameters={
        "type": "object",
        "properties": {"code": {"type": "string"}},
        "required": ["code"],
        "additionalProperties": False,
    },
)


def run_probe(llm: OllamaLLM) -> bool:
    def ask(prompt, **options):
        return llm.chat([Message("user", prompt)], **options).message

    def basic() -> bool:
        reply = ask("请只回复这四个汉字：连接成功。")
        return "连接成功" in reply.content

    def multi_turn() -> bool:
        messages = [Message("user", "Remember the code ORCHID-719. Reply OK.")]
        first = llm.chat(messages).message
        messages.extend([
            first,
            Message("user", "What was the code in my first message? Reply with just the code."),
        ])
        return "ORCHID-719" in llm.chat(messages).message.content

    def streaming() -> bool:
        messages = [Message("user", "Write a short sentence about the ocean in English.")]
        chunks = list(llm.stream(messages))
        count = sum(bool(chunk.message.content) for chunk in chunks)
        print(f"  {count} text chunks")
        return bool(chunks and chunks[-1].done and count > 1)

    def structured() -> bool:
        schema = {
            "type": "object",
            "properties": {"topic": {"type": "string"}, "priority": {"type": "integer"}},
            "required": ["topic", "priority"],
            "additionalProperties": False,
        }
        reply = ask("Return topic SQLite and priority 2 as JSON.", response_format=schema)
        data = json.loads(reply.content)
        return data == {"topic": "SQLite", "priority": 2} and type(data["priority"]) is int

    def reasoning() -> bool:
        reply = ask("Three boxes have four books each. Two books total are removed. "
                    "How many books remain? Reply only with the number.")
        return re.fullmatch(r"10[.。]?", reply.content.strip()) is not None

    def tool_call() -> bool:
        reply = ask("Use lookup_project to retrieve the status of project R-27.",
                    tools=[PROFILE_TOOL])
        calls = reply.tool_calls
        return len(calls) == 1 and (
            calls[0].name == "lookup_project"
            and calls[0].arguments == {"code": "R-27"}
        )

    cases: dict[str, Callable[[], bool]] = {
        "basic_chat": basic,
        "multi_turn": multi_turn,
        "streaming": streaming,
        "structured_json": structured,
        "reasoning": reasoning,
        "tool_calling": tool_call,
    }
    passed = 0
    for name, check in cases.items():
        started = perf_counter()
        try:
            ok = check()
        except (LLMError, ValueError, KeyError, TypeError) as error:
            print(f"  {type(error).__name__}: {error}")
            ok = False
        passed += ok
        print(f"{'PASS' if ok else 'FAIL'} {name} ({perf_counter() - started:.2f} s)")
    print(f"{llm.settings.model}: {passed}/{len(cases)} checks passed")
    return passed == len(cases)
