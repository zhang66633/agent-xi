"""Scheduler — 定时任务系统。

参考 cc-haha 的 Scheduled Tasks 设计。

使用 APScheduler 在后台运行定时任务，
每个任务在独立会话中执行，结果记录到 .data/scheduler/。
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..brain.engine import Brain


@dataclass(slots=True)
class ScheduledTask:
    """定时任务定义。"""

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    prompt: str = ""  # 发送给 Xi 的 prompt
    cron_expression: str = ""  # 如 "0 9 * * *"（每天 9 点）
    enabled: bool = True
    created_at: float = field(default_factory=time.time)
    last_run: float = 0.0
    run_count: int = 0
    last_result: str = ""


class SchedulerStore:
    """定时任务持久化存储。

    存储路径：<data_dir>/scheduler/tasks.json
    运行日志：<data_dir>/scheduler/logs/<task_id>/
    """

    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "scheduler"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._tasks_path = self._dir / "tasks.json"
        self._logs_dir = self._dir / "logs"
        self._logs_dir.mkdir(parents=True, exist_ok=True)

    def load_tasks(self) -> list[ScheduledTask]:
        """加载所有定时任务。"""
        if not self._tasks_path.exists():
            return []
        try:
            data = json.loads(self._tasks_path.read_text(encoding="utf-8"))
            return [
                ScheduledTask(
                    id=t["id"],
                    name=t["name"],
                    prompt=t["prompt"],
                    cron_expression=t.get("cron_expression", ""),
                    enabled=t.get("enabled", True),
                    created_at=t.get("created_at", 0),
                    last_run=t.get("last_run", 0),
                    run_count=t.get("run_count", 0),
                    last_result=t.get("last_result", ""),
                )
                for t in data
            ]
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("加载定时任务失败: %s", e)
            return []

    def save_tasks(self, tasks: list[ScheduledTask]) -> None:
        """保存定时任务列表。"""
        data = [
            {
                "id": t.id,
                "name": t.name,
                "prompt": t.prompt,
                "cron_expression": t.cron_expression,
                "enabled": t.enabled,
                "created_at": t.created_at,
                "last_run": t.last_run,
                "run_count": t.run_count,
                "last_result": t.last_result,
            }
            for t in tasks
        ]
        self._tasks_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def log_result(self, task_id: str, result: str, success: bool) -> None:
        """记录任务执行结果。"""
        task_log_dir = self._logs_dir / task_id
        task_log_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        log_path = task_log_dir / f"{timestamp}.log"
        log_path.write_text(
            f"# {task_id} — {'成功' if success else '失败'}\n"
            f"时间: {timestamp}\n\n"
            f"{result}",
            encoding="utf-8",
        )

    def get_logs(self, task_id: str, limit: int = 10) -> list[dict[str, Any]]:
        """获取任务执行日志列表。"""
        task_log_dir = self._logs_dir / task_id
        if not task_log_dir.exists():
            return []

        logs = []
        for log_file in sorted(task_log_dir.glob("*.log"), reverse=True)[:limit]:
            logs.append({
                "timestamp": log_file.stem,
                "path": str(log_file),
            })
        return logs


class SchedulerRunner:
    """定时任务执行器。

    使用简单的 asyncio 循环检查 cron 表达式，
    而非 APScheduler（减少依赖）。

    用法：
        runner = SchedulerRunner(store, brain_factory)
        await runner.start()
        # ... 应用运行中 ...
        await runner.stop()
    """

    def __init__(
        self,
        store: SchedulerStore,
        brain_factory: Any,  # Callable[[], Brain] — 每次执行创建新 Brain
        check_interval: float = 60.0,  # 每 60 秒检查一次
    ) -> None:
        self._store = store
        self._brain_factory = brain_factory
        self._check_interval = check_interval
        self._tasks: list[ScheduledTask] = []
        self._running = False
        self._task: asyncio.Task[None] | None = None  # type: ignore[valid-type]

    async def start(self) -> None:
        """启动调度器。"""
        import asyncio

        self._tasks = self._store.load_tasks()
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(
            "调度器已启动，%d 个任务，检查间隔 %.0fs",
            len(self._tasks),
            self._check_interval,
        )

    async def stop(self) -> None:
        """停止调度器。"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("调度器已停止")

    async def _loop(self) -> None:
        """主循环：定期检查 cron 表达式并执行到期任务。"""
        import asyncio

        while self._running:
            now = time.time()
            for task in self._tasks:
                if not task.enabled:
                    continue
                if self._should_run(task, now):
                    await self._run_task(task)
                    task.last_run = now
                    self._store.save_tasks(self._tasks)

            await asyncio.sleep(self._check_interval)

    def _should_run(self, task: ScheduledTask, now: float) -> bool:
        """检查 cron 表达式是否匹配当前时间。"""
        if not task.cron_expression:
            return False

        # 简单 cron 解析（支持 "*/N" 和具体值）
        # 格式: minute hour day_of_month month day_of_week
        try:
            parts = task.cron_expression.strip().split()
            if len(parts) != 5:
                return False

            dt = datetime.fromtimestamp(now)
            fields = {
                "minute": dt.minute,
                "hour": dt.hour,
                "day": dt.day,
                "month": dt.month,
                "weekday": dt.weekday(),  # 0=Monday
            }

            field_names = ["minute", "hour", "day", "month", "weekday"]
            for i, field_name in enumerate(field_names):
                if not self._match_field(parts[i], fields[field_name]):
                    return False

            # 避免同一分钟内重复执行
            if task.last_run > 0 and (now - task.last_run) < 60:
                return False

            return True
        except Exception:
            return False

    @staticmethod
    def _match_field(pattern: str, value: int) -> bool:
        """匹配单个 cron 字段。"""
        if pattern == "*":
            return True

        # 逗号分隔的多个值: "1,3,5"
        if "," in pattern:
            return any(
                SchedulerRunner._match_field(p.strip(), value)
                for p in pattern.split(",")
            )

        # 步长: "*/5"
        if pattern.startswith("*/"):
            step = int(pattern[2:])
            return value % step == 0

        # 范围: "1-5"
        if "-" in pattern:
            low, high = pattern.split("-")
            return int(low) <= value <= int(high)

        # 精确值
        return value == int(pattern)

    async def _run_task(self, task: ScheduledTask) -> None:
        """执行单个定时任务。"""
        logger.info("执行定时任务: %s", task.name)
        task.run_count += 1

        try:
            brain = self._brain_factory()
            full_text = ""
            async for event in brain.chat(task.prompt):
                if hasattr(event, "text") and event.text:
                    full_text += event.text

            task.last_result = full_text[:500]
            self._store.log_result(task.id, full_text, True)
            logger.info("定时任务完成: %s", task.name)
        except Exception as e:
            error_msg = f"执行失败: {e}"
            task.last_result = error_msg
            self._store.log_result(task.id, error_msg, False)
            logger.error("定时任务失败: %s — %s", task.name, e)