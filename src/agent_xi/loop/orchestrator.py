"""Outer Loop — 自主推进编排引擎。

参考 cc-haha 的 coordinator/goals/tasks 系统设计。

核心职责：
- 接收用户目标 → 拆解为步骤 → 分配执行 → 验证 → 续跑
- 状态外置到文件系统，支持断点续跑
- 防失控三机制：步骤上限、token 预算、停止条件
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from .guard import LoopGuard
from .state import LoopState, StepStatus

if TYPE_CHECKING:
    from ..brain.engine import Brain

logger = logging.getLogger(__name__)


class GoalStatus(StrEnum):
    """目标状态。"""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class Step:
    """单个执行步骤。"""
    index: int
    description: str
    verification: str = ""  # 如何验证此步完成
    status: StepStatus = StepStatus.PENDING
    result: str = ""
    error: str = ""
    depends_on: list[int] = field(default_factory=list)  # 依赖的步骤索引


@dataclass(slots=True)
class Goal:
    """一个用户目标。"""
    id: str
    description: str
    steps: list[Step] = field(default_factory=list)
    status: GoalStatus = GoalStatus.PENDING
    created_at: float = 0.0
    updated_at: float = 0.0


class Orchestrator:
    """Outer Loop 编排器。

    负责：
    1. 目标拆解（调用 LLM 将用户目标分解为步骤）
    2. 逐步执行（驱动 Brain 完成每个步骤）
    3. 验证与续跑（检查步骤完成状态，失败时调整）
    4. 状态持久化（断点续跑）

    使用方式：
        orchestrator = Orchestrator(brain, state_dir=Path(".data/loop_state"))
        async for event in orchestrator.run_goal("重构认证模块"):
            # 处理事件（进度更新、步骤完成等）
    """

    def __init__(
        self,
        brain: Brain,
        state: LoopState,
        guard: LoopGuard | None = None,
    ) -> None:
        self._brain = brain
        self._state = state
        self._guard = guard or LoopGuard()
        self._current_goal: Goal | None = None

    @property
    def current_goal(self) -> Goal | None:
        return self._current_goal

    async def run_goal(self, goal_description: str) -> Goal:
        """执行一个完整目标：拆解 → 执行 → 验证 → 汇总。

        Args:
            goal_description: 用户目标描述。

        Returns:
            完成后的 Goal 对象（含所有步骤结果）。
        """
        import time
        import uuid

        goal_id = str(uuid.uuid4())[:8]
        goal = Goal(
            id=goal_id,
            description=goal_description,
            status=GoalStatus.RUNNING,
            created_at=time.time(),
            updated_at=time.time(),
        )
        self._current_goal = goal

        # 1. 拆解目标
        goal.steps = await self._decompose(goal_description)
        if not goal.steps:
            goal.status = GoalStatus.FAILED
            return goal

        self._state.save_goal(goal)

        # 2. 逐步执行
        for step in goal.steps:
            if self._guard.should_stop(goal):
                goal.status = GoalStatus.PAUSED
                logger.warning(
                    "目标 %s 达到停止条件，暂停（已完成 %d/%d 步）",
                    goal_id,
                    self._completed_steps(goal),
                    len(goal.steps),
                )
                break

            step.status = StepStatus.RUNNING
            goal.updated_at = time.time()
            self._state.save_goal(goal)

            try:
                step.result = await self._execute_step(step)
                step.status = StepStatus.DONE
            except Exception as e:
                step.error = str(e)
                # 尝试调整：重新执行一次
                logger.warning("步骤 %d 失败: %s，尝试调整后重试", step.index, e)
                try:
                    step.result = await self._execute_step(step)
                    step.status = StepStatus.DONE
                    step.error = ""
                except Exception as e2:
                    step.error = str(e2)
                    step.status = StepStatus.FAILED
                    if self._guard.consecutive_failures >= 2:
                        logger.error("连续失败，终止目标")
                        goal.status = GoalStatus.FAILED
                        break

            goal.updated_at = time.time()
            self._state.save_goal(goal)

        # 3. 汇总
        if goal.status != GoalStatus.FAILED:
            goal.status = GoalStatus.DONE
        self._state.save_goal(goal)
        return goal

    async def resume_goal(self, goal_id: str) -> Goal:
        """断点续跑：从状态文件恢复并继续执行。"""
        goal = self._state.load_goal(goal_id)
        if not goal:
            raise ValueError(f"目标不存在: {goal_id}")

        self._current_goal = goal
        goal.status = GoalStatus.RUNNING
        self._state.save_goal(goal)

        import time

        for step in goal.steps:
            if step.status == StepStatus.DONE:
                continue  # 跳过已完成的步骤

            if self._guard.should_stop(goal):
                goal.status = GoalStatus.PAUSED
                break

            step.status = StepStatus.RUNNING
            goal.updated_at = time.time()
            self._state.save_goal(goal)

            try:
                step.result = await self._execute_step(step)
                step.status = StepStatus.DONE
            except Exception as e:
                step.error = str(e)
                step.status = StepStatus.FAILED
                if self._guard.consecutive_failures >= 2:
                    goal.status = GoalStatus.FAILED
                    break

            goal.updated_at = time.time()
            self._state.save_goal(goal)

        if goal.status != GoalStatus.FAILED:
            goal.status = GoalStatus.DONE
        self._state.save_goal(goal)
        return goal

    async def _decompose(self, goal_description: str) -> list[Step]:
        """调用 LLM 将目标拆解为步骤清单。

        使用 Brain.chat 进行单轮对话，让 LLM 产出结构化步骤。
        """
        decompose_prompt = f"""\
将以下目标拆解为 3-10 个可独立执行的步骤。每个步骤包含：
1. 一句话描述
2. 验证标准（如何判断完成）

目标：{goal_description}

输出格式（JSON）：
```json
[
  {{"index": 1, "description": "...", "verification": "..."}},
  ...
]
```

要求：
- 步骤之间逻辑清晰，有依赖关系的标注在前
- 每步都应该是可独立验证的
- 如果目标很简单，3-5 步即可；复杂的 8-10 步"""

        try:
            full_text = ""
            async for event in self._brain.chat(decompose_prompt):
                if hasattr(event, "text") and event.text:
                    full_text += event.text
            return self._parse_steps(full_text)
        except Exception as e:
            logger.error("目标拆解失败: %s", e)
            return []

    def _parse_steps(self, raw: str) -> list[Step]:
        """从 LLM 输出中解析步骤 JSON。"""
        import json
        import re

        # 尝试提取 JSON 块
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
        if json_match:
            raw = json_match.group(1)

        # 尝试找到 JSON 数组
        array_match = re.search(r"\[[\s\S]*\]", raw)
        if not array_match:
            return []
        raw = array_match.group(0)

        try:
            items = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("无法解析步骤 JSON: %s", raw[:200])
            return []

        if not isinstance(items, list):
            return []

        return [
            Step(
                index=item.get("index", i + 1),
                description=item.get("description", ""),
                verification=item.get("verification", ""),
            )
            for i, item in enumerate(items)
        ]

    async def _execute_step(self, step: Step) -> str:
        """执行单个步骤：通过 Brain 调用 LLM + 工具。"""
        prompt = (
            f"执行以下步骤（这是 Outer Loop 的第 {step.index} 步）：\n\n"
            f"{step.description}\n\n"
            f"验证标准：{step.verification}\n\n"
            "执行完成后，用一句话汇报结果。"
        )

        full_text = ""
        async for event in self._brain.chat(prompt):
            if hasattr(event, "text") and event.text:
                full_text += event.text

        return full_text.strip() or "（步骤执行完成，无文本输出）"

    def _completed_steps(self, goal: Goal) -> int:
        return sum(1 for s in goal.steps if s.status == StepStatus.DONE)

    def cancel(self) -> None:
        """取消当前目标。"""
        if self._current_goal:
            self._current_goal.status = GoalStatus.CANCELLED
            self._state.save_goal(self._current_goal)