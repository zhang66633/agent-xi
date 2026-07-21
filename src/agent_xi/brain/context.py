"""上下文构建 — 组装发给 LLM 的完整 prompt。

Phase 1：system prompt + 对话历史（滑动窗口）。
Phase 2：注入记忆检索结果。
Phase 3：传递工具定义。
Phase 4：Token 预算智能裁剪（从最新消息向前贪心填充）。
"""

from __future__ import annotations

from ..llm.types import ChatRequest, Message, ToolDefinition
from .tokenizer import TokenCounter, count_message_tokens, count_tools_tokens


class ContextBuilder:
    """构建 LLM 请求上下文。

    职责：
    - 管理 system prompt
    - 按 token 预算智能裁剪对话历史
    - 组装 ChatRequest

    裁剪策略（Phase 4）：
    - 计算固定开销（system + memory + tools schema）
    - 从最新消息向前贪心填充，直到用完可用预算
    - 保证最后一条 user 消息一定保留
    """

    def __init__(
        self,
        system_prompt: str = "",
        max_history_turns: int = 50,
        max_context_tokens: int = 128_000,
        reserved_output_tokens: int = 4096,
    ) -> None:
        self._system_prompt = system_prompt
        self._max_history_turns = max_history_turns
        self._max_context_tokens = max_context_tokens
        self._reserved_output_tokens = reserved_output_tokens
        self._counter = TokenCounter()

    @property
    def system_prompt(self) -> str:
        return self._system_prompt

    @system_prompt.setter
    def system_prompt(self, value: str) -> None:
        self._system_prompt = value

    @property
    def max_history_turns(self) -> int:
        return self._max_history_turns

    def build_request(
        self,
        history: list[Message],
        *,
        memory_context: str = "",
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> ChatRequest:
        """将 history 组装为 ChatRequest（Token 预算裁剪）。

        裁剪流程：
        1. 计算固定开销：system prompt + memory_context + tools schema
        2. 可用预算 = max_context - reserved_output - 固定开销
        3. 从最新消息向前贪心选择，不超预算
        4. 硬上限：最多 max_history_turns * 2 条（防止极端情况）
        """
        # 组装 system prompt
        system = self._system_prompt
        if memory_context:
            system = f"{system}\n\n{memory_context}"

        # 固定 token 开销
        system_tokens = self._counter.count_text(system)
        tools_tokens = count_tools_tokens(tools) if tools else 0
        fixed_cost = system_tokens + tools_tokens

        # 可用预算
        available = (
            self._max_context_tokens
            - self._reserved_output_tokens
            - fixed_cost
        )
        # 防止负数（prompt 本身就超了的极端情况）
        available = max(available, 1000)

        # 从最新消息向前贪心填充
        trimmed = self._select_within_budget(history, available)

        return ChatRequest(
            messages=trimmed,
            system=system,
            tools=tools or [],
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def _select_within_budget(
        self, history: list[Message], budget: int
    ) -> list[Message]:
        """从最新消息向前选择，不超过 token 预算。

        保证：
        - 最后一条消息一定保留（通常是最新 user 输入）
        - 硬上限 max_history_turns * 2 条
        """
        if not history:
            return []

        max_messages = self._max_history_turns * 2
        # 先应用硬上限
        candidates = history[-max_messages:] if len(history) > max_messages else history

        # 从后向前贪心
        selected: list[Message] = []
        used = 0

        for msg in reversed(candidates):
            msg_tokens = count_message_tokens(msg)
            if used + msg_tokens > budget and selected:
                # 预算用完（但已保证至少保留最后一条）
                break
            selected.insert(0, msg)
            used += msg_tokens

        return selected
