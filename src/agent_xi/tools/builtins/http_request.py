"""http_request — 发送 HTTP 请求。SENSITIVE 级别。"""

from __future__ import annotations

from typing import Any

import httpx

from ..base import SecurityLevel, Tool, ToolResult

_TIMEOUT = 30
_MAX_RESPONSE_SIZE = 10_000  # 响应体最大截取长度


class HttpRequestTool(Tool):
    """发送 HTTP 请求并返回响应。"""

    @property
    def name(self) -> str:
        return "http_request"

    @property
    def description(self) -> str:
        return (
            "发送 HTTP 请求（GET/POST/PUT/DELETE），返回状态码和响应内容。"
            "适用于调用 API、获取网页内容、测试接口等。"
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "请求 URL",
                },
                "method": {
                    "type": "string",
                    "description": "HTTP 方法",
                    "enum": ["GET", "POST", "PUT", "DELETE"],
                },
                "headers": {
                    "type": "string",
                    "description": "请求头（JSON 格式字符串，可选）",
                },
                "body": {
                    "type": "string",
                    "description": "请求体（可选）",
                },
            },
            "required": ["url"],
        }

    @property
    def security_level(self) -> SecurityLevel:
        return SecurityLevel.SENSITIVE

    async def execute(self, **kwargs: Any) -> ToolResult:
        url = kwargs.get("url", "")
        method = kwargs.get("method", "GET").upper()
        headers_str = kwargs.get("headers", "")
        body = kwargs.get("body", "")

        if not url:
            return ToolResult(
                success=False, output="", error="未指定 URL"
            )

        # 解析 headers
        headers: dict[str, str] = {}
        if headers_str:
            import json

            try:
                headers = json.loads(headers_str)
            except json.JSONDecodeError:
                return ToolResult(
                    success=False,
                    output="",
                    error="headers 格式错误，需要 JSON 字符串",
                )

        try:
            async with httpx.AsyncClient(
                timeout=_TIMEOUT, follow_redirects=True
            ) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers or None,
                    content=body or None,
                )

            # 格式化响应
            status = response.status_code
            resp_headers = dict(response.headers)
            content_type = resp_headers.get("content-type", "")
            resp_text = response.text[:_MAX_RESPONSE_SIZE]

            truncated = ""
            if len(response.text) > _MAX_RESPONSE_SIZE:
                truncated = f"\n...（已截断，原始 {len(response.text)} 字符）"

            output = (
                f"HTTP {status} {response.reason_phrase}\n"
                f"Content-Type: {content_type}\n"
                f"---\n"
                f"{resp_text}{truncated}"
            )

            return ToolResult(
                success=True,
                output=output,
                metadata={"status_code": status},
            )

        except httpx.TimeoutException:
            return ToolResult(
                success=False, output="", error=f"请求超时（{_TIMEOUT}s）：{url}"
            )
        except httpx.HTTPError as e:
            return ToolResult(
                success=False, output="", error=f"请求失败：{e}"
            )
