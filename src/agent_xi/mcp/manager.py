"""MCP Manager — 管理多个 MCP Server 的生命周期。"""

from __future__ import annotations

import logging
from pathlib import Path

from ..tools.base import Tool
from .bridge import MCPToolAdapter
from .client import MCPClient
from .config import load_mcp_config

logger = logging.getLogger(__name__)


class MCPManager:
    """管理所有 MCP Server 连接。

    职责：
    - 加载配置
    - 启动/停止所有 server
    - 提供适配后的 Tool 列表供 ToolRegistry 注册
    """

    def __init__(self, config_path: Path | None = None) -> None:
        self._configs = load_mcp_config(config_path)
        self._clients: list[MCPClient] = []
        self._tools: list[MCPToolAdapter] = []

    @property
    def server_count(self) -> int:
        return len(self._clients)

    @property
    def tool_count(self) -> int:
        return len(self._tools)

    async def start_all(self) -> None:
        """启动所有已启用的 MCP Server。"""
        for config in self._configs:
            if not config.enabled:
                logger.info("MCP '%s' disabled, skipping", config.name)
                continue

            if not config.command:
                logger.warning(
                    "MCP '%s' has no command, skipping", config.name
                )
                continue

            try:
                client = MCPClient(
                    name=config.name,
                    command=config.command,
                    args=config.args,
                    env=config.env or None,
                )
                await client.start()
                self._clients.append(client)

                # 为此 server 的每个工具创建适配器
                for tool_def in client.tools:
                    adapter = MCPToolAdapter(client, tool_def)
                    self._tools.append(adapter)

                logger.info(
                    "MCP '%s' started with %d tools",
                    config.name,
                    len(client.tools),
                )

            except Exception as e:
                logger.error(
                    "Failed to start MCP '%s': %s", config.name, e
                )

    async def stop_all(self) -> None:
        """停止所有 MCP Server。"""
        for client in self._clients:
            try:
                await client.stop()
            except Exception as e:
                logger.warning(
                    "Error stopping MCP '%s': %s", client.name, e
                )
        self._clients.clear()
        self._tools.clear()

    def get_adapted_tools(self) -> list[Tool]:
        """获取所有 MCP 工具（已适配为 Tool 接口）。"""
        return list(self._tools)
