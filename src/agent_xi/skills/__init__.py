"""Skills 语义技能系统。

技能 = 可复用的流程知识，通过语义匹配触发，注入对话上下文指导 LLM 执行。
存储：SQLite 元数据 + LanceDB 向量检索。
"""

from .matcher import SkillMatcher
from .models import Skill
from .store import SkillStore

__all__ = ["Skill", "SkillMatcher", "SkillStore"]
