"""Coordinator — 多智能体编排角色。

启动角色、传递信息、汇总结果、决定下一步。
不做具体工作，只做编排决策。

参考 cc-haha 的 coordinator 设计。
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any

from .base import AgentContext, AgentResult, AgentRole
from .coder import Coder
from .planner import Planner
from .reviewer import Reviewer

if TYPE_CHECKING:
    from ..llm.base import LLMClient

logger = logging.getLogger(__name__)


class Coordinator:
    """多智能体编排器。

    协调 Planner → Coder → Reviewer 的工作流程。
    用户与 Coordinator 交互，Coordinator 决定何时启动哪个角色。

    使用方式：
        coord = Coordinator(client)
        result = await coord.run(user_request="重构认证模块")
    """

    def __init__(self, client: LLMClient) -> None:
        self._client = client
        self._planner = Planner(client)
        self._coder = Coder(client)
        self._reviewer = Reviewer(client)

    async def run(self, user_request: str) -> dict[str, Any]:
        """运行完整的多智能体协作流程。

        Args:
            user_request: 用户需求。

        Returns:
            包含方案、执行结果、审查意见的汇总字典。
        """
        result: dict[str, Any] = {
            "request": user_request,
            "plan": None,
            "execution": [],
            "review": None,
            "status": "pending",
        }

        # 1. Planner: 拆解方案
        logger.info("Coordinator: 启动 Planner 拆解方案")
        plan_context = AgentContext(
            task=f"为以下需求拆解执行方案：\n\n{user_request}",
            constraints=[
                "考虑现有代码结构和工具能力",
                "标注破坏性变更的风险点",
                "如果需求不清晰，先列出需要澄清的问题",
            ],
        )
        plan_result = await self._planner.execute(plan_context)
        if not plan_result.success:
            result["status"] = "plan_failed"
            result["error"] = plan_result.error
            return result

        plan = self._parse_plan(plan_result.output)
        result["plan"] = plan

        # 2. Coder: 逐步执行
        logger.info("Coordinator: 启动 Coder 逐步执行")
        steps = plan.get("steps", [])
        for step in steps:
            step_context = AgentContext(
                task=(
                    f"执行以下步骤（方案 {steps.index(step) + 1}/{len(steps)}）：\n\n"
                    f"**描述**: {step.get('description', '')}\n"
                    f"**验证标准**: {step.get('verification', '')}\n\n"
                    f"原始需求: {user_request}"
                ),
                constraints=[
                    "遵循现有代码风格",
                    "最小化改动，不顺手重构无关代码",
                    "执行后验证结果",
                ],
            )
            exec_result = await self._coder.execute(step_context)
            result["execution"].append({
                "step": step.get("index", 0),
                "description": step.get("description", ""),
                "success": exec_result.success,
                "output": exec_result.output,
                "error": exec_result.error,
            })

            if not exec_result.success:
                logger.warning("步骤 %d 执行失败，暂停", step.get("index", 0))
                result["status"] = "execution_failed"
                return result

        # 3. Reviewer: 审查产出
        logger.info("Coordinator: 启动 Reviewer 审查")
        execution_summary = "\n".join(
            f"- 步骤 {e['step']}: {'成功' if e['success'] else '失败'} — {e['description']}"
            for e in result["execution"]
        )
        review_context = AgentContext(
            task=(
                f"审查以下任务的执行结果：\n\n"
                f"## 原始需求\n{user_request}\n\n"
                f"## 执行方案\n{plan.get('summary', '')}\n\n"
                f"## 执行结果\n{execution_summary}\n\n"
                "请检查代码变更的正确性、完整性和安全性。"
            ),
            constraints=[
                "关注实质而非形式",
                "如有 critical 问题，verdict 必须是 needs_fix",
                "给出具体的修改建议",
            ],
        )
        review_result = await self._reviewer.execute(review_context)
        result["review"] = self._parse_review(review_result.output)

        # 4. 判断是否需要返工
        if result["review"] and result["review"].get("verdict") == "needs_fix":
            logger.info("Coordinator: 审查不通过，需要修改")
            result["status"] = "needs_revision"
            # 最多再执行一轮修正
            fix_context = AgentContext(
                task=(
                    f"修复以下审查意见：\n\n"
                    + json.dumps(result["review"].get("issues", []), ensure_ascii=False, indent=2)
                ),
                constraints=[
                    "只修复审查意见中指出的问题",
                    "不要引入新的改动",
                ],
            )
            fix_result = await self._coder.execute(fix_context)
            result["fix"] = {
                "success": fix_result.success,
                "output": fix_result.output,
            }
            result["status"] = "fixed" if fix_result.success else "fix_failed"
        else:
            result["status"] = "completed"

        return result

    def _parse_plan(self, raw: str) -> dict[str, Any]:
        """从 Planner 输出中解析 JSON 方案。"""
        try:
            json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
            if json_match:
                return json.loads(json_match.group(1))
            # 尝试直接解析
            return json.loads(raw)
        except (json.JSONDecodeError, AttributeError):
            return {
                "summary": raw[:200],
                "steps": [{"index": 1, "description": raw, "verification": ""}],
                "risks": [],
                "notes": "",
            }

    def _parse_review(self, raw: str) -> dict[str, Any]:
        """从 Reviewer 输出中解析 JSON 审查结果。"""
        try:
            json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
            if json_match:
                return json.loads(json_match.group(1))
            return json.loads(raw)
        except (json.JSONDecodeError, AttributeError):
            return {
                "verdict": "pass",
                "summary": raw[:200],
                "issues": [],
                "praise": [],
            }