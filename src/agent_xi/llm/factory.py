"""LLM 客户端工厂 — 根据配置创建对应的 client 实例。"""

from __future__ import annotations

from ..config import LLMSettings
from .claude import ClaudeClient
from .openai_compat import OpenAICompatClient


def create_client(settings: LLMSettings) -> ClaudeClient | OpenAICompatClient:
    """根据配置创建 LLM 客户端。

    支持的 provider：
    - "deepseek": OpenAI-compatible 格式
    - "claude": Claude Messages API 格式
    - "openai": OpenAI 原生（也走 OpenAI-compatible）

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

    if provider in ("deepseek", "openai"):
        return OpenAICompatClient(
            api_key=settings.api_key,
            model=settings.model,
            base_url=settings.base_url,
            timeout=settings.timeout,
            max_retries=settings.max_retries,
            provider_name=provider,
        )

    msg = f"不支持的 LLM provider: {provider!r}。支持: deepseek, claude, openai"
    raise ValueError(msg)
