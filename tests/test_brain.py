"""冒烟测试 — Brain ReAct 循环（mock LLM，不发真实请求）。"""

from __future__ import annotations

import pytest

from agent_xi.brain.context import ContextBuilder
from agent_xi.brain.engine import Brain
from agent_xi.llm.types import Role, StreamEventType
from agent_xi.tools.registry import ToolRegistry

from .conftest import ScriptedLLM

pytestmark = pytest.mark.asyncio


def _make_brain(llm, registry=None, confirm=None):
    return Brain(
        client=llm,
        context_builder=ContextBuilder(system_prompt="你是 Xi"),
        memory=None,
        tool_registry=registry,
        confirm_callback=confirm,
    )


async def _collect(brain, text):
    events = []
    async for ev in brain.chat(text):
        events.append(ev)
    return events


async def test_plain_text_reply():
    llm = ScriptedLLM([[("text", "你好"), ("text", "，指挥官")]])
    brain = _make_brain(llm)

    events = await _collect(brain, "在吗")
    types = [e.type for e in events]
    assert StreamEventType.TEXT_DELTA in types
    assert StreamEventType.DONE in types

    # 历史：user + assistant
    assert brain.turn_count == 1
    assert brain.history[-1].role == Role.ASSISTANT
    assert brain.history[-1].text == "你好，指挥官"


async def test_react_tool_loop(echo_tool):
    """LLM 先调工具，看到结果后给出最终回复。"""
    llm = ScriptedLLM(
        [
            [("tool", "echo", {"text": "ping"}), ("text", "让我回显一下")],
            [("text", "回显结果是 ping")],
        ]
    )
    reg = ToolRegistry()
    reg.register(echo_tool)
    brain = _make_brain(llm, registry=reg)

    events = await _collect(brain, "帮我回显 ping")
    types = [e.type for e in events]

    assert StreamEventType.TOOL_USE_START in types
    assert StreamEventType.TOOL_EXECUTING in types
    assert StreamEventType.TOOL_RESULT in types

    # 工具结果事件带预览
    result_ev = next(e for e in events if e.type == StreamEventType.TOOL_RESULT)
    assert "echo: ping" in result_ev.text

    # 两次 LLM 调用（工具前 + 工具后）
    assert len(llm.requests) == 2
    # 最终回复入库
    assert brain.history[-1].text == "回显结果是 ping"


async def test_sensitive_tool_denied(secret_tool):
    """敏感工具被用户拒绝 → TOOL_CONFIRM_DENIED + 错误结果回传 LLM。"""
    llm = ScriptedLLM(
        [
            [("tool", "secret", {})],
            [("text", "好的，已取消")],
        ]
    )
    reg = ToolRegistry()
    reg.register(secret_tool)

    confirm_calls = []

    async def deny(name, args):
        confirm_calls.append(name)
        return False

    brain = _make_brain(llm, registry=reg, confirm=deny)
    events = await _collect(brain, "执行敏感操作")
    types = [e.type for e in events]

    assert confirm_calls == ["secret"]
    assert StreamEventType.TOOL_CONFIRM_DENIED in types
    assert StreamEventType.TOOL_RESULT not in types
    # LLM 看到了拒绝结果并回复
    assert brain.history[-1].text == "好的，已取消"


async def test_sensitive_tool_allowed(secret_tool):
    """敏感工具确认通过 → 正常执行。"""
    llm = ScriptedLLM(
        [
            [("tool", "secret", {})],
            [("text", "执行完毕")],
        ]
    )
    reg = ToolRegistry()
    reg.register(secret_tool)

    async def allow(name, args):
        return True

    brain = _make_brain(llm, registry=reg, confirm=allow)
    events = await _collect(brain, "执行敏感操作")
    types = [e.type for e in events]

    assert StreamEventType.TOOL_RESULT in types
    assert StreamEventType.TOOL_CONFIRM_DENIED not in types


async def test_unknown_tool_error():
    """LLM 调用未注册工具 → 错误结果回传，不崩溃。"""
    llm = ScriptedLLM(
        [
            [("tool", "ghost", {})],
            [("text", "抱歉，没有这个工具")],
        ]
    )
    brain = _make_brain(llm, registry=ToolRegistry())
    events = await _collect(brain, "调用幽灵工具")

    result_ev = next(e for e in events if e.type == StreamEventType.TOOL_RESULT)
    assert "未找到工具" in result_ev.text
    assert brain.history[-1].text == "抱歉，没有这个工具"


async def test_max_react_iterations_guard(echo_tool):
    """LLM 无限调工具 → 达到上限后安全退出。"""
    # 6 个脚本全在调工具（上限 5 次迭代）
    scripts = [[("tool", "echo", {"text": str(i)})] for i in range(6)]
    llm = ScriptedLLM(scripts)
    reg = ToolRegistry()
    reg.register(echo_tool)
    brain = _make_brain(llm, registry=reg)

    events = await _collect(brain, "循环调用")
    # 不应无限执行：LLM 调用次数 <= 5
    assert len(llm.requests) <= 5
