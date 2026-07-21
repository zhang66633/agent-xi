"""MCP 协议定义 — JSON-RPC 2.0 消息结构。

MCP 使用 JSON-RPC 2.0 over stdio，消息帧格式：
Content-Length: <N>\r\n\r\n<JSON payload>

参考：https://spec.modelcontextprotocol.io/
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

# ─── JSON-RPC 2.0 基础 ─────────────────────────────────────────────────────────


@dataclass(slots=True)
class JsonRpcRequest:
    """JSON-RPC 2.0 请求。"""

    method: str
    params: dict[str, Any] = field(default_factory=dict)
    id: int | str | None = None
    jsonrpc: str = "2.0"

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"jsonrpc": self.jsonrpc, "method": self.method}
        if self.params:
            d["params"] = self.params
        if self.id is not None:
            d["id"] = self.id
        return d

    def encode(self) -> bytes:
        """编码为 MCP 帧格式。"""
        payload = json.dumps(self.to_dict(), ensure_ascii=False)
        header = f"Content-Length: {len(payload.encode())}\r\n\r\n"
        return header.encode() + payload.encode()


@dataclass(slots=True)
class JsonRpcNotification:
    """JSON-RPC 2.0 通知（无 id，不期望响应）。"""

    method: str
    params: dict[str, Any] = field(default_factory=dict)
    jsonrpc: str = "2.0"

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"jsonrpc": self.jsonrpc, "method": self.method}
        if self.params:
            d["params"] = self.params
        return d

    def encode(self) -> bytes:
        payload = json.dumps(self.to_dict(), ensure_ascii=False)
        header = f"Content-Length: {len(payload.encode())}\r\n\r\n"
        return header.encode() + payload.encode()


@dataclass(slots=True)
class JsonRpcResponse:
    """JSON-RPC 2.0 响应。"""

    id: int | str | None = None
    result: Any = None
    error: dict[str, Any] | None = None
    jsonrpc: str = "2.0"

    @property
    def is_error(self) -> bool:
        return self.error is not None


# ─── MCP 特有数据结构 ──────────────────────────────────────────────────────────


@dataclass(slots=True)
class MCPToolDef:
    """MCP Server 提供的工具定义。"""

    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MCPToolResult:
    """MCP 工具调用结果。"""

    content: list[dict[str, Any]] = field(default_factory=list)
    is_error: bool = False

    @property
    def text(self) -> str:
        """提取文本内容。"""
        parts = []
        for block in self.content:
            if block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts)


# ─── 帧解析 ────────────────────────────────────────────────────────────────────


def parse_frame(data: bytes) -> dict[str, Any] | None:
    """解析单个 MCP 帧（Content-Length 头 + JSON body）。"""
    text = data.decode("utf-8", errors="replace")

    # 分离 header 和 body
    if "\r\n\r\n" in text:
        _header, body = text.split("\r\n\r\n", 1)
    else:
        body = text

    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def encode_message(msg: dict[str, Any]) -> bytes:
    """将消息字典编码为 MCP 帧。"""
    payload = json.dumps(msg, ensure_ascii=False)
    header = f"Content-Length: {len(payload.encode())}\r\n\r\n"
    return header.encode() + payload.encode()
