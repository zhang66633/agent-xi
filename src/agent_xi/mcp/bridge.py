"""MCP Bridge — 将 MCP 工具适配为 Agent Xi 的 Tool 接口。"""

from __future__ import annotations

from typing import Any

from ..tools.base import SecurityLevel, Tool, ToolResult
from .client import MCPClient
from .protocol import MCPToolDef


class MCPToolAdapter(Tool):
    """将 MCP Server 的工具适配为 Agent Xi Tool。

    对 Brain 和 ToolRegistry 完全透明 — 看起来就是普通内置工具。
    """

    def __init__(
        self,
        client: MCPClient,
        tool_def: MCPToolDef,
    ) -> None:
        self._client = client
        self._tool_def = tool_def

    @property
    def name(self) -> str:
        """带 server 前缀避免命名冲突。"""
        return f"mcp_{self._client.name}_{self._tool_def.name}"

    @property
    def description(self) -> str:
        desc = self._tool_def.description or self._tool_def.name
        return f"[MCP:{self._client.name}] {desc}"

    @property
    def parameters_schema(self) -> dict[str, Any]:
        """直接使用 MCP 提供的 inputSchema。"""
        schema = self._tool_def.input_schema
        if not schema:
            return {"type": "object", "properties": {}, "required": []}
        return schema

    @property
    def security_level(self) -> SecurityLevel:
        """MCP 工具默认 SENSITIVE（外部系统交互）。"""
        return SecurityLevel.SENSITIVE

    async def execute(self, **kwargs: Any) -> ToolResult:
        """通过 MCP Client 调用远程工具。"""
        try:
            result = await self._client.call_tool(
                self._tool_def.name, kwargs
            )

            if result.is_error:
                return ToolResult(
                    success=False,
                    output="",
                    error=result.text or "MCP tool returned error",
                )

            return ToolResult(success=True, output=result.text)

        except TimeoutError as e:
            return ToolResult(
                success=False, output="", error=f"MCP 调用超时：{e}"
            )
        except RuntimeError as e:
            return ToolResult(
                success=False, output="", error=f"MCP 错误：{e}"
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"MCP 调用异常：{type(e).__name__}: {e}",
            )
