"""Brain — 对话引擎核心。

Phase 1：上下文构建 → LLM 流式调用 → 返回事件流。
Phase 2：集成记忆系统（检索注入 + 规则快捕）。
Phase 3：ReAct 工具循环（检测 tool_use → 安全确认 → 执行 → 回传结果 → 再调 LLM）。
Phase 4：中断支持、权限追踪、输出截断、并行工具、错误回滚。

设计要点：
- Brain 输出 AsyncIterator[StreamEvent]，不关心谁在消费
- CLI、WebSocket server、测试代码都可以消费同一个事件流
- 对话历史由 Brain 管理，外部通过 history 属性只读访问
- 工具执行通过 ToolRegistry 分发，安全确认通过 confirm_callback 委托给上层
- interrupt() 可随时中止正在进行的 chat()
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
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
    from ..loop.orchestrator import Goal, Orchestrator
    from ..memory.manager import MemoryManager
    from ..skills.matcher import SkillMatcher
    from ..tools.base import ToolResult
    from ..tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

# ReAct 循环最大迭代次数（对标 Claude Code，支持 20-80 次工具调用）
_MAX_REACT_ITERATIONS = 30

# 工具输出截断：存入历史的 tool result 最多保留的字符数
_MAX_TOOL_OUTPUT_CHARS = 4000

# 权限拒绝追踪：同一工具被拒绝后，N 秒内不再重复确认
_DENIAL_COOLDOWN_SECONDS = 300  # 5 分钟

# 确认回调类型：(tool_name, arguments) -> 是否允许执行
ConfirmCallback = Callable[[str, dict[str, Any]], Awaitable[bool]]


class Brain:
    """对话引擎核心。

    管理对话历史，构建上下文，调用 LLM，返回流式事件。
    Phase 2：集成记忆系统（检索注入 + 规则快捕）。
    Phase 3：ReAct 工具循环（检测 tool_use → 执行 → 回传 → 再调 LLM）。
    Phase 4：中断支持、权限追踪、输出截断、并行工具、错误回滚。
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

        # Phase 4: 中断支持
        self._abort_event = asyncio.Event()

        # Phase 4: 上下文压缩（延迟创建，避免循环导入）
        self._compactor: Any = None

        # Phase 4: 工具大结果存盘
        self._data_dir: Any = None
        self._session_id: str = ""

        # Phase 4: 权限拒绝追踪
        self._permission_denials: list[dict[str, Any]] = []

        # Phase 4: 用量追踪回调（外部注入）
        self._usage_callback: Callable[[str, str, int, int], None] | None = None

    @property
    def history(self) -> list[Message]:
        """当前对话历史（只读副本）。"""
        return list(self._history)

    @property
    def turn_count(self) -> int:
        """对话轮次数（user 消息数）。"""
        return sum(1 for m in self._history if m.role == Role.USER)

    @property
    def is_interrupted(self) -> bool:
        """当前是否有未处理的中断请求。"""
        return self._abort_event.is_set()

    def interrupt(self) -> None:
        """中止当前正在进行的 chat() 调用。"""
        self._abort_event.set()
        logger.info("Brain interrupt requested")

    def set_usage_callback(
        self, callback: Callable[[str, str, int, int], None]
    ) -> None:
        """设置用量追踪回调 (model, provider, input_tokens, output_tokens)。"""
        self._usage_callback = callback

    async def chat(self, user_input: str) -> AsyncIterator[StreamEvent]:
        """处理一轮用户输入，返回流式事件。

        Phase 4 完整流程：
        1. 保存历史快照（出错回滚）
        2. 将 user_input 加入 history
        3. 记忆检索 + 技能匹配 → 注入上下文
        4. 构建完整上下文（system + memory_context + history + tools）
        5. 调用 LLM chat_stream（含中断检查 + 流重试）
        6. 逐事件 yield，同时收集文本和 tool_use 块
        7. 如果有 tool_use：执行工具（安全确认 → 权限拒绝追踪）→ 回传截断结果 → 重新调用 LLM
        8. 无 tool_use 或达到最大迭代：将完整回复加入 history
        9. 出错时回滚历史到快照
        """
        # 0. 重置中断标记
        self._abort_event.clear()

        # 0.5. 保存历史快照（出错时回滚）
        history_snapshot = list(self._history)

        # 1. 用户消息加入历史
        user_msg = Message(role=Role.USER, content=user_input)
        self._history.append(user_msg)

        try:
            # 2. 记忆检索 → 注入上下文（只在第一轮迭代前做）
            memory_context = ""
            if self._memory:
                memory_context = await self._memory.recall_context(user_input)

            # 2.5 技能匹配
            if self._skill_matcher:
                skill_context = await self._skill_matcher.get_context(user_input)
                if skill_context:
                    memory_context = (
                        f"{memory_context}\n\n{skill_context}"
                        if memory_context
                        else skill_context
                    )

            # 3. 获取工具定义
            tool_definitions = self._tools.to_definitions() if self._tools else []

            # 4. 注入权限拒绝历史（让 LLM 知道用户偏好）
            denial_hint = self._build_denial_hint()
            if denial_hint:
                memory_context = (
                    f"{memory_context}\n\n{denial_hint}"
                    if memory_context
                    else denial_hint
                )

            # 5-7. ReAct 循环
            for iteration in range(_MAX_REACT_ITERATIONS):
                # 中断检查点
                if self._abort_event.is_set():
                    yield StreamEvent(
                        type=StreamEventType.ERROR,
                        error="操作已被用户中断",
                    )
                    return

                # 上下文压缩检查（首次迭代，token 超 70% 预算时触发）
                if iteration == 0:
                    await self._maybe_compact()

                # 构建请求
                request = self._context.build_request(
                    self._history,
                    memory_context=memory_context if iteration == 0 else "",
                    tools=tool_definitions or None,
                )

                # 流式调用 + 收集
                collected_text: list[str] = []
                collected_tool_uses: list[ToolUseBlock] = []
                current_tool_name: str = ""
                current_tool_args: str = ""
                had_error = False
                last_usage: Any = None  # 捕最后一条 DONE 事件的 usage

                try:
                    async for event in self._client.chat_stream(request):
                        # 流中检查中断
                        if self._abort_event.is_set():
                            yield StreamEvent(
                                type=StreamEventType.ERROR,
                                error="流已被用户中断",
                            )
                            return

                        if event.type == StreamEventType.TEXT_DELTA:
                            collected_text.append(event.text)
                        elif event.type == StreamEventType.TOOL_USE_START:
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
                        elif event.type == StreamEventType.DONE:
                            last_usage = event.usage
                        # 所有事件都 yield 给消费方
                        yield event
                except Exception as stream_err:
                    logger.warning("Stream failed, attempting retry: %s", stream_err)
                    # 流重试：非流式 fallback
                    try:
                        response = await self._client.chat(request)
                        yield StreamEvent(
                            type=StreamEventType.TEXT_DELTA,
                            text=response.message.text,
                        )
                        yield StreamEvent(
                            type=StreamEventType.DONE,
                            finish_reason=response.finish_reason,
                            usage=response.usage,
                        )
                        collected_text.append(response.message.text)
                    except Exception as retry_err:
                        logger.exception("Stream retry also failed")
                        yield StreamEvent(
                            type=StreamEventType.ERROR,
                            error=f"流式调用失败: {retry_err}",
                        )
                        return

                # 记录用量
                if last_usage and self._usage_callback:
                    model = getattr(self._client, "_model", "unknown")
                    provider = getattr(self._client, "provider_name", "unknown")
                    self._usage_callback(
                        provider, model,
                        last_usage.input_tokens, last_usage.output_tokens,
                    )

                # 流结束，保存最后一个未完成的工具调用
                if current_tool_name:
                    collected_tool_uses.append(
                        self._build_tool_use_block(current_tool_name, current_tool_args)
                    )

                # 出错时退出
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

                # ─── 有工具调用：构建 assistant 消息 ───
                assistant_content: list[TextBlock | ToolUseBlock] = []
                if collected_text:
                    assistant_content.append(TextBlock(text="".join(collected_text)))
                assistant_content.extend(collected_tool_uses)

                assistant_msg = Message(role=Role.ASSISTANT, content=assistant_content)
                self._history.append(assistant_msg)

                # ─── 执行工具：安全工具并行，危险工具串行 ───
                tool_results: list[ToolResultBlock] = []

                # 分类工具
                safe_tools = []
                dangerous_tools = []
                for tool_use in collected_tool_uses:
                    tool = self._tools.get(tool_use.name) if self._tools else None
                    if tool and tool.security_level.value == "safe":
                        safe_tools.append(tool_use)
                    else:
                        dangerous_tools.append(tool_use)

                # 并行执行安全工具
                if safe_tools:
                    for tool_use in safe_tools:
                        yield StreamEvent(
                            type=StreamEventType.TOOL_EXECUTING,
                            tool_name=tool_use.name,
                        )
                    safe_results = await asyncio.gather(
                        *[self._execute_tool(tu) for tu in safe_tools],
                        return_exceptions=True,
                    )
                    for i, (tool_use, result) in enumerate(zip(safe_tools, safe_results)):
                        if isinstance(result, Exception):
                            result = (
                                ToolResultBlock(
                                    tool_use_id=tool_use.id,
                                    content=f"并行执行异常: {result}",
                                    is_error=True,
                                ),
                                False,
                            )
                        result_block, denied = result
                        tool_results.append(self._truncate_result(result_block))
                        if denied:
                            yield StreamEvent(
                                type=StreamEventType.TOOL_CONFIRM_DENIED,
                                tool_name=tool_use.name,
                            )
                        else:
                            yield StreamEvent(
                                type=StreamEventType.TOOL_RESULT,
                                tool_name=tool_use.name,
                                text=result_block.content[:200],
                            )

                # 串行执行敏感/危险工具
                for tool_use in dangerous_tools:
                    # 中断检查
                    if self._abort_event.is_set():
                        yield StreamEvent(
                            type=StreamEventType.ERROR,
                            error="工具执行已被用户中断",
                        )
                        return

                    yield StreamEvent(
                        type=StreamEventType.TOOL_EXECUTING,
                        tool_name=tool_use.name,
                    )

                    result_block, denied = await self._execute_tool(tool_use)
                    tool_results.append(self._truncate_result(result_block))

                    if denied:
                        # 权限拒绝追踪
                        self._record_denial(tool_use)
                        yield StreamEvent(
                            type=StreamEventType.TOOL_CONFIRM_DENIED,
                            tool_name=tool_use.name,
                        )
                    else:
                        yield StreamEvent(
                            type=StreamEventType.TOOL_RESULT,
                            tool_name=tool_use.name,
                            text=result_block.content[:200],
                        )

                # 将工具结果加入历史
                for result_block in tool_results:
                    tool_msg = Message(role=Role.TOOL, content=[result_block])
                    self._history.append(tool_msg)

                logger.debug(
                    "ReAct iteration %d: %d tool(s) executed",
                    iteration + 1,
                    len(collected_tool_uses),
                )

            # 达到最大迭代次数
            yield StreamEvent(
                type=StreamEventType.ERROR,
                error=f"已达最大工具调用轮数 ({_MAX_REACT_ITERATIONS})，对话可继续",
            )
            logger.warning("ReAct loop reached max iterations (%d)", _MAX_REACT_ITERATIONS)

        except Exception:
            # 出错时回滚历史到快照
            logger.exception("Chat error, rolling back history")
            self._history = history_snapshot
            yield StreamEvent(
                type=StreamEventType.ERROR,
                error="处理失败，对话已回滚到本消息之前",
            )

    async def _execute_tool(
        self, tool_use: ToolUseBlock
    ) -> tuple[ToolResultBlock, bool]:
        """执行单个工具调用，返回 (ToolResultBlock, denied)。"""
        if self._tools is None:
            return ToolResultBlock(
                tool_use_id=tool_use.id,
                content="错误：工具系统未初始化",
                is_error=True,
            ), False

        tool = self._tools.get(tool_use.name)
        if tool is None:
            return ToolResultBlock(
                tool_use_id=tool_use.id,
                content=f"错误：未找到工具 '{tool_use.name}'",
                is_error=True,
            ), False

        # 安全确认
        from ..tools.base import SecurityLevel

        if tool.security_level in (
            SecurityLevel.SENSITIVE,
            SecurityLevel.DANGEROUS,
            SecurityLevel.ASK_EVERY,
        ):
            # 检查是否在冷却期内被拒绝过
            if self._was_recently_denied(tool_use):
                return ToolResultBlock(
                    tool_use_id=tool_use.id,
                    content=f"工具 '{tool_use.name}' 刚才已被拒绝，请换一种方式。",
                    is_error=True,
                ), True

            if self._confirm_callback:
                allowed = await self._confirm_callback(
                    tool_use.name, tool_use.arguments
                )
                if not allowed:
                    self._record_denial(tool_use)
                    return ToolResultBlock(
                        tool_use_id=tool_use.id,
                        content="用户拒绝了此工具的执行。请换一种方式回答。",
                        is_error=True,
                    ), True

        # 执行工具
        try:
            result: ToolResult = await tool.execute(**tool_use.arguments)
            if result.success:
                return ToolResultBlock(
                    tool_use_id=tool_use.id,
                    content=result.output,
                ), False
            else:
                return ToolResultBlock(
                    tool_use_id=tool_use.id,
                    content=f"工具执行失败：{result.error}",
                    is_error=True,
                ), False
        except Exception as e:
            logger.exception("Tool '%s' execution failed", tool_use.name)
            return ToolResultBlock(
                tool_use_id=tool_use.id,
                content=f"工具执行异常：{type(e).__name__}: {e}",
                is_error=True,
            ), False

    # ─── 权限拒绝追踪 ─────────────────────────────────────────────

    def _record_denial(self, tool_use: ToolUseBlock) -> None:
        """记录一次工具拒绝。"""
        args_hash = hashlib.md5(
            json.dumps(tool_use.arguments, sort_keys=True).encode()
        ).hexdigest()[:8]
        self._permission_denials.append({
            "tool_name": tool_use.name,
            "args_hash": args_hash,
            "timestamp": time.time(),
        })

    def _was_recently_denied(self, tool_use: ToolUseBlock) -> bool:
        """检查同一工具 + 相似参数是否在冷却期内被拒绝过。"""
        now = time.time()
        args_hash = hashlib.md5(
            json.dumps(tool_use.arguments, sort_keys=True).encode()
        ).hexdigest()[:8]
        return any(
            d["tool_name"] == tool_use.name
            and d["args_hash"] == args_hash
            and (now - d["timestamp"]) < _DENIAL_COOLDOWN_SECONDS
            for d in self._permission_denials
        )

    def _build_denial_hint(self) -> str:
        """构建权限拒绝提示（注入 system context）。"""
        if not self._permission_denials:
            return ""
        now = time.time()
        recent = [
            d for d in self._permission_denials
            if (now - d["timestamp"]) < _DENIAL_COOLDOWN_SECONDS
        ]
        if not recent:
            return ""
        tools_names = list({d["tool_name"] for d in recent})
        return (
            "[系统提示] 用户刚才拒绝了以下工具的执行，"
            "请避免再次调用它们，换一种方式完成任务：\n"
            + "\n".join(f"- {t}" for t in tools_names)
        )

    # ─── 辅助方法 ─────────────────────────────────────────────────

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

    def _truncate_result(self, block: ToolResultBlock) -> ToolResultBlock:
        """截断工具输出（防止历史膨胀）。大结果存盘返回预览。"""
        content = block.content
        if len(content) <= _MAX_TOOL_OUTPUT_CHARS:
            return block

        # 尝试存盘
        if self._data_dir and self._session_id:
            from ..server.tool_storage import store_tool_result
            preview = store_tool_result(
                self._data_dir, self._session_id,
                "unknown", content,
            )
            if preview:
                return ToolResultBlock(
                    tool_use_id=block.tool_use_id,
                    content=preview,
                    is_error=block.is_error,
                )

        # 截断 fallback
        truncated = (
            content[:_MAX_TOOL_OUTPUT_CHARS // 2]
            + f"\n\n... [截断 {len(content) - _MAX_TOOL_OUTPUT_CHARS} 字符] ...\n\n"
            + content[-(_MAX_TOOL_OUTPUT_CHARS // 4):]
        )
        return ToolResultBlock(
            tool_use_id=block.tool_use_id,
            content=truncated,
            is_error=block.is_error,
        )

    async def _maybe_compact(self) -> None:
        """检查 token 用量，超阈值时压缩旧消息为摘要。"""
        from .compactor import ContextCompactor
        from .tokenizer import count_tools_tokens

        if self._compactor is None:
            self._compactor = ContextCompactor(
                llm_client=self._client,
                max_budget=self._context._max_context_tokens,
            )
        # 计算固定开销
        tools_def = self._tools.to_definitions() if self._tools else []
        tools_tokens = count_tools_tokens(tools_def)
        system_tokens = self._compactor._counter.count_text(
            self._context.system_prompt
        )
        fixed_cost = tools_tokens + system_tokens

        if not self._compactor.should_compact(self._history, fixed_cost):
            return

        result = await self._compactor.compact(self._history)
        if result:
            self._history = result["truncated_history"]
            summary = result["summary"]
            # 注入摘要到 system prompt
            self._context.system_prompt = (
                f"{self._context.system_prompt}\n\n"
                f"[对话摘要 — 之前的内容已被压缩]\n{summary}"
            )
            logger.info(
                "上下文已压缩: %d 条消息 -> %d 条保留",
                result["compacted_count"],
                len(self._history),
            )

    def clear_history(self) -> None:
        """清空对话历史（开始新对话）。"""
        self._history.clear()
        self._permission_denials.clear()

    def inject_message(self, message: Message) -> None:
        """向历史中注入消息（用于系统消息、记忆注入等）。"""
        self._history.append(message)

    async def run_goal(self, goal_description: str) -> Goal:
        """通过 Outer Loop 编排器执行一个完整目标。"""
        from ..loop import LoopGuard, LoopState, Orchestrator
        from pathlib import Path

        data_dir = Path(".data")
        state = LoopState(data_dir)
        guard = LoopGuard()
        orchestrator = Orchestrator(self, state, guard)

        return await orchestrator.run_goal(goal_description)