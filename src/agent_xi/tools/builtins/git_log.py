"""Git Log 工具 — 查看提交历史。

对标 Claude Code 的 git 集成。
"""

from __future__ import annotations

import subprocess
from typing import Any

from ..base import SecurityLevel, Tool, ToolResult

_MAX_COMMITS = 30


class GitLogTool(Tool):
    """查看 Git 提交历史。"""

    @property
    def name(self) -> str:
        return "git_log"

    @property
    def description(self) -> str:
        return (
            "查看 Git 提交历史。显示最近 N 条 commit 的 hash、作者、日期、消息。"
            "支持指定文件路径查看该文件的提交历史。"
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                    "description": f"返回的提交数量，默认 10，最大 {_MAX_COMMITS}",
                },
                "file_path": {
                    "type": "string",
                    "description": "可选：只显示该文件的提交历史",
                },
                "oneline": {
                    "type": "boolean",
                    "description": "单行模式（仅 hash + 消息），默认 false",
                },
            },
            "required": [],
        }

    @property
    def security_level(self) -> SecurityLevel:
        return SecurityLevel.SAFE

    @property
    def is_read_only(self) -> bool:
        return True

    def tool_prompt(self) -> str:
        return (
            "- **git_log**: 查看 Git 提交历史。显示最近 N 条 commit 的 hash、"
            "作者、日期、消息。可按文件过滤。"
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        count = min(kwargs.get("count", 10), _MAX_COMMITS)
        file_path = kwargs.get("file_path", "")
        oneline = kwargs.get("oneline", False)

        cmd = [
            "git", "log",
            f"-{count}",
            "--no-color",
            "--no-pager",
        ]
        if oneline:
            cmd.append("--oneline")
        else:
            cmd.append("--pretty=format:%h | %an | %ad | %s")
            cmd.append("--date=short")
        if file_path:
            cmd.append("--")
            cmd.append(file_path)

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=15,
                cwd=".",
            )

            if result.returncode != 0:
                return ToolResult(
                    success=False, output="",
                    error=f"Git log 失败: {result.stderr.strip()}",
                )

            output = result.stdout.strip()
            if not output:
                return ToolResult(success=True, output="（无提交记录）")

        except FileNotFoundError:
            return ToolResult(
                success=False, output="",
                error="未找到 git 命令",
            )
        except Exception as e:
            return ToolResult(
                success=False, output="", error=f"Git log 异常: {e}",
            )

        return ToolResult(
            success=True,
            output=output,
            metadata={"count": len(output.split("\n")), "oneline": oneline},
        )