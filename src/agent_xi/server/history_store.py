"""会话持久化 — 按 session_id 存储对话历史。

设计：
- 每个会话一个 JSON 文件：<data_dir>/sessions/<session_id>.json
- 前端在 localStorage 保存 session_id，WS 连接时通过查询参数上报
- 刷新页面 / 断线重连后恢复同一会话的对话历史
- 服务端在每轮对话结束后保存（Brain 历史含工具消息，完整保留）

安全：session_id 仅允许 [A-Za-z0-9_-]，防止路径穿越。
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from ..llm.types import Message, Role, TextBlock, ToolResultBlock, ToolUseBlock

logger = logging.getLogger(__name__)

# session_id 白名单（uuid4 格式 + 前端 crypto.randomUUID 兼容）
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

# 单个会话文件最多保留的消息条数（防止无限膨胀）
_MAX_STORED_MESSAGES = 200


def is_valid_session_id(session_id: str) -> bool:
    """校验 session_id 格式（防路径穿越）。"""
    return bool(_SESSION_ID_RE.match(session_id))


class SessionStore:
    """会话历史的文件存储。"""

    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "sessions"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        if not is_valid_session_id(session_id):
            raise ValueError(f"非法 session_id: {session_id!r}")
        return self._dir / f"{session_id}.json"

    def load_history(self, session_id: str) -> list[Message]:
        """加载会话历史；文件不存在或损坏时返回空列表。"""
        path = self._path(session_id)
        if not path.exists():
            return []
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            items = raw.get("messages", [])
            messages = [self._deserialize(m) for m in items]
            return [m for m in messages if m is not None]
        except Exception as e:
            logger.warning("会话历史加载失败 %s: %s", session_id, e)
            return []

    def save_history(self, session_id: str, history: list[Message]) -> None:
        """保存会话历史（覆盖写，限长）。"""
        path = self._path(session_id)
        items = [self._serialize(m) for m in history[-_MAX_STORED_MESSAGES:]]
        payload = {"session_id": session_id, "messages": items}
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
        tmp.replace(path)

    def exists(self, session_id: str) -> bool:
        return self._path(session_id).exists()

    def turn_count(self, session_id: str) -> int:
        """该会话的用户消息轮次（供 /api/history 展示）。"""
        path = self._path(session_id)
        if not path.exists():
            return 0
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return sum(
                1 for m in raw.get("messages", []) if m.get("role") == "user"
            )
        except Exception:
            return 0

    # ─── 序列化 ─────────────────────────────────────────────

    @staticmethod
    def _serialize(msg: Message) -> dict[str, Any]:
        if isinstance(msg.content, str):
            content: Any = msg.content
        else:
            content = [SessionStore._serialize_block(b) for b in msg.content]
        return {"role": str(msg.role), "content": content}

    @staticmethod
    def _serialize_block(block: Any) -> dict[str, Any]:
        if isinstance(block, TextBlock):
            return {"type": "text", "text": block.text}
        if isinstance(block, ToolUseBlock):
            return {
                "type": "tool_use",
                "id": block.id,
                "name": block.name,
                "arguments": block.arguments,
            }
        if isinstance(block, ToolResultBlock):
            return {
                "type": "tool_result",
                "tool_use_id": block.tool_use_id,
                "content": block.content,
                "is_error": block.is_error,
            }
        return {"type": "text", "text": str(block)}

    @staticmethod
    def _deserialize(raw: dict[str, Any]) -> Message | None:
        try:
            role = Role(raw["role"])
            content = raw["content"]
            if isinstance(content, list):
                blocks: list[Any] = []
                for b in content:
                    btype = b.get("type", "")
                    if btype == "text":
                        blocks.append(TextBlock(text=b.get("text", "")))
                    elif btype == "tool_use":
                        blocks.append(
                            ToolUseBlock(
                                id=b.get("id", ""),
                                name=b.get("name", ""),
                                arguments=b.get("arguments", {}),
                            )
                        )
                    elif btype == "tool_result":
                        blocks.append(
                            ToolResultBlock(
                                tool_use_id=b.get("tool_use_id", ""),
                                content=b.get("content", ""),
                                is_error=b.get("is_error", False),
                            )
                        )
                return Message(role=role, content=blocks)
            return Message(role=role, content=str(content))
        except Exception as e:
            logger.warning("消息反序列化失败: %s", e)
            return None
