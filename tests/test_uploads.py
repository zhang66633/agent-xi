"""P4 上传存储 + 附件上下文注入测试。"""

from __future__ import annotations

import pytest

from agent_xi.server import uploads
from agent_xi.server.uploads import (
    MAX_UPLOAD_SIZE,
    is_valid_file_id,
    resolve_attachment,
    save_upload,
)
from agent_xi.server.ws_chat import _build_attachment_context

_VALID_SESSION = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"


@pytest.fixture
def upload_root(tmp_path, monkeypatch):
    """把上传根目录重定向到 tmp_path。"""
    monkeypatch.setattr(uploads, "_ROOT", tmp_path)
    return tmp_path


# ─── file_id 校验 ──────────────────────────────────────────


def test_file_id_validation():
    assert is_valid_file_id("a1b2c3d4e5f6")
    assert not is_valid_file_id("../escape")
    assert not is_valid_file_id("A1B2C3D4E5F6")  # 大写 hex 不允许
    assert not is_valid_file_id("short")
    assert not is_valid_file_id("")


# ─── 存储 / 解析往返 ───────────────────────────────────────


def test_save_and_resolve(upload_root):
    result = save_upload(_VALID_SESSION, "report.txt", b"hello xi", "text/plain")
    assert result["ok"] is True
    assert result["name"] == "report.txt"
    assert result["size"] == 8
    assert is_valid_file_id(result["file_id"])

    # 落盘位置：<root>/<session>/<file_id>_<name>
    expected = upload_root / _VALID_SESSION / f"{result['file_id']}_report.txt"
    assert expected.exists()
    assert expected.read_bytes() == b"hello xi"

    info = resolve_attachment(_VALID_SESSION, result["file_id"])
    assert info is not None
    assert info["name"] == "report.txt"
    assert info["size"] == 8
    assert info["path"] == str(expected.resolve())


def test_save_rejects(upload_root):
    # 非法 session_id（路径穿越）
    bad = save_upload("../escape", "a.txt", b"x")
    assert bad["ok"] is False

    # 空文件
    empty = save_upload(_VALID_SESSION, "a.txt", b"")
    assert empty["ok"] is False

    # 超过 20MB
    too_big = save_upload(_VALID_SESSION, "big.bin", b"\0" * (MAX_UPLOAD_SIZE + 1))
    assert too_big["ok"] is False
    assert "20MB" in too_big["error"]


def test_save_sanitizes_filename(upload_root):
    # 路径穿越 → 仅保留 basename
    r1 = save_upload(_VALID_SESSION, "../../evil.txt", b"x")
    assert r1["ok"] is True
    assert r1["name"] == "evil.txt"

    # Windows 保留设备名 → 退化为 file
    r2 = save_upload(_VALID_SESSION, "nul.txt", b"x")
    assert r2["ok"] is True
    assert r2["name"] == "file"

    # 控制字符 / 非法字符替换
    r3 = save_upload(_VALID_SESSION, 'a<b>c|d?".txt', b"x")
    assert r3["ok"] is True
    assert "<" not in r3["name"] and "?" not in r3["name"]


def test_resolve_missing(upload_root):
    assert resolve_attachment(_VALID_SESSION, "a1b2c3d4e5f6") is None
    assert resolve_attachment(_VALID_SESSION, "BAD_ID") is None
    assert resolve_attachment("short", "a1b2c3d4e5f6") is None


# ─── ws_chat 附件上下文注入 ────────────────────────────────


def test_attachment_context(upload_root):
    img = save_upload(_VALID_SESSION, "cat.png", b"\x89PNG", "image/png")
    doc = save_upload(_VALID_SESSION, "notes.md", b"# hi", "text/markdown")

    ctx = _build_attachment_context(
        _VALID_SESSION,
        [
            {"file_id": img["file_id"], "name": "cat.png", "mime": "image/png"},
            {"file_id": doc["file_id"], "name": "notes.md", "mime": "text/markdown"},
            {"file_id": "ffffffffffff", "name": "ghost.txt", "mime": "text/plain"},
        ],
    )

    lines = ctx.splitlines()
    assert len(lines) == 2  # 不存在的附件被跳过
    assert "图片" in lines[0] and "cat.png" in lines[0]
    assert "暂不支持图片理解" in lines[0]
    assert "read_file" in lines[1] and "notes.md" in lines[1]
    # 注入文本必须包含真实磁盘路径
    assert str(upload_root) in lines[0]


def test_attachment_context_empty(upload_root):
    assert _build_attachment_context(_VALID_SESSION, []) == ""
    assert _build_attachment_context(_VALID_SESSION, ["not-a-dict"]) == ""
