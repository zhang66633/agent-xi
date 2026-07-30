"""测试 Outer Loop — orchestrator / state / guard。"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from agent_xi.loop.guard import LoopGuard
from agent_xi.loop.orchestrator import Goal, GoalStatus, Orchestrator
from agent_xi.loop.state import LoopState, StepStatus
from agent_xi.brain.context import ContextBuilder
from agent_xi.brain.engine import Brain
from tests.conftest import ScriptedLLM


# ─── LoopGuard ──────────────────────────────────────────────────────────


class TestLoopGuard:
    def test_stops_on_max_steps(self):
        guard = LoopGuard(max_steps=3)
        goal = Goal(id="g1", description="test")
        # 模拟 3 步全完成
        from agent_xi.loop.orchestrator import Step
        goal.steps = [
            Step(index=1, description="s1", status=StepStatus.DONE),
            Step(index=2, description="s2", status=StepStatus.DONE),
            Step(index=3, description="s3", status=StepStatus.DONE),
        ]
        assert guard.should_stop(goal)

    def test_stops_on_consecutive_failures(self):
        guard = LoopGuard(max_failures=2)
        goal = Goal(id="g1", description="test")
        goal.steps = []
        assert not guard.should_stop(goal)
        guard.record_failure()
        guard.record_failure()
        assert guard.consecutive_failures == 2
        assert guard.should_stop(goal)

    def test_success_resets_failure_count(self):
        guard = LoopGuard(max_failures=2)
        guard.record_failure()
        guard.record_success()
        assert guard.consecutive_failures == 0

    def test_default_limits(self):
        guard = LoopGuard()
        assert guard.consecutive_failures == 0


# ─── LoopState ──────────────────────────────────────────────────────────


class TestLoopState:
    def test_save_and_load_goal(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = LoopState(Path(tmp))
            goal = Goal(id="g1", description="测试目标")
            goal.steps = [
                type("Step", (), {
                    "index": 1, "description": "步骤1", "verification": "验证1",
                    "status": StepStatus.DONE, "result": "完成", "error": "",
                    "depends_on": [],
                }),
            ]
            goal.status = GoalStatus.DONE

            state.save_goal(goal)
            loaded = state.load_goal("g1")

            assert loaded is not None
            assert loaded.id == "g1"
            assert loaded.description == "测试目标"
            assert str(loaded.status) == "done"
            assert len(loaded.steps) == 1

    def test_load_nonexistent_goal(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = LoopState(Path(tmp))
            assert state.load_goal("nonexistent") is None

    def test_list_goals(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = LoopState(Path(tmp))
            goal = Goal(id="g1", description="目标1")
            state.save_goal(goal)
            goals = state.list_goals()
            assert len(goals) == 1
            assert goals[0]["id"] == "g1"

    def test_delete_goal(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = LoopState(Path(tmp))
            goal = Goal(id="g1", description="目标1")
            state.save_goal(goal)
            assert state.delete_goal("g1")
            assert state.load_goal("g1") is None
            assert not state.delete_goal("nonexistent")


# ─── Orchestrator ─────────────────────────────────────────────────────


class TestOrchestrator:
    pytestmark_orch = pytest.mark.asyncio

    @pytest.mark.asyncio
    async def test_decompose_goal_to_steps(self):
        """目标拆解 → 产生步骤清单。"""
        llm = ScriptedLLM([
            [
                ("text", '```json\n[{"index":1,"description":"步骤 A","verification":"A 完成"},{"index":2,"description":"步骤 B","verification":"B 完成"}]\n```'),
            ],
        ])
        brain = Brain(
            client=llm,
            context_builder=ContextBuilder(system_prompt="你是 Xi"),
        )

        with tempfile.TemporaryDirectory() as tmp:
            state = LoopState(Path(tmp))
            guard = LoopGuard()
            orchestrator = Orchestrator(brain, state, guard)

            steps = await orchestrator._decompose("测试目标")

            assert len(steps) == 2
            assert steps[0].description == "步骤 A"
            assert steps[1].description == "步骤 B"
            assert steps[0].verification == "A 完成"

    @pytest.mark.asyncio
    async def test_run_goal_flow(self):
        """完整目标执行流程。"""
        llm = ScriptedLLM([
            # 第1次调用：拆解目标
            [
                ("text", '```json\n[{"index":1,"description":"步骤1","verification":"验证1"}]\n```'),
            ],
            # 第2次调用：执行步骤1
            [
                ("text", "步骤1 已执行完成"),
            ],
        ])
        brain = Brain(
            client=llm,
            context_builder=ContextBuilder(system_prompt="你是 Xi"),
        )

        with tempfile.TemporaryDirectory() as tmp:
            state = LoopState(Path(tmp))
            guard = LoopGuard()
            orchestrator = Orchestrator(brain, state, guard)

            goal = await orchestrator.run_goal("测试目标")

            assert goal.status == GoalStatus.DONE
            assert len(goal.steps) == 1
            assert goal.steps[0].status == StepStatus.DONE
            assert "完成" in goal.steps[0].result

    async def test_cancel_goal(self):
        llm = ScriptedLLM([])
        brain = Brain(
            client=llm,
            context_builder=ContextBuilder(system_prompt="你是 Xi"),
        )

        with tempfile.TemporaryDirectory() as tmp:
            state = LoopState(Path(tmp))
            orchestrator = Orchestrator(brain, state)

            orchestrator._current_goal = Goal(id="g1", description="will cancel")
            orchestrator.cancel()
            goal_path = state._goals_dir / "g1.json"
            assert goal_path.exists()
            data = json.loads(goal_path.read_text(encoding="utf-8"))
            assert data["status"] == "cancelled"


# ─── Resumption ───────────────────────────────────────────────────────


class TestResumption:
    async def test_resume_goal(self):
        """断点续跑：跳过已完成步骤，继续未完成。"""
        with tempfile.TemporaryDirectory() as tmp:
            state = LoopState(Path(tmp))
            # 预存一个部分完成的目标
            from agent_xi.loop.orchestrator import Step
            goal = Goal(id="g1", description="续跑测试")
            goal.steps = [
                Step(index=1, description="已完成步骤", status=StepStatus.DONE, result="done"),
                Step(index=2, description="待执行步骤", status=StepStatus.PENDING),
            ]
            state.save_goal(goal)

            # 第二个脚本：执行步骤2
            llm = ScriptedLLM([
                [("text", "步骤2 完成")],
            ])
            brain = Brain(
                client=llm,
                context_builder=ContextBuilder(system_prompt="你是 Xi"),
            )
            guard = LoopGuard()
            orchestrator = Orchestrator(brain, state, guard)

            resumed = await orchestrator.resume_goal("g1")

            assert resumed.status == GoalStatus.DONE
            assert resumed.steps[0].status == StepStatus.DONE  # 保持完成
            assert resumed.steps[1].status == StepStatus.DONE  # 新完成
            assert "完成" in resumed.steps[1].result
