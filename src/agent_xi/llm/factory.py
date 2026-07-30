"""LLM 客户端工厂 — 根据配置创建对应的 client 实例。"""

from __future__ import annotations

from ..config import LLMSettings
from .claude import ClaudeClient
from .ollama import OllamaClient
from .openai_compat import OpenAICompatClient
from .openai_native import OpenAINativeClient


def create_client(
    settings: LLMSettings,
) -> ClaudeClient | OpenAICompatClient | OpenAINativeClient | OllamaClient:
    """根据配置创建 LLM 客户端。

    支持的 provider：
    - "deepseek": OpenAI-compatible 格式（默认）
    - "claude": Claude Messages API 格式
    - "openai": OpenAI 原生 Chat Completions API
    - "ollama": 本地 Ollama 服务

    Raises:
        ValueError: 不支持的 provider 名称。
    """
    provider = settings.provider.lower()

    if provider == "claude":
        return ClaudeClient(
            api_key=settings.api_key,
            model=settings.model,
            base_url=settings.base_url,
            timeout=settings.timeout,
            max_retries=settings.max_retries,
        )

    if provider == "openai":
        return OpenAINativeClient(
            api_key=settings.api_key,
            model=settings.model,
            base_url=settings.base_url or "https://api.openai.com",
            timeout=settings.timeout,
            max_retries=settings.max_retries,
        )

    if provider == "ollama":
        return OllamaClient(
            model=settings.model,
            base_url=settings.base_url or "http://localhost:11434",
            timeout=settings.timeout,
            max_retries=settings.max_retries,
        )

    # 默认：DeepSeek 及其他 OpenAI-compatible providers
    if provider in ("deepseek",):
        return OpenAICompatClient(
            api_key=settings.api_key,
            model=settings.model,
            base_url=settings.base_url,
            timeout=settings.timeout,
            max_retries=settings.max_retries,
            provider_name=provider,
        )

    # 通用 fallback：任何 OpenAI-compatible API
    return OpenAICompatClient(
        api_key=settings.api_key,
        model=settings.model,
        base_url=settings.base_url,
        timeout=settings.timeout,
        max_retries=settings.max_retries,
        provider_name=provider,
    )