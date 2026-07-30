"""Loop State — 状态外置持久化。

将 Outer Loop 的进度、计划写入文件系统，
即使上下文被截断也能断点续跑。

参考 cc-haha 的 scheduled tasks 和 session 持久化模式。
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class StepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class GoalStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class StepRecord:
    """步骤持久化记录。"""
    index: int
    description: str
    verification: str = ""
    status: str = "pending"
    result: str = ""
    error: str = ""
    depends_on: list[int] = field(default_factory=list)


@dataclass(slots=True)
class GoalRecord:
    """目标持久化记录。"""
    id: str
    description: str
    steps: list[StepRecord] = field(default_factory=list)
    status: str = "pending"
    created_at: float = 0.0
    updated_at: float = 0.0


class LoopState:
    """Outer Loop 状态管理。

    持久化路径：<data_dir>/loop_state/
    - goals/<goal_id>.json  — 单个目标的状态
    - index.json             — 目标索引（最近 N 个目标）
    """

    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "loop_state"
        self._goals_dir = self._dir / "goals"
        self._goals_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._dir / "index.json"

    def save_goal(self, goal: Any) -> None:
        """保存目标状态到文件。"""
        steps_data = []
        for step in goal.steps:
            steps_data.append({
                "index": step.index,
                "description": step.description,
                "verification": getattr(step, "verification", ""),
                "status": str(step.status),
                "result": getattr(step, "result", ""),
                "error": getattr(step, "error", ""),
                "depends_on": getattr(step, "depends_on", []),
            })

        record = {
            "id": goal.id,
            "description": goal.description,
            "steps": steps_data,
            "status": str(goal.status),
            "created_at": goal.created_at,
            "updated_at": time.time(),
        }

        # 写入目标文件
        goal_path = self._goals_dir / f"{goal.id}.json"
        goal_path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # 更新索引
        self._update_index(goal.id, goal.description, str(goal.status))

    def load_goal(self, goal_id: str) -> Any | None:
        """从文件加载目标状态。"""
        goal_path = self._goals_dir / f"{goal_id}.json"
        if not goal_path.exists():
            return None

        try:
            data = json.loads(goal_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("加载目标状态失败 %s: %s", goal_id, e)
            return None

        # 重建 Goal 对象（避免循环导入）
        from .orchestrator import Goal, GoalStatus, Step

        steps = [
            Step(
                index=s["index"],
                description=s["description"],
                verification=s.get("verification", ""),
                status=StepStatus(s["status"]),
                result=s.get("result", ""),
                error=s.get("error", ""),
                depends_on=s.get("depends_on", []),
            )
            for s in data.get("steps", [])
        ]

        return Goal(
            id=data["id"],
            description=data["description"],
            steps=steps,
            status=GoalStatus(data["status"]),
            created_at=data.get("created_at", 0.0),
            updated_at=data.get("updated_at", 0.0),
        )

    def list_goals(self, limit: int = 20) -> list[dict[str, Any]]:
        """列出最近的目标摘要。"""
        index = self._load_index()
        return index[-limit:]

    def delete_goal(self, goal_id: str) -> bool:
        """删除目标及其状态文件。"""
        goal_path = self._goals_dir / f"{goal_id}.json"
        if goal_path.exists():
            goal_path.unlink()
            self._remove_from_index(goal_id)
            return True
        return False

    def _update_index(self, goal_id: str, description: str, status: str) -> None:
        index = self._load_index()
        # 更新或追加
        for entry in index:
            if entry["id"] == goal_id:
                entry["description"] = description
                entry["status"] = status
                entry["updated_at"] = time.time()
                break
        else:
            index.append({
                "id": goal_id,
                "description": description[:100],
                "status": status,
                "created_at": time.time(),
                "updated_at": time.time(),
            })

        # 限制索引大小
        if len(index) > 100:
            index = index[-100:]

        self._index_path.write_text(
            json.dumps(index, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _remove_from_index(self, goal_id: str) -> None:
        index = self._load_index()
        index = [e for e in index if e["id"] != goal_id]
        self._index_path.write_text(
            json.dumps(index, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load_index(self) -> list[dict[str, Any]]:
        if not self._index_path.exists():
            return []
        try:
            return json.loads(self._index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []