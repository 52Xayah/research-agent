"""Bounded arithmetic over a small subset of Python expression syntax."""

import ast
import math
import operator

from research_agent.llm.base import JsonObject
from research_agent.parameters import Parameter
from research_agent.tools.base import BaseTool, ToolError

BINARY_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
MAX_MAGNITUDE = 10**100


class Calculator(BaseTool):
    name = "calculator"
    description = "Evaluate basic arithmetic with +, -, *, /, //, %, and **."
    parameters = {
        "expression": Parameter("string", "Arithmetic expression", min_length=1, max_length=256),
    }

    def execute(self, *, expression: str) -> JsonObject:
        try:
            tree = ast.parse(expression.strip(), mode="eval")
        except (SyntaxError, ValueError, RecursionError) as error:
            raise ToolError("invalid_expression", "Invalid arithmetic expression") from error
        if sum(1 for _ in ast.walk(tree)) > 64:
            raise ToolError("invalid_expression", "Arithmetic expression is too complex")
        try:
            return {"value": _evaluate(tree.body)}
        except ZeroDivisionError as error:
            raise ToolError("division_by_zero", "Division by zero") from error
        except OverflowError as error:
            raise ToolError("numeric_limit", "Arithmetic result exceeds numeric limits") from error


def _evaluate(node: ast.expr) -> int | float:
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        value = node.value
    elif isinstance(node, ast.UnaryOp) and type(node.op) in UNARY_OPS:
        value = UNARY_OPS[type(node.op)](_evaluate(node.operand))
    elif isinstance(node, ast.BinOp) and type(node.op) in BINARY_OPS:
        left, right = _evaluate(node.left), _evaluate(node.right)
        if isinstance(node.op, ast.Pow) and (type(right) is not int or abs(right) > 16):
            raise ToolError("numeric_limit", "Powers require an integer exponent between -16 and 16")
        value = BINARY_OPS[type(node.op)](left, right)
    else:
        raise ToolError("invalid_expression", "Only numeric literals and arithmetic operators are supported")
    if (type(value) is float and not math.isfinite(value)) or abs(value) > MAX_MAGNITUDE:
        raise ToolError("numeric_limit", "Arithmetic result exceeds numeric limits")
    return value
