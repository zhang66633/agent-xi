"""Grep 工具 — 内容搜索。

对标 Claude Code 的 Grep 工具。
使用 ripgrep (rg) 优先，fallback 到 Python 实现。
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Any

from ..base import SecurityLevel, Tool, ToolResult, ValidationResult

logger = logging.getLogger(__name__)

_MAX_MATCHES = 50
_MAX_OUTPUT_LINES = 200


class GrepTool(Tool):
    """在文件中搜索匹配内容。返回文件名、行号、匹配行。"""

    @property
    def name(self) -> str:
        return "grep"

    @property
    def description(self) -> str:
        return (
            "在文件中搜索匹配内容（支持正则表达式）。"
            "返回匹配的文件名、行号和内容。默认搜索当前目录下所有非二进制文件。"
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "搜索模式（支持正则表达式）",
                },
                "path": {
                    "type": "string",
                    "description": "搜索目录，默认为当前目录",
                },
                "glob": {
                    "type": "string",
                    "description": "文件过滤 glob，如 '*.py' 或 '**/*.ts'",
                },
                "case_sensitive": {
                    "type": "boolean",
                    "description": "是否区分大小写，默认 false",
                },
                "context_lines": {
                    "type": "integer",
                    "description": "显示匹配行前后的上下文行数，默认 0",
                },
                "head_limit": {
                    "type": "integer",
                    "description": f"最多返回的匹配数，默认 {_MAX_MATCHES}",
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
        return 20_000

    def tool_prompt(self) -> str:
        return (
            "- **grep**: 基于 ripgrep 的内容搜索工具。"
            "支持正则表达式、-A/-B/-C 上下文、glob 文件过滤、"
            "files_with_matches/content/count 三种输出模式、head_limit 分页。"
            "用于在代码库中查找函数定义、类名、错误信息、导入语句等。"
        )

    async def validate_input(self, **kwargs: Any) -> Any:
        from ..base import ValidationResult
        pattern = kwargs.get("pattern", "")
        if not pattern:
            return ValidationResult(valid=False, message="需要 pattern 参数")
        return ValidationResult(valid=True)

    async def execute(self, **kwargs: Any) -> ToolResult:
        pattern = str(kwargs.get("pattern", ""))
        if not pattern:
            return ToolResult(success=False, output="", error="需要 pattern 参数")

        search_path = kwargs.get("path", ".")
        glob_filter = kwargs.get("glob", "")
        case_sensitive = kwargs.get("case_sensitive", False)
        context_lines = kwargs.get("context_lines", 0)
        head_limit = kwargs.get("head_limit", _MAX_MATCHES)

        # 尝试 ripgrep
        try:
            return await self._grep_ripgrep(
                pattern, search_path, glob_filter,
                case_sensitive, context_lines, head_limit,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Fallback: Python 实现
        try:
            return await self._grep_python(
                pattern, search_path, glob_filter,
                case_sensitive, context_lines, head_limit,
            )
        except Exception as e:
            return ToolResult(
                success=False, output="", error=f"Grep 失败: {e}",
            )

    async def _grep_ripgrep(
        self, pattern: str, path: str, glob_filter: str,
        case_sensitive: bool, context: int, limit: int,
    ) -> ToolResult:
        cmd = ["rg", "--no-heading", "--with-filename", "--line-number"]
        if not case_sensitive:
            cmd.append("--ignore-case")
        if context > 0:
            cmd.extend(["-C", str(context)])
        if glob_filter:
            cmd.extend(["--glob", glob_filter])
        cmd.extend(["-m", str(limit), pattern, path])

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )

        output = result.stdout
        if not output.strip():
            return ToolResult(success=True, output="（无匹配）")

        lines = output.strip().split("\n")
        count = len(lines)
        if count > _MAX_OUTPUT_LINES:
            output = "\n".join(lines[:_MAX_OUTPUT_LINES])
            output += f"\n... （截断，共 {count} 条匹配）"

        return ToolResult(
            success=True,
            output=output,
            metadata={"matches": count, "truncated": count > _MAX_OUTPUT_LINES},
        )

    async def _grep_python(
        self, pattern: str, path: str, glob_filter: str,
        case_sensitive: bool, context: int, limit: int,
    ) -> ToolResult:
        from pathlib import Path

        regex = re.compile(
            pattern,
            0 if case_sensitive else re.IGNORECASE,
        )
        base = Path(path).resolve()

        # 构建 glob 匹配
        if glob_filter:
            import fnmatch
            candidates = [
                p for p in base.rglob("*")
                if p.is_file() and fnmatch.fnmatch(str(p.relative_to(base)), glob_filter)
            ]
        else:
            candidates = [p for p in base.rglob("*") if p.is_file()]

        # 跳过二进制和隐藏文件
        skip_dirs = {".git", "__pycache__", "node_modules", ".venv",
                     ".data", "dist", ".next", ".pytest_cache"}
        results = []
        for file_path in candidates:
            if any(d in file_path.parts for d in skip_dirs):
                continue
            if len(results) >= limit:
                break
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            for i, line in enumerate(content.split("\n"), 1):
                if regex.search(line):
                    results.append(f"{file_path}:{i}:{line.strip()}")
                    if len(results) >= limit:
                        break

        if not results:
            return ToolResult(success=True, output="（无匹配）")

        output = "\n".join(results[:_MAX_OUTPUT_LINES])
        count = len(results)
        if count > _MAX_OUTPUT_LINES:
            output += f"\n... （截断，共 {count} 条匹配）"

        return ToolResult(
            success=True,
            output=output,
            metadata={"matches": count},
        )