"""python -m agent_xi 入口。"""

from __future__ import annotations

import asyncio
import sys

from .config import AppSettings, load_settings


def main() -> None:
    """同步入口：加载配置 → 校验 → 启动异步主循环。"""
    settings = load_settings()

    if not settings.llm.api_key:
        provider = settings.llm.provider
        print(f"错误：未配置 {provider} 的 API Key。")
        print("请在 .env 文件中设置对应的环境变量：")
        if provider == "deepseek":
            print("  DEEPSEEK_API_KEY=your-key-here")
        elif provider == "claude":
            print("  ANTHROPIC_API_KEY=your-key-here")
        sys.exit(1)

    try:
        asyncio.run(_async_main(settings))
    except KeyboardInterrupt:
        print("\n再见！")


async def _async_main(settings: AppSettings) -> None:
    """异步主流程：创建 client → 初始化记忆 → 注册工具 → 构建 brain → 启动 CLI。"""
    from pathlib import Path

    from .brain.context import ContextBuilder
    from .brain.engine import Brain
    from .brain.prompt import PromptBuilder
    from .cli.app import CliApp
    from .llm.factory import create_client
    from .mcp.manager import MCPManager
    from .memory.embedding import EmbeddingClient
    from .memory.manager import MemoryManager
    from .skills.matcher import SkillMatcher
    from .skills.store import SkillStore
    from .tools.builtins import load_all_builtins
    from .tools.registry import ToolRegistry

    async with create_client(settings.llm) as client:
        # 初始化记忆系统
        data_dir = Path(settings.data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)

        embedding_client = EmbeddingClient(
            api_key=settings.embedding.api_key,
            base_url=settings.embedding.base_url,
            model=settings.embedding.model,
        )

        memory = MemoryManager(
            data_dir=data_dir,
            embedding_client=embedding_client,
            llm_client=client,
        )

        # 自动发现并注册所有内置工具
        registry = ToolRegistry()
        for tool in load_all_builtins():
            registry.register(tool)

        # 启动 MCP Server 并注册外部工具
        mcp_manager = MCPManager()
        await mcp_manager.start_all()
        for tool in mcp_manager.get_adapted_tools():
            registry.register(tool)

        # 初始化技能系统
        skill_store = SkillStore(
            data_dir=data_dir,
            embedding_client=embedding_client,
        )
        skill_matcher = SkillMatcher(skill_store)

        try:
            # 从模板渲染 system prompt（含工具列表 + 记忆指引）
            prompt_builder = PromptBuilder()
            system_prompt = prompt_builder.build(
                tools=registry.to_definitions(),
                has_memory=True,
            )

            context = ContextBuilder(
                system_prompt=system_prompt,
                max_history_turns=settings.max_history_turns,
                max_context_tokens=settings.max_context_tokens,
                reserved_output_tokens=settings.reserved_output_tokens,
            )
            app = CliApp(
                brain=None,  # type: ignore[arg-type]
                memory=memory,
                skill_store=skill_store,
            )
            brain = Brain(
                client=client,
                context_builder=context,
                memory=memory,
                tool_registry=registry,
                confirm_callback=app.confirm_tool_execution,
                skill_matcher=skill_matcher,
            )
            app._brain = brain  # 注入 brain（避免循环依赖）
            await app.run()
        finally:
            await mcp_manager.stop_all()
            skill_store.close()
            await embedding_client.close()
            memory.close()


if __name__ == "__main__":
    main()
