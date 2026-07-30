"""Outer Loop 包。

提供自主目标推进能力：
- Orchestrator: 目标拆解 → 执行 → 验证 → 续跑
- LoopState: 状态外置持久化
- LoopGuard: 防失控安全边界
"""

from .guard import LoopGuard
from .orchestrator import Goal, GoalStatus, Orchestrator, Step
from .state import LoopState, StepStatus

__all__ = [
    "Goal",
    "GoalStatus",
    "LoopGuard",
    "LoopState",
    "Orchestrator",
    "Step",
    "StepStatus",
]