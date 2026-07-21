"""配置管理 — Pydantic Settings + YAML。

优先级：环境变量 > .env > config/default.yaml > 代码默认值
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    """LLM 相关配置。"""

    model_config = SettingsConfigDict(
        env_prefix="AGENT_XI_LLM_",
        extra="ignore",
    )

    provider: str = "deepseek"
    model: str = "deepseek-chat"
    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout: float = 120.0
    max_retries: int = 3


class EmbeddingSettings(BaseSettings):
    """Embedding API 配置。"""

    model_config = SettingsConfigDict(
        env_prefix="EMBEDDING_",
        extra="ignore",
    )

    api_key: str = ""
    base_url: str = "https://token.nau.edu.cn"
    model: str = "qwen3-embedding-8b"


class AppSettings(BaseSettings):
    """应用级配置。"""

    model_config = SettingsConfigDict(
        env_prefix="AGENT_XI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm: LLMSettings = Field(default_factory=LLMSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    system_prompt: str = "你是 Xi，一个友好、诚实的 AI 伙伴。"
    max_history_turns: int = 50
    max_context_tokens: int = 128_000
    reserved_output_tokens: int = 4096
    data_dir: str = ".data"
    debug: bool = False


def _load_yaml_config(config_path: Path) -> dict[str, Any]:
    """从 YAML 文件加载配置字典。"""
    if not config_path.exists():
        return {}
    with config_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def _resolve_api_key(provider: str) -> str:
    """根据 provider 从环境变量解析 API Key。

    支持的映射：
    - deepseek → DEEPSEEK_API_KEY
    - claude → ANTHROPIC_API_KEY
    """
    import os

    key_map: dict[str, str] = {
        "deepseek": "DEEPSEEK_API_KEY",
        "claude": "ANTHROPIC_API_KEY",
    }
    env_var = key_map.get(provider, "")
    return os.environ.get(env_var, "")


def load_settings(config_path: Path | None = None) -> AppSettings:
    """加载配置，合并 YAML 默认值和环境变量。

    合并优先级（从低到高）：
    1. 代码默认值
    2. config/default.yaml
    3. .env 文件
    4. 系统环境变量
    """
    from dotenv import load_dotenv

    # 先加载 .env 到 os.environ，使 DEEPSEEK_API_KEY 等变量可被 _resolve_api_key 读取
    load_dotenv(override=False)

    if config_path is None:
        config_path = Path(__file__).parent.parent.parent / "config" / "default.yaml"

    yaml_data = _load_yaml_config(config_path)

    # 从 YAML 提取各层配置作为默认值
    llm_yaml = yaml_data.get("llm", {})
    app_yaml = yaml_data.get("app", {})

    # 构建 LLMSettings：YAML 值作为初始值，环境变量覆盖
    llm_settings = LLMSettings(**llm_yaml)

    # 如果 YAML/env 没有显式设置 api_key，尝试从 provider 对应的环境变量获取
    if not llm_settings.api_key:
        llm_settings.api_key = _resolve_api_key(llm_settings.provider)

    # 构建 EmbeddingSettings
    embedding_settings = EmbeddingSettings()

    # 构建 AppSettings
    settings = AppSettings(
        llm=llm_settings,
        embedding=embedding_settings,
        system_prompt=app_yaml.get(
            "system_prompt", AppSettings.model_fields["system_prompt"].default
        ),
        max_history_turns=app_yaml.get("max_history_turns", 50),
        max_context_tokens=app_yaml.get("max_context_tokens", 128_000),
        reserved_output_tokens=app_yaml.get("reserved_output_tokens", 4096),
        data_dir=app_yaml.get("data_dir", ".data"),
        debug=app_yaml.get("debug", False),
    )

    return settings
