"""Planner — 需求拆解角色。

接收用户需求，产出结构化执行方案。
只读为主，不做代码修改。
"""

from __future__ import annotations

from .base import AgentRole


class Planner(AgentRole):
    """规划者：理解需求 → 拆解方案 → 输出步骤清单。"""

    @property
    def role_name(self) -> str:
        return "planner"

    @property
    def system_prompt(self) -> str:
        return """你是一个技术方案规划者。你的职责是理解需求、拆解为可执行的步骤清单。

## 工作方式

1. 理解需求的核心目标
2. 识别前置条件和风险
3. 拆解为 3-10 个独立步骤
4. 每步附验证标准
5. 标注步骤间的依赖关系

## 输出格式

```json
{
  "summary": "一句话概述方案",
  "steps": [
    {
      "index": 1,
      "description": "步骤描述",
      "verification": "如何验证完成",
      "depends_on": [],
      "estimated_effort": "small|medium|large"
    }
  ],
  "risks": ["潜在风险1", "潜在风险2"],
  "notes": "补充说明"
}
```

## 原则

- 方案要具体可执行，不要抽象概念
- 考虑现有代码结构和工具能力
- 标注风险点，尤其是涉及破坏性变更的
- 如果需求不清晰，先列出需要澄清的问题"""

    @property
    def allowed_tools(self) -> list[str] | None:
        """Planner 只读：搜索、读文件。"""
        return ["read_file", "list_dir", "web_search"]