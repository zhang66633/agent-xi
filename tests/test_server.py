"""冒烟测试 — 会话持久化 + 市场安装。"""

from __future__ import annotations

import pytest

from agent_xi.llm.types import Message, Role, TextBlock, ToolResultBlock, ToolUseBlock
from agent_xi.server.history_store import SessionStore, is_valid_session_id
from agent_xi.server.market import install_skill
from agent_xi.skills.store import SkillStore

from .conftest import FakeEmbedding

_VALID_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"


# ─── session_id 校验 ───────────────────────────────────────


def test_session_id_validation():
    assert is_valid_session_id(_VALID_ID)
    assert is_valid_session_id("abc123_-XYZ")
    assert not is_valid_session_id("../etc/passwd")
    assert not is_valid_session_id("a/b")
    assert not is_valid_session_id("short")  # < 8 字符
    assert not is_valid_session_id("")


# ─── SessionStore 往返 ─────────────────────────────────────


def test_store_roundtrip(tmp_path):
    store = SessionStore(tmp_path)
    hist = [
        Message(role=Role.USER, content="你好"),
        Message(
            role=Role.ASSISTANT,
            content=[
                TextBlock(text="查一下"),
                ToolUseBlock(id="t1", name="echo", arguments={"text": "hi"}),
            ],
        ),
        Message(role=Role.TOOL, content=[ToolResultBlock(tool_use_id="t1", content="ok")]),
    ]
    store.save_history(_VALID_ID, hist)
    assert store.exists(_VALID_ID)
    assert store.turn_count(_VALID_ID) == 1

    loaded = store.load_history(_VALID_ID)
    assert len(loaded) == 3
    assert loaded[0].text == "你好"
    assert loaded[1].tool_use_blocks[0].name == "echo"
    assert loaded[2].content[0].content == "ok"


def test_store_missing_and_corrupt(tmp_path):
    store = SessionStore(tmp_path)
    assert store.load_history(_VALID_ID) == []
    assert store.turn_count(_VALID_ID) == 0

    # 损坏文件 → 安全返回空
    (tmp_path / "sessions" / f"{_VALID_ID}.json").write_text("{broken", encoding="utf-8")
    assert store.load_history(_VALID_ID) == []


def test_store_rejects_traversal(tmp_path):
    store = SessionStore(tmp_path)
    with pytest.raises(ValueError):
        store.load_history("../escape")


# ─── 市场：技能安装 ────────────────────────────────────────


async def test_install_skill_success(tmp_path):
    store = SkillStore(data_dir=tmp_path, embedding_client=FakeEmbedding())
    result = await install_skill("summarize", store)
    assert result["ok"] is True

    saved = store.get("summarize")
    assert saved is not None
    assert saved.name == "文档摘要"
    assert "摘要" in saved.trigger_keywords
    store.close()


async def test_install_skill_duplicate(tmp_path):
    store = SkillStore(data_dir=tmp_path, embedding_client=FakeEmbedding())
    first = await install_skill("translate", store)
    assert first["ok"] is True
    second = await install_skill("translate", store)
    assert second["ok"] is False
    assert "已安装" in second["error"]
    store.close()


async def test_install_skill_errors(tmp_path):
    store = SkillStore(data_dir=tmp_path, embedding_client=FakeEmbedding())
    missing = await install_skill("no-such-skill", store)
    assert missing["ok"] is False

    no_store = await install_skill("summarize", None)
    assert no_store["ok"] is False
    store.close()
