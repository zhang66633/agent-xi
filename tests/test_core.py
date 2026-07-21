"""冒烟测试 — tokenizer / registry / context 裁剪。"""

from __future__ import annotations

from agent_xi.brain.context import ContextBuilder
from agent_xi.brain.tokenizer import (
    TokenCounter,
    count_message_tokens,
    count_tools_tokens,
)
from agent_xi.llm.types import Message, Role, TextBlock, ToolUseBlock
from agent_xi.tools.registry import ToolRegistry


# ─── tokenizer ─────────────────────────────────────────────


def test_count_text_positive_and_monotonic():
    c = TokenCounter()
    assert c.count_text("") == 0
    short = c.count_text("你好")
    long = c.count_text("你好" * 100)
    assert 0 < short < long


def test_count_message_overhead():
    empty = count_message_tokens(Message(role=Role.USER, content=""))
    assert empty >= 4  # 每条消息固定开销
    with_text = count_message_tokens(Message(role=Role.USER, content="hello world"))
    assert with_text > empty


def test_count_message_content_blocks():
    msg = Message(
        role=Role.ASSISTANT,
        content=[
            TextBlock(text="我来查一下"),
            ToolUseBlock(id="t1", name="get_time", arguments={"tz": "UTC"}),
        ],
    )
    assert count_message_tokens(msg) > 4


def test_count_tools_tokens():
    reg = ToolRegistry()
    from tests.conftest import EchoTool

    reg.register(EchoTool())
    defs = reg.to_definitions()
    assert count_tools_tokens(defs) > 0
    assert count_tools_tokens([]) == 0


# ─── registry ──────────────────────────────────────────────


def test_registry_register_lookup(echo_tool):
    reg = ToolRegistry()
    reg.register(echo_tool)
    assert "echo" in reg
    assert len(reg) == 1
    assert reg.get("echo") is echo_tool
    assert reg.get("nonexistent") is None

    reg.unregister("echo")
    assert "echo" not in reg


def test_registry_to_definitions(echo_tool):
    reg = ToolRegistry()
    reg.register(echo_tool)
    defs = reg.to_definitions()
    assert len(defs) == 1
    d = defs[0]
    assert d.name == "echo"
    schema = d.to_json_schema()
    assert schema["properties"]["text"]["type"] == "string"
    assert schema["required"] == ["text"]


# ─── context 裁剪 ──────────────────────────────────────────


def test_context_keeps_latest_on_tiny_budget():
    """预算极小时，至少保留最后一条消息。"""
    builder = ContextBuilder(
        system_prompt="S" * 500,
        max_context_tokens=100,  # 故意给极小窗口
        reserved_output_tokens=50,
    )
    history = [
        Message(role=Role.USER, content="第一条" + "长" * 200),
        Message(role=Role.ASSISTANT, content="回复" + "长" * 200),
        Message(role=Role.USER, content="最新一条"),
    ]
    req = builder.build_request(history)
    assert len(req.messages) >= 1
    assert req.messages[-1].content == "最新一条"


def test_context_turn_hard_cap():
    """硬上限 max_history_turns * 2 条。"""
    builder = ContextBuilder(max_history_turns=2)
    history = [
        Message(role=Role.USER if i % 2 == 0 else Role.ASSISTANT, content=f"msg{i}")
        for i in range(20)
    ]
    req = builder.build_request(history)
    assert len(req.messages) <= 4
    assert req.messages[-1].content == "msg19"


def test_context_memory_injected_into_system():
    builder = ContextBuilder(system_prompt="base")
    req = builder.build_request(
        [Message(role=Role.USER, content="hi")], memory_context="[记忆] 用户喜欢猫"
    )
    assert "base" in req.system
    assert "用户喜欢猫" in req.system
