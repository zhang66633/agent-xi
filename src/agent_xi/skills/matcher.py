"""Skill 匹配引擎 — 关键词 + 语义混合检索。"""

from __future__ import annotations

import logging

from .models import Skill
from .store import SkillStore

logger = logging.getLogger(__name__)

# 语义匹配最低分数阈值
_MIN_SEMANTIC_SCORE = 0.4


class SkillMatcher:
    """技能匹配器：混合关键词 + 语义检索。

    匹配流程：
    1. 关键词快速过滤（精确命中）
    2. 语义向量检索 top-K
    3. 合并去重，按综合分排序
    """

    def __init__(self, store: SkillStore) -> None:
        self._store = store

    async def match(
        self, user_input: str, top_k: int = 3
    ) -> list[Skill]:
        """匹配用户输入相关的技能。

        Args:
            user_input: 用户输入文本。
            top_k: 最多返回几个匹配结果。

        Returns:
            匹配到的技能列表（按相关度排序）。
        """
        if self._store.count == 0:
            return []

        # 1. 关键词命中
        keyword_hits = self._store.search_by_keywords(user_input)

        # 2. 语义检索
        semantic_hits = await self._store.semantic_search(
            user_input, top_k=top_k * 2
        )

        # 3. 合并去重
        seen_ids: set[str] = set()
        merged: list[tuple[Skill, float]] = []

        # 关键词命中的给高分
        for skill in keyword_hits:
            if skill.id not in seen_ids:
                seen_ids.add(skill.id)
                merged.append((skill, 0.9))

        # 语义检索结果
        for skill, score in semantic_hits:
            if skill.id not in seen_ids and score >= _MIN_SEMANTIC_SCORE:
                seen_ids.add(skill.id)
                merged.append((skill, score))

        # 按分数排序
        merged.sort(key=lambda x: x[1], reverse=True)

        return [skill for skill, _ in merged[:top_k]]

    async def get_context(self, user_input: str) -> str:
        """获取匹配技能的上下文注入文本。

        如果匹配到技能，返回格式化的步骤指引；否则返回空字符串。
        """
        matched = await self.match(user_input, top_k=1)

        if not matched:
            return ""

        skill = matched[0]
        self._store.update_usage(skill.id)

        logger.debug("Skill matched: '%s' for input: %s", skill.name, user_input[:50])

        return (
            "## 匹配到相关技能，请参考以下步骤执行：\n\n"
            + skill.to_context_block()
        )
