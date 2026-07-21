"""Claude Messages API 客户端实现。

Claude 使用独立的 Messages API 格式，与 OpenAI 有显著差异：
- System prompt 是顶层字段，不在 messages 数组中
- 流式使用 event: 前缀的 SSE（content_block_start/delta/stop）
- 工具调用通过 content block type=tool_use 表达
- 工具结果通过 role=user + tool_result block 传递

本模块负责 IR <-> Claude 原生格式的双向转换。
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from collections.abc import AsyncIterator
from typing import Any

import httpx

from .types import (
    ChatRequest,
    ChatResponse,
    Message,
    Role,
    StreamEvent,
    StreamEventType,
    TextBlock,
    ToolDefinition,
    ToolResultBlock,
    ToolUseBlock,
    UsageInfo,
)

logger = logging.getLogger(__name__)

_ANTHROPIC_VERSION = "2023-06-01"
_RETRYABLE_STATUS = {429, 500, 502, 503, 529}


class ClaudeClient:
    """Claude Messages API 客户端。"""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        base_url: str = "https://api.anthropic.com",
        timeout: float = 120.0,
        max_retries: int = 3,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._max_retries = max_retries
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(connect=10.0, read=timeout, write=10.0, pool=10.0),
            headers={
                "x-api-key": api_key,
                "anthropic-version": _ANTHROPIC_VERSION,
                "Content-Type": "application/json",
            },
        )

    @property
    def provider_name(self) -> str:
        return "claude"

    # ─── 公开接口 ────────────────────────────────────────────────────────────────

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """非流式调用。"""
        payload = self._build_payload(request, stream=False)
        data = await self._request_with_retry(payload)
        return self._parse_response(data)

    async def chat_stream(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        """流式调用 — 解析 Claude SSE 事件流。

        Claude SSE 事件结构：
        - event: message_start → 消息开始（含 usage.input_tokens）
        - event: content_block_start → 新 block 开始（text 或 tool_use）
        - event: content_block_delta → 增量内容
        - event: content_block_stop → block 结束
        - event: message_delta → finish_reason + usage.output_tokens
        - event: message_stop → 消息结束
        """
        payload = self._build_payload(request, stream=True)

        try:
            async with self._client.stream(
                "POST",
                "/v1/messages",
                json=payload,
            ) as response:
                if response.status_code != 200:
                    error_body = await response.aread()
                    error_msg = self._extract_error_message(
                        response.status_code, error_body
                    )
                    yield StreamEvent(type=StreamEventType.ERROR, error=error_msg)
                    return

                async for event in self._parse_sse_stream(response):
                    yield event

        except httpx.TimeoutException as e:
            yield StreamEvent(type=StreamEventType.ERROR, error=f"请求超时: {e}")
        except httpx.HTTPError as e:
            yield StreamEvent(type=StreamEventType.ERROR, error=f"HTTP 错误: {e}")

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> ClaudeClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    # ─── 格式转换：IR → Claude ───────────────────────────────────────────────────

    def _build_payload(self, request: ChatRequest, *, stream: bool) -> dict[str, Any]:
        """将 ChatRequest IR 转换为 Claude Messages API payload。"""
        messages: list[dict[str, Any]] = []

        for msg in request.messages:
            # Claude 不接受 system role 在 messages 中
            if msg.role == Role.SYSTEM:
                continue
            messages.append(self._message_to_claude(msg))

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "stream": stream,
        }

        # System prompt 是顶层字段
        if request.system:
            payload["system"] = request.system

        if request.temperature is not None:
            payload["temperature"] = request.temperature

        if request.stop_sequences:
            payload["stop_sequences"] = request.stop_sequences

        # 工具定义（Phase 3 启用）
        if request.tools:
            payload["tools"] = [self._tool_to_claude(t) for t in request.tools]

        return payload

    def _message_to_claude(self, msg: Message) -> dict[str, Any]:
        """将 IR Message 转换为 Claude 消息格式。"""
        if isinstance(msg.content, str):
            return {"role": msg.role.value, "content": msg.content}

        # 内容块列表 → Claude content blocks
        blocks: list[dict[str, Any]] = []

        for block in msg.content:
            if isinstance(block, TextBlock):
                blocks.append({"type": "text", "text": block.text})
            elif isinstance(block, ToolUseBlock):
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.arguments,
                    }
                )
            elif isinstance(block, ToolResultBlock):
                blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.tool_use_id,
                        "content": block.content,
                        "is_error": block.is_error,
                    }
                )

        # Claude 的 tool result 需要放在 role=user 消息中
        role = msg.role.value
        if msg.role == Role.TOOL:
            role = "user"

        return {"role": role, "content": blocks}

    def _tool_to_claude(self, tool: ToolDefinition) -> dict[str, Any]:
        """将 IR ToolDefinition 转换为 Claude tools 格式。"""
        return {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.to_json_schema(),
        }

    # ─── 格式转换：Claude → IR ───────────────────────────────────────────────────

    def _parse_response(self, data: dict[str, Any]) -> ChatResponse:
        """将 Claude 非流式响应转换为 IR。"""
        content_blocks = data.get("content", [])
        blocks = self._parse_content_blocks(content_blocks)

        message = Message(role=Role.ASSISTANT, content=blocks)

        usage_data = data.get("usage", {})
        usage = UsageInfo(
            input_tokens=usage_data.get("input_tokens", 0),
            output_tokens=usage_data.get("output_tokens", 0),
        )

        return ChatResponse(
            message=message,
            finish_reason=data.get("stop_reason", "end_turn"),
            usage=usage,
        )

    def _parse_content_blocks(
        self, raw_blocks: list[dict[str, Any]]
    ) -> str | list[TextBlock | ToolUseBlock]:
        """解析 Claude content blocks 为 IR。"""
        if not raw_blocks:
            return ""

        # 如果只有一个 text block，简化为纯字符串
        if len(raw_blocks) == 1 and raw_blocks[0].get("type") == "text":
            return raw_blocks[0].get("text", "")

        blocks: list[TextBlock | ToolUseBlock] = []
        for raw in raw_blocks:
            block_type = raw.get("type")
            if block_type == "text":
                blocks.append(TextBlock(text=raw.get("text", "")))
            elif block_type == "tool_use":
                blocks.append(
                    ToolUseBlock(
                        id=raw.get("id", ""),
                        name=raw.get("name", ""),
                        arguments=raw.get("input", {}),
                    )
                )

        return blocks

    # ─── SSE 流式解析 ────────────────────────────────────────────────────────────

    async def _parse_sse_stream(
        self, response: httpx.Response
    ) -> AsyncIterator[StreamEvent]:
        """解析 Claude SSE 事件流。

        Claude 的 SSE 使用 event: 和 data: 两行一组：
            event: content_block_delta
            data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"你"}}
        """
        current_event_type: str = ""
        input_tokens: int = 0
        output_tokens: int = 0
        finish_reason: str | None = None

        async for line in response.aiter_lines():
            line = line.strip()

            if line.startswith("event:"):
                current_event_type = line[6:].strip()
                continue

            if not line.startswith("data:"):
                continue

            data_str = line[5:].strip()
            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            # 根据事件类型分发处理
            if current_event_type == "message_start":
                usage_data = data.get("message", {}).get("usage", {})
                input_tokens = usage_data.get("input_tokens", 0)

            elif current_event_type == "content_block_delta":
                delta = data.get("delta", {})
                delta_type = delta.get("type")

                if delta_type == "text_delta":
                    yield StreamEvent(
                        type=StreamEventType.TEXT_DELTA,
                        text=delta.get("text", ""),
                    )
                elif delta_type == "input_json_delta":
                    yield StreamEvent(
                        type=StreamEventType.TOOL_USE_DELTA,
                        tool_arguments=delta.get("partial_json", ""),
                    )

            elif current_event_type == "content_block_start":
                block = data.get("content_block", {})
                if block.get("type") == "tool_use":
                    yield StreamEvent(
                        type=StreamEventType.TOOL_USE_START,
                        tool_name=block.get("name", ""),
                    )

            elif current_event_type == "content_block_stop":
                # 可能是 tool_use block 结束
                yield StreamEvent(type=StreamEventType.TOOL_USE_END)

            elif current_event_type == "message_delta":
                delta = data.get("delta", {})
                if delta.get("stop_reason"):
                    finish_reason = delta["stop_reason"]
                usage_data = data.get("usage", {})
                output_tokens = usage_data.get("output_tokens", output_tokens)

            elif current_event_type == "message_stop":
                yield StreamEvent(
                    type=StreamEventType.DONE,
                    finish_reason=finish_reason or "end_turn",
                    usage=UsageInfo(
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                    ),
                )
                return

        # 流结束但没有 message_stop（异常情况）
        yield StreamEvent(
            type=StreamEventType.DONE,
            finish_reason=finish_reason or "end_turn",
            usage=UsageInfo(input_tokens=input_tokens, output_tokens=output_tokens),
        )

    # ─── 重试逻辑 ────────────────────────────────────────────────────────────────

    async def _request_with_retry(self, payload: dict[str, Any]) -> dict[str, Any]:
        """带指数退避重试的 HTTP 请求（用于非流式调用）。"""
        last_error: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.post("/v1/messages", json=payload)

                if response.status_code == 200:
                    return response.json()

                if response.status_code in _RETRYABLE_STATUS:
                    retry_after = self._get_retry_after(response)
                    delay = retry_after or self._backoff_delay(attempt)
                    logger.warning(
                        "请求失败 (HTTP %d)，%.1fs 后重试 (attempt %d/%d)",
                        response.status_code,
                        delay,
                        attempt + 1,
                        self._max_retries,
                    )
                    await asyncio.sleep(delay)
                    last_error = httpx.HTTPStatusError(
                        f"HTTP {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                    continue

                error_msg = self._extract_error_message(
                    response.status_code, response.content
                )
                raise httpx.HTTPStatusError(
                    error_msg, request=response.request, response=response
                )

            except httpx.TimeoutException as e:
                last_error = e
                if attempt < self._max_retries:
                    delay = self._backoff_delay(attempt)
                    logger.warning("请求超时，%.1fs 后重试", delay)
                    await asyncio.sleep(delay)
                    continue
                raise

        raise last_error or RuntimeError("重试耗尽")

    def _backoff_delay(self, attempt: int) -> float:
        base = 1.0 * (2**attempt)
        jitter = random.uniform(0, base * 0.1)  # noqa: S311
        return base + jitter

    @staticmethod
    def _get_retry_after(response: httpx.Response) -> float | None:
        retry_after = response.headers.get("retry-after")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass
        return None

    @staticmethod
    def _extract_error_message(status_code: int, body: bytes) -> str:
        try:
            data = json.loads(body)
            if "error" in data:
                err = data["error"]
                if isinstance(err, dict):
                    return f"[HTTP {status_code}] {err.get('message', str(err))}"
                return f"[HTTP {status_code}] {err}"
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
        return f"[HTTP {status_code}] {body.decode('utf-8', errors='replace')[:200]}"
