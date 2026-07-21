"""工具基类、安全分级、执行结果。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class SecurityLevel(StrEnum):
    """工具安全分级。"""

    SAFE = "safe"  # 任何平台自动执行
    SENSITIVE = "sensitive"  # 需要用户确认
    DANGEROUS = "dangerous"  # 需要用户确认 + 仅特定平台可用


@dataclass(frozen=True, slots=True)
class ToolResult:
    """工具执行结果。"""

    success: bool
    output: str
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class Tool(ABC):
    """工具抽象基类。

    所有内置工具和插件工具都继承此类。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """工具唯一标识名。"""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述（会传给 LLM 做决策）。"""
        ...

    @property
    @abstractmethod
    def parameters_schema(self) -> dict[str, Any]:
        """参数的 JSON Schema 描述。"""
        ...

    @property
    def security_level(self) -> SecurityLevel:
        """安全等级，默认 SAFE。"""
        return SecurityLevel.SAFE

    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        """执行工具。"""
        ...

    def to_tool_definition(self) -> dict[str, Any]:
        """转换为 LLM tool calling 格式（OpenAI function 格式）。"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters_schema,
        }
