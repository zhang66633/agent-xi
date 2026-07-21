"""list_dir — 列出目录内容。SAFE 级别。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import SecurityLevel, Tool, ToolResult

_MAX_ENTRIES = 100


class ListDirTool(Tool):
    """列出指定目录的文件和子目录。"""

    @property
    def name(self) -> str:
        return "list_dir"

    @property
    def description(self) -> str:
        return (
            "列出指定目录下的文件和子目录。"
            "显示名称、类型（文件/目录）和大小。"
            "适用于了解项目结构、查找文件等。"
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "目录路径（默认为当前目录）",
                },
                "pattern": {
                    "type": "string",
                    "description": "文件名过滤模式（如 '*.py'），可选",
                },
            },
            "required": [],
        }

    @property
    def security_level(self) -> SecurityLevel:
        return SecurityLevel.SAFE

    async def execute(self, **kwargs: Any) -> ToolResult:
        path_str = kwargs.get("path", ".")
        pattern = kwargs.get("pattern", "")

        try:
            dir_path = Path(path_str).expanduser().resolve()

            if not dir_path.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"路径不存在：{path_str}",
                )

            if not dir_path.is_dir():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"不是目录：{path_str}",
                )

            # 获取条目
            if pattern:
                entries = sorted(dir_path.glob(pattern))
            else:
                entries = sorted(dir_path.iterdir())

            # 限制数量
            truncated = len(entries) > _MAX_ENTRIES
            entries = entries[:_MAX_ENTRIES]

            # 格式化输出
            lines = [f"目录：{dir_path}\n"]
            dirs_count = 0
            files_count = 0

            for entry in entries:
                if entry.is_dir():
                    lines.append(f"  📁 {entry.name}/")
                    dirs_count += 1
                else:
                    size = entry.stat().st_size
                    size_str = self._format_size(size)
                    lines.append(f"  📄 {entry.name} ({size_str})")
                    files_count += 1

            lines.append(
                f"\n共 {dirs_count} 个目录，{files_count} 个文件"
            )
            if truncated:
                lines.append(f"（仅显示前 {_MAX_ENTRIES} 项）")

            return ToolResult(success=True, output="\n".join(lines))

        except PermissionError:
            return ToolResult(
                success=False,
                output="",
                error=f"无权限访问：{path_str}",
            )
        except OSError as e:
            return ToolResult(
                success=False, output="", error=f"读取目录失败：{e}"
            )

    @staticmethod
    def _format_size(size: int) -> str:
        """格式化文件大小。"""
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.1f} GB"
