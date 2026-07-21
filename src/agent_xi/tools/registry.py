"""工具注册中心 — 管理所有可用工具。"""

from __future__ import annotations

from ..llm.types import ToolDefinition, ToolParameter
from .base import Tool


class ToolRegistry:
    """工具注册中心。

    职责：
    - 注册/注销工具
    - 按名称查找工具
    - 生成 LLM 所需的工具定义列表
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """注册一个工具。"""
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        """注销一个工具。"""
        self._tools.pop(name, None)

    def get(self, name: str) -> Tool | None:
        """按名称获取工具。"""
        return self._tools.get(name)

    def list_tools(self) -> list[Tool]:
        """列出所有已注册工具。"""
        return list(self._tools.values())

    def to_definitions(self) -> list[ToolDefinition]:
        """生成 LLM 所需的 ToolDefinition 列表。"""
        definitions: list[ToolDefinition] = []
        for tool in self._tools.values():
            schema = tool.parameters_schema
            params: list[ToolParameter] = []
            properties = schema.get("properties", {})
            required = set(schema.get("required", []))

            for param_name, param_info in properties.items():
                params.append(
                    ToolParameter(
                        name=param_name,
                        type=param_info.get("type", "string"),
                        description=param_info.get("description", ""),
                        required=param_name in required,
                        enum=param_info.get("enum"),
                    )
                )

            definitions.append(
                ToolDefinition(
                    name=tool.name,
                    description=tool.description,
                    parameters=params,
                )
            )
        return definitions

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
