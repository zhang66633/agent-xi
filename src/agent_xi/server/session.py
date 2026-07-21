"""会话管理 — 每个 WS 连接对应一个独立 Brain 实例。

共享 Memory、ToolRegistry、SkillMatcher（全局状态），
但对话历史隔离（每个连接独立）。

持久化：前端通过 localStorage 保存 session_id 并在连接时上报，
SessionStore 按 id 落盘历史，刷新 / 重连后可恢复同一会话。
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from ..brain.context import ContextBuilder
from ..brain.engine import Brain
from ..brain.prompt import PromptBuilder
from ..llm.base import LLMClient
from ..memory.manager import MemoryManager
from ..skills.matcher import SkillMatcher
from ..tools.registry import ToolRegistry
from .history_store import SessionStore, is_valid_session_id

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class Session:
    """单个客户端会话。"""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    brain: Brain | None = None
    platform: str = "web"


class SessionManager:
    """管理所有活跃会话。

    共享组件（client, memory, registry, skill_matcher）由外部注入，
    每个新会话创建独立 Brain 实例。
    可选注入 SessionStore 实现历史持久化。
    """

    def __init__(
        self,
        client: LLMClient,
        memory: MemoryManager,
        tool_registry: ToolRegistry,
        skill_matcher: SkillMatcher | None = None,
        system_prompt: str = "",
        max_history_turns: int = 50,
        max_context_tokens: int = 128_000,
        reserved_output_tokens: int = 4096,
        store: SessionStore | None = None,
    ) -> None:
        self._client = client
        self._memory = memory
        self._registry = tool_registry
        self._skill_matcher = skill_matcher
        self._system_prompt = system_prompt
        self._max_history_turns = max_history_turns
        self._max_context_tokens = max_context_tokens
        self._reserved_output_tokens = reserved_output_tokens
        self._store = store
        self._sessions: dict[str, Session] = {}

    def create_session(self, platform: str = "web") -> Session:
        """创建新会话（服务端生成 id）。"""
        session = Session(platform=platform)
        session.brain = self._create_brain(session)
        self._sessions[session.id] = session
        return session

    def get_or_create_session(
        self, session_id: str | None, platform: str = "web"
    ) -> tuple[Session, bool]:
        """按前端上报的 session_id 获取或创建会话。

        Returns:
            (session, restored) — restored 表示是否从磁盘恢复了历史。
        """
        # 活跃会话直接复用（同一 id 二次连接）
        if session_id and session_id in self._sessions:
            return self._sessions[session_id], False

        # 非法 id → 退回新建
        if session_id and not is_valid_session_id(session_id):
            logger.warning("非法 session_id，已忽略: %r", session_id[:80])
            session_id = None

        session = Session(
            id=session_id or str(uuid.uuid4()), platform=platform
        )
        session.brain = self._create_brain(session)

        # 从磁盘恢复历史
        restored = False
        if self._store and session_id and session.brain:
            history = self._store.load_history(session_id)
            if history:
                for msg in history:
                    session.brain.inject_message(msg)
                restored = True
                logger.info(
                    "会话 %s 恢复 %d 条历史消息", session_id[:8], len(history)
                )

        self._sessions[session.id] = session
        return session, restored

    def save_session(self, session: Session) -> None:
        """持久化会话历史（每轮对话结束后调用）。"""
        if self._store and session.brain:
            try:
                self._store.save_history(session.id, session.brain.history)
            except Exception:
                logger.exception("会话历史保存失败: %s", session.id[:8])

    def get_session(self, session_id: str) -> Session | None:
        """获取会话。"""
        return self._sessions.get(session_id)

    def remove_session(self, session_id: str) -> None:
        """移除会话（历史已落盘，下次连接可恢复）。"""
        self._sessions.pop(session_id, None)

    @property
    def active_count(self) -> int:
        return len(self._sessions)

    def _create_brain(self, session: Session) -> Brain:
        """为会话创建 Brain 实例。

        confirm_callback 通过 WS 双向通信实现，
        在 ws_chat.py 中通过闭包绑定到具体 WebSocket 连接。
        这里先传 None，由 ws_chat 层覆盖。
        """
        context = ContextBuilder(
            system_prompt=self._system_prompt,
            max_history_turns=self._max_history_turns,
            max_context_tokens=self._max_context_tokens,
            reserved_output_tokens=self._reserved_output_tokens,
        )

        return Brain(
            client=self._client,
            context_builder=context,
            memory=self._memory,
            tool_registry=self._registry,
            confirm_callback=None,  # 由 ws_chat 层注入
            skill_matcher=self._skill_matcher,
        )
