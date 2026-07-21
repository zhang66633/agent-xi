"""LLM 抽象层的核心数据模型。

设计原则：
- Provider-neutral 的中间表示（IR），上层代码不感知底层是 Claude 还是 DeepSeek
- 各 provider 实现负责 IR <-> 原生格式的双向转换
- 使用 Python 3.12 modern syntax（StrEnum, type alias, slots）
- frozen dataclass 保证不可变性，避免意外修改消息历史
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

# ─── 消息模型 ───────────────────────────────────────────────────────────────────


class Role(StrEnum):
    """消息角色。"""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass(frozen=True, slots=True)
class TextBlock:
    """纯文本内容块。"""

    text: str
    type: str = "text"


@dataclass(frozen=True, slots=True)
class ToolUseBlock:
    """LLM 请求调用工具（出现在 assistant 消息中）。

    Phase 3 启用，Phase 1 先定义接口。
    """

    id: str
    name: str
    arguments: dict[str, Any]
    type: str = "tool_use"


@dataclass(frozen=True, slots=True)
class ToolResultBlock:
    """工具执行结果（出现在 tool 消息中）。

    Phase 3 启用，Phase 1 先定义接口。
    """

    tool_use_id: str
    content: str
    is_error: bool = False
    type: str = "tool_result"


# 内容块联合类型
ContentBlock = TextBlock | ToolUseBlock | ToolResultBlock


@dataclass(frozen=True, slots=True)
class Message:
    """统一消息格式 — provider-neutral IR。

    content 可以是纯字符串（简单文本消息）或内容块列表（包含工具调用等）。
    """

    role: Role
    content: str | list[ContentBlock]
    name: str | None = None

    @property
    def text(self) -> str:
        """便捷方法：提取纯文本内容。"""
        if isinstance(self.content, str):
            return self.content
        return "".join(
            block.text for block in self.content if isinstance(block, TextBlock)
        )

    @property
    def tool_use_blocks(self) -> list[ToolUseBlock]:
        """便捷方法：提取所有工具调用块。"""
        if isinstance(self.content, str):
            return []
        return [b for b in self.content if isinstance(b, ToolUseBlock)]


# ─── 工具定义（Phase 3 启用，Phase 1 先定义接口）─────────────────────────────────


@dataclass(frozen=True, slots=True)
class ToolParameter:
    """工具参数的 JSON Schema 描述。"""

    name: str
    type: str
    description: str
    required: bool = True
    enum: list[str] | None = None


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """工具定义 — 会被转换为各 provider 的原生格式。"""

    name: str
    description: str
    parameters: list[ToolParameter] = field(default_factory=list)

    def to_json_schema(self) -> dict[str, Any]:
        """转换为 JSON Schema 格式（两种 provider 都需要）。"""
        properties: dict[str, Any] = {}
        required: list[str] = []

        for param in self.parameters:
            prop: dict[str, Any] = {
                "type": param.type,
                "description": param.description,
            }
            if param.enum:
                prop["enum"] = param.enum
            properties[param.name] = prop
            if param.required:
                required.append(param.name)

        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }


# ─── 流式事件 ───────────────────────────────────────────────────────────────────


class StreamEventType(StrEnum):
    """流式事件类型。"""

    TEXT_DELTA = "text_delta"
    TOOL_USE_START = "tool_use_start"
    TOOL_USE_DELTA = "tool_use_delta"
    TOOL_USE_END = "tool_use_end"
    # Phase 3: Brain 发出的工具执行状态事件
    TOOL_EXECUTING = "tool_executing"  # 正在执行工具
    TOOL_RESULT = "tool_result"  # 工具执行完成
    TOOL_CONFIRM_DENIED = "tool_confirm_denied"  # 用户拒绝执行
    DONE = "done"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class UsageInfo:
    """Token 用量统计。"""

    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True, slots=True)
class StreamEvent:
    """流式输出的统一事件。

    不同 type 使用不同字段：
    - TEXT_DELTA: text 有值
    - TOOL_USE_START: tool_name 有值
    - TOOL_USE_DELTA: tool_arguments 有值（增量 JSON 片段）
    - TOOL_USE_END: tool_name 有值
    - DONE: finish_reason 有值，usage 可能有值
    - ERROR: error 有值
    """

    type: StreamEventType
    text: str = ""
    tool_name: str = ""
    tool_arguments: str = ""
    finish_reason: str | None = None
    error: str = ""
    usage: UsageInfo | None = None


# ─── 请求/响应 ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ChatRequest:
    """统一的聊天请求。"""

    messages: list[Message]
    system: str = ""
    tools: list[ToolDefinition] = field(default_factory=list)
    temperature: float = 0.7
    max_tokens: int = 4096
    stop_sequences: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ChatResponse:
    """非流式的完整响应（用于测试或不需要流式的场景）。"""

    message: Message
    finish_reason: str
    usage: UsageInfo
