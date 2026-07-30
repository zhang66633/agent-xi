"""OpenAI 原生 Chat Completions API 客户端。

与 OpenAICompatClient 共享相同的 API 格式（OpenAI-compatible），
但使用专门的 provider_name 和默认 URL。

用于 ChatGPT、GPT-4 等 OpenAI 官方模型。
"""

from __future__ import annotations

from .openai_compat import OpenAICompatClient


class OpenAINativeClient(OpenAICompatClient):
    """OpenAI 原生 API 客户端。

    继承 OpenAICompatClient，只改变默认 provider_name。
    OpenAI 官方模型的 Chat Completions API 与 DeepSeek 等兼容 API 格式完全一致。
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        base_url: str = "https://api.openai.com",
        timeout: float = 120.0,
        max_retries: int = 3,
    ) -> None:
        super().__init__(
            api_key=api_key,
            model=model,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            provider_name="openai",
        )