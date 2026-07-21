"""设置 API — API Key 的 .env 读写逻辑。

设计要点：
- 只允许白名单内的环境变量被写入（防任意文件内容注入）
- 行级编辑 .env：保留注释和其他配置行，替换或追加目标行
- 写入后需重启后端才生效（不做热重载，前端提示用户）
- 展示一律 masked，接口永不回传明文
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_ENV_PATH = Path(__file__).parent.parent.parent.parent / ".env"

# 白名单：var → 展示信息
KEY_REGISTRY: list[dict] = [
    {
        "var": "DEEPSEEK_API_KEY",
        "name": "DeepSeek",
        "desc": "DeepSeek 对话模型（当前主用）",
    },
    {
        "var": "ANTHROPIC_API_KEY",
        "name": "Anthropic Claude",
        "desc": "Claude 模型（切换 provider 时用）",
    },
    {
        "var": "EMBEDDING_API_KEY",
        "name": "Embedding",
        "desc": "记忆向量化服务",
    },
]

_ALLOWED_VARS = {e["var"] for e in KEY_REGISTRY}


def _mask(value: str) -> str:
    """脱敏：前 3 位 + **** + 后 4 位；太短则全星号。"""
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return f"{value[:3]}****{value[-4:]}"


def _read_env_lines() -> list[str]:
    if not _ENV_PATH.exists():
        return []
    with open(_ENV_PATH, encoding="utf-8") as f:
        return f.read().splitlines()


def _env_file_value(var: str) -> str:
    """从 .env 文件读取某变量的值（忽略注释行）。"""
    prefix = f"{var}="
    for line in _read_env_lines():
        stripped = line.strip()
        if stripped.startswith("#") or not stripped.startswith(prefix):
            continue
        return stripped[len(prefix):].strip().strip('"').strip("'")
    return ""


def list_keys() -> list[dict]:
    """返回各 key 的 masked 状态。

    取值优先级：.env 文件 > 系统环境变量。
    .env 优先是因为它代表"下次启动实际加载的值"，
    保存新 key 后无需重启即可看到正确的 masked 展示。
    """
    result = []
    for entry in KEY_REGISTRY:
        var = entry["var"]
        value = _env_file_value(var) or os.environ.get(var, "")
        configured = bool(value)
        result.append({
            "var": var,
            "name": entry["name"],
            "desc": entry["desc"],
            "configured": configured,
            "masked": _mask(value) if configured else "",
        })
    return result


def save_key(var: str, key: str) -> dict:
    """将 key 写入 .env（行级替换/追加，保留注释）。"""
    if var not in _ALLOWED_VARS:
        return {"ok": False, "error": f"不允许的配置项: {var}"}
    key = key.strip()
    if not key:
        return {"ok": False, "error": "Key 不能为空"}

    lines = _read_env_lines()
    prefix = f"{var}="
    new_line = f"{var}={key}"

    replaced = False
    for i, line in enumerate(lines):
        if line.strip().startswith(prefix):
            lines[i] = new_line
            replaced = True
            break
    if not replaced:
        if lines and lines[-1].strip():
            lines.append("")  # 与已有内容隔一空行
        lines.append(new_line)

    try:
        with open(_ENV_PATH, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except OSError as e:
        logger.error("save key failed: %s", e)
        return {"ok": False, "error": f"写入 .env 失败: {e}"}

    name = next(e["name"] for e in KEY_REGISTRY if e["var"] == var)
    logger.info("Key saved: %s", var)  # 只记变量名，不记值
    return {"ok": True, "message": f"{name} 已保存，重启后端后生效"}
