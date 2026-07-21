"""web_search — 网络搜索。SENSITIVE 级别（需要网络访问）。

主搜索引擎：Bing（国内可用）。
备用：DuckDuckGo HTML（需翻墙）。
"""

from __future__ import annotations

import re
import urllib.parse
from typing import Any

import httpx

from ..base import SecurityLevel, Tool, ToolResult

_MAX_RESULTS = 5
_TIMEOUT = 15

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


class WebSearchTool(Tool):
    """使用 Bing 进行网络搜索（国内可用）。"""

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return (
            "在网络上搜索信息，返回相关结果摘要。"
            "适用于查找最新信息、技术文档、新闻等。"
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词",
                },
                "num_results": {
                    "type": "integer",
                    "description": "返回结果数量，默认 5",
                },
            },
            "required": ["query"],
        }

    @property
    def security_level(self) -> SecurityLevel:
        return SecurityLevel.SENSITIVE

    async def execute(self, **kwargs: Any) -> ToolResult:
        query = kwargs.get("query", "")
        num_results = min(kwargs.get("num_results", _MAX_RESULTS), 10)

        if not query:
            return ToolResult(
                success=False, output="", error="未提供搜索关键词"
            )

        # 优先 Bing，失败则尝试 DuckDuckGo
        results: list[dict[str, str]] = []
        errors: list[str] = []

        try:
            results = await self._search_bing(query, num_results)
        except Exception as e:
            errors.append(f"Bing: {e}")

        if not results:
            try:
                results = await self._search_duckduckgo(query, num_results)
            except Exception as e:
                errors.append(f"DuckDuckGo: {e}")

        if not results:
            if errors:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"搜索失败（{'；'.join(errors)}）",
                )
            return ToolResult(
                success=True,
                output=f"未找到与「{query}」相关的结果。",
            )

        # 格式化输出
        lines = [f"搜索「{query}」的结果：\n"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r['title']}")
            lines.append(f"   {r['snippet']}")
            lines.append(f"   链接：{r['url']}\n")

        return ToolResult(success=True, output="\n".join(lines))

    # ─── Bing 搜索 ─────────────────────────────────────────────────────────────

    async def _search_bing(
        self, query: str, num_results: int
    ) -> list[dict[str, str]]:
        """通过 Bing 搜索（国内可用）。"""
        async with httpx.AsyncClient(
            timeout=_TIMEOUT, follow_redirects=True
        ) as client:
            response = await client.get(
                "https://www.bing.com/search",
                params={"q": query, "count": str(num_results)},
                headers=_HEADERS,
            )
            response.raise_for_status()

        return self._parse_bing_results(response.text, num_results)

    @staticmethod
    def _parse_bing_results(
        html: str, num_results: int
    ) -> list[dict[str, str]]:
        """解析 Bing 搜索页面 HTML。

        Bing 结果结构：
        <li class="b_algo">
          <h2><a href="url">title</a></h2>
          <p>snippet</p>  (或 <div class="b_caption"><p>...)
        </li>
        """
        results: list[dict[str, str]] = []

        # 匹配每个搜索结果块
        blocks = re.findall(
            r'<li[^>]*class="b_algo"[^>]*>(.*?)</li>',
            html,
            re.DOTALL,
        )

        for block in blocks[:num_results]:
            # 提取标题和 URL
            title_match = re.search(
                r'<h2[^>]*>\s*<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
                block,
                re.DOTALL,
            )
            if not title_match:
                continue

            url = title_match.group(1)
            title = re.sub(r"<[^>]+>", "", title_match.group(2)).strip()

            # 提取摘要
            snippet = ""
            snippet_match = re.search(
                r'<p[^>]*>(.*?)</p>', block, re.DOTALL
            )
            if snippet_match:
                snippet = re.sub(
                    r"<[^>]+>", "", snippet_match.group(1)
                ).strip()

            if title:
                results.append(
                    {"title": title, "snippet": snippet, "url": url}
                )

        return results

    # ─── DuckDuckGo 备用 ───────────────────────────────────────────────────────

    async def _search_duckduckgo(
        self, query: str, num_results: int
    ) -> list[dict[str, str]]:
        """通过 DuckDuckGo HTML 接口搜索（备用，需翻墙）。"""
        async with httpx.AsyncClient(
            timeout=_TIMEOUT, follow_redirects=True
        ) as client:
            response = await client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers=_HEADERS,
            )
            response.raise_for_status()

        return self._parse_ddg_results(response.text, num_results)

    @staticmethod
    def _parse_ddg_results(
        html: str, num_results: int
    ) -> list[dict[str, str]]:
        """从 DuckDuckGo HTML 响应中解析搜索结果。"""
        results: list[dict[str, str]] = []

        blocks = re.findall(
            r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>'
            r"(.*?)</a>.*?"
            r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
            html,
            re.DOTALL,
        )

        for url, title, snippet in blocks[:num_results]:
            clean_title = re.sub(r"<[^>]+>", "", title).strip()
            clean_snippet = re.sub(r"<[^>]+>", "", snippet).strip()
            # DuckDuckGo 的 URL 可能是重定向链接
            if "uddg=" in url:
                parsed = urllib.parse.parse_qs(
                    urllib.parse.urlparse(url).query
                )
                url = parsed.get("uddg", [url])[0]

            results.append(
                {"title": clean_title, "snippet": clean_snippet, "url": url}
            )

        return results
