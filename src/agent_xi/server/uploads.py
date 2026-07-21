"""文件上传存储 — P4 多模态上传。

设计：
- 存储路径：<data_dir>/uploads/<session_id>/<file_id>_<原文件名>
- file_id 为 uuid4 hex 前 12 位，前端上传后拿到，随 WS chat 消息上报
- ws_chat 收到 attachments 时通过 resolve_attachment 校验文件确实存在
- 单文件上限 20MB；session_id / file_id 均做白名单校验防路径穿越

安全：
- 文件名仅保留 basename，额外剥离 Windows 保留设备名（nul/con/...）
- 本模块不提供文件下载/静态服务，上传目录不对外暴露
"""

from __future__ import annotations

import logging
import mimetypes
import re
import uuid
from pathlib import Path

from .history_store import is_valid_session_id

logger = logging.getLogger(__name__)

# 单文件大小上限
MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20MB

# file_id 白名单（uuid4 hex 前缀）
_FILE_ID_RE = re.compile(r"^[0-9a-f]{12}$")

# Windows 保留设备名（避免创建出无法操作的文件）
_WINDOWS_RESERVED = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}

# 上传根目录缓存（首次使用时从配置解析）
_ROOT: Path | None = None


def _uploads_root() -> Path:
    """懒加载上传根目录：<data_dir>/uploads。"""
    global _ROOT
    if _ROOT is None:
        from ..config import load_settings

        _ROOT = Path(load_settings().data_dir) / "uploads"
        _ROOT.mkdir(parents=True, exist_ok=True)
    return _ROOT


def _safe_name(filename: str) -> str:
    """剥离路径与 Windows 保留名，返回可安全落盘的文件名。"""
    name = Path(filename.replace("\\", "/")).name.strip()
    name = re.sub(r'[\x00-\x1f<>:"|?*]', "_", name)
    stem = name.split(".")[0].lower()
    if not name or name in (".", "..") or stem in _WINDOWS_RESERVED:
        return "file"
    return name[:120] or "file"


def is_valid_file_id(file_id: str) -> bool:
    """校验 file_id 格式（防路径穿越）。"""
    return bool(_FILE_ID_RE.match(file_id))


def save_upload(
    session_id: str,
    filename: str,
    content: bytes,
    mime: str = "",
) -> dict:
    """保存上传文件，返回 {ok, file_id, name, size, mime, path}。"""
    if not is_valid_session_id(session_id):
        return {"ok": False, "error": "非法的 session_id"}
    if len(content) > MAX_UPLOAD_SIZE:
        return {"ok": False, "error": "文件超过 20MB 限制"}
    if not content:
        return {"ok": False, "error": "空文件"}

    name = _safe_name(filename)
    file_id = uuid.uuid4().hex[:12]
    session_dir = _uploads_root() / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    path = session_dir / f"{file_id}_{name}"
    path.write_bytes(content)

    if not mime:
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"

    logger.info(
        "Upload saved: %s (%d bytes) session=%s", name, len(content), session_id
    )
    return {
        "ok": True,
        "file_id": file_id,
        "name": name,
        "size": len(content),
        "mime": mime,
        "path": str(path.resolve()),
    }


def resolve_attachment(session_id: str, file_id: str) -> dict | None:
    """按 file_id 查找已上传文件，返回 {name, size, mime, path}；不存在返回 None。"""
    if not is_valid_session_id(session_id) or not is_valid_file_id(file_id):
        return None
    session_dir = _uploads_root() / session_id
    if not session_dir.is_dir():
        return None

    matches = sorted(session_dir.glob(f"{file_id}_*"))
    if not matches:
        return None
    path = matches[0]
    name = path.name[len(file_id) + 1 :] or path.name
    return {
        "name": name,
        "size": path.stat().st_size,
        "mime": mimetypes.guess_type(name)[0] or "application/octet-stream",
        "path": str(path.resolve()),
    }
