"""Edit 工具 — 精确字符串替换编辑。

对标 Claude Code 的 Edit 工具。
读文件 → old_string 精确匹配 → 替换为 new_string → 写回。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import SecurityLevel, Tool, ToolResult


class EditFileTool(Tool):
    """精确字符串替换编辑。old_string 必须在文件中精确匹配（只替换一次）。"""

    @property
    def name(self) -> str:
        return "edit_file"

    @property
    def description(self) -> str:
        return (
            "精确编辑文件：用 new_string 替换文件中 old_string 的第一次出现。"
            "old_string 必须精确匹配（含缩进和空格）。"
            "创建文件请用 write_file 工具。"
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "要编辑的文件路径（相对或绝对）",
                },
                "old_string": {
                    "type": "string",
                    "description": "要被替换的文本（必须精确匹配）",
                },
                "new_string": {
                    "type": "string",
                    "description": "替换后的文本",
                },
                "replace_all": {
                    "type": "boolean",
                    "description": "是否替换所有匹配项（默认只替换第一个）",
                },
            },
            "required": ["file_path", "old_string", "new_string"],
        }

    @property
    def security_level(self) -> SecurityLevel:
        return SecurityLevel.SENSITIVE

    @property
    def is_read_only(self) -> bool:
        return False

    @property
    def max_result_size(self) -> int:
        return 10_000

    def tool_prompt(self) -> str:
        return (
            "- **edit_file**: 精确字符串替换编辑工具。"
            "old_string 必须在文件中精确匹配（含缩进和空格）。"
            "只替换第一次出现（除非 replace_all=true）。"
            "创建新文件请用 write_file 工具。"
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        file_path = str(kwargs.get("file_path", ""))
        old_string = str(kwargs.get("old_string", ""))
        new_string = str(kwargs.get("new_string", ""))
        replace_all = kwargs.get("replace_all", False)

        if not file_path or not old_string:
            return ToolResult(success=False, output="", error="需要 file_path 和 old_string")

        path = Path(file_path).resolve()

        if not path.exists():
            return ToolResult(
                success=False, output="", error=f"文件不存在: {file_path}",
            )

        try:
            content = path.read_text(encoding="utf-8")
        except Exception as e:
            return ToolResult(
                success=False, output="", error=f"无法读取文件: {e}",
            )

        # 精确匹配
        count = content.count(old_string)
        if count == 0:
            return ToolResult(
                success=False,
                output="",
                error=f"未找到 old_string 匹配项。"
                      f"\n提示：请确保字符串精确匹配（含缩进、空行、引号）。"
                      f"\n文件路径: {file_path}",
            )

        if replace_all:
            new_content = content.replace(old_string, new_string)
            replaced = count
        else:
            new_content = content.replace(old_string, new_string, 1)
            replaced = 1

        try:
            path.write_text(new_content, encoding="utf-8")
        except Exception as e:
            return ToolResult(
                success=False, output="", error=f"无法写入文件: {e}",
            )

        return ToolResult(
            success=True,
            output=(
                f"文件已编辑: {file_path}\n"
                f"替换了 {replaced} 处匹配"
                + (f"（共 {count} 处，使用了 replace_all）" if replace_all else ""),
            ),
            metadata={
                "file": str(path),
                "replacements": replaced,
                "total_matches": count,
            },
        )