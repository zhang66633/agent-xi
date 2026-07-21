"""共享 fixtures — mock LLM / mock embedding / 示例工具。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from agent_xi.llm.types import (
    ChatRequest,
    ChatResponse,
    Message,
    Role,
    StreamEvent,
    StreamEventType,
    TextBlock,
    UsageInfo,
)
from agent_xi.tools.base import SecurityLevel, Tool, ToolResult


class ScriptedLLM:
    """按脚本回复的 mock LLM。

    scripts: 每次 chat_stream 调用消费一个脚本。
    脚本元素：
      ("text", "你好")           → TEXT_DELTA
      ("tool", name, args_dict)  → TOOL_USE_START + 完整 TOOL_USE_DELTA JSON
    最后自动补 DONE。
    """

    provider_name = "mock"

    def __init__(self, scripts: list[list[tuple[str, Any, Any] | tuple[str, Any]]]):
        self.scripts = list(scripts)
        self.requests: list[ChatRequest] = []

    async def chat(self, request: ChatRequest) -> ChatResponse:
        self.requests.append(request)
        text = "".join(
            part[1] for part in self._next_script() if part[0] == "text"
        )
        return ChatResponse(
            message=Message(role=Role.ASSISTANT, content=text or "ok"),
            finish_reason="stop",
            usage=UsageInfo(),
        )

    async def chat_stream(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        self.requests.append(request)
        for part in self._next_script():
            if part[0] == "text":
                yield StreamEvent(type=StreamEventType.TEXT_DELTA, text=part[1])
            elif part[0] == "tool":
                import json

                _, name, args = part
                yield StreamEvent(
                    type=StreamEventType.TOOL_USE_START, tool_name=name
                )
                yield StreamEvent(
                    type=StreamEventType.TOOL_USE_DELTA,
                    tool_arguments=json.dumps(args, ensure_ascii=False),
                )
        yield StreamEvent(type=StreamEventType.DONE, finish_reason="stop")

    def _next_script(self) -> list[Any]:
        if not self.scripts:
            return [("text", "（脚本耗尽）")]
        return self.scripts.pop(0)

    async def close(self) -> None:
        pass

    async def __aenter__(self) -> "ScriptedLLM":
        return self

    async def __aexit__(self, *args: object) -> None:
        pass


class FakeEmbedding:
    """确定性 mock embedding（32 维，按字符 hash），接口对齐 EmbeddingClient。"""

    dim = 32

    def _vec(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for i, ch in enumerate(text):
            vec[(ord(ch) + i) % self.dim] += 1.0
        norm = sum(x * x for x in vec) ** 0.5 or 1.0
        return [x / norm for x in vec]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    async def embed_one(self, text: str) -> list[float]:
        return self._vec(text)

    async def close(self) -> None:
        pass


class EchoTool(Tool):
    """测试用安全工具：回显参数。"""

    name = "echo"
    description = "回显输入文本"
    parameters_schema = {
        "type": "object",
        "properties": {"text": {"type": "string", "description": "要回显的文本"}},
        "required": ["text"],
    }

    async def execute(self, **kwargs: Any) -> ToolResult:
        return ToolResult(success=True, output=f"echo: {kwargs.get('text', '')}")


class SecretTool(Tool):
    """测试用敏感工具：需要确认。"""

    name = "secret"
    description = "敏感操作（测试）"
    parameters_schema = {"type": "object", "properties": {}}

    @property
    def security_level(self) -> SecurityLevel:
        return SecurityLevel.SENSITIVE

    async def execute(self, **kwargs: Any) -> ToolResult:
        return ToolResult(success=True, output="secret executed")


@pytest.fixture
def echo_tool() -> EchoTool:
    return EchoTool()


@pytest.fixture
def secret_tool() -> SecretTool:
    return SecretTool()
