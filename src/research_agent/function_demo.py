"""One tool-call round and a fixed live evaluation set."""

import json
from dataclasses import dataclass
from time import perf_counter

from research_agent.llm.base import BaseLLM, JsonObject, LLMError, Message, ToolSpec
from research_agent.parameters import InvalidArguments, Parameter, parameter_schema, validate_arguments

FIELDS = {
    "lookup_project": {"code": Parameter("string", "Exact project code", min_length=1, max_length=32)},
    "lookup_inventory": {"sku": Parameter("integer", "Numeric stock keeping unit", minimum=1)},
}
SPECS = (
    ToolSpec("lookup_project", "Look up the current status of a project by its code.",
             parameter_schema(FIELDS["lookup_project"])),
    ToolSpec("lookup_inventory", "Get the number of items in stock for a numeric SKU.",
             parameter_schema(FIELDS["lookup_inventory"])),
)
PROJECTS = {"R-27": "amber", "T-105": "blue", "CN-42": "green"}
INVENTORY = {381: 19, 642: 73, 904: 58}


@dataclass(frozen=True)
class Example:
    prompt: str
    tool: str
    arguments: JsonObject
    answer: str


EXAMPLES = (
    Example("What is the current status of project R-27? Use a tool and return only its status.",
            "lookup_project", {"code": "R-27"}, "amber"),
    Example("Use the appropriate tool to find the stock count of SKU 381. Return only the count.",
            "lookup_inventory", {"sku": 381}, "19"),
    Example("请调用合适的工具查询项目 T-105 的状态，只返回状态原文。",
            "lookup_project", {"code": "T-105"}, "blue"),
    Example("请用工具查一下编号 642 的商品有多少库存，只回复数字。",
            "lookup_inventory", {"sku": 642}, "73"),
    Example("Use the appropriate tool to check project CN-42. Reply with the exact status only.",
            "lookup_project", {"code": "CN-42"}, "green"),
    Example("Look up how many units are available for stock keeping unit 904. Reply with the number.",
            "lookup_inventory", {"sku": 904}, "58"),
)


@dataclass(frozen=True)
class Outcome:
    selected: bool = False
    arguments_match: bool = False
    answer_matches: bool = False
    detail: str = ""


def run_example(llm: BaseLLM, case: Example) -> Outcome:
    messages = [
        Message("system", "Use the supplied tools for lookups. After receiving a tool result, "
                "reply with only its status or stock value as plain text."),
        Message("user", case.prompt),
    ]
    request = llm.chat(tuple(messages), tools=SPECS).message
    if len(request.tool_calls) != 1:
        return Outcome(detail=f"expected one tool call, received {len(request.tool_calls)}")
    call = request.tool_calls[0]
    if call.name not in FIELDS:
        return Outcome(detail="unknown tool")
    selected = call.name == case.tool
    try:
        validate_arguments(FIELDS[call.name], call.arguments)
    except InvalidArguments as error:
        return Outcome(selected, detail=str(error))
    arguments_match = selected and call.arguments == case.arguments
    if call.name == "lookup_project":
        result = {"status": PROJECTS.get(call.arguments["code"])}
    else:
        result = {"stock": INVENTORY.get(call.arguments["sku"])}
    messages.extend([
        request,
        Message("tool", json.dumps(result, allow_nan=False), tool_name=call.name),
    ])
    try:
        reply = llm.chat(messages).message
    except LLMError as error:
        return Outcome(selected, arguments_match, detail=f"tool result follow-up failed: {error}")
    answer = reply.content.strip().lower().rstrip(".。")
    matches = not reply.tool_calls and answer == case.answer and arguments_match
    return Outcome(selected, arguments_match, matches,
                   f"{call.name} {call.arguments!r} -> {result!r} -> {reply.content.strip()!r}")


def run_examples(llm: BaseLLM, *, all_cases: bool) -> bool:
    cases = EXAMPLES if all_cases else EXAMPLES[:1]
    selected = arguments = answers = 0
    for index, case in enumerate(cases, start=1):
        started = perf_counter()
        try:
            result = run_example(llm, case)
        except LLMError as error:
            result = Outcome(detail=str(error))
        selected += result.selected
        arguments += result.arguments_match
        answers += result.answer_matches
        label = "PASS" if result.answer_matches else "FAIL"
        print(f"{label} {index} ({perf_counter() - started:.2f} s): {result.detail}")
    print(f"Tool selection: {selected}/{len(cases)}")
    print(f"Exact arguments with correct tool: {arguments}/{len(cases)}")
    print(f"End-to-end tool result: {answers}/{len(cases)}")
    return answers == len(cases)
