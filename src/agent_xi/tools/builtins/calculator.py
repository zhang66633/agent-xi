"""calculator — 数学计算。SAFE 级别。"""

from __future__ import annotations

import math
from typing import Any

from ..base import SecurityLevel, Tool, ToolResult

# 允许的安全函数/常量白名单
_SAFE_NAMES: dict[str, Any] = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "pow": pow,
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "log2": math.log2,
    "log10": math.log10,
    "exp": math.exp,
    "floor": math.floor,
    "ceil": math.ceil,
    "factorial": math.factorial,
    "gcd": math.gcd,
    "pi": math.pi,
    "e": math.e,
    "inf": math.inf,
}


class CalculatorTool(Tool):
    """安全的数学表达式计算器。"""

    @property
    def name(self) -> str:
        return "calculator"

    @property
    def description(self) -> str:
        return (
            "计算数学表达式。支持四则运算、幂运算、取模、"
            "以及 sqrt/sin/cos/log/factorial 等常用函数。"
            "例如：'2**10 + sqrt(144)' 或 'factorial(10)'。"
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "数学表达式（Python 语法）",
                },
            },
            "required": ["expression"],
        }

    @property
    def security_level(self) -> SecurityLevel:
        return SecurityLevel.SAFE

    async def execute(self, **kwargs: Any) -> ToolResult:
        expression = kwargs.get("expression", "")

        if not expression:
            return ToolResult(
                success=False, output="", error="未提供数学表达式"
            )

        # 安全检查：禁止危险字符
        forbidden = {"import", "exec", "eval", "__", "open", "os", "sys"}
        expr_lower = expression.lower()
        for word in forbidden:
            if word in expr_lower:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"表达式包含不允许的内容：'{word}'",
                )

        try:
            # 在受限命名空间中 eval
            result = eval(expression, {"__builtins__": {}}, _SAFE_NAMES)  # noqa: S307
            return ToolResult(
                success=True,
                output=f"{expression} = {result}",
            )
        except ZeroDivisionError:
            return ToolResult(
                success=False, output="", error="除零错误"
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"计算错误：{type(e).__name__}: {e}",
            )
