"""Notebook 工具 — 读取 Jupyter notebook (.ipynb) 文件。

对标 Claude Code 的 NotebookRead 工具。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..base import SecurityLevel, Tool, ToolResult


class NotebookReadTool(Tool):
    """读取 Jupyter notebook 文件内容（cell 源码）。"""

    @property
    def name(self) -> str:
        return "notebook_read"

    @property
    def description(self) -> str:
        return (
            "读取 Jupyter notebook (.ipynb) 文件内容。"
            "返回所有 cell 的源码和输出摘要。"
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "notebook 文件路径",
                },
                "max_cells": {
                    "type": "integer",
                    "description": "最多显示的 cell 数量，默认 50",
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

    def tool_prompt(self) -> str:
        return (
            "- **notebook_read**: 读取 Jupyter notebook 文件内容。"
            "返回所有 cell 的源码（含行号）和输出摘要。"
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        file_path = str(kwargs.get("path", ""))
        max_cells = kwargs.get("max_cells", 50)

        if not file_path:
            return ToolResult(success=False, output="", error="需要 path 参数")

        path = Path(file_path).expanduser()
        if not path.exists():
            return ToolResult(success=False, output="", error=f"文件不存在: {file_path}")
        if path.suffix != ".ipynb":
            return ToolResult(success=False, output="", error="仅支持 .ipynb 文件")

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            return ToolResult(success=False, output="", error=f"无法解析 notebook: {e}")

        cells = data.get("cells", [])
        metadata = data.get("metadata", {})
        total_cells = len(cells)
        cells = cells[:max_cells]

        lines = [
            f"# Notebook: {path.name}",
            f"共 {total_cells} 个 cell，显示前 {len(cells)} 个\n",
        ]

        for i, cell in enumerate(cells):
            cell_type = cell.get("cell_type", "code")
            source = "".join(cell.get("source", []))
            if not source.strip():
                continue

            prefix = "#" if cell_type == "markdown" else ""
            numbered = "\n".join(
                f"  {j+1:3d}\t{line}"
                for j, line in enumerate(source.split("\n"))
            )
            lines.append(
                f"## Cell {i+1} [{cell_type}]\n{prefix} {numbered}\n"
            )

            # 输出摘要
            outputs = cell.get("outputs", [])
            if outputs:
                for out in outputs[:3]:  # 每个 cell 最多 3 个输出
                    if out.get("output_type") == "stream":
                        text = "".join(out.get("text", []))[:200]
                        if text.strip():
                            lines.append(f"  [output]: {text.strip()[:150]}")
                    elif out.get("output_type") == "execute_result":
                        text = "".join(
                            out.get("data", {}).get("text/plain", [])
                        )[:200]
                        if text.strip():
                            lines.append(f"  [result]: {text.strip()[:150]}")
                    elif out.get("output_type") == "error":
                        ename = out.get("ename", "Error")
                        evalue = out.get("evalue", "")[:100]
                        lines.append(f"  [error]: {ename}: {evalue}")

        output = "\n".join(lines)
        return ToolResult(
            success=True,
            output=output,
            metadata={
                "total_cells": total_cells,
                "displayed_cells": len(cells),
                "kernel": metadata.get("kernelspec", {}).get("name", ""),
            },
        )