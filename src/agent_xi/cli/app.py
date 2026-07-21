"""CLI 交互界面 — Phase 3 版本。

使用 rich 做流式渲染，不引入 Textual。
Windows 兼容：用 asyncio.to_thread 包装 input() 避免阻塞事件循环。

Phase 3 新增：
- 工具调用状态显示（正在调用、执行结果）
- SENSITIVE/DANGEROUS 工具的用户确认交互

支持的命令：
- /exit, /quit, exit: 退出（触发 LLM 深度提取）
- /clear: 清空对话历史
- /history: 显示对话轮次数
- /remember <内容>: 显式存储情景记忆
- /memory: 查看已存储的记忆统计
- /help: 显示帮助
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from ..brain.engine import Brain
from ..llm.types import StreamEventType

if TYPE_CHECKING:
    from ..memory.manager import MemoryManager
    from ..skills.store import SkillStore


class CliApp:
    """终端交互应用。"""

    def __init__(
        self,
        brain: Brain,
        memory: MemoryManager | None = None,
        skill_store: SkillStore | None = None,
    ) -> None:
        self._brain = brain
        self._memory = memory
        self._skill_store = skill_store
        self._console = Console()

    async def confirm_tool_execution(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> bool:
        """工具安全确认回调 — 由 Brain 在调用 SENSITIVE/DANGEROUS 工具时触发。

        显示工具名和参数，等待用户 y/n 确认。
        """
        self._console.print()
        # 格式化参数显示
        args_str = json.dumps(arguments, ensure_ascii=False, indent=2)
        if len(args_str) > 300:
            args_str = args_str[:300] + "..."

        warn_text = Text()
        warn_text.append("⚠ 工具确认\n", style="bold yellow")
        warn_text.append("  工具: ", style="dim")
        warn_text.append(f"{tool_name}\n", style="bold cyan")
        warn_text.append("  参数: ", style="dim")
        warn_text.append(args_str, style="white")

        self._console.print(
            Panel(warn_text, border_style="yellow", padding=(0, 1))
        )

        # 异步读取用户输入
        answer = await asyncio.to_thread(
            self._console.input,
            Text("  允许执行？(y/n): ", style="bold yellow"),
        )
        return answer.strip().lower() in ("y", "yes", "是")

    async def run(self) -> None:
        """主循环：读取输入 → 调用 brain → 流式渲染。"""
        self._print_welcome()

        while True:
            try:
                # Windows 兼容：to_thread 避免阻塞事件循环
                user_input = await asyncio.to_thread(
                    self._console.input,
                    Text("你> ", style="bold green"),
                )
            except (EOFError, KeyboardInterrupt):
                break

            stripped = user_input.strip()

            if not stripped:
                continue

            # 命令处理
            if stripped.startswith("/"):
                handled = await self._handle_command(stripped)
                if handled:
                    continue
                # 未知命令，当作普通消息处理

            if stripped.lower() in ("exit", "quit"):
                break

            await self._stream_response(stripped)

        # 退出时触发 LLM 深度提取
        await self._on_exit()
        self._console.print("\n[dim]再见！下次聊。[/]")

    async def _handle_command(self, command: str) -> bool:
        """处理斜杠命令。返回 True 表示已处理，False 表示未知命令。"""
        parts = command.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        match cmd:
            case "/exit" | "/quit":
                raise KeyboardInterrupt
            case "/clear":
                self._brain.clear_history()
                self._console.print("[dim]对话已清空，开始新对话。[/]")
                return True
            case "/history":
                turns = self._brain.turn_count
                self._console.print(f"[dim]当前对话：{turns} 轮[/]")
                return True
            case "/remember":
                await self._handle_remember(arg)
                return True
            case "/memory":
                self._show_memory_stats()
                return True
            case "/save-skill":
                await self._handle_save_skill(arg)
                return True
            case "/skills":
                self._show_skills()
                return True
            case "/help":
                self._print_help()
                return True
            case _:
                return False

    async def _handle_remember(self, content: str) -> None:
        """处理 /remember 命令：显式存储情景记忆。"""
        if not content:
            self._console.print("[dim]用法：/remember <要记住的内容>[/]")
            return

        if not self._memory:
            self._console.print("[yellow]记忆系统未启用。[/]")
            return

        self._console.print("[dim]正在记忆...[/]", end="")
        await self._memory.remember_episode(content)
        self._console.print(
            f"\r[green]✓ 已记住：[/]{content[:50]}"
            f"{'...' if len(content) > 50 else ''}"
        )

    def _show_memory_stats(self) -> None:
        """显示记忆统计信息。"""
        if not self._memory:
            self._console.print("[yellow]记忆系统未启用。[/]")
            return

        episode_count = self._memory.episodic.count
        semantic_count = self._memory.semantic.count
        self._console.print(
            f"[dim]情景记忆：{episode_count} 条 | 语义记忆：{semantic_count} 条[/]"
        )

    async def _handle_save_skill(self, arg: str) -> None:
        """处理 /save-skill 命令：从描述中创建新技能。"""
        if not self._skill_store:
            self._console.print("[yellow]技能系统未启用。[/]")
            return

        if not arg:
            self._console.print(
                "[dim]用法：/save-skill <名称> | <描述> | <步骤>[/]"
            )
            self._console.print(
                "[dim]示例：/save-skill 代码审查 | 审查代码质量 | "
                "1.读取文件 2.检查风格 3.总结问题[/]"
            )
            return

        parts = [p.strip() for p in arg.split("|")]
        name = parts[0] if parts else "未命名技能"
        description = parts[1] if len(parts) > 1 else name
        steps = parts[2] if len(parts) > 2 else "（待补充）"

        from ..skills.models import Skill

        skill = Skill(
            name=name,
            description=description,
            steps=steps,
            trigger_keywords=[w for w in name.split() if len(w) > 1],
        )

        self._console.print("[dim]正在保存技能...[/]", end="")
        await self._skill_store.save(skill)
        self._console.print(f"\r[green]✓ 技能已保存：[/]{name}")

    def _show_skills(self) -> None:
        """显示已保存的技能列表。"""
        if not self._skill_store:
            self._console.print("[yellow]技能系统未启用。[/]")
            return

        skills = self._skill_store.list_all()
        if not skills:
            self._console.print("[dim]暂无保存的技能。[/]")
            return

        self._console.print(f"[bold]已保存的技能（{len(skills)} 个）：[/]")
        for s in skills:
            used = f"（使用 {s.use_count} 次）" if s.use_count else ""
            self._console.print(
                f"  [cyan]{s.name}[/] [dim]— {s.description}{used}[/]"
            )

    async def _on_exit(self) -> None:
        """退出时触发 LLM 深度提取语义记忆。"""
        if not self._memory:
            return

        history = self._brain.history
        if len(history) < 2:
            return

        self._console.print("[dim]正在整理本次对话的记忆...[/]", end="")
        extracted = await self._memory.on_conversation_end(history)
        if extracted:
            self._console.print(
                f"\r[green]✓ 从对话中提取了 {len(extracted)} 条新记忆[/]"
            )
        else:
            self._console.print("\r[dim]本次对话无新记忆提取。[/]  ")

    async def _stream_response(self, user_input: str) -> None:
        """流式渲染 LLM 回复（含工具调用状态）。"""
        self._console.print()  # 空行分隔
        self._console.print(Text("Xi> ", style="bold blue"), end="")

        full_text = ""

        async for event in self._brain.chat(user_input):
            match event.type:
                case StreamEventType.TEXT_DELTA:
                    self._console.print(event.text, end="", highlight=False)
                    full_text += event.text

                case StreamEventType.TOOL_USE_START:
                    # LLM 决定调用工具
                    self._console.print()
                    self._console.print(
                        f"  [dim]🔧 调用工具:[/] [cyan]{event.tool_name}[/]",
                        highlight=False,
                    )

                case StreamEventType.TOOL_EXECUTING:
                    # Brain 正在执行工具
                    self._console.print(
                        f"  [dim]⏳ 执行中:[/] [cyan]{event.tool_name}[/]",
                        highlight=False,
                    )

                case StreamEventType.TOOL_RESULT:
                    # 工具执行完成
                    result_preview = event.text[:100]
                    if len(event.text) > 100:
                        result_preview += "..."
                    self._console.print(
                        f"  [dim]✓ 结果:[/] [dim]{result_preview}[/]",
                        highlight=False,
                    )
                    # 工具结果后，LLM 会继续生成文本
                    self._console.print()
                    self._console.print(Text("Xi> ", style="bold blue"), end="")

                case StreamEventType.TOOL_CONFIRM_DENIED:
                    self._console.print(
                        f"  [yellow]⚠ 用户拒绝执行:[/] [cyan]{event.tool_name}[/]",
                        highlight=False,
                    )

                case StreamEventType.ERROR:
                    self._console.print()
                    self._console.print(
                        f"[bold red]错误:[/] {event.error}",
                    )
                    return

                case StreamEventType.DONE:
                    pass

        # 流结束，换行
        self._console.print()

        if not full_text:
            self._console.print("[dim]（无回复）[/]")

    def _print_welcome(self) -> None:
        """打印欢迎信息。"""
        welcome = Text()
        welcome.append("Agent Xi", style="bold magenta")
        welcome.append(" — 你的 AI 伙伴\n", style="dim")
        welcome.append("输入消息开始对话，", style="dim")
        welcome.append("/help", style="cyan")
        welcome.append(" 查看命令，", style="dim")
        welcome.append("/exit", style="cyan")
        welcome.append(" 退出。", style="dim")

        self._console.print(Panel(welcome, border_style="magenta", padding=(1, 2)))
        self._console.print()

    def _print_help(self) -> None:
        """打印帮助信息。"""
        help_text = Text()
        help_text.append("可用命令：\n", style="bold")
        help_text.append("  /exit, /quit      ", style="cyan")
        help_text.append("退出程序\n", style="dim")
        help_text.append("  /clear            ", style="cyan")
        help_text.append("清空对话历史\n", style="dim")
        help_text.append("  /history          ", style="cyan")
        help_text.append("查看对话轮次\n", style="dim")
        help_text.append("  /remember <内容>  ", style="cyan")
        help_text.append("记住一条信息\n", style="dim")
        help_text.append("  /memory           ", style="cyan")
        help_text.append("查看记忆统计\n", style="dim")
        help_text.append("  /save-skill <...> ", style="cyan")
        help_text.append("保存新技能\n", style="dim")
        help_text.append("  /skills           ", style="cyan")
        help_text.append("查看技能列表\n", style="dim")
        help_text.append("  /help             ", style="cyan")
        help_text.append("显示此帮助", style="dim")

        self._console.print(Panel(help_text, title="帮助", border_style="cyan"))
