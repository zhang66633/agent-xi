"""FastAPI 应用 — 路由注册 + 静态文件服务。"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .session import SessionManager
from .ws_chat import handle_ws_chat

# 前端构建产物目录
_WEB_DIST = Path(__file__).parent.parent.parent.parent / "web" / "dist"


def create_app(session_manager: SessionManager) -> FastAPI:
    """创建 FastAPI 应用。"""
    app = FastAPI(title="Agent Xi Server", version="0.5.0")

    # CORS（开发时允许 Vite dev server）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ─── WebSocket 对话 ────────────────────────────────────────────

    @app.websocket("/ws/chat")
    async def ws_chat(ws: WebSocket) -> None:
        """WebSocket 对话端点。"""
        session = session_manager.create_session(platform="web")
        try:
            await handle_ws_chat(ws, session)
        finally:
            session_manager.remove_session(session.id)

    # ─── REST API ──────────────────────────────────────────────────

    @app.get("/api/health")
    async def health() -> dict:
        """健康检查。"""
        return {
            "status": "ok",
            "sessions": session_manager.active_count,
        }

    @app.get("/api/tools")
    async def list_tools() -> dict:
        """列出所有已注册工具。"""
        tools = session_manager._registry.list_tools()
        return {
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "security_level": t.security_level.value,
                }
                for t in tools
            ]
        }

    @app.get("/api/memory/stats")
    async def memory_stats() -> dict:
        """记忆统计。"""
        memory = session_manager._memory
        return {
            "episodic_count": memory.episodic.count,
            "semantic_count": memory.semantic.count,
        }

    @app.get("/api/skills")
    async def list_skills() -> dict:
        """列出所有技能。"""
        if not session_manager._skill_matcher:
            return {"skills": []}
        store = session_manager._skill_matcher._store
        skills = store.list_all()
        return {
            "skills": [
                {
                    "id": s.id,
                    "name": s.name,
                    "description": s.description,
                    "use_count": s.use_count,
                }
                for s in skills
            ]
        }

    # ─── 市场 API ─────────────────────────────────────────────────

    @app.get("/api/market/mcp")
    async def market_mcp() -> dict:
        """列出可安装的 MCP 服务器。"""
        from .market import MCP_MARKET
        return {"items": MCP_MARKET}

    @app.get("/api/market/skills")
    async def market_skills() -> dict:
        """列出可安装的技能包。"""
        from .market import SKILL_MARKET
        return {"items": SKILL_MARKET}

    @app.post("/api/market/install")
    async def market_install(data: dict) -> dict:
        """安装 MCP 服务器或技能。"""
        item_type = data.get("type", "")  # "mcp" | "skill"
        item_id = data.get("id", "")
        if not item_type or not item_id:
            return {"ok": False, "error": "缺少 type 或 id"}

        if item_type == "mcp":
            from .market import install_mcp
            result = install_mcp(item_id)
        elif item_type == "skill":
            from .market import install_skill
            result = install_skill(item_id)
        else:
            return {"ok": False, "error": f"未知类型: {item_type}"}

        return result

    # ─── 静态文件（生产模式）────────────────────────────────────────

    if _WEB_DIST.exists():
        app.mount(
            "/",
            StaticFiles(directory=str(_WEB_DIST), html=True),
            name="static",
        )

    return app
