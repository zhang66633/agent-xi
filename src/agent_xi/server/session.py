"""会话管理 — 每个 WS 连接对应一个独立 Brain 实例。

共享 Memory、ToolRegistry、SkillMatcher（全局状态），
但对话历史隔离（每个连接独立）。
"""

from __future__ import annotations

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
    ) -> None:
        self._client = client
        self._memory = memory
        self._registry = tool_registry
        self._skill_matcher = skill_matcher
        self._system_prompt = system_prompt
        self._max_history_turns = max_history_turns
        self._max_context_tokens = max_context_tokens
        self._reserved_output_tokens = reserved_output_tokens
        self._sessions: dict[str, Session] = {}

    def create_session(self, platform: str = "web") -> Session:
        """创建新会话。"""
        session = Session(platform=platform)
        session.brain = self._create_brain(session)
        self._sessions[session.id] = session
        return session

    def get_session(self, session_id: str) -> Session | None:
        """获取会话。"""
        return self._sessions.get(session_id)

    def remove_session(self, session_id: str) -> None:
        """移除会话。"""
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
