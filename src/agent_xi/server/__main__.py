"""python -m agent_xi.server 入口。

启动 FastAPI WebSocket Server，复用 Agent Xi 核心。
"""

from __future__ import annotations

import argparse
import asyncio
import sys


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Agent Xi Server")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=9731, help="监听端口")
    return parser.parse_args()


def main() -> None:
    """同步入口：加载配置 → 初始化核心 → 启动 uvicorn。"""
    from ..config import load_settings

    args = _parse_args()
    settings = load_settings()

    if not settings.llm.api_key:
        print("错误：未配置 LLM API Key。请检查 .env 文件。")
        sys.exit(1)

    try:
        asyncio.run(_async_main(settings, host=args.host, port=args.port))
    except KeyboardInterrupt:
        print("\nServer stopped.")


async def _async_main(settings: object, *, host: str = "127.0.0.1", port: int = 9731) -> None:
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
    from .history_store import SessionStore
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

        # Session manager（含历史持久化）
        session_store = SessionStore(data_dir)
        session_mgr = SessionManager(
            client=client,
            memory=memory,
            tool_registry=registry,
            skill_matcher=skill_matcher,
            system_prompt=system_prompt,
            max_history_turns=settings.max_history_turns,
            max_context_tokens=settings.max_context_tokens,
            reserved_output_tokens=settings.reserved_output_tokens,
            store=session_store,
        )

        # FastAPI app
        app = create_app(session_mgr)

        # 启动 uvicorn
        config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level="info",
        )
        server = uvicorn.Server(config)

        print(f"\n  Agent Xi Server")
        print("  ─────────────────────────────")
        print(f"  WebSocket: ws://{host}:{port}/ws/chat")
        print(f"  Health:    http://{host}:{port}/api/health")
        if (Path(__file__).parent.parent.parent.parent / "web" / "dist").exists():
            print(f"  Web UI:    http://{host}:{port}/")
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
