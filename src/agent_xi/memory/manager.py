"""记忆管理器 — 统一协调两层持久记忆。

职责：
- 初始化并持有情景记忆 / 语义记忆实例
- 提供统一的 remember / recall 接口
- 对话结束时触发 LLM 深度提取（语义记忆）
- 规则快捕：每轮用户输入后自动扫描偏好/事实

注：对话滑动窗口（原 WorkingMemory）已移除，
当前对话历史由 Brain.history + ContextBuilder 裁剪管理。
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..llm.base import LLMClient
from ..llm.types import ChatRequest, Message, Role
from .embedding import EmbeddingClient
from .episodic import EpisodicMemory
from .semantic import SemanticMemory

logger = logging.getLogger(__name__)

# LLM 提取语义记忆的 prompt
_EXTRACT_PROMPT = """\
分析以下对话，提取用户的偏好、习惯、事实信息。
只输出确定性的信息，每条一行，格式：类别|内容
类别包括：preference（偏好）、habit（习惯）、fact（事实）、current_project（当前项目）
如果没有新信息，输出：无

对话内容：
{conversation}
"""


class MemoryManager:
    """统一记忆管理器。"""

    def __init__(
        self,
        data_dir: Path,
        embedding_client: EmbeddingClient,
        llm_client: LLMClient,
    ) -> None:
        self._data_dir = data_dir
        self._llm = llm_client

        # 初始化两层持久记忆（对话窗口由 Brain.history + ContextBuilder 管理）
        self.episodic = EpisodicMemory(
            db_path=data_dir / "episodic",
            embedding_client=embedding_client,
        )
        self.semantic = SemanticMemory(
            db_path=data_dir / "semantic.db",
        )

    async def on_user_input(self, text: str) -> list[str]:
        """每轮用户输入后调用：规则快捕语义记忆。

        Returns:
            新捕获的事实列表（用于反馈给用户）。
        """
        captures = self.semantic.extract_from_text(text)
        stored: list[str] = []
        for content, category in captures:
            is_new = self.semantic.store(content, category=category, source="rule")
            if is_new:
                stored.append(content)
                logger.info("规则捕获: [%s] %s", category, content)
        return stored

    async def remember_episode(
        self,
        content: str,
        summary: str = "",
        tags: list[str] | None = None,
    ) -> str:
        """显式记忆：用户说"记住..."时调用。"""
        memory_id = await self.episodic.remember(content, summary, tags)
        logger.info("情景记忆已存储: %s", content[:50])
        return memory_id

    async def recall_context(self, query: str, top_k: int = 3) -> str:
        """检索相关记忆，格式化为可注入 prompt 的文本。

        合并情景记忆和语义记忆的结果。
        """
        parts: list[str] = []

        # 情景记忆检索
        episodes = await self.episodic.recall(query, top_k=top_k)
        if episodes:
            parts.append("[相关历史记忆]")
            for ep in episodes:
                parts.append(f"- {ep['summary']}")

        # 语义记忆（用户画像）
        semantic_text = self.semantic.format_for_prompt(limit=5)
        if semantic_text:
            parts.append(semantic_text)

        return "\n".join(parts)

    async def on_conversation_end(self, history: list[Message]) -> list[str]:
        """对话结束时调用：LLM 深度提取语义记忆。

        Args:
            history: 本次对话的完整消息历史。

        Returns:
            新提取的事实列表。
        """
        if len(history) < 2:
            return []

        # 格式化对话内容
        conversation_text = self._format_history(history)

        # 调用 LLM 提取
        extract_content = _EXTRACT_PROMPT.format(
            conversation=conversation_text
        )
        request = ChatRequest(
            messages=[Message(role=Role.USER, content=extract_content)],
            system="你是一个信息提取助手，只输出结构化结果。",
            temperature=0.1,
            max_tokens=500,
        )

        try:
            response = await self._llm.chat(request)
            extracted_text = response.message.text
        except Exception as e:
            logger.warning("LLM 提取失败: %s", e)
            return []

        # 解析提取结果
        return self._parse_extraction(extracted_text)

    def _parse_extraction(self, text: str) -> list[str]:
        """解析 LLM 提取结果并存入语义记忆。"""
        stored: list[str] = []
        for line in text.strip().splitlines():
            line = line.strip()
            if not line or line == "无":
                continue
            if "|" in line:
                category, content = line.split("|", 1)
                category = category.strip().lower()
                content = content.strip()
                if content and len(content) >= 4:
                    is_new = self.semantic.store(
                        content, category=category, source="llm", confidence=0.8
                    )
                    if is_new:
                        stored.append(content)
                        logger.info("LLM 提取: [%s] %s", category, content)
        return stored

    @staticmethod
    def _format_history(history: list[Message], max_turns: int = 20) -> str:
        """将消息历史格式化为文本（限制长度）。"""
        lines: list[str] = []
        recent = history[-(max_turns * 2):]
        for msg in recent:
            role_label = "用户" if msg.role == Role.USER else "Xi"
            lines.append(f"{role_label}: {msg.text}")
        return "\n".join(lines)

    def close(self) -> None:
        """关闭所有资源。"""
        self.semantic.close()
