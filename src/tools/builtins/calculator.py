"""The one real worked tool — the template a build copies. Schema on one side,
run() on the other."""
from __future__ import annotations

import ast
import operator

from tools.base import BaseTool

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
        ast.USub: operator.neg}


def _eval(n: ast.AST) -> float:
    if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
        return n.value
    if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
        return _OPS[type(n.op)](_eval(n.left), _eval(n.right))
    if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
        return _OPS[type(n.op)](_eval(n.operand))
    raise ValueError("unsupported expression")


class CalculatorTool(BaseTool):
    name = "calculator"
    description = "Evaluate a basic arithmetic expression (+ - * / ** %, parens). Use for any arithmetic."
    input_schema = {
        "type": "object",
        "properties": {"expression": {"type": "string", "description": "e.g. '47 * 89'"}},
        "required": ["expression"],
    }

    def run(self, expression: str) -> str:
        r = _eval(ast.parse(expression, mode="eval").body)
        return str(int(r) if isinstance(r, float) and r.is_integer() else r)
