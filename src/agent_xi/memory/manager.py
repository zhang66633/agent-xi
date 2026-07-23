"""记忆管理器 — 整合文档范式。

核心变化（v2）：
- 用户画像 = config/service.md（整合文档），会话结束时 LLM 整体重写
- 不再使用原子 fact 提取（删除规则快捕 + SQLite semantic）
- 情景记忆（LanceDB）保留：用户显式"记住..."时存储，向量检索浮现

职责：
- 初始化并持有情景记忆实例
- recall_context：检索相关情景记忆
- on_conversation_end：整体重写 service.md + 版本快照
- remember_episode：显式记忆存储
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from ..llm.base import LLMClient
from ..llm.types import ChatRequest, Message, Role
from .embedding import EmbeddingClient
from .episodic import EpisodicMemory

logger = logging.getLogger(__name__)

# 整体重写 service.md 的 prompt
_REWRITE_PROMPT = """\
你正在更新你的「我为谁服务」档案——这是你对用户的长期认知，是你下次醒来时了解他们的唯一依据。

当前档案：
---
{current_service}
---

本轮对话：
---
{conversation}
---

请重写这份档案。规则：
- 写入前先问自己："这条信息下次醒来不知道，会做错事吗？"答 yes 再写
- 这是状态档案，不是日志。记"用户是什么样的人"，不记"今天聊了什么"
- 整合新信息，删除过时内容，合并重复项
- 只保留长期有价值的认知（偏好、习惯、能力水平、当前项目、沟通风格）
- 不要记录一次性任务细节（"今天让我写了个快排"不是档案）
- 保持简洁，控制在 300 字以内
- 用自然语言描述，像写给未来的自己看的备忘录
- 保留开头的 "# 我为谁服务" 标题
- 如果本轮对话没有产生新认知，原样返回当前档案即可

好的档案内容：
✅ "用户是开发者，主力 Python，正在做 Agent Xi 项目"
✅ "喜欢简洁回答，代码给到位就行不用多解释"
✅ "决策风格：先跑起来再说，不喜欢过度设计"

不要这样写：
❌ "用户今天问了快排怎么写"（事件，不是认知）
❌ "用户说了'不错'"（无信息量）

直接输出完整的新档案内容："""

# 人设进化建议 prompt（identity/personality 修改建议）
_EVOLVE_PROMPT = """\
基于以下对话，你对自己的身份或行为准则有没有新的感悟？

当前身份：
{identity}

当前行为准则：
{personality}

本轮对话：
{conversation}

如果有感悟，用以下格式输出修改建议（可以多条）：
文件|修改描述
例如：personality|加一条"用户讨论架构时，先给结论再展开"

如果没有感悟，输出：无"""


class MemoryManager:
    """整合文档范式的记忆管理器。"""

    def __init__(
        self,
        data_dir: Path,
        embedding_client: EmbeddingClient,
        llm_client: LLMClient,
        config_dir: Path | None = None,
    ) -> None:
        self._data_dir = data_dir
        self._llm = llm_client
        self._config_dir = config_dir or (
            Path(__file__).parent.parent.parent.parent / "config"
        )

        # 情景记忆（保留）
        self.episodic = EpisodicMemory(
            db_path=data_dir / "episodic",
            embedding_client=embedding_client,
        )

        # 人设文件路径
        self._service_path = self._config_dir / "service.md"
        self._identity_path = self._config_dir / "identity.md"
        self._personality_path = self._config_dir / "personality.md"

        # 版本快照目录
        self._history_dir = data_dir / "persona_history"
        self._history_dir.mkdir(parents=True, exist_ok=True)

    async def on_user_input(self, text: str) -> list[str]:
        """兼容接口：不再做规则快捕，直接返回空。

        保留方法签名避免调用方报错，但不再提取任何内容。
        """
        return []

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
        """检索相关情景记忆，格式化为可注入 prompt 的文本。

        注意：用户画像（service.md）已在 system prompt 中，
        此处只返回情景记忆的检索结果。
        """
        episodes = await self.episodic.recall(query, top_k=top_k)
        if not episodes:
            return ""

        parts = ["[相关历史记忆]"]
        for ep in episodes:
            parts.append(f"- {ep['summary']}")
        return "\n".join(parts)

    def get_profile_summary(self) -> str:
        """读取 service.md 内容（去掉标题行），供 API/命令展示。

        如果还是初始占位符则返回空串。
        """
        content = self._read_file(self._service_path).strip()
        if not content or "尚未了解用户" in content:
            return ""
        # 去掉第一行标题
        lines = content.splitlines()
        body = "\n".join(lines[1:]).strip() if lines else ""
        return body

    async def on_conversation_end(self, history: list[Message]) -> list[str]:
        """对话结束时：整体重写 service.md + 人设进化建议。

        Returns:
            变更描述列表（用于通知用户）。
        """
        if len(history) < 2:
            return []

        changes: list[str] = []
        conversation_text = self._format_history(history)

        # 1. 整体重写 service.md
        service_changed = await self._rewrite_service(conversation_text)
        if service_changed:
            changes.append("更新了对你的了解")

        # 2. 人设进化建议（仅记录日志，不自动修改）
        await self._suggest_evolution(conversation_text)

        return changes

    async def _rewrite_service(self, conversation_text: str) -> bool:
        """整体重写 service.md。

        Returns:
            True 如果内容发生了变化。
        """
        current = self._read_file(self._service_path)

        prompt = _REWRITE_PROMPT.format(
            current_service=current,
            conversation=conversation_text,
        )

        request = ChatRequest(
            messages=[Message(role=Role.USER, content=prompt)],
            system="你是一个档案维护助手。只输出档案内容，不要解释。",
            temperature=0.3,
            max_tokens=800,
        )

        try:
            response = await self._llm.chat(request)
            new_content = response.message.text.strip()
        except Exception as e:
            logger.warning("service.md 重写失败: %s", e)
            return False

        # 基本校验：不能为空，必须有一定长度
        if not new_content or len(new_content) < 10:
            logger.warning("service.md 重写结果过短，跳过")
            return False

        # 确保有标题
        if not new_content.startswith("#"):
            new_content = f"# 我为谁服务\n\n{new_content}"

        # 比较是否有变化
        if new_content.strip() == current.strip():
            return False

        # 保存快照
        self._save_snapshot("service.md", current)

        # 写入新内容
        self._service_path.write_text(new_content, encoding="utf-8")
        logger.info("service.md 已更新 (%d → %d 字符)", len(current), len(new_content))
        return True

    async def _suggest_evolution(self, conversation_text: str) -> None:
        """人设进化建议（v1 仅记录，不自动修改）。"""
        identity = self._read_file(self._identity_path)
        personality = self._read_file(self._personality_path)

        prompt = _EVOLVE_PROMPT.format(
            identity=identity,
            personality=personality,
            conversation=conversation_text,
        )

        request = ChatRequest(
            messages=[Message(role=Role.USER, content=prompt)],
            system="你是一个自省助手。只输出结构化结果。",
            temperature=0.2,
            max_tokens=300,
        )

        try:
            response = await self._llm.chat(request)
            result = response.message.text.strip()
            if result and result != "无":
                logger.info("人设进化建议: %s", result)
                # TODO v2: 存储建议，下次对话时征求用户同意后应用
        except Exception as e:
            logger.debug("人设进化建议生成失败（非关键）: %s", e)

    def _save_snapshot(self, filename: str, content: str) -> None:
        """保存文件快照到 persona_history/。"""
        if not content.strip():
            return
        ts = time.strftime("%Y%m%d_%H%M%S")
        snapshot_path = self._history_dir / f"{filename}.{ts}.bak"
        snapshot_path.write_text(content, encoding="utf-8")
        logger.debug("快照已保存: %s", snapshot_path.name)

        # 清理旧快照（每个文件最多保留 20 个）
        self._cleanup_snapshots(filename, keep=20)

    def _cleanup_snapshots(self, filename: str, keep: int = 20) -> None:
        """清理多余快照。"""
        pattern = f"{filename}.*.bak"
        snapshots = sorted(self._history_dir.glob(pattern))
        while len(snapshots) > keep:
            oldest = snapshots.pop(0)
            oldest.unlink()

    @staticmethod
    def _read_file(path: Path) -> str:
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

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
        pass
