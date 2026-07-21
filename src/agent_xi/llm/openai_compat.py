"""OpenAI-compatible LLM 客户端实现。

适用于所有兼容 OpenAI Chat Completions API 的 provider：
- DeepSeek（主要目标）
- OpenAI
- 其他兼容服务（如 vLLM、Ollama 等）

核心职责：
- IR (types.py) <-> OpenAI 原生格式的双向转换
- SSE 流式解析
- 指数退避重试
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
    ToolUseBlock,
    UsageInfo,
)

logger = logging.getLogger(__name__)

# 可重试的 HTTP 状态码
_RETRYABLE_STATUS = {429, 500, 502, 503, 529}


class OpenAICompatClient:
    """OpenAI-compatible API 客户端。"""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.deepseek.com",
        timeout: float = 120.0,
        max_retries: int = 3,
        provider_name: str = "deepseek",
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._max_retries = max_retries
        self._provider_name = provider_name
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(connect=10.0, read=timeout, write=10.0, pool=10.0),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    @property
    def provider_name(self) -> str:
        return self._provider_name

    # ─── 公开接口 ────────────────────────────────────────────────────────────────

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """非流式调用。"""
        payload = self._build_payload(request, stream=False)
        data = await self._request_with_retry(payload)
        return self._parse_response(data)

    async def chat_stream(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        """流式调用 — 解析 SSE 事件流。"""
        payload = self._build_payload(request, stream=True)

        try:
            async with self._client.stream(
                "POST",
                "/chat/completions",
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
            yield StreamEvent(
                type=StreamEventType.ERROR,
                error=f"请求超时: {e}",
            )
        except httpx.HTTPError as e:
            yield StreamEvent(
                type=StreamEventType.ERROR,
                error=f"HTTP 错误: {e}",
            )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> OpenAICompatClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    # ─── 格式转换：IR → OpenAI ───────────────────────────────────────────────────

    def _build_payload(self, request: ChatRequest, *, stream: bool) -> dict[str, Any]:
        """将 ChatRequest IR 转换为 OpenAI API payload。"""
        messages: list[dict[str, Any]] = []

        # System prompt → OpenAI 格式的 system message
        if request.system:
            messages.append({"role": "system", "content": request.system})

        # 转换消息历史
        for msg in request.messages:
            messages.append(self._message_to_openai(msg))

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": stream,
        }

        if request.stop_sequences:
            payload["stop"] = request.stop_sequences

        # 工具定义（Phase 3 启用）
        if request.tools:
            payload["tools"] = [self._tool_to_openai(t) for t in request.tools]

        if stream:
            payload["stream_options"] = {"include_usage": True}

        return payload

    def _message_to_openai(self, msg: Message) -> dict[str, Any]:
        """将 IR Message 转换为 OpenAI 消息格式。"""
        if isinstance(msg.content, str):
            result: dict[str, Any] = {"role": msg.role.value, "content": msg.content}
            if msg.name:
                result["name"] = msg.name
            return result

        # 内容块列表
        if msg.role == Role.ASSISTANT:
            # assistant 消息可能包含 text + tool_calls
            text_parts: list[str] = []
            tool_calls: list[dict[str, Any]] = []

            for block in msg.content:
                if isinstance(block, TextBlock):
                    text_parts.append(block.text)
                elif isinstance(block, ToolUseBlock):
                    tool_calls.append(
                        {
                            "id": block.id,
                            "type": "function",
                            "function": {
                                "name": block.name,
                                "arguments": json.dumps(
                                    block.arguments, ensure_ascii=False
                                ),
                            },
                        }
                    )

            result = {"role": "assistant"}
            result["content"] = "".join(text_parts) if text_parts else None
            if tool_calls:
                result["tool_calls"] = tool_calls
            return result

        if msg.role == Role.TOOL:
            # tool result 消息
            from .types import ToolResultBlock

            for block in msg.content:
                if isinstance(block, ToolResultBlock):
                    return {
                        "role": "tool",
                        "tool_call_id": block.tool_use_id,
                        "content": block.content,
                    }

        # 默认：拼接文本
        return {"role": msg.role.value, "content": msg.text}

    def _tool_to_openai(self, tool: ToolDefinition) -> dict[str, Any]:
        """将 IR ToolDefinition 转换为 OpenAI tools 格式。"""
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.to_json_schema(),
            },
        }

    # ─── 格式转换：OpenAI → IR ───────────────────────────────────────────────────

    def _parse_response(self, data: dict[str, Any]) -> ChatResponse:
        """将 OpenAI 非流式响应转换为 IR。"""
        choice = data["choices"][0]
        raw_msg = choice["message"]

        content_blocks = self._parse_assistant_content(raw_msg)
        message = Message(role=Role.ASSISTANT, content=content_blocks)

        usage_data = data.get("usage", {})
        usage = UsageInfo(
            input_tokens=usage_data.get("prompt_tokens", 0),
            output_tokens=usage_data.get("completion_tokens", 0),
        )

        return ChatResponse(
            message=message,
            finish_reason=choice.get("finish_reason", "stop"),
            usage=usage,
        )

    def _parse_assistant_content(
        self, raw_msg: dict[str, Any]
    ) -> str | list[TextBlock | ToolUseBlock]:
        """解析 assistant 消息内容。"""
        text = raw_msg.get("content") or ""
        tool_calls = raw_msg.get("tool_calls")

        if not tool_calls:
            return text

        blocks: list[TextBlock | ToolUseBlock] = []
        if text:
            blocks.append(TextBlock(text=text))

        for tc in tool_calls:
            func = tc["function"]
            try:
                arguments = json.loads(func["arguments"])
            except json.JSONDecodeError:
                arguments = {"_raw": func["arguments"]}
            blocks.append(
                ToolUseBlock(
                    id=tc["id"],
                    name=func["name"],
                    arguments=arguments,
                )
            )

        return blocks

    # ─── SSE 流式解析 ────────────────────────────────────────────────────────────

    async def _parse_sse_stream(
        self, response: httpx.Response
    ) -> AsyncIterator[StreamEvent]:
        """解析 OpenAI SSE 流，yield 统一 StreamEvent。

        SSE 格式：
        - data: {"choices":[{"delta":{"content":"你"}}]}
        - data: {"choices":[{"delta":{"tool_calls":[...]}}]}
        - data: [DONE]
        """
        finish_reason: str | None = None
        usage: UsageInfo | None = None

        async for line in response.aiter_lines():
            line = line.strip()

            if not line or not line.startswith("data:"):
                continue

            data_str = line[5:].strip()

            if data_str == "[DONE]":
                yield StreamEvent(
                    type=StreamEventType.DONE,
                    finish_reason=finish_reason or "stop",
                    usage=usage,
                )
                return

            try:
                chunk = json.loads(data_str)
            except json.JSONDecodeError:
                logger.warning("无法解析 SSE chunk: %s", data_str[:100])
                continue

            # 提取 usage（通常在最后一个 chunk）
            if "usage" in chunk and chunk["usage"]:
                u = chunk["usage"]
                usage = UsageInfo(
                    input_tokens=u.get("prompt_tokens", 0),
                    output_tokens=u.get("completion_tokens", 0),
                )

            choices = chunk.get("choices")
            if not choices:
                continue

            delta = choices[0].get("delta", {})

            # 更新 finish_reason
            if choices[0].get("finish_reason"):
                finish_reason = choices[0]["finish_reason"]

            # 文本增量
            if "content" in delta and delta["content"]:
                yield StreamEvent(
                    type=StreamEventType.TEXT_DELTA,
                    text=delta["content"],
                )

            # 工具调用增量（Phase 3 完整支持）
            if "tool_calls" in delta:
                for tc_delta in delta["tool_calls"]:
                    func = tc_delta.get("function", {})
                    if func.get("name"):
                        yield StreamEvent(
                            type=StreamEventType.TOOL_USE_START,
                            tool_name=func["name"],
                        )
                    if func.get("arguments"):
                        yield StreamEvent(
                            type=StreamEventType.TOOL_USE_DELTA,
                            tool_arguments=func["arguments"],
                        )

        # 流正常结束但没有 [DONE] 标记（某些 provider 的行为）
        yield StreamEvent(
            type=StreamEventType.DONE,
            finish_reason=finish_reason or "stop",
            usage=usage,
        )

    # ─── 重试逻辑 ────────────────────────────────────────────────────────────────

    async def _request_with_retry(self, payload: dict[str, Any]) -> dict[str, Any]:
        """带指数退避重试的 HTTP 请求（用于非流式调用）。"""
        last_error: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.post("/chat/completions", json=payload)

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

                # 不可重试的错误（401, 403 等）
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
        """指数退避 + 随机抖动。"""
        base = 1.0 * (2**attempt)
        jitter = random.uniform(0, base * 0.1)  # noqa: S311
        return base + jitter

    @staticmethod
    def _get_retry_after(response: httpx.Response) -> float | None:
        """从 Retry-After header 获取等待时间。"""
        retry_after = response.headers.get("retry-after")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass
        return None

    @staticmethod
    def _extract_error_message(status_code: int, body: bytes) -> str:
        """从错误响应体中提取错误信息。"""
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
