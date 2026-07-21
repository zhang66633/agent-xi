"""Brain — 对话引擎核心。

Phase 1：上下文构建 → LLM 流式调用 → 返回事件流。
Phase 2：集成记忆系统（检索注入 + 规则快捕）。
Phase 3：ReAct 工具循环（检测 tool_use → 安全确认 → 执行 → 回传结果 → 再调 LLM）。

设计要点：
- Brain 输出 AsyncIterator[StreamEvent]，不关心谁在消费
- CLI、WebSocket server、测试代码都可以消费同一个事件流
- 对话历史由 Brain 管理，外部通过 history 属性只读访问
- 工具执行通过 ToolRegistry 分发，安全确认通过 confirm_callback 委托给上层
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TYPE_CHECKING, Any

from ..llm.base import LLMClient
from ..llm.types import (
    Message,
    Role,
    StreamEvent,
    StreamEventType,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)
from .context import ContextBuilder

if TYPE_CHECKING:
    from ..memory.manager import MemoryManager
    from ..skills.matcher import SkillMatcher
    from ..tools.base import ToolResult
    from ..tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

# ReAct 循环最大迭代次数（防止无限工具调用）
_MAX_REACT_ITERATIONS = 5

# 确认回调类型：(tool_name, arguments) -> 是否允许执行
ConfirmCallback = Callable[[str, dict[str, Any]], Awaitable[bool]]


class Brain:
    """对话引擎核心。

    管理对话历史，构建上下文，调用 LLM，返回流式事件。
    Phase 2：集成记忆系统（检索注入 + 规则快捕）。
    Phase 3：ReAct 工具循环（检测 tool_use → 执行 → 回传 → 再调 LLM）。
    """

    def __init__(
        self,
        client: LLMClient,
        context_builder: ContextBuilder,
        memory: MemoryManager | None = None,
        tool_registry: ToolRegistry | None = None,
        confirm_callback: ConfirmCallback | None = None,
        skill_matcher: SkillMatcher | None = None,
    ) -> None:
        self._client = client
        self._context = context_builder
        self._memory = memory
        self._tools = tool_registry
        self._confirm_callback = confirm_callback
        self._skill_matcher = skill_matcher
        self._history: list[Message] = []

    @property
    def history(self) -> list[Message]:
        """当前对话历史（只读副本）。"""
        return list(self._history)

    @property
    def turn_count(self) -> int:
        """对话轮次数（user 消息数）。"""
        return sum(1 for m in self._history if m.role == Role.USER)

    async def chat(self, user_input: str) -> AsyncIterator[StreamEvent]:
        """处理一轮用户输入，返回流式事件。

        Phase 3 完整流程：
        1. 将 user_input 加入 history
        2. 规则快捕：从用户输入中提取偏好/事实
        3. 记忆检索：查找相关情景记忆 + 语义记忆，注入上下文
        4. 构建完整上下文（system + memory_context + history + tools）
        5. 调用 LLM chat_stream
        6. 逐事件 yield，同时收集文本和 tool_use 块
        7. 如果有 tool_use：执行工具 → 回传结果 → 重新调用 LLM（循环）
        8. 无 tool_use 或达到最大迭代：将完整回复加入 history
        """
        # 1. 用户消息加入历史
        user_msg = Message(role=Role.USER, content=user_input)
        self._history.append(user_msg)

        # 2. 规则快捕
        if self._memory:
            await self._memory.on_user_input(user_input)

        # 3. 记忆检索 → 注入上下文
        memory_context = ""
        if self._memory:
            memory_context = await self._memory.recall_context(user_input)

        # 3.5 技能匹配 → 注入流程指引
        if self._skill_matcher:
            skill_context = await self._skill_matcher.get_context(user_input)
            if skill_context:
                memory_context = (
                    f"{memory_context}\n\n{skill_context}"
                    if memory_context
                    else skill_context
                )

        # 4. 获取工具定义
        tool_definitions = self._tools.to_definitions() if self._tools else []

        # 5-7. ReAct 循环
        for iteration in range(_MAX_REACT_ITERATIONS):
            # 构建请求
            request = self._context.build_request(
                self._history,
                memory_context=memory_context,
                tools=tool_definitions or None,
            )

            # 流式调用 + 收集
            collected_text: list[str] = []
            collected_tool_uses: list[ToolUseBlock] = []
            current_tool_name: str = ""
            current_tool_args: str = ""
            had_error = False

            async for event in self._client.chat_stream(request):
                # 收集文本
                if event.type == StreamEventType.TEXT_DELTA:
                    collected_text.append(event.text)
                # 收集工具调用
                elif event.type == StreamEventType.TOOL_USE_START:
                    # 如果有上一个未完成的工具调用，先保存
                    if current_tool_name:
                        collected_tool_uses.append(
                            self._build_tool_use_block(
                                current_tool_name, current_tool_args
                            )
                        )
                    current_tool_name = event.tool_name
                    current_tool_args = ""
                elif event.type == StreamEventType.TOOL_USE_DELTA:
                    current_tool_args += event.tool_arguments
                elif event.type == StreamEventType.ERROR:
                    had_error = True
                # 所有事件都 yield 给消费方
                yield event

            # 流结束，保存最后一个未完成的工具调用
            if current_tool_name:
                collected_tool_uses.append(
                    self._build_tool_use_block(current_tool_name, current_tool_args)
                )

            # 出错时直接退出循环
            if had_error:
                return

            # 无工具调用 → 正常结束
            if not collected_tool_uses:
                if collected_text:
                    assistant_text = "".join(collected_text)
                    assistant_msg = Message(
                        role=Role.ASSISTANT, content=assistant_text
                    )
                    self._history.append(assistant_msg)
                return

            # ─── 有工具调用：构建 assistant 消息（含 text + tool_use）───
            assistant_content: list[TextBlock | ToolUseBlock] = []
            if collected_text:
                assistant_content.append(TextBlock(text="".join(collected_text)))
            assistant_content.extend(collected_tool_uses)

            assistant_msg = Message(role=Role.ASSISTANT, content=assistant_content)
            self._history.append(assistant_msg)

            # ─── 执行每个工具调用 ───
            tool_results: list[ToolResultBlock] = []

            for tool_use in collected_tool_uses:
                result_block = await self._execute_tool(tool_use)
                tool_results.append(result_block)

                # yield 工具执行结果事件（供 CLI 显示）
                yield StreamEvent(
                    type=StreamEventType.TOOL_RESULT,
                    tool_name=tool_use.name,
                    text=result_block.content[:200],  # 截断显示
                )

            # 将工具结果加入历史（每个结果一条 tool 消息，OpenAI 格式要求）
            for result_block in tool_results:
                tool_msg = Message(role=Role.TOOL, content=[result_block])
                self._history.append(tool_msg)

            # 继续循环，重新调用 LLM（让它看到工具结果）
            logger.debug(
                "ReAct iteration %d: %d tool(s) executed",
                iteration + 1,
                len(collected_tool_uses),
            )

        # 达到最大迭代次数，记录警告
        logger.warning("ReAct loop reached max iterations (%d)", _MAX_REACT_ITERATIONS)

    async def _execute_tool(self, tool_use: ToolUseBlock) -> ToolResultBlock:
        """执行单个工具调用，返回 ToolResultBlock。

        流程：
        1. 从 registry 查找工具
        2. 检查安全等级 → SENSITIVE/DANGEROUS 需确认
        3. 执行工具
        4. 包装为 ToolResultBlock
        """
        # 查找工具
        if not self._tools:
            return ToolResultBlock(
                tool_use_id=tool_use.id,
                content="错误：工具系统未初始化",
                is_error=True,
            )

        tool = self._tools.get(tool_use.name)
        if tool is None:
            return ToolResultBlock(
                tool_use_id=tool_use.id,
                content=f"错误：未找到工具 '{tool_use.name}'",
                is_error=True,
            )

        # 安全确认
        from ..tools.base import SecurityLevel

        if tool.security_level in (SecurityLevel.SENSITIVE, SecurityLevel.DANGEROUS):
            if self._confirm_callback:
                allowed = await self._confirm_callback(
                    tool_use.name, tool_use.arguments
                )
                if not allowed:
                    return ToolResultBlock(
                        tool_use_id=tool_use.id,
                        content="用户拒绝了此工具的执行。请换一种方式回答。",
                        is_error=True,
                    )

        # 执行工具
        try:
            result: ToolResult = await tool.execute(**tool_use.arguments)
            if result.success:
                return ToolResultBlock(
                    tool_use_id=tool_use.id,
                    content=result.output,
                )
            else:
                return ToolResultBlock(
                    tool_use_id=tool_use.id,
                    content=f"工具执行失败：{result.error}",
                    is_error=True,
                )
        except Exception as e:
            logger.exception("Tool '%s' execution failed", tool_use.name)
            return ToolResultBlock(
                tool_use_id=tool_use.id,
                content=f"工具执行异常：{type(e).__name__}: {e}",
                is_error=True,
            )

    @staticmethod
    def _build_tool_use_block(name: str, args_json: str) -> ToolUseBlock:
        """从收集的工具名和 JSON 参数字符串构建 ToolUseBlock。"""
        try:
            arguments = json.loads(args_json) if args_json.strip() else {}
        except json.JSONDecodeError:
            logger.warning("Failed to parse tool arguments: %s", args_json[:100])
            arguments = {}

        return ToolUseBlock(
            id=str(uuid.uuid4()),
            name=name,
            arguments=arguments,
        )

    def clear_history(self) -> None:
        """清空对话历史（开始新对话）。"""
        self._history.clear()

    def inject_message(self, message: Message) -> None:
        """向历史中注入消息（用于系统消息、记忆注入等）。"""
        self._history.append(message)
