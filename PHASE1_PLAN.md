# Agent Xi — Phase 1 实现计划

> Phase 1 目标：在终端里能连续对话，流式输出 LLM 回复。

---

## 一、范围确认

**包含**：

- LLM 完整抽象层（含 tool calling 接口设计，Phase 1 不启用）
- Brain 对话引擎（上下文管理 + 流式调用）
- CLI 简单交互（input loop + rich 流式渲染）
- 配置管理（Pydantic Settings + .env + YAML）

**不包含**：

- Memory 系统（Phase 2）
- Tool 执行（Phase 3）
- WebSocket / Server（Phase 4）
- Textual TUI（后续）

---

## 二、文件结构

```
agent_xi_project/
├── pyproject.toml                  # 项目元数据 + 依赖 + 入口点
├── .env                            # API keys（已存在，gitignore）
├── .env.example                    # 示例环境变量
├── config/
│   └── default.yaml                # 默认配置（模型选择、参数等）
├── src/
│   └── agent_xi/
│       ├── __init__.py             # 版本号
│       ├── __main__.py             # python -m agent_xi 入口
│       ├── config.py               # 配置加载（Pydantic Settings）
│       ├── llm/
│       │   ├── __init__.py         # 公开接口 re-export
│       │   ├── types.py            # 所有数据模型（messages, events, tools）
│       │   ├── base.py             # LLMClient Protocol 定义
│       │   ├── claude.py           # Claude Messages API 实现
│       │   ├── openai_compat.py    # OpenAI-compatible 实现（DeepSeek 复用）
│       │   └── factory.py          # 根据配置创建 client 实例
│       ├── brain/
│       │   ├── __init__.py
│       │   ├── engine.py           # Brain 核心：对话循环 + 流式输出
│       │   └── context.py          # 上下文构建（system prompt + history）
│       └── cli/
│           ├── __init__.py
│           └── app.py              # CLI 主循环 + rich 渲染
└── tests/
    ├── __init__.py
    ├── test_llm_types.py           # 数据模型序列化测试
    ├── test_brain.py               # Brain 逻辑测试（mock LLM）
    └── test_cli.py                 # CLI 集成测试
```

**设计理由**：

- 使用 `src/` layout，现代 Python 项目标准做法，避免开发时意外 import 未安装的包
- `llm/types.py` 集中所有数据模型，避免循环依赖
- `brain/` 和 `cli/` 分离，为 Phase 4 的 WebSocket server 复用 brain 做准备
- 文件数量极少（~12 个源文件），但每个文件职责清晰

---

## 三、模块职责

| 模块 | 职责 | Phase 1 行为 | 未来扩展点 |
|------|------|-------------|-----------|
| `llm/types.py` | 定义所有 LLM 交互的数据模型 | 消息、流事件、工具定义 | 不变，直接复用 |
| `llm/base.py` | LLMClient Protocol | chat_stream() | 加 embed() 等 |
| `llm/claude.py` | Claude API 适配 | 流式对话 | 加 tool_use 解析 |
| `llm/openai_compat.py` | OpenAI 格式适配 | 流式对话 | 加 function_call 解析 |
| `llm/factory.py` | 根据配置实例化 client | 读 config 选 provider | 支持多 client 池 |
| `brain/engine.py` | 对话引擎 | 单轮 LLM 调用 + 流式返回 | 加 ReAct 工具循环 |
| `brain/context.py` | 上下文组装 | system prompt + history 拼接 | 加记忆检索注入 |
| `cli/app.py` | 终端交互 | input loop + rich 流式打印 | 替换为 Textual TUI |
| `config.py` | 配置管理 | .env + yaml 加载 | 加 personality.yaml |

---

## 四、关键接口定义

### 4.1 LLM 数据模型 (`llm/types.py`)

```python
"""LLM 抽象层的核心数据模型。

设计原则：
- 使用 provider-neutral 的中间表示（IR）
- 各 provider 实现负责 IR <-> 原生格式的转换
- 使用 Python 3.12 的 type alias 和 modern syntax
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


# ─── 消息模型 ───────────────────────────────────────────────

class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"  # Phase 3 用，现在先定义


@dataclass(frozen=True, slots=True)
class TextBlock:
    """纯文本内容块"""
    text: str
    type: str = "text"


@dataclass(frozen=True, slots=True)
class ToolUseBlock:
    """LLM 请求调用工具（assistant 消息中出现）"""
    id: str
    name: str
    arguments: dict[str, Any]
    type: str = "tool_use"


@dataclass(frozen=True, slots=True)
class ToolResultBlock:
    """工具执行结果（tool 消息中出现）"""
    tool_use_id: str
    content: str
    is_error: bool = False
    type: str = "tool_result"


# 内容块联合类型
ContentBlock = TextBlock | ToolUseBlock | ToolResultBlock


@dataclass(frozen=True, slots=True)
class Message:
    """统一消息格式 — provider-neutral IR"""
    role: Role
    content: str | list[ContentBlock]
    name: str | None = None  # tool 调用时的函数名（OpenAI 格式需要）

    @property
    def text(self) -> str:
        """便捷方法：提取纯文本内容"""
        if isinstance(self.content, str):
            return self.content
        return "".join(
            block.text for block in self.content
            if isinstance(block, TextBlock)
        )


# ─── 工具定义（Phase 3 启用，Phase 1 先定义接口）─────────────

@dataclass(frozen=True, slots=True)
class ToolParameter:
    """工具参数的 JSON Schema 描述"""
    name: str
    type: str
    description: str
    required: bool = True
    enum: list[str] | None = None


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """工具定义 — 会被转换为各 provider 的原生格式"""
    name: str
    description: str
    parameters: list[ToolParameter] = field(default_factory=list)

    def to_json_schema(self) -> dict[str, Any]:
        """转换为 JSON Schema 格式（两种 provider 都需要）"""
        ...


# ─── 流式事件 ───────────────────────────────────────────────

class StreamEventType(StrEnum):
    TEXT_DELTA = "text_delta"           # 文本增量
    TOOL_USE_START = "tool_use_start"   # 工具调用开始（Phase 3）
    TOOL_USE_DELTA = "tool_use_delta"   # 工具参数增量（Phase 3）
    TOOL_USE_END = "tool_use_end"       # 工具调用结束（Phase 3）
    DONE = "done"                       # 流结束
    ERROR = "error"                     # 错误


@dataclass(frozen=True, slots=True)
class StreamEvent:
    """流式输出的统一事件"""
    type: StreamEventType
    text: str = ""                      # text_delta 时的增量文本
    tool_name: str = ""                 # tool_use_start 时的工具名
    tool_arguments: str = ""            # tool_use_delta 时的参数片段
    finish_reason: str | None = None    # done 时的结束原因
    error: str = ""                     # error 时的错误信息
    usage: UsageInfo | None = None      # done 时附带 token 用量


@dataclass(frozen=True, slots=True)
class UsageInfo:
    """Token 用量统计"""
    input_tokens: int = 0
    output_tokens: int = 0


# ─── 请求/响应 ──────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class ChatRequest:
    """统一的聊天请求"""
    messages: list[Message]
    system: str = ""
    tools: list[ToolDefinition] = field(default_factory=list)
    temperature: float = 0.7
    max_tokens: int = 4096
    stop_sequences: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ChatResponse:
    """非流式的完整响应（用于测试或不需要流式的场景）"""
    message: Message
    finish_reason: str
    usage: UsageInfo
```

### 4.2 LLM Client Protocol (`llm/base.py`)

```python
"""LLM 客户端的 Protocol 定义。

使用 Protocol 而非 ABC，原因：
- 结构化子类型（duck typing），不需要继承
- 方便测试时 mock
- 未来如果有第三方 adapter 无需修改基类
"""
from typing import Protocol, AsyncIterator, runtime_checkable

from .types import ChatRequest, ChatResponse, StreamEvent


@runtime_checkable
class LLMClient(Protocol):
    """LLM 客户端统一接口"""

    @property
    def provider_name(self) -> str:
        """提供商标识，如 'claude', 'deepseek'"""
        ...

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """非流式调用（完整等待响应）"""
        ...

    async def chat_stream(
        self, request: ChatRequest
    ) -> AsyncIterator[StreamEvent]:
        """流式调用 — 核心方法。

        返回 async generator，yield StreamEvent。
        调用方通过 async for 消费。
        """
        ...

    async def close(self) -> None:
        """关闭底层 HTTP 连接"""
        ...

    async def __aenter__(self) -> "LLMClient": ...
    async def __aexit__(self, *args) -> None: ...
```

### 4.3 Brain 引擎 (`brain/engine.py`)

```python
"""Brain — 对话引擎。

Phase 1：简单的 上下文构建 → LLM 流式调用 → 返回事件流。
Phase 3 扩展：加入 ReAct 工具循环。
"""
from typing import AsyncIterator

from ..llm.types import Message, StreamEvent, Role
from ..llm.base import LLMClient
from .context import ContextBuilder


class Brain:
    """对话引擎核心"""

    def __init__(
        self,
        client: LLMClient,
        context_builder: ContextBuilder,
    ) -> None:
        self._client = client
        self._context = context_builder
        self._history: list[Message] = []

    @property
    def history(self) -> list[Message]:
        """当前对话历史（只读视图）"""
        return list(self._history)

    async def chat(self, user_input: str) -> AsyncIterator[StreamEvent]:
        """处理一轮用户输入，返回流式事件。

        Phase 1 流程：
        1. 将 user_input 加入 history
        2. 构建完整上下文（system + history）
        3. 调用 LLM stream
        4. 收集完整回复，加入 history
        5. yield 每个 StreamEvent 给调用方

        Phase 3 扩展点：
        - 在 step 3 之后检查是否有 tool_use
        - 如果有，执行工具，将结果加入 history，重新调用 LLM
        """
        ...

    def clear_history(self) -> None:
        """清空对话历史（开始新对话）"""
        self._history.clear()
```

### 4.4 上下文构建器 (`brain/context.py`)

```python
"""上下文构建 — 组装发给 LLM 的完整 prompt。

Phase 1：system prompt + 对话历史。
Phase 2 扩展：注入记忆检索结果。
"""
from ..llm.types import Message, ChatRequest


class ContextBuilder:
    """构建 LLM 请求上下文"""

    def __init__(
        self,
        system_prompt: str = "",
        max_history_turns: int = 50,
    ) -> None:
        self._system_prompt = system_prompt
        self._max_history_turns = max_history_turns

    def build_request(
        self,
        history: list[Message],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> ChatRequest:
        """将 history 组装为 ChatRequest。

        Phase 2 扩展点：
        - 在 system prompt 后追加记忆检索结果
        - 根据 token 预算裁剪 history
        """
        ...

    @property
    def system_prompt(self) -> str:
        return self._system_prompt

    @system_prompt.setter
    def system_prompt(self, value: str) -> None:
        self._system_prompt = value
```

### 4.5 配置管理 (`config.py`)

```python
"""配置管理 — Pydantic Settings + YAML。

优先级：环境变量 > .env > config/default.yaml > 代码默认值
"""
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    """LLM 相关配置"""
    model_config = SettingsConfigDict(env_prefix="AGENT_XI_LLM_")

    provider: str = "deepseek"  # "claude" | "deepseek"
    model: str = "deepseek-chat"
    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout: float = 120.0
    max_retries: int = 3


class AppSettings(BaseSettings):
    """应用级配置"""
    model_config = SettingsConfigDict(
        env_prefix="AGENT_XI_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    llm: LLMSettings = Field(default_factory=LLMSettings)
    system_prompt: str = "你是 Xi，一个友好、诚实的 AI 伙伴。"
    max_history_turns: int = 50
    debug: bool = False


def load_settings(config_path: Path | None = None) -> AppSettings:
    """加载配置，合并 YAML 默认值和环境变量。"""
    ...
```

### 4.6 CLI 应用 (`cli/app.py`)

```python
"""CLI 交互界面 — Phase 1 简单版本。

使用 rich 做流式渲染，不引入 Textual。
"""
import asyncio
from rich.console import Console

from ..brain.engine import Brain
from ..llm.types import StreamEventType


class CliApp:
    """终端交互应用"""

    def __init__(self, brain: Brain) -> None:
        self._brain = brain
        self._console = Console()

    async def run(self) -> None:
        """主循环：读取输入 → 调用 brain → 流式渲染"""
        self._print_welcome()

        while True:
            try:
                # Windows 兼容：用 to_thread 避免阻塞事件循环
                user_input = await asyncio.to_thread(
                    self._console.input, "[bold green]你>[/] "
                )
            except (EOFError, KeyboardInterrupt):
                break

            if user_input.strip().lower() in ("/exit", "/quit", "exit"):
                break
            if user_input.strip() == "/clear":
                self._brain.clear_history()
                self._console.print("[dim]对话已清空。[/]")
                continue
            if not user_input.strip():
                continue

            await self._stream_response(user_input)

        self._console.print("\n[dim]再见！下次聊。[/]")

    async def _stream_response(self, user_input: str) -> None:
        """流式渲染 LLM 回复"""
        self._console.print("[bold blue]Xi>[/] ", end="")
        full_text = ""

        async for event in self._brain.chat(user_input):
            match event.type:
                case StreamEventType.TEXT_DELTA:
                    self._console.print(event.text, end="", highlight=False)
                    full_text += event.text
                case StreamEventType.ERROR:
                    self._console.print(f"\n[red]错误: {event.error}[/]")
                    return
                case StreamEventType.DONE:
                    self._console.print()  # 换行
```

---

## 五、依赖清单

```toml
[project]
name = "agent-xi"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "httpx>=0.27",           # 异步 HTTP 客户端（LLM API 调用）
    "pydantic>=2.7",         # 数据验证
    "pydantic-settings>=2.3",# 配置管理（.env + 环境变量）
    "pyyaml>=6.0",           # YAML 配置文件解析
    "rich>=13.7",            # CLI 美化输出 + 流式渲染
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.4",
]

[project.scripts]
agent-xi = "agent_xi.__main__:main"
```

**依赖极简**：只有 5 个运行时依赖。不引入 LangChain、openai SDK、anthropic SDK。

---

## 六、实现顺序

```
Step 1: 项目骨架 + 配置
  pyproject.toml, config.py, config/default.yaml, __main__.py
  理由：所有模块都依赖配置，先搭好地基。

Step 2: LLM 数据模型
  llm/types.py
  理由：这是整个系统的"语言"，所有模块都引用这些类型。

Step 3: LLM Client Protocol + OpenAI-compatible 实现
  llm/base.py, llm/openai_compat.py
  理由：DeepSeek 用 OpenAI 格式，用户已有 API key，可以最早跑通。

Step 4: Claude 实现
  llm/claude.py
  理由：有了 IR 和 OpenAI 实现的经验，格式转换是体力活。

Step 5: LLM Factory
  llm/factory.py
  理由：简单胶水代码。

Step 6: Brain 引擎
  brain/context.py, brain/engine.py
  理由：依赖 LLM 层，组装上下文 + 管理 history + 流式转发。

Step 7: CLI
  cli/app.py, __main__.py 完善
  理由：最后做 UI 层，此时可以端到端跑通。

Step 8: 测试 + 打磨
  tests/, 错误处理完善, edge cases
```

---

## 七、关键设计决策

### 7.1 流式输出：Async Generator 模式

核心模式：`chat_stream` 返回 `AsyncIterator[StreamEvent]`。

- Brain.chat() 也是 async generator，Phase 1 直接 yield LLM 的事件流
- CLI 用 `async for event in brain.chat(input)` 消费
- 未来 WebSocket server 消费同一个 generator，把事件序列化为 JSON
- **Brain 不关心谁在消费它的事件流**

### 7.2 Claude vs OpenAI 格式差异

核心策略：Provider 实现负责双向转换，IR 层完全 provider-neutral。

| 差异点 | Claude (Messages API) | OpenAI/DeepSeek |
|--------|----------------------|-----------------|
| System prompt | 顶层 `system` 字段 | messages 中 role=system |
| 流式格式 | `event: content_block_delta` | `data: {"choices":[{"delta":...}]}` |
| 工具定义 | `tools: [{name, input_schema}]` | `tools: [{function: {name, parameters}}]` |
| 工具调用 | content block type=tool_use | message.tool_calls 数组 |
| 工具结果 | role=user + tool_result block | role=tool + tool_call_id |
| 结束标志 | `event: message_stop` | `data: [DONE]` |

### 7.3 错误处理与重试

- 指数退避：delay = base_delay * 2^attempt + jitter
- 429 时尊重 Retry-After header
- 可重试状态码：429, 500, 502, 503, 529
- 流式传输中途断开：yield ERROR event 让上层决定
- 超时：connect=10s, read=120s（LLM 生成慢）
- 401/403：不重试，直接报错

### 7.4 Windows 终端兼容

- `asyncio.to_thread(input)` 避免阻塞事件循环
- rich 自动处理 Windows Terminal 的 ANSI 支持

### 7.5 配置优先级

```
代码默认值 < config/default.yaml < .env 文件 < 环境变量
```

---

## 八、为后续 Phase 预留的扩展点

| 扩展点 | Phase 1 状态 | 未来如何使用 |
|--------|-------------|-------------|
| `Message.content: list[ContentBlock]` | 只用 TextBlock | Phase 3 加 ToolUseBlock/ToolResultBlock |
| `ChatRequest.tools` | 传空列表 | Phase 3 传入注册的工具定义 |
| `StreamEvent` 的 tool 事件类型 | 定义了但不产生 | Phase 3 Brain 解析并处理 |
| `Brain.chat()` 的 generator | 直接 yield LLM 事件 | Phase 3 插入工具执行循环 |
| `ContextBuilder.build_request()` | 只拼 history | Phase 2 注入记忆检索结果 |
| `LLMClient` Protocol | chat + chat_stream | Phase 5 可能加 embed() |
| `CliApp` | 简单 input loop | 可替换为 Textual TUI 或 WebSocket adapter |

---

## 九、潜在风险与应对

| 风险 | 影响 | 应对 |
|------|------|------|
| DeepSeek SSE 格式与 OpenAI 有微妙差异 | 流式解析出错 | 先写集成测试跑通 DeepSeek |
| Windows 终端 async stdin 兼容性 | input() 阻塞事件循环 | `asyncio.to_thread(input)` |
| httpx 流式连接超时 | 长回复被截断 | read timeout 设 120s+ |
| Claude API 的 `anthropic-version` header | 401 错误 | 硬编码 `2023-06-01` |
| 对话历史过长超 token 限制 | API 报错 | Phase 1 简单截断最近 N 轮 |

---

*创建时间：2026-07-20*
