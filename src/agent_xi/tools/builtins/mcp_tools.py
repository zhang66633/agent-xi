"""MCP 资源 & 工具发现 — 对标 cc-haha ListMcpResourcesTool。

列出已连接 MCP Server 提供的所有工具和资源。
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
            "每个工具以 'mcp_<server>_<name>' 格式注册，"
            "可直接在对话中调用这些工具。"
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

    @property
    def is_concurrency_safe(self) -> bool:
        return True

    def tool_prompt(self) -> str:
        return (
            "- **list_mcp_tools**: 发现已连接 MCP Server 提供的工具。"
            "使用此工具了解可通过 MCP 访问的扩展能力。"
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        server_filter = kwargs.get("server", "")

        try:
            import yaml
            from pathlib import Path

            mcp_yaml = Path(__file__).parent.parent.parent.parent.parent / "config" / "mcp.yaml"
            if not mcp_yaml.exists():
                return ToolResult(success=True, output="未配置 MCP 服务器（config/mcp.yaml 不存在）")

            config = yaml.safe_load(mcp_yaml.read_text(encoding="utf-8"))
            servers = config.get("servers", []) if isinstance(config, dict) else []

            if not servers:
                return ToolResult(success=True, output="未配置任何 MCP 服务器")

            lines = [f"共 {len(servers)} 个 MCP 服务器:\n"]
            for s in servers:
                name = s.get("name", "unknown")
                if server_filter and name != server_filter:
                    continue
                cmd = s.get("command", "")
                args = " ".join(s.get("args", []))
                enabled = s.get("enabled", True)
                status = "启用" if enabled else "禁用"
                lines.append(f"## {name} [{status}]")
                lines.append(f"  命令: {cmd} {args}")
                if "env" in s:
                    env_keys = ", ".join(s["env"].keys())
                    lines.append(f"  需要配置: {env_keys}")
                lines.append("")

            if not any(s.get("name") == server_filter or not server_filter for s in servers):
                return ToolResult(success=True, output=f"未找到 MCP server: {server_filter}")

            return ToolResult(
                success=True,
                output="\n".join(lines),
                metadata={"server_count": len(servers)},
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=f"无法读取 MCP 配置: {e}")


class ListMcpResourcesTool(Tool):
    """列出 MCP 服务器提供的资源（对标 cc-haha ListMcpResourcesTool）。"""

    @property
    def name(self) -> str:
        return "list_mcp_resources"

    @property
    def description(self) -> str:
        return "列出 MCP 服务器提供的资源（文件、数据等）"

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "server": {
                    "type": "string",
                    "description": "可选：只列出指定 server 的资源",
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
            "- **list_mcp_resources**: 列出 MCP 服务器提供的资源（文件、数据库表等）。"
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        server_filter = kwargs.get("server", "")
        try:
            import yaml
            from pathlib import Path

            mcp_yaml = Path(__file__).parent.parent.parent.parent.parent / "config" / "mcp.yaml"
            if not mcp_yaml.exists():
                return ToolResult(success=True, output="未配置 MCP 服务器")

            config = yaml.safe_load(mcp_yaml.read_text(encoding="utf-8"))
            servers = config.get("servers", []) if isinstance(config, dict) else []

            if not servers:
                return ToolResult(success=True, output="未配置任何 MCP 服务器")

            lines = ["MCP 资源列表（通过 MCP 协议访问的外部资源）:\n"]
            for s in servers:
                name = s.get("name", "?")
                if server_filter and name != server_filter:
                    continue
                lines.append(f"- **{name}**: 已连接，工具自动注册为 mcp_{name}_* 格式")
                lines.append(f"  使用 list_mcp_tools 查看该 server 提供的具体工具")

            return ToolResult(success=True, output="\n".join(lines))
        except Exception as e:
            return ToolResult(success=False, output="", error=f"获取资源列表失败: {e}")
