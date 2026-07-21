"""LLM 客户端的 Protocol 定义。

使用 Protocol 而非 ABC：
- 结构化子类型（duck typing），不需要继承
- 方便测试时 mock
- 未来第三方 adapter 无需修改基类
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from .types import ChatRequest, ChatResponse, StreamEvent


@runtime_checkable
class LLMClient(Protocol):
    """LLM 客户端统一接口。

    所有 provider 实现（Claude、DeepSeek、OpenAI 等）都遵循此协议。
    上层代码（Brain、Server）只依赖此接口，不感知具体 provider。
    """

    @property
    def provider_name(self) -> str:
        """提供商标识，如 'claude', 'deepseek'。"""
        ...

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """非流式调用（完整等待响应）。

        适用于：测试、短回复、不需要实时反馈的场景。
        """
        ...

    async def chat_stream(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        """流式调用 — 核心方法。

        返回 async generator，yield StreamEvent。
        调用方通过 async for 消费事件流。

        事件顺序保证：
        - TEXT_DELTA 事件按文本顺序 yield
        - 最后一个事件一定是 DONE 或 ERROR
        """
        ...

    async def close(self) -> None:
        """关闭底层 HTTP 连接，释放资源。"""
        ...

    async def __aenter__(self) -> LLMClient:
        """支持 async with 上下文管理。"""
        ...

    async def __aexit__(self, *args: object) -> None:
        """退出时自动关闭连接。"""
        ...
