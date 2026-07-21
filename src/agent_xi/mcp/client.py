"""MCP Client — stdio 子进程通信。

管理与单个 MCP Server 的生命周期：
启动子进程 → initialize 握手 → tools/list → tools/call → 关闭。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from .protocol import MCPToolDef, MCPToolResult, encode_message

logger = logging.getLogger(__name__)

# 协议版本
_PROTOCOL_VERSION = "2024-11-05"


class MCPClient:
    """单个 MCP Server 的 stdio 客户端。"""

    def __init__(
        self,
        name: str,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        self._name = name
        self._command = command
        self._args = args or []
        self._env = env
        self._process: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._reader_task: asyncio.Task[None] | None = None
        self._tools: list[MCPToolDef] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def tools(self) -> list[MCPToolDef]:
        return list(self._tools)

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    async def start(self) -> None:
        """启动子进程并完成 initialize 握手。"""
        # 构建环境变量
        proc_env = os.environ.copy()
        if self._env:
            proc_env.update(self._env)

        self._process = await asyncio.create_subprocess_exec(
            self._command,
            *self._args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=proc_env,
        )

        # 启动读取循环
        self._reader_task = asyncio.create_task(self._read_loop())

        # initialize 握手
        result = await self._request("initialize", {
            "protocolVersion": _PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {
                "name": "agent-xi",
                "version": "0.4.0",
            },
        })

        logger.info(
            "MCP '%s' initialized: %s",
            self._name,
            result.get("serverInfo", {}),
        )

        # 发送 initialized 通知
        await self._notify("notifications/initialized", {})

        # 获取工具列表
        await self._refresh_tools()

    async def _refresh_tools(self) -> None:
        """获取 server 的工具列表。"""
        result = await self._request("tools/list", {})
        raw_tools = result.get("tools", [])
        self._tools = [
            MCPToolDef(
                name=t["name"],
                description=t.get("description", ""),
                input_schema=t.get("inputSchema", {}),
            )
            for t in raw_tools
        ]
        logger.info(
            "MCP '%s' provides %d tools: %s",
            self._name,
            len(self._tools),
            [t.name for t in self._tools],
        )

    async def call_tool(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> MCPToolResult:
        """调用 MCP Server 上的工具。"""
        result = await self._request("tools/call", {
            "name": tool_name,
            "arguments": arguments,
        })

        return MCPToolResult(
            content=result.get("content", []),
            is_error=result.get("isError", False),
        )

    async def stop(self) -> None:
        """关闭子进程。"""
        if self._process and self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except TimeoutError:
                self._process.kill()

        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

        self._process = None
        self._reader_task = None

    # ─── 内部通信 ──────────────────────────────────────────────────────────────

    async def _request(
        self, method: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """发送请求并等待响应。"""
        self._request_id += 1
        req_id = self._request_id

        msg = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }

        loop = asyncio.get_event_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[req_id] = future

        await self._send(msg)

        try:
            response = await asyncio.wait_for(future, timeout=30)
        except TimeoutError:
            self._pending.pop(req_id, None)
            raise TimeoutError(
                f"MCP '{self._name}' request '{method}' timed out"
            )

        if "error" in response:
            error = response["error"]
            raise RuntimeError(
                f"MCP error [{error.get('code')}]: {error.get('message')}"
            )

        return response.get("result", {})

    async def _notify(
        self, method: str, params: dict[str, Any]
    ) -> None:
        """发送通知（不期望响应）。"""
        msg = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        await self._send(msg)

    async def _send(self, msg: dict[str, Any]) -> None:
        """编码并写入 stdin。"""
        if not self._process or not self._process.stdin:
            raise RuntimeError(f"MCP '{self._name}' process not running")

        data = encode_message(msg)
        self._process.stdin.write(data)
        await self._process.stdin.drain()

    async def _read_loop(self) -> None:
        """持续读取 stdout，解析帧并分发响应。"""
        assert self._process and self._process.stdout

        buffer = b""
        while True:
            try:
                chunk = await self._process.stdout.read(4096)
                if not chunk:
                    break  # EOF — 进程退出

                buffer += chunk

                # 尝试解析完整帧
                while b"\r\n\r\n" in buffer:
                    header_end = buffer.index(b"\r\n\r\n")
                    header = buffer[:header_end].decode("utf-8", errors="replace")

                    # 解析 Content-Length
                    content_length = 0
                    for line in header.split("\r\n"):
                        if line.lower().startswith("content-length:"):
                            content_length = int(line.split(":")[1].strip())
                            break

                    body_start = header_end + 4
                    body_end = body_start + content_length

                    if len(buffer) < body_end:
                        break  # 数据不完整，等待更多

                    body = buffer[body_start:body_end]
                    buffer = buffer[body_end:]

                    # 解析 JSON
                    try:
                        msg = json.loads(body.decode("utf-8"))
                        self._dispatch(msg)
                    except json.JSONDecodeError:
                        logger.warning(
                            "MCP '%s': invalid JSON frame", self._name
                        )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("MCP '%s' read error: %s", self._name, e)
                break

    def _dispatch(self, msg: dict[str, Any]) -> None:
        """分发收到的消息（匹配 pending futures）。"""
        msg_id = msg.get("id")
        if msg_id is not None and msg_id in self._pending:
            future = self._pending.pop(msg_id)
            if not future.done():
                future.set_result(msg)
