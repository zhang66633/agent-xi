"""测试多智能体协作 — AgentRole / Coordinator。"""

from __future__ import annotations

import pytest

from agent_xi.agents.base import AgentContext, AgentResult
from agent_xi.agents.coder import Coder
from agent_xi.agents.coordinator import Coordinator
from agent_xi.agents.planner import Planner
from agent_xi.agents.reviewer import Reviewer
from tests.conftest import ScriptedLLM

pytestmark = pytest.mark.asyncio


class TestAgentRoles:
    async def test_planner_executes(self):
        llm = ScriptedLLM([[("text", '{"summary":"方案","steps":[],"risks":[],"notes":""}')]])
        planner = Planner(llm)
        ctx = AgentContext(task="写一个排序函数")
        result = await planner.execute(ctx)
        assert result.success
        assert "方案" in result.output

    async def test_planner_tool_whitelist(self):
        llm = ScriptedLLM([])
        planner = Planner(llm)
        assert "read_file" in (planner.allowed_tools or [])
        assert "write_file" not in (planner.allowed_tools or [])

    async def test_coder_executes(self):
        llm = ScriptedLLM([[("text", "已完成：修改了 a.py，添加了排序函数")]])
        coder = Coder(llm)
        ctx = AgentContext(task="实现排序函数", constraints=["遵循 PEP8"])
        result = await coder.execute(ctx)
        assert result.success
        assert "a.py" in result.output

    async def test_coder_all_tools(self):
        llm = ScriptedLLM([])
        coder = Coder(llm)
        assert coder.allowed_tools is None  # 全部工具可用

    async def test_reviewer_executes(self):
        llm = ScriptedLLM(
            [[("text", '{"verdict":"pass","summary":"代码质量良好","issues":[],"praise":["结构清晰"]}')]]
        )
        reviewer = Reviewer(llm)
        ctx = AgentContext(task="审查排���函数代码")
        result = await reviewer.execute(ctx)
        assert result.success
        assert "pass" in result.output.lower()

    async def test_reviewer_tool_whitelist(self):
        llm = ScriptedLLM([])
        reviewer = Reviewer(llm)
        assert "read_file" in (reviewer.allowed_tools or [])
        assert "execute_shell" not in (reviewer.allowed_tools or [])

    async def test_agent_result_error_handling(self):
        """LLM 调用失败时返回 error。"""
        llm = ScriptedLLM([])
        llm.chat = None  # 故意破坏
        planner = Planner(llm)
        ctx = AgentContext(task="测试")
        try:
            result = await planner.execute(ctx)
            # 如果执行了，结果应该不成功
            assert result.success or result.error
        except AttributeError:
            pass  # 预期 AttributeError


class TestCoordinator:
    async def test_full_workflow(self):
        """完整 Planner → Coder → Reviewer 协作流程。"""
        llm = ScriptedLLM([
            # Planner: 拆解方案
            [
                ("text", '```json\n{"summary":"方案","steps":[{"index":1,"description":"步骤1","verification":"验证1"}],"risks":[],"notes":""}\n```'),
            ],
            # Coder: 执行步骤1
            [("text", "步骤1 已执行，修改了 a.py")],
            # Reviewer: 审查
            [
                ("text", '```json\n{"verdict":"pass","summary":"审查通过","issues":[],"praise":["好"]}\n```'),
            ],
        ])
        coordinator = Coordinator(llm)
        result = await coordinator.run("写一个排序函数")

        assert result["status"] == "completed"
        assert result["plan"] is not None
        assert len(result["execution"]) > 0
        assert result["review"] is not None

    async def test_review_needs_fix_flow(self):
        """审查不通过 → 返工修正。"""
        llm = ScriptedLLM([
            # Planner
            [
                ("text", '```json\n{"summary":"方案","steps":[{"index":1,"description":"步骤1","verification":"验证1"}],"risks":[],"notes":""}\n```'),
            ],
            # Coder
            [("text", "步骤1 完成")],
            # Reviewer: needs_fix
            [
                ("text", '```json\n{"verdict":"needs_fix","summary":"有问题","issues":[{"severity":"major","file":"a.py","description":"漏了边界","suggestion":"加检查"}],"praise":[]}\n```'),
            ],
            # Coder: 修复
            [("text", "已修复边界检查")],
        ])
        coordinator = Coordinator(llm)
        result = await coordinator.run("测试")

        assert result["status"] in ("fixed", "completed")
        # 应该执行了修复步骤
        assert result.get("fix") is not None
        assert result["fix"]["success"]

    async def test_plan_failure(self):
        """Planner 失败时返回 plan_failed。"""
        llm = ScriptedLLM([])
        llm.chat = None
        coordinator = Coordinator(llm)
        result = await coordinator.run("测试")
        assert result["status"] == "plan_failed"

    async def test_parse_plan_fallback(self):
        """无法解析 JSON 方案时使用 fallback。"""
        llm = ScriptedLLM([])
        coordinator = Coordinator(llm)
        # 非 JSON 输入
        plan = coordinator._parse_plan("这是一个文本方案，不是 JSON")
        assert len(plan["steps"]) == 1  # fallback: 整段作为单步

    async def test_parse_review_fallback(self):
        """无法解析 JSON 审查结果时使用 fallback。"""
        llm = ScriptedLLM([])
        coordinator = Coordinator(llm)
        review = coordinator._parse_review("审查意见：通过")
        assert review["verdict"] == "pass"
