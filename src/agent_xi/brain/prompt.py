"""Prompt 组装器 — 从模板渲染最终 system prompt。

将 config/prompt.md 模板中的占位符替换为运行时动态内容：
- {capabilities}: 已注册工具列表
- {memory_instruction}: 记忆系统指引（有记忆时注入）
"""

from __future__ import annotations

from pathlib import Path

from ..llm.types import ToolDefinition

_DEFAULT_TEMPLATE_PATH = (
    Path(__file__).parent.parent.parent.parent / "config" / "prompt.md"
)

_MEMORY_INSTRUCTION = """你拥有跨会话的记忆能力：
- 情景记忆：用户显式要求"记住"的信息，会在相关对话中自动浮现
- 语义记忆：从对话中提炼的用户偏好、习惯、事实
- 当记忆与当前对话相关时，自然地引用，不要生硬地列举
- 如果用户说"记住..."，确认你已记录"""

_NO_MEMORY_INSTRUCTION = "（记忆系统未启用）"


class PromptBuilder:
    """从 Markdown 模板渲染 system prompt。"""

    def __init__(self, template_path: Path | None = None) -> None:
        self._template_path = template_path or _DEFAULT_TEMPLATE_PATH
        self._template = self._load_template()

    def _load_template(self) -> str:
        """加载模板文件。"""
        if self._template_path.exists():
            return self._template_path.read_text(encoding="utf-8")
        # 模板不存在时用最小 fallback
        return "你是 Xi，一个友好、诚实的 AI 伙伴。\n\n{capabilities}"

    def build(
        self,
        *,
        tools: list[ToolDefinition] | None = None,
        has_memory: bool = False,
    ) -> str:
        """渲染最终 system prompt。

        Args:
            tools: 已注册的工具定义列表。
            has_memory: 记忆系统是否启用。

        Returns:
            完整的 system prompt 字符串。
        """
        capabilities = self._render_capabilities(tools)
        memory_instruction = (
            _MEMORY_INSTRUCTION if has_memory else _NO_MEMORY_INSTRUCTION
        )

        prompt = self._template.replace("{capabilities}", capabilities)
        prompt = prompt.replace("{memory_instruction}", memory_instruction)

        return prompt.strip()

    @staticmethod
    def _render_capabilities(tools: list[ToolDefinition] | None) -> str:
        """将工具列表渲染为可读的能力描述。"""
        if not tools:
            return "（当前无可用工具）"

        lines: list[str] = []
        for tool in tools:
            lines.append(f"- **{tool.name}**: {tool.description}")
        return "\n".join(lines)

    def reload(self) -> None:
        """重新加载模板（热更新）。"""
        self._template = self._load_template()
