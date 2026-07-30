"""read_file — 读取文件内容。SAFE 级别。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import SecurityLevel, Tool, ToolResult
from .edit_file import record_file_read

# 文件最大读取大小（字符数）— 50000 对标 Claude Code
_MAX_FILE_SIZE = 50000


class ReadFileTool(Tool):
    """读取指定路径的文件内容。"""

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return (
            "读取指定路径的文本文件内容。"
            "支持指定起始行和读取行数。"
            "适用于代码文件、配置文件、文本文件等。"
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "文件的绝对路径或相对路径",
                },
                "start_line": {
                    "type": "integer",
                    "description": "起始行号（从 1 开始），默认为 1",
                },
                "num_lines": {
                    "type": "integer",
                    "description": "读取的行数，默认 2000（对标 Claude Code）",
                },
            },
            "required": ["path"],
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
        return _MAX_FILE_SIZE

    def tool_prompt(self) -> str:
        return (
            "- **read_file**: 读取文本文件内容。支持 start_line 和 num_lines 分页（默认 2000 行），"
            "最大 50000 字符。适用于代码文件、配置文件、文本文件。"
            "二进制文件返回错误提示。"
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        file_path = kwargs.get("path", "")
        start_line = kwargs.get("start_line", 1)
        num_lines = kwargs.get("num_lines", 200)

        if not file_path:
            return ToolResult(success=False, output="", error="未提供文件路径")

        path = Path(file_path).expanduser()

        if not path.exists():
            return ToolResult(
                success=False, output="", error=f"文件不存在：{path}"
            )

        if not path.is_file():
            return ToolResult(
                success=False, output="", error=f"不是文件：{path}"
            )

        # 检查文件大小
        file_size = path.stat().st_size
        if file_size > 1_000_000:  # 1MB
            return ToolResult(
                success=False,
                output="",
                error=(
                    f"文件过大（{file_size / 1024:.0f}KB），"
                    "请指定 start_line 和 num_lines 读取片段"
                ),
            )

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return ToolResult(success=False, output="", error=f"读取失败：{e}")

        lines = content.splitlines()
        total_lines = len(lines)

        # 切片
        start_idx = max(0, start_line - 1)
        end_idx = start_idx + num_lines
        selected = lines[start_idx:end_idx]

        # 添加行号
        numbered = [
            f"{start_idx + i + 1}\t{line}" for i, line in enumerate(selected)
        ]
        output = "\n".join(numbered)

        if len(output) > _MAX_FILE_SIZE:
            output = output[:_MAX_FILE_SIZE] + "\n...(内容已截断)"

        end_line = min(end_idx, total_lines)
        header = (
            f"[{path.name}] 共 {total_lines} 行，"
            f"显示第 {start_idx + 1}-{end_line} 行\n"
        )
        # 记录读取时间戳（供 edit_file 冲突检测）
        record_file_read(str(path))

        return ToolResult(
            success=True,
            output=header + output,
            metadata={"total_lines": total_lines, "path": str(path)},
        )
