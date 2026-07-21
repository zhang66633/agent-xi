"""write_file — 写入文件。SENSITIVE 级别。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import SecurityLevel, Tool, ToolResult


class WriteFileTool(Tool):
    """写入或追加文本到指定文件。"""

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return (
            "将文本内容写入指定文件。支持覆盖写入或追加模式。"
            "适用于保存代码、笔记、配置等。"
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "目标文件路径",
                },
                "content": {
                    "type": "string",
                    "description": "要写入的内容",
                },
                "mode": {
                    "type": "string",
                    "description": "写入模式：overwrite（覆盖）或 append（追加）",
                    "enum": ["overwrite", "append"],
                },
            },
            "required": ["path", "content"],
        }

    @property
    def security_level(self) -> SecurityLevel:
        return SecurityLevel.SENSITIVE

    async def execute(self, **kwargs: Any) -> ToolResult:
        path_str = kwargs.get("path", "")
        content = kwargs.get("content", "")
        mode = kwargs.get("mode", "overwrite")

        if not path_str:
            return ToolResult(
                success=False, output="", error="未指定文件路径"
            )

        try:
            file_path = Path(path_str).expanduser().resolve()

            # 确保父目录存在
            file_path.parent.mkdir(parents=True, exist_ok=True)

            write_mode = "a" if mode == "append" else "w"
            with file_path.open(write_mode, encoding="utf-8") as f:
                f.write(content)

            action = "追加到" if mode == "append" else "写入"
            size = file_path.stat().st_size
            return ToolResult(
                success=True,
                output=f"已{action} {file_path}（{size} 字节）",
            )
        except PermissionError:
            return ToolResult(
                success=False, output="", error=f"无权限写入：{path_str}"
            )
        except OSError as e:
            return ToolResult(
                success=False, output="", error=f"写入失败：{e}"
            )
