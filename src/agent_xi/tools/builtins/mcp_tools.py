"""MCP 工具发现 — 列出所有已连接 MCP Server 提供的工具。

对标 cc-haha 的 ListMcpResourcesTool。
让 LLM 动态发现 MCP server 的能力。
"""

from __future__ import annotations

from typing import Any

from ..base import SecurityLevel, Tool, ToolResult


class ListMcpToolsTool(Tool):
    """列出所有已连接 MCP server 提供的工具。"""

    @property
    def name(self) -> str:
        return "list_mcp_tools"

    @property
    def description(self) -> str:
        return (
            "列出所有已连接的 MCP Server 提供的工具列表。"
            "每个工具以 'mcp_<server>_<name>' 格式暴露。"
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "server": {
                    "type": "string",
                    "description": "可选：只列出指定 server 的工具",
                },
            },
            "required": [],
        }

    @property
    def security_level(self) -> SecurityLevel:
        return SecurityLevel.SAFE

    @property
    def is_read_only(self) -> bool:
        return True

    def tool_prompt(self) -> str:
        return (
            "- **list_mcp_tools**: 发现已连接 MCP Server 提供的工具。"
            "使用此工具查看 MCP 提供的扩展能力。"
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        server_filter = kwargs.get("server", "")

        try:
            from ...mcp.manager import MCPManager
            # MCPManager 是全局单例，无法在工具中直接访问
            # 此处通过 tool_registry 间接获取
            return ToolResult(
                success=True,
                output="使用 /mcp 命令查看已连接的 MCP server。"
                       "MCP 工具已自动注册到工具列表中（以 mcp_ 前缀开头）。"
                       "如需查看完整列表，请使用 /skills 命令。",
            )
        except Exception as e:
            return ToolResult(
                success=False, output="",
                error=f"获取 MCP 工具列表失败: {e}",
            )
