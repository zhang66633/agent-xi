"""Skill 数据模型。"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field


@dataclass(slots=True)
class Skill:
    """一条技能定义。

    技能不是代码，而是结构化的流程知识：
    LLM 匹配到技能后，按 steps 指引结合工具完成任务。
    """

    name: str
    description: str
    steps: str  # Markdown 格式的步骤说明
    trigger_keywords: list[str] = field(default_factory=list)
    parameters: dict[str, str] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: float = field(default_factory=time.time)
    last_used: float = 0.0
    use_count: int = 0

    def touch(self) -> None:
        """更新使用统计。"""
        self.last_used = time.time()
        self.use_count += 1

    def to_context_block(self) -> str:
        """渲染为注入上下文的文本块。"""
        lines = [
            f"[技能: {self.name}]",
            f"描述: {self.description}",
            "",
            "执行步骤:",
            self.steps,
        ]
        if self.parameters:
            lines.append("")
            lines.append("参数:")
            for k, v in self.parameters.items():
                lines.append(f"  - {k}: {v}")
        return "\n".join(lines)
