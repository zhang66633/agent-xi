"""execute_shell — 执行 shell 命令。DANGEROUS 级别，需要用户确认。"""

from __future__ import annotations

import asyncio
import platform
from typing import Any

from ..base import PermissionBehavior, PermissionDecision, SecurityLevel, Tool, ToolResult

# 命令输出最大长度（防止刷屏）
_MAX_OUTPUT_LENGTH = 4000
# 命令执行超时（秒）
_TIMEOUT = 30

# 只读命令前缀（自动 SAFE，跳过确认）
_READ_ONLY_COMMANDS = [
    "ls", "dir", "cat", "head", "tail", "wc", "stat",
    "grep", "rg", "find", "locate", "which", "where",
    "echo", "printf", "date", "pwd", "whoami", "hostname",
    "uname", "env", "printenv", "type", "file", "du", "df",
    "git log", "git diff", "git status", "git branch",
    "git show", "git tag", "git remote", "git config",
    "git stash list", "python --version", "python -V",
    "node --version", "npm --version", "pip list", "pip show",
]


class ExecuteShellTool(Tool):
    """执行 shell 命令并返回输出。"""

    @property
    def name(self) -> str:
        return "execute_shell"

    @property
    def description(self) -> str:
        return (
            "在用户的系统上执行 shell 命令。"
            "Windows 下使用 cmd，其他系统使用 bash。"
            "注意：此操作有安全风险，需要用户确认。"
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的 shell 命令",
                },
            },
            "required": ["command"],
        }

    @property
    def security_level(self) -> SecurityLevel:
        return SecurityLevel.DANGEROUS

    async def check_permission(self, **kwargs: Any) -> PermissionDecision:
        """只读命令自动放行。"""
        command = str(kwargs.get("command", "")).strip()
        for prefix in _READ_ONLY_COMMANDS:
            if command.startswith(prefix):
                return PermissionDecision(
                    behavior=PermissionBehavior.ALLOW,
                    reason="read_only_command",
                )
        return await super().check_permission(**kwargs)

    def tool_prompt(self) -> str:
        return (
            "- **execute_shell**: 执行 shell 命令。"
            "只读命令（ls/cat/grep/find/git log 等）自动执行无需确认。"
            "其他命令需要用户确认。"
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        command = kwargs.get("command", "")
        if not command:
            return ToolResult(success=False, output="", error="未提供命令")

        # 根据平台选择 shell
        is_windows = platform.system() == "Windows"
        if is_windows:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        else:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                executable="/bin/bash",
            )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=_TIMEOUT
            )
        except TimeoutError:
            process.kill()
            return ToolResult(
                success=False,
                output="",
                error=f"命令执行超时（>{_TIMEOUT}s）：{command}",
            )

        stdout_text = stdout.decode("utf-8", errors="replace")
        stderr_text = stderr.decode("utf-8", errors="replace")

        # 截断过长输出
        if len(stdout_text) > _MAX_OUTPUT_LENGTH:
            stdout_text = stdout_text[:_MAX_OUTPUT_LENGTH] + "\n...(输出已截断)"

        if process.returncode == 0:
            return ToolResult(
                success=True,
                output=stdout_text or "(无输出)",
                metadata={"returncode": 0},
            )
        else:
            error_output = stderr_text or stdout_text or f"退出码: {process.returncode}"
            return ToolResult(
                success=False,
                output=stdout_text,
                error=error_output[:2000],
                metadata={"returncode": process.returncode},
            )
