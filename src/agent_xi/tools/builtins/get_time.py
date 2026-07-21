"""get_time — 获取当前时间。SAFE 级别。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ..base import SecurityLevel, Tool, ToolResult


class GetTimeTool(Tool):
    """获取当前日期和时间。"""

    @property
    def name(self) -> str:
        return "get_time"

    @property
    def description(self) -> str:
        return "获取当前的日期和时间。可以指定时区，默认为 Asia/Shanghai (UTC+8)。"

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "timezone": {
                    "type": "string",
                    "description": "时区偏移，如 '+8' 或 '-5'，默认为 '+8'（北京时间）",
                },
            },
            "required": [],
        }

    @property
    def security_level(self) -> SecurityLevel:
        return SecurityLevel.SAFE

    async def execute(self, **kwargs: Any) -> ToolResult:
        tz_offset = kwargs.get("timezone", "+8")
        try:
            hours = int(tz_offset.replace("+", ""))
        except (ValueError, AttributeError):
            hours = 8

        tz = timezone(timedelta(hours=hours))
        now = datetime.now(tz)

        output = (
            f"当前时间：{now.strftime('%Y-%m-%d %H:%M:%S')} "
            f"(UTC{tz_offset})，星期{'一二三四五六日'[now.weekday()]}"
        )
        return ToolResult(success=True, output=output)
