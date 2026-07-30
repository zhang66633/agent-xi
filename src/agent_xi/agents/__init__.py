"""多智能体协作包。

参考 cc-haha 的 assistant/coordinator/goals/tasks 多角色设计。

提供：
- AgentRole 基类：独立 system prompt + 工具白名单
- Planner: 需求拆解为方案
- Coder: 按方案执行代码
- Reviewer: 对抗验证审查
- Coordinator: 编排多角色协作
"""

from .base import AgentContext, AgentResult, AgentRole
from .coder import Coder
from .coordinator import Coordinator
from .planner import Planner
from .reviewer import Reviewer

__all__ = [
    "AgentContext",
    "AgentResult",
    "AgentRole",
    "Coder",
    "Coordinator",
    "Planner",
    "Reviewer",
]