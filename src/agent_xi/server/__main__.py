"""python -m agent_xi.server 入口。

启动 FastAPI WebSocket Server，复用 Agent Xi 核心。
"""

from __future__ import annotations

import asyncio
import sys


def main() -> None:
    """同步入口：加载配置 → 初始化核心 → 启动 uvicorn。"""
    from ..config import load_settings

    settings = load_settings()

    if not settings.llm.api_key:
        print("错误：未配置 LLM API Key。请检查 .env 文件。")
        sys.exit(1)

    try:
        asyncio.run(_async_main(settings))
    except KeyboardInterrupt:
        print("\nServer stopped.")


async def _async_main(settings: object) -> None:
    """异步主流程：初始化所有组件 → 启动 uvicorn。"""
    from pathlib import Path

    import uvicorn

    from ..brain.prompt import PromptBuilder
    from ..llm.factory import create_client
    from ..mcp.manager import MCPManager
    from ..memory.embedding import EmbeddingClient
    from ..memory.manager import MemoryManager
    from ..skills.matcher import SkillMatcher
    from ..skills.store import SkillStore
    from ..tools.builtins import load_all_builtins
    from ..tools.registry import ToolRegistry
    from .app import create_app
    from .session import SessionManager

    async with create_client(settings.llm) as client:
        # 数据目录
        data_dir = Path(settings.data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)

        # Embedding
        embedding_client = EmbeddingClient(
            api_key=settings.embedding.api_key,
            base_url=settings.embedding.base_url,
            model=settings.embedding.model,
        )

        # Memory
        memory = MemoryManager(
            data_dir=data_dir,
            embedding_client=embedding_client,
            llm_client=client,
            max_working_turns=settings.max_history_turns,
        )

        # Tools
        registry = ToolRegistry()
        for tool in load_all_builtins():
            registry.register(tool)

        # MCP
        mcp_manager = MCPManager()
        await mcp_manager.start_all()
        for tool in mcp_manager.get_adapted_tools():
            registry.register(tool)

        # Skills
        skill_store = SkillStore(
            data_dir=data_dir,
            embedding_client=embedding_client,
        )
        skill_matcher = SkillMatcher(skill_store)

        # System prompt
        prompt_builder = PromptBuilder()
        system_prompt = prompt_builder.build(
            tools=registry.to_definitions(),
            has_memory=True,
        )

        # Session manager
        session_mgr = SessionManager(
            client=client,
            memory=memory,
            tool_registry=registry,
            skill_matcher=skill_matcher,
            system_prompt=system_prompt,
            max_history_turns=settings.max_history_turns,
            max_context_tokens=settings.max_context_tokens,
            reserved_output_tokens=settings.reserved_output_tokens,
        )

        # FastAPI app
        app = create_app(session_mgr)

        # 启动 uvicorn
        config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=9731,
            log_level="info",
        )
        server = uvicorn.Server(config)

        print("\n  Agent Xi Server")
        print("  ─────────────────────────────")
        print("  WebSocket: ws://127.0.0.1:9731/ws/chat")
        print("  Health:    http://127.0.0.1:9731/api/health")
        if (Path(__file__).parent.parent.parent.parent / "web" / "dist").exists():
            print("  Web UI:    http://127.0.0.1:9731/")
        else:
            print("  Web UI:    (未构建，运行 cd web && npm run build)")
        print("  ─────────────────────────────\n")

        try:
            await server.serve()
        finally:
            await mcp_manager.stop_all()
            skill_store.close()
            await embedding_client.close()
            memory.close()


if __name__ == "__main__":
    main()
