"""Glob 工具 — 文件模式匹配。

对标 Claude Code 的 Glob 工具。
使用 pathlib.Path.rglob，按修改时间排序。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import SecurityLevel, Tool, ToolResult

_MAX_FILES = 200


class GlobTool(Tool):
    """查找文件（支持 ** 递归匹配）。返回排序后的文件路径列表。"""

    @property
    def name(self) -> str:
        return "glob"

    @property
    def description(self) -> str:
        return (
            "查找匹配模式的文件路径。支持 ** 递归匹配（如 'src/**/*.py'）。"
            "返回按修改时间排序的文件列表（最新的在前）。"
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "文件匹配模式，如 '**/*.py' 或 'src/**/*.ts'",
                },
                "path": {
                    "type": "string",
                    "description": "搜索根目录，默认为当前目录",
                },
                "max_results": {
                    "type": "integer",
                    "description": f"最多返回的文件数，默认 {_MAX_FILES}",
                },
                "show_size": {
                    "type": "boolean",
                    "description": "是否显示文件大小，默认 true",
                },
            },
            "required": ["pattern"],
        }

    @property
    def security_level(self) -> SecurityLevel:
        return SecurityLevel.SAFE

    @property
    def is_read_only(self) -> bool:
        return True

    @property
    def is_concurrency_safe(self) -> bool:
        return True

    @property
    def max_result_size(self) -> int:
        return 10_000

    def tool_prompt(self) -> str:
        return (
            "- **glob**: 文件模式匹配工具。支持 `**/*.py` 递归匹配。"
            "返回按修改时间排序的文件列表（最新的在前），"
            "附带文件大小信息。默认最多返回 200 个文件。"
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        pattern = str(kwargs.get("pattern", ""))
        if not pattern:
            return ToolResult(success=False, output="", error="需要 pattern 参数")

        root = kwargs.get("path", ".")
        max_results = kwargs.get("max_results", _MAX_FILES)
        show_size = kwargs.get("show_size", True)

        base = Path(root).resolve()
        if not base.exists():
            return ToolResult(
                success=False, output="", error=f"路径不存在: {root}",
            )

        # 收集匹配文件 with stat
        try:
            entries = []
            for p in base.glob(pattern):
                if not p.is_file():
                    continue
                # 跳过常见忽略目录
                skip_parts = {".git", "__pycache__", "node_modules",
                              ".venv", ".data", "dist"}
                if any(d in skip_parts for d in p.parts):
                    continue
                try:
                    stat = p.stat()
                    entries.append((p, stat.st_mtime, stat.st_size))
                except OSError:
                    entries.append((p, 0.0, 0))

        except Exception as e:
            return ToolResult(
                success=False, output="", error=f"Glob 搜索失败: {e}",
            )

        if not entries:
            return ToolResult(
                success=True, output=f"（无匹配: {pattern}）",
            )

        # 按修改时间排序（最新的在前）
        entries.sort(key=lambda x: x[1], reverse=True)

        # 格式化输出
        truncated = len(entries) > max_results
        entries = entries[:max_results]

        lines = []
        for rel_path, mtime, size in entries:
            rel = str(rel_path.relative_to(base))
            if show_size:
                size_str = _fmt_size(size)
                lines.append(f"{rel} ({size_str})")
            else:
                lines.append(rel)

        output = "\n".join(lines)
        if truncated:
            output += f"\n... （共 {len(entries)} 个文件，显示前 {max_results} 个）"

        return ToolResult(
            success=True,
            output=output,
            metadata={
                "count": len(entries),
                "truncated": truncated,
            },
        )


def _fmt_size(size: int) -> str:
    if size < 1024:
        return f"{size}B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f}KB"
    return f"{size / 1024 / 1024:.1f}MB"