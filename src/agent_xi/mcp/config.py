"""MCP 配置加载。

从 config/mcp.yaml 读取 MCP Server 配置列表。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_DEFAULT_CONFIG_PATH = (
    Path(__file__).parent.parent.parent.parent / "config" / "mcp.yaml"
)


@dataclass(slots=True)
class MCPServerConfig:
    """单个 MCP Server 的配置。"""

    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    enabled: bool = True


def _expand_env_vars(value: str) -> str:
    """展开 ${VAR} 形式的环境变量引用。"""
    def _replace(match: re.Match) -> str:
        var_name = match.group(1)
        return os.environ.get(var_name, "")

    return re.sub(r"\$\{(\w+)\}", _replace, value)


def load_mcp_config(
    config_path: Path | None = None,
) -> list[MCPServerConfig]:
    """加载 MCP 配置文件。

    Args:
        config_path: 配置文件路径，默认为 config/mcp.yaml。

    Returns:
        MCP Server 配置列表。
    """
    path = config_path or _DEFAULT_CONFIG_PATH

    if not path.exists():
        return []

    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        return []

    servers: list[MCPServerConfig] = []
    for item in data.get("servers") or []:
        if not isinstance(item, dict):
            continue

        # 展开环境变量
        env: dict[str, str] = {}
        for k, v in item.get("env", {}).items():
            env[k] = _expand_env_vars(str(v)) if isinstance(v, str) else str(v)

        servers.append(
            MCPServerConfig(
                name=item.get("name", "unnamed"),
                command=item.get("command", ""),
                args=item.get("args", []),
                env=env,
                enabled=item.get("enabled", True),
            )
        )

    return servers
