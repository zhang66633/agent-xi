"""MCP 客户端 — Model Context Protocol 接入。

通过 stdio 子进程与 MCP Server 通信（JSON-RPC 2.0），
将外部工具桥接到 Agent Xi 的 Tool 体系。
"""

from .bridge import MCPToolAdapter
from .client import MCPClient
from .config import MCPServerConfig, load_mcp_config
from .manager import MCPManager

__all__ = [
    "MCPClient",
    "MCPManager",
    "MCPServerConfig",
    "MCPToolAdapter",
    "load_mcp_config",
]
