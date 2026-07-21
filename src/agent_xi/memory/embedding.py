"""Embedding 客户端 — 调用 qwen3-embedding-8b 获取文本向量。

使用 OpenAI 兼容的 /v1/embeddings 接口。
"""

from __future__ import annotations

import httpx


class EmbeddingClient:
    """轻量 embedding 客户端，httpx 直调。"""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://token.nau.edu.cn",
        model: str = "qwen3-embedding-8b",
        timeout: float = 30.0,
    ) -> None:
        self._model = model
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """获取文本向量列表。

        Args:
            texts: 待编码的文本列表（支持批量）。

        Returns:
            与 texts 等长的向量列表。

        Raises:
            httpx.HTTPStatusError: API 返回非 200。
        """
        response = await self._client.post(
            "/v1/embeddings",
            json={"model": self._model, "input": texts},
        )
        response.raise_for_status()
        data = response.json()
        # 按 index 排序确保顺序正确
        items = sorted(data["data"], key=lambda x: x["index"])
        return [item["embedding"] for item in items]

    async def embed_one(self, text: str) -> list[float]:
        """获取单条文本的向量。"""
        results = await self.embed([text])
        return results[0]

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> EmbeddingClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()
