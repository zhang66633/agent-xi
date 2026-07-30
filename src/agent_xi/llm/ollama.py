"""Ollama 本地模型客户端。

通过 Ollama 的 OpenAI-compatible API 接入本地模型。

Ollama 默认端点: http://localhost:11434/v1
Ollama 虽然兼容 OpenAI API 但有一些差异：
- 不需要 api_key（本地服务）
- 默认模型列表由已 pull 的模型决定
"""

from __future__ import annotations

from .openai_compat import OpenAICompatClient


class OllamaClient(OpenAICompatClient):
    """Ollama 本地模型客户端。

    继承 OpenAICompatClient，使用 Ollama 的 OpenAI-compatible 端点。
    Ollama v0.5+ 内置 /v1/chat/completions 兼容接口，无需额外配置。
    """

    def __init__(
        self,
        model: str = "qwen2.5:7b",
        base_url: str = "http://localhost:11434",
        api_key: str = "ollama",  # Ollama 不需要真实 key，但需要占位
        timeout: float = 300.0,  # 本地模型推理较慢
        max_retries: int = 2,
    ) -> None:
        super().__init__(
            api_key=api_key,
            model=model,
            base_url=f"{base_url.rstrip('/')}/v1",
            timeout=timeout,
            max_retries=max_retries,
            provider_name="ollama",
        )