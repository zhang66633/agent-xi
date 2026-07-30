"""Task 工具 — 任务清单管理。

对标 Claude Code 的 TodoWrite 工具。
让 LLM 可以创建和更新自己的任务清单，追踪进度。
"""

from __future__ import annotations

import json
from typing import Any

from ..base import SecurityLevel, Tool, ToolResult


class TaskListTool(Tool):
    """任务清单管理：创建/更新任务列表，追踪执行进度。"""

    @property
    def name(self) -> str:
        return "task"

    @property
    def description(self) -> str:
        return (
            "创建并管理任务清单。用于追踪多步任务的执行进度。"
            "每次更新时传入完整的任务列表（替换而非追加）。"
            "任务状态: pending, in_progress, completed, cancelled。"
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "description": "任务列表",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {
                                "type": "string",
                                "description": "任务标识符",
                            },
                            "status": {
                                "type": "string",
                                "enum": ["pending", "in_progress", "completed", "cancelled"],
                                "description": "任务状态",
                            },
                            "content": {
                                "type": "string",
                                "description": "任务描述",
                            },
                        },
                        "required": ["id", "status", "content"],
                    },
                },
            },
            "required": ["tasks"],
        }

    @property
    def security_level(self) -> SecurityLevel:
        return SecurityLevel.SAFE

    async def execute(self, **kwargs: Any) -> ToolResult:
        tasks = kwargs.get("tasks", [])
        if not isinstance(tasks, list):
            return ToolResult(success=False, output="", error="tasks 必须是列表")

        # 格式化展示
        status_icons = {
            "pending": "○",
            "in_progress": "◉",
            "completed": "✔",
            "cancelled": "✗",
        }

        lines = [f"# 任务清单 ({len(tasks)} 项)\n"]
        for t in tasks:
            icon = status_icons.get(t.get("status", "pending"), "?")
            lines.append(f"- {icon} [{t.get('id', '?')}] {t.get('content', '')}")

        output = "\n".join(lines)

        return ToolResult(
            success=True,
            output=output,
            metadata={"task_count": len(tasks)},
        )