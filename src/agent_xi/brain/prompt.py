"""Prompt 组装器 — 从三段式人设文件渲染最终 system prompt。

人设文件（config/ 下，用户可直接编辑）：
- identity.md   — 我是谁（名字、本质、气质）
- personality.md — 行为准则（说话风格、价值观、工具规范）
- service.md    — 我为谁服务（用户画像 + 关系定位，会话结束时整体重写）

动态注入：
- {capabilities}: 已注册工具列表
- 记忆指引（情景记忆使用说明）
"""

from __future__ import annotations

from pathlib import Path

from ..llm.types import ToolDefinition

_CONFIG_DIR = Path(__file__).parent.parent.parent.parent / "config"

_IDENTITY_FILE = _CONFIG_DIR / "identity.md"
_PERSONALITY_FILE = _CONFIG_DIR / "personality.md"
_SERVICE_FILE = _CONFIG_DIR / "service.md"

# 兼容旧模板（如果三段文件不存在则 fallback）
_LEGACY_TEMPLATE = _CONFIG_DIR / "prompt.md"

_MEMORY_INSTRUCTION = """\
# 记忆

你拥有跨会话的记忆能力：
- 情景记忆：用户显式要求"记住"的信息，会在相关对话中自动浮现
- 用户画像：见「我为谁服务」部分，每次会话结束后你会自动更新它
- 当记忆与当前对话相关时，自然地引用，不要生硬地列举
- 如果用户说"记住..."，确认你已记录"""

_NO_MEMORY_INSTRUCTION = "# 记忆\n\n（记忆系统未启用）"


class PromptBuilder:
    """从三段式人设文件渲染 system prompt。"""

    def __init__(self, config_dir: Path | None = None) -> None:
        self._config_dir = config_dir or _CONFIG_DIR
        self._identity_path = self._config_dir / "identity.md"
        self._personality_path = self._config_dir / "personality.md"
        self._service_path = self._config_dir / "service.md"

    def build(
        self,
        *,
        tools: list[ToolDefinition] | None = None,
        has_memory: bool = False,
    ) -> str:
        """渲染最终 system prompt。

        组装顺序：identity → personality → capabilities → memory → service
        """
        # 优先三段式，fallback 旧模板
        if self._identity_path.exists():
            return self._build_modular(tools=tools, has_memory=has_memory)
        return self._build_legacy(tools=tools, has_memory=has_memory)

    def _build_modular(
        self,
        *,
        tools: list[ToolDefinition] | None,
        has_memory: bool,
    ) -> str:
        """三段式组装。"""
        identity = self._read(self._identity_path)
        personality = self._read(self._personality_path)
        service = self._read(self._service_path)

        capabilities = self._render_capabilities(tools)
        memory_instruction = (
            _MEMORY_INSTRUCTION if has_memory else _NO_MEMORY_INSTRUCTION
        )

        parts = [
            identity,
            personality,
            f"# 能力\n\n你可以通过工具与外部世界交互。当前已注册的工具：\n\n{capabilities}",
            memory_instruction,
            service,
        ]

        return "\n\n".join(p.strip() for p in parts if p.strip())

    def _build_legacy(
        self,
        *,
        tools: list[ToolDefinition] | None,
        has_memory: bool,
    ) -> str:
        """兼容旧 prompt.md 模板。"""
        if _LEGACY_TEMPLATE.exists():
            template = _LEGACY_TEMPLATE.read_text(encoding="utf-8")
        else:
            template = "你是 Xi，一个友好、诚实的 AI 伙伴。\n\n{capabilities}"

        capabilities = self._render_capabilities(tools)
        memory_instruction = (
            _MEMORY_INSTRUCTION if has_memory else _NO_MEMORY_INSTRUCTION
        )

        prompt = template.replace("{capabilities}", capabilities)
        prompt = prompt.replace("{memory_instruction}", memory_instruction)
        return prompt.strip()

    @staticmethod
    def _read(path: Path) -> str:
        """安全读取文件，不存在则返回空串。"""
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

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
        """热更新：三段式无需缓存，每次 build 都重新读文件。"""
        pass

    def get_service_content(self) -> str:
        """读取当前 service.md 内容（供 MemoryManager 重写用）。"""
        return self._read(self._service_path)

    @property
    def service_path(self) -> Path:
        return self._service_path
