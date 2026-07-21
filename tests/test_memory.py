"""冒烟测试 — 记忆系统（语义 SQLite + 情景 LanceDB，全本地无网络）。"""

from __future__ import annotations

import pytest

from agent_xi.memory.episodic import EpisodicMemory
from agent_xi.memory.manager import MemoryManager
from agent_xi.memory.semantic import SemanticMemory

from .conftest import FakeEmbedding, ScriptedLLM


# ─── 语义记忆 ──────────────────────────────────────────────


def test_semantic_store_and_dedupe(tmp_path):
    mem = SemanticMemory(db_path=tmp_path / "semantic.db")
    assert mem.store("我喜欢像素风游戏", category="preference") is True
    # 重复存储 → 返回 False（更新而非新增）
    assert mem.store("我喜欢像素风游戏", category="preference") is False
    assert mem.count == 1
    mem.close()


def test_semantic_query_and_prompt(tmp_path):
    mem = SemanticMemory(db_path=tmp_path / "semantic.db")
    mem.store("我喜欢星露谷物语", category="preference")
    mem.store("我的项目在 D 盘", category="fact")

    hits = mem.query(keyword="星露谷")
    assert len(hits) == 1
    assert "星露谷" in hits[0]["content"]

    prompt = mem.format_for_prompt()
    assert "用户画像" in prompt
    assert "星露谷物语" in prompt
    mem.close()


def test_semantic_rule_capture(tmp_path):
    mem = SemanticMemory(db_path=tmp_path / "semantic.db")
    captures = mem.extract_from_text("我喜欢在深夜写代码，记住我的咖啡是美式")
    categories = {c for _, c in captures}
    assert "preference" in categories
    assert "fact" in categories
    mem.close()


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


async def test_manager_on_user_input_captures(tmp_path):
    llm = ScriptedLLM([])
    mgr = MemoryManager(
        data_dir=tmp_path, embedding_client=FakeEmbedding(), llm_client=llm
    )
    stored = await mgr.on_user_input("我喜欢像素风游戏，我习惯深夜写代码")
    assert any("像素风游戏" in s for s in stored)
    assert any("深夜写代码" in s for s in stored)
    assert mgr.semantic.count >= 2
    mgr.close()


async def test_manager_recall_context_merges(tmp_path):
    llm = ScriptedLLM([])
    mgr = MemoryManager(
        data_dir=tmp_path, embedding_client=FakeEmbedding(), llm_client=llm
    )
    await mgr.remember_episode("一起修复了 CSS 遮罩 bug", summary="修 bug")
    mgr.semantic.store("用户喜欢像素风", category="preference")

    ctx = await mgr.recall_context("CSS 问题")
    assert "相关历史记忆" in ctx
    assert "用户画像" in ctx
    mgr.close()


async def test_manager_deep_extraction(tmp_path):
    """对话结束 → LLM 提取 '类别|内容' 行入库。"""
    llm = ScriptedLLM([[("text", "preference|用户喜欢喝美式咖啡\nfact|用户养了一只猫")]])
    mgr = MemoryManager(
        data_dir=tmp_path, embedding_client=FakeEmbedding(), llm_client=llm
    )
    from agent_xi.llm.types import Message, Role

    history = [
        Message(role=Role.USER, content="你好"),
        Message(role=Role.ASSISTANT, content="你好呀"),
    ]
    extracted = await mgr.on_conversation_end(history)
    assert len(extracted) == 2
    assert mgr.semantic.count == 2
    mgr.close()
