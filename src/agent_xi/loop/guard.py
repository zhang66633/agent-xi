"""Loop Guard — 防失控机制。

参考 cc-haha 的权限系统和 cc-haha 的 step limits。

三机制：
1. 最大步数限制（防止无限循环）
2. 连续失败检测（连续 2 步失败 → 暂停）
3. 时间/预算限制（可选）
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .orchestrator import Goal

logger = logging.getLogger(__name__)


class LoopGuard:
    """Outer Loop 防失控守卫。

    每个目标执行期间持续检查安全边界，
    触发任一条件时 should_stop() 返回 True。
    """

    def __init__(
        self,
        max_steps: int = 20,
        max_failures: int = 2,
        max_duration_seconds: float | None = None,
    ) -> None:
        self._max_steps = max_steps
        self._max_failures = max_failures
        self._max_duration = max_duration_seconds
        self._consecutive_failures = 0
        self._start_time: float | None = None

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    def should_stop(self, goal: Any) -> bool:
        """检查是否应该停止当前目标。

        Args:
            goal: 当前 Goal 对象。

        Returns:
            True 表示应该停止。
        """
        # 1. 步数检查
        completed = sum(
            1 for s in goal.steps
            if getattr(s, "status", None) and str(s.status) == "done"
        )
        if completed >= self._max_steps:
            logger.warning(
                "目标 %s 达到最大步数上限 (%d)，建议拆分目标",
                goal.id,
                self._max_steps,
            )
            return True

        # 2. 连续失败检查
        if self._consecutive_failures >= self._max_failures:
            logger.warning(
                "目标 %s 连续失败 %d 次，暂停执行",
                goal.id,
                self._consecutive_failures,
            )
            return True

        # 3. 时间限制
        if self._max_duration and self._start_time:
            elapsed = time.time() - self._start_time
            if elapsed > self._max_duration:
                logger.warning(
                    "目标 %s 超时 (%.0fs > %.0fs)",
                    goal.id,
                    elapsed,
                    self._max_duration,
                )
                return True

        return False

    def record_success(self) -> None:
        """记录一次成功（重置连续失败计数器）。"""
        self._consecutive_failures = 0

    def record_failure(self) -> None:
        """记录一次失败（递增连续失败计数器）。"""
        self._consecutive_failures += 1

    def reset(self) -> None:
        """重置所有计数器（开始新目标时调用）。"""
        self._consecutive_failures = 0
        self._start_time = time.time()