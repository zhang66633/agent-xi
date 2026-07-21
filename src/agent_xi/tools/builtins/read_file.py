"""read_file — 读取文件内容。SAFE 级别。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import SecurityLevel, Tool, ToolResult

# 文件最大读取大小（字符数）
_MAX_FILE_SIZE = 10000


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
                    "description": "读取的行数，默认读取全部（最多 200 行）",
                },
            },
            "required": ["path"],
        }

    @property
    def security_level(self) -> SecurityLevel:
        return SecurityLevel.SAFE

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
        return ToolResult(
            success=True,
            output=header + output,
            metadata={"total_lines": total_lines, "path": str(path)},
        )
