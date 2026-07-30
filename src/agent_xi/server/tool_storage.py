"""工具结果持久化 — 对标 cc-haha toolResultStorage。

大结果（>10KB）存到磁盘，返回预览给 LLM。
路径：.data/tool_results/<session_id>/<tool_name>_<timestamp>.txt
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path


_PREVIEW_SIZE = 3_000  # 返回给 LLM 的预览字符数
_STORE_THRESHOLD = 10_000  # 超过此值才存盘


def store_tool_result(
    data_dir: Path,
    session_id: str,
    tool_name: str,
    output: str,
) -> str | None:
    """存储大工具结果到磁盘。返回嵌入 LLM 上下文的预览文本，或 None 表示不需要存储。"""
    if len(output) <= _STORE_THRESHOLD:
        return None

    result_dir = data_dir / "tool_results" / session_id
    result_dir.mkdir(parents=True, exist_ok=True)

    ts = int(time.time())
    file_id = uuid.uuid4().hex[:8]
    filename = f"{tool_name}_{ts}_{file_id}.txt"
    file_path = result_dir / filename

    file_path.write_text(output, encoding="utf-8", errors="replace")

    preview = (
        output[:_PREVIEW_SIZE // 2]
        + f"\n\n... [共 {len(output)} 字符，已保存到 {file_path}] ...\n\n"
        + output[-(_PREVIEW_SIZE // 4):]
    )
    return preview