"""工具基类、安全分级、执行结果 — 对标 cc-haha buildTool 模式。

cc-haha 参考:
- Tool 接口: isReadOnly(), isConcurrencySafe(), prompt(), validateInput(), checkPermissions()
- 权限管道: validateInput → preparePermissionMatcher → checkPermissions → allow/deny/ask
- 结构化输出: outputSchema + mapToolResultToToolResultBlockParam()
- 结果大小: 每工具独立 maxResultSizeChars
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class SecurityLevel(StrEnum):
    """工具安全分级 — 对标 cc-haha 5 级。

    SAFE:      自动执行，无需确认
    ALLOW_ONCE: 本次会话允许一次
    SENSITIVE:  每次确认
    ASK_EVERY:  每次确认 + 不记忆
    DANGEROUS:  确认 + 冷却期拒绝拦截
    """

    SAFE = "safe"
    ALLOW_ONCE = "allow_once"
    SENSITIVE = "sensitive"
    ASK_EVERY = "ask_every"
    DANGEROUS = "dangerous"


class PermissionBehavior(StrEnum):
    """权限决策行为 — 对标 cc-haha allow/deny/ask。"""
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


@dataclass(frozen=True, slots=True)
class PermissionDecision:
    """权限决策结果。"""
    behavior: PermissionBehavior
    message: str = ""
    reason: str = ""  # 'rule', 'user', 'security_level', 'cooldown'


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """输入校验结果 — 对标 cc-haha ValidationResult。"""
    valid: bool
    message: str = ""


@dataclass(slots=True)
class ToolResult:
    """工具执行结果 — 对标 cc-haha ToolResult。

    支持结构化输出（output_data）和纯文本输出（output）。
    """

    success: bool
    output: str
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    output_data: Any = None  # 结构化输出（可选）
    truncated: bool = False
    duration_ms: float = 0.0


class Tool(ABC):
    """工具抽象基类 — 对标 cc-haha buildTool 模式。

    新增方法（第三轮优化）：
    - is_read_only(): 是否只读（SAFE 工具默认为 True）
    - is_concurrency_safe(): 是否可并行执行
    - max_result_size(): 结果最大字符数
    - prompt(): 工具在 system prompt 中的自描述
    - validate_input(): 输入校验（权限检查前）
    - get_activity_description(): 人类可读的活动描述

    子类必须实现: name, description, parameters_schema, execute
    子类可选覆盖: 所有其他方法
    """

    # ─── 必须实现 ───────────────────────────────────────────────

    @property
    @abstractmethod
    def name(self) -> str:
        """工具唯一标识名。"""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述（传给 LLM 做决策）。"""
        ...

    @property
    @abstractmethod
    def parameters_schema(self) -> dict[str, Any]:
        """参数的 JSON Schema 描述。"""
        ...

    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        """执行工具。"""
        ...

    # ─── 安全元数据 ─────────────────────────────────────────────

    @property
    def security_level(self) -> SecurityLevel:
        """安全等级，默认 SAFE。"""
        return SecurityLevel.SAFE

    @property
    def is_read_only(self) -> bool:
        """是否只读操作。对标 cc-haha isReadOnly()。

        SAFE 工具默认 True，其他默认 False。
        """
        return self.security_level == SecurityLevel.SAFE

    @property
    def is_concurrency_safe(self) -> bool:
        """是否可并行执行。对标 cc-haha isConcurrencySafe()。

        只读工具默认为 True。
        """
        return self.is_read_only

    @property
    def max_result_size(self) -> int:
        """结果最大字符数。对标 cc-haha maxResultSizeChars。

        默认 20_000（搜索工具），覆盖类可设更大值。
        """
        return 20_000

    @property
    def is_search_or_read(self) -> dict[str, bool]:
        """搜索/读取分类。对标 cc-haha isSearchOrReadCommand()。

        用于安全分类器：只读工具自动跳过权限检查。
        """
        return {"is_search": False, "is_read": self.is_read_only}

    # ─── 权限管道 ───────────────────────────────────────────────

    async def validate_input(self, **kwargs: Any) -> ValidationResult:
        """输入校验 — 对标 cc-haha validateInput()。

        在权限检查之前执行。默认总是通过。
        子类可覆盖：检查文件是否存在、路径是否合法等。
        """
        return ValidationResult(valid=True)

    async def check_permission(
        self, **kwargs: Any
    ) -> PermissionDecision:
        """权限检查 — 对标 cc-haha checkPermissions()。

        默认基于 security_level 做决策：
        - SAFE → ALLOW
        - ALLOW_ONCE → ALLOW (由 Brain 追踪一次)
        - SENSITIVE/ASK_EVERY → ASK
        - DANGEROUS → ASK
        """
        if self.security_level == SecurityLevel.SAFE:
            return PermissionDecision(
                behavior=PermissionBehavior.ALLOW,
                reason="security_level",
            )
        return PermissionDecision(
            behavior=PermissionBehavior.ASK,
            reason="security_level",
            message=f"确认执行 {self.name}",
        )

    # ─── System Prompt 注入 ─────────────────────────────────────

    def tool_prompt(self) -> str:
        """工具在 system prompt 中的自描述段。

        对标 cc-haha prompt() 方法。
        默认返回 name + description 的简单格式。
        复杂工具（如 Bash/shell）应覆盖此方法提供详细说明。
        """
        return f"- **{self.name}**: {self.description}"

    # ─── 活动描述 ───────────────────────────────────────────────

    def get_activity_description(self, **kwargs: Any) -> str:
        """人类可读的活动描述（用于任务追踪 UI）。

        对标 cc-haha getActivityDescription()。
        """
        return f"调用 {self.name}"

    # ─── 辅助 ───────────────────────────────────────────────────

    def to_tool_definition(self) -> dict[str, Any]:
        """转换为 LLM tool calling 格式（OpenAI function 格式）。"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters_schema,
        }

    def to_openai_tool(self) -> dict[str, Any]:
        """转换�� OpenAI tools 格式。"""
        return {
            "type": "function",
            "function": self.to_tool_definition(),
        }