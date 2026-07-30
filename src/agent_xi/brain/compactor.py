"""上下文压缩器 — 对标 cc-haha 的 snip/compact。

当 token 预算使用超过阈值时，用 LLM 将旧消息总结为摘要，
替换原始消息以释放上下文空间。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..llm.types import (
    ChatRequest,
    Message,
    Role,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)
from .tokenizer import TokenCounter

if TYPE_CHECKING:
    from ..llm.base import LLMClient

logger = logging.getLogger(__name__)

# 触发压缩的预算使用阈值（70%）
_COMPACT_THRESHOLD = 0.7

# 保留最近 N 轮对话不压缩
_PRESERVE_RECENT_TURNS = 3

# 压缩 prompt 模板
_COMPACT_PROMPT = """\
请将以下对话历史压缩为一段简洁的摘要。保留关键信息：
- 用户问了什么、要求了什么
- 做了什么操作（工具调用及其结果）
- 做出了什么决定
- 当前进行到哪一步

用第三人称叙述，不超过 500 字，不要丢失任何重要的上下文。

对话历史：
---
{conversation}
---

摘要："""


class ContextCompactor:
    """上下文压缩器。

    用途：当对话历史的 token 数超过预算的 70% 时，
    将旧消息压缩为摘要，释放空间给新对话。

    用法：
        compactor = ContextCompactor(llm_client, max_budget=128000)
        if compactor.should_compact(history, fixed_cost):
            compaction = await compactor.compact(history)
            # 将 compaction.summary 注入 system prompt
            # 将 history 替换为 compaction.truncated_history
    """

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        max_budget: int = 128_000,
        threshold: float = _COMPACT_THRESHOLD,
    ) -> None:
        self._llm = llm_client
        self._max_budget = max_budget
        self._threshold = threshold
        self._counter = TokenCounter()

    def should_compact(
        self,
        history: list[Message],
        fixed_cost: int = 0,
    ) -> bool:
        """检查是否需要压缩。"""
        total = self._counter.count_messages(history) + fixed_cost
        return total > self._max_budget * self._threshold

    async def compact(
        self,
        history: list[Message],
    ) -> dict | None:
        """压缩对话历史。

        保留最近的 _PRESERVE_RECENT_TURNS 轮对话不变，
        将更早的消息总结为一段摘要。

        Returns:
            {"summary": str, "compacted_count": int, "truncated_history": list[Message]}
            如果无法压缩（没有 LLM 客户端或历史太短）返回 None。
        """
        if not self._llm or len(history) < 4:
            return None

        # 找分割点：从后往前数 user 消息
        user_indices = [
            i for i, m in enumerate(history) if m.role == Role.USER
        ]
        if len(user_indices) <= _PRESERVE_RECENT_TURNS:
            return None

        split_idx = user_indices[-(_PRESERVE_RECENT_TURNS)]

        old_messages = history[:split_idx]
        recent_messages = history[split_idx:]

        # 将旧消息格式化为文本
        conversation_text = self._format_for_compaction(old_messages)
        if len(conversation_text) < 200:
            return None  # 太短不值得压缩

        prompt = _COMPACT_PROMPT.format(conversation=conversation_text)

        try:
            request = ChatRequest(
                messages=[Message(role=Role.USER, content=prompt)],
                system="你是一个对话摘要助手。只输出摘要，不要解释。",
                temperature=0.2,
                max_tokens=800,
            )
            response = await self._llm.chat(request)
            summary = response.message.text.strip()
        except Exception as e:
            logger.warning("上下文压缩失败: %s", e)
            return None

        logger.info(
            "上下文已压缩: %d 条消息 → %d 字符摘要",
            len(old_messages),
            len(summary),
        )

        return {
            "summary": summary,
            "compacted_count": len(old_messages),
            "truncated_history": recent_messages,
        }

    @staticmethod
    def _format_for_compaction(messages: list[Message]) -> str:
        """将消息列表格式化为 LLM 可理解的文本。"""
        lines = []
        for msg in messages:
            if msg.role == Role.USER:
                lines.append(f"用户: {msg.text}")
            elif msg.role == Role.ASSISTANT:
                text = msg.text
                tus = msg.tool_use_blocks
                if tus:
                    tools_str = ", ".join(t.name for t in tus)
                    text = f"{text}\n  [调用工具: {tools_str}]"
                lines.append(f"Xi: {text}")
            elif msg.role == Role.TOOL:
                # 只取前 200 字符的工具结果
                result = msg.text[:200]
                lines.append(f"  [工具结果]: {result}...")
        return "\n".join(lines)