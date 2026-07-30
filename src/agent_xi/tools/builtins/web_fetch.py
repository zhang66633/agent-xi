"""Web Fetch 工具 — 获取网页内容。

对标 Claude Code 的 WebFetch 工具。
获取 URL 内容，提取文本（去 HTML 标签）。
"""

from __future__ import annotations

import html as _html
import re
import urllib.parse
from typing import Any

import httpx

from ..base import SecurityLevel, Tool, ToolResult

_TIMEOUT = 20.0
_MAX_LENGTH = 30_000

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AgentXi/3.0; +https://github.com/zhang66633/agent-xi)",
    "Accept": "text/html,application/xhtml+xml,text/plain",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


class WebFetchTool(Tool):
    """获取 URL 内容，提取可读文本。"""

    @property
    def name(self) -> str:
        return "web_fetch"

    @property
    def description(self) -> str:
        return (
            "获取网页 URL 的内容，自动提取文本（去 HTML 标签）。"
            "适用于查阅在线文档、API 参考、博客文章等。"
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "要获取的网页 URL",
                },
                "max_length": {
                    "type": "integer",
                    "description": f"返回的最大字符数，默认 {_MAX_LENGTH}",
                },
            },
            "required": ["url"],
        }

    @property
    def security_level(self) -> SecurityLevel:
        return SecurityLevel.SENSITIVE

    async def execute(self, **kwargs: Any) -> ToolResult:
        url = str(kwargs.get("url", ""))
        max_len = min(kwargs.get("max_length", _MAX_LENGTH), 100_000)

        if not url:
            return ToolResult(success=False, output="", error="需要 url 参数")

        # 协议白名单
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return ToolResult(
                success=False, output="",
                error=f"不支持的协议: {parsed.scheme}。仅支持 http/https。",
            )

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
                response = await client.get(url, headers=_HEADERS)
                response.raise_for_status()
        except httpx.TimeoutException:
            return ToolResult(success=False, output="", error=f"请求超时 ({_TIMEOUT}s): {url}")
        except httpx.HTTPStatusError as e:
            return ToolResult(success=False, output="", error=f"HTTP {e.response.status_code}: {url}")
        except Exception as e:
            return ToolResult(success=False, output="", error=f"请求失败: {e}")

        # 提取文本
        text = self._extract_text(response.text)

        # 截断
        truncated = len(text) > max_len
        if truncated:
            text = text[:max_len] + f"\n\n...[截断，共 {len(text)} 字符]"

        return ToolResult(
            success=True,
            output=text,
            metadata={
                "url": url,
                "status_code": response.status_code,
                "content_type": response.headers.get("content-type", ""),
                "original_length": len(response.text),
                "extracted_length": len(text),
                "truncated": truncated,
            },
        )

    @staticmethod
    def _extract_text(html: str) -> str:
        """从 HTML 中提取可读文本。"""
        # 移除 script/style
        text = re.sub(
            r'<(script|style|noscript|iframe|svg)[^>]*>.*?</\1>',
            '', html, flags=re.DOTALL | re.IGNORECASE,
        )
        # 移除 HTML 注释
        text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
        # 换行标签 → 换行
        text = re.sub(
            r'<(br|hr)[^>]*/?>', '\n', text, flags=re.IGNORECASE,
        )
        # 块级标签前后加换行
        text = re.sub(
            r'</?(div|p|h[1-6]|li|tr|article|section|header|footer|nav|main)[^>]*>',
            '\n', text, flags=re.IGNORECASE,
        )
        # 移除所有剩余标签
        text = re.sub(r'<[^>]+>', '', text)
        # HTML 实体解码
        text = _html.unescape(text)
        # 压缩连续空行
        text = re.sub(r'\n{3,}', '\n\n', text)
        # 压缩行内空白
        text = re.sub(r'[ \t]+', ' ', text)
        # 去除首尾空白
        return text.strip()