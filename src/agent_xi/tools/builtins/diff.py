"""Git Diff 工具 — 查看代码变更。

对标 cc-haha 的代码审查 & diff 查看功能。

提供：
- 查看工作区变更（git diff）
- 查看暂存区变更（git diff --staged）
- 查看提交间变更（git diff <commit> <commit>）
- 安全分级：SAFE（只读操作）
"""

from __future__ import annotations

import subprocess
from typing import Any

from ..base import SecurityLevel, Tool, ToolResult


class GitDiffTool(Tool):
    """Git diff 查看工具 — 只读，显示代码变更。

    支持查看工作区、暂存区、或提交间的差异。
    返回 unified diff 格式的输出。
    """

    @property
    def name(self) -> str:
        return "git_diff"

    @property
    def description(self) -> str:
        return (
            "查看 Git 代码变更（diff）。支持工作区、暂存区、提交间对比。"
            "返回 unified diff 格式的变更内容。"
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "description": "对比模式：'unstaged'（工作区变更，默认）、'staged'（暂存区）、'commit'（最近一次提交）",
                    "enum": ["unstaged", "staged", "commit"],
                },
                "file_path": {
                    "type": "string",
                    "description": "可选：只查看特定文件的变更",
                },
                "lines": {
                    "type": "integer",
                    "description": "返回的最大行数（默认 200）",
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

    @property
    def is_concurrency_safe(self) -> bool:
        return False

    @property
    def max_result_size(self) -> int:
        return 30_000

    def tool_prompt(self) -> str:
        return (
            "- **git_diff**: 查看 Git 代码变更（unified diff 格式）。"
            "支持三种模式：unstaged（工作区变更）、staged（暂存区）、commit（最近一次提交）。"
            "可指定 file_path 只查看特定文件。"
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        mode = kwargs.get("mode", "unstaged")
        file_path = kwargs.get("file_path", "")
        max_lines = kwargs.get("lines", 200)

        try:
            cmd = ["git", "diff", "--no-color"]

            if mode == "staged":
                cmd.append("--staged")
            elif mode == "commit":
                cmd = ["git", "diff", "--no-color", "HEAD~1", "HEAD"]

            if file_path:
                cmd.append("--")
                cmd.append(file_path)

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                cwd=".",
            )

            if result.returncode != 0:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Git diff 失败: {result.stderr.strip()}",
                )

            output = result.stdout
            if not output.strip():
                return ToolResult(
                    success=True,
                    output="（无变更）",
                )

            # 截断过长输出
            lines = output.split("\n")
            if len(lines) > max_lines:
                truncated = "\n".join(lines[:max_lines])
                truncated += f"\n... (截断，共 {len(lines)} 行，显示前 {max_lines} 行)"
                return ToolResult(
                    success=True,
                    output=truncated,
                    metadata={
                        "total_lines": len(lines),
                        "truncated": True,
                        "mode": mode,
                    },
                )

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "total_lines": len(lines),
                    "mode": mode,
                    "files_changed": self._count_files(output),
                },
            )

        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                output="",
                error="Git diff 超时（30s）",
            )
        except FileNotFoundError:
            return ToolResult(
                success=False,
                output="",
                error="未找到 git 命令，请确认 git 已安装且在 PATH 中",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Git diff 异常: {e}",
            )

    @staticmethod
    def _count_files(output: str) -> int:
        """统计变更的 file 数量。"""
        count = 0
        for line in output.split("\n"):
            if line.startswith("diff --git"):
                count += 1
        return count