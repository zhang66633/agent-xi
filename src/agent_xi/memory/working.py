"""工作记忆 — 当前对话的滑动窗口。

Phase 1 中 Brain._history 已承担此职责，Phase 2 将其正式化为独立模块，
便于 MemoryManager 统一管理和未来扩展（如 token 计数裁剪）。
"""

from __future__ import annotations

from ..llm.types import Message, Role


class WorkingMemory:
    """工作记忆：维护当前会话的消息窗口。

    职责：
    - 存储当前对话的 user/assistant 消息
    - 按 max_turns 滑动窗口裁剪
    - 提供只读视图供 ContextBuilder 使用
    """

    def __init__(self, max_turns: int = 50) -> None:
        self._messages: list[Message] = []
        self._max_turns = max_turns

    @property
    def messages(self) -> list[Message]:
        """当前窗口内的消息（只读副本）。"""
        return list(self._messages)

    @property
    def turn_count(self) -> int:
        """对话轮次数（user 消息数）。"""
        return sum(1 for m in self._messages if m.role == Role.USER)

    def append(self, message: Message) -> None:
        """追加消息并执行窗口裁剪。"""
        self._messages.append(message)
        self._trim()

    def clear(self) -> None:
        """清空工作记忆（开始新对话）。"""
        self._messages.clear()

    def _trim(self) -> None:
        """滑动窗口裁剪：保留最近 max_turns*2 条消息。"""
        max_messages = self._max_turns * 2
        if len(self._messages) > max_messages:
            self._messages = self._messages[-max_messages:]
