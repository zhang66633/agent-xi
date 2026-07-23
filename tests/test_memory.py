"""冒烟测试 — 记忆系统（整合文档范式 + 情景 LanceDB，全本地无网络）。"""

from __future__ import annotations

import pytest

from agent_xi.memory.episodic import EpisodicMemory
from agent_xi.memory.manager import MemoryManager

from .conftest import FakeEmbedding, ScriptedLLM


# ─── 情景记忆 ──────────────────────────────────────────────


async def test_episodic_remember_recall(tmp_path):
    mem = EpisodicMemory(
        db_path=tmp_path / "episodic", embedding_client=FakeEmbedding()
    )
    await mem.remember("今天调试了 WebSocket 重连逻辑", summary="调试 WS", tags=["dev"])
    await mem.remember("中午吃了拉面", summary="午餐", tags=["life"])
    assert mem.count == 2

    results = await mem.recall("WebSocket 断线怎么办", top_k=1)
    assert len(results) == 1
    assert "WS" in results[0]["summary"] or "WebSocket" in results[0]["content"]


# ─── MemoryManager 集成 ────────────────────────────────────


async def test_manager_on_user_input_returns_empty(tmp_path):
    """v2: on_user_input 不再做规则快捕，返回空列表。"""
    llm = ScriptedLLM([])
    mgr = MemoryManager(
        data_dir=tmp_path, embedding_client=FakeEmbedding(), llm_client=llm,
        config_dir=tmp_path / "config",
    )
    (tmp_path / "config").mkdir(exist_ok=True)
    (tmp_path / "config" / "service.md").write_text("# 我为谁服务\n\n（尚未了解用户）", encoding="utf-8")
    stored = await mgr.on_user_input("我喜欢像素风游戏，我习惯深夜写代码")
    assert stored == []
    mgr.close()


async def test_manager_recall_context_episodic_only(tmp_path):
    """v2: recall_context 只返回情景记忆，不再注入语义 facts。"""
    llm = ScriptedLLM([])
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    (config_dir / "service.md").write_text("# 我为谁服务\n\n（尚未了解用户）", encoding="utf-8")

    mgr = MemoryManager(
        data_dir=tmp_path, embedding_client=FakeEmbedding(), llm_client=llm,
        config_dir=config_dir,
    )
    await mgr.remember_episode("一起修复了 CSS 遮罩 bug", summary="修 bug")

    ctx = await mgr.recall_context("CSS 问题")
    assert "相关历史记忆" in ctx
    assert "修 bug" in ctx
    mgr.close()


async def test_manager_recall_context_empty(tmp_path):
    """无情景记忆时返回空串。"""
    llm = ScriptedLLM([])
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    (config_dir / "service.md").write_text("# 我为谁服务\n\n（尚未了解用户）", encoding="utf-8")

    mgr = MemoryManager(
        data_dir=tmp_path, embedding_client=FakeEmbedding(), llm_client=llm,
        config_dir=config_dir,
    )
    ctx = await mgr.recall_context("随便问点什么")
    assert ctx == ""
    mgr.close()


async def test_manager_rewrite_service(tmp_path):
    """对话结束 → LLM 整体重写 service.md。"""
    new_profile = "# 我为谁服务\n\n用户是开发者，主力 Python，喜欢简洁回答。"
    llm = ScriptedLLM([
        [("text", new_profile)],  # _rewrite_service 调用
        [("text", "无")],         # _suggest_evolution 调用
    ])
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    (config_dir / "service.md").write_text("# 我为谁服务\n\n（尚未了解用户）", encoding="utf-8")
    (config_dir / "identity.md").write_text("# 我是谁\n\nXi", encoding="utf-8")
    (config_dir / "personality.md").write_text("# 行为准则\n\n简洁", encoding="utf-8")

    mgr = MemoryManager(
        data_dir=tmp_path, embedding_client=FakeEmbedding(), llm_client=llm,
        config_dir=config_dir,
    )

    from agent_xi.llm.types import Message, Role

    history = [
        Message(role=Role.USER, content="帮我写个快排"),
        Message(role=Role.ASSISTANT, content="好的，这是快排实现..."),
    ]
    changes = await mgr.on_conversation_end(history)

    # service.md 应该被更新
    updated = (config_dir / "service.md").read_text(encoding="utf-8")
    assert "开发者" in updated
    assert "Python" in updated
    assert "更新了对你的了解" in changes

    # 应该有快照
    snapshots = list((tmp_path / "persona_history").glob("service.md.*.bak"))
    assert len(snapshots) == 1
    mgr.close()


async def test_manager_no_change_no_snapshot(tmp_path):
    """对话无新认知 → service.md 不变 → 无快照。"""
    original = "# 我为谁服务\n\n用户是开发者。"
    llm = ScriptedLLM([
        [("text", original)],  # 返回相同内容
        [("text", "无")],
    ])
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    (config_dir / "service.md").write_text(original, encoding="utf-8")
    (config_dir / "identity.md").write_text("# 我是谁", encoding="utf-8")
    (config_dir / "personality.md").write_text("# 行为准则", encoding="utf-8")

    mgr = MemoryManager(
        data_dir=tmp_path, embedding_client=FakeEmbedding(), llm_client=llm,
        config_dir=config_dir,
    )

    from agent_xi.llm.types import Message, Role

    history = [
        Message(role=Role.USER, content="你好"),
        Message(role=Role.ASSISTANT, content="你好呀"),
    ]
    changes = await mgr.on_conversation_end(history)
    assert changes == []

    snapshots = list((tmp_path / "persona_history").glob("*.bak"))
    assert len(snapshots) == 0
    mgr.close()


def test_get_profile_summary(tmp_path):
    """get_profile_summary 正确返回/隐藏内容。"""
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    llm = ScriptedLLM([])

    # 占位符 → 空
    (config_dir / "service.md").write_text("# 我为谁服务\n\n（尚未了解用户，等待第一次对话。）", encoding="utf-8")
    mgr = MemoryManager(
        data_dir=tmp_path, embedding_client=FakeEmbedding(), llm_client=llm,
        config_dir=config_dir,
    )
    assert mgr.get_profile_summary() == ""

    # 有内容 → 返回去掉标题的正文
    (config_dir / "service.md").write_text("# 我为谁服务\n\n用户是开发者，喜欢简洁。", encoding="utf-8")
    assert "开发者" in mgr.get_profile_summary()
    mgr.close()
