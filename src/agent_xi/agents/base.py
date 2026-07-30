"""Agent 角色基类。

参考 cc-haha 的 assistant/coordinator 多角色设计。

每个 Agent 角色拥有：
- 独立的 system prompt（角色人设）
- 可选的工具白名单（限制能力范围）
- 独立的对话历史（角色间隔离）
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..llm.base import LLMClient
from ..llm.types import Message, Role, StreamEvent


@dataclass(slots=True)
class AgentContext:
    """Agent 角色上下文 — 传递给执行环境的参数。"""

    task: str  # 当前任务描述
    inputs: dict[str, Any] = field(default_factory=dict)  # 上游输出
    constraints: list[str] = field(default_factory=list)  # 约束条件


@dataclass(slots=True)
class AgentResult:
    """Agent 角色执行结果。"""

    success: bool
    output: str  # 自然语言产出
    artifacts: dict[str, Any] = field(default_factory=dict)  # 结构化产出
    error: str = ""


class AgentRole(ABC):
    """多智能体角色基类。

    每个角色封装了特定领域的能力和视角：
    - Planner: 需求拆解
    - Coder: 代码执行
    - Reviewer: 质量审查
    - Coordinator: 编排协调

    子类需要实现：
    - role_name: 角色名称
    - system_prompt: 角色专属 system prompt
    - allowed_tools: 可使用的工具列表（None = 全部）
    """

    def __init__(
        self,
        client: LLMClient,
        allowed_tools: list[str] | None = None,
    ) -> None:
        self._client = client
        self._allowed_tools = allowed_tools  # None = 全部工具可用
        self._history: list[Message] = []

    @property
    @abstractmethod
    def role_name(self) -> str:
        """角色名称，如 'planner', 'coder', 'reviewer'。"""
        ...

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """角色专属 system prompt。"""
        ...

    @property
    def allowed_tools(self) -> list[str] | None:
        """角色可用的工具白名单。None = 全部可用。"""
        return self._allowed_tools

    async def execute(self, context: AgentContext) -> AgentResult:
        """执行角色任务。

        Args:
            context: 任务上下文。

        Returns:
            AgentResult 包含执行结果。
        """
        prompt = self._build_prompt(context)

        try:
            full_text = ""
            # 这里使用 LLM 直调（非流式），因为角色间通信不需要流式
            from ..llm.types import ChatRequest, Message, Role

            request = ChatRequest(
                messages=[Message(role=Role.USER, content=prompt)],
                system=self.system_prompt,
                temperature=0.7,
                max_tokens=2048,
            )

            response = await self._client.chat(request)
            full_text = response.message.text

            return AgentResult(
                success=True,
                output=full_text.strip(),
                artifacts={"raw_response": full_text},
            )
        except Exception as e:
            return AgentResult(
                success=False,
                output="",
                error=f"{self.role_name} 执行失败: {e}",
            )

    def _build_prompt(self, context: AgentContext) -> str:
        """构建角色执行 prompt。"""
        parts = [f"## 任务\n\n{context.task}"]

        if context.inputs:
            parts.append("\n## 输入\n")
            for k, v in context.inputs.items():
                parts.append(f"- **{k}**: {v}")

        if context.constraints:
            parts.append("\n## 约束\n")
            for c in context.constraints:
                parts.append(f"- {c}")

        parts.append("\n## 输出要求\n请直接给出你的产出，不要多余的引言或解释。")
        return "\n".join(parts)

    def clear_history(self) -> None:
        """清空角色对话历史。"""
        self._history.clear()