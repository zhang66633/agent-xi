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

    # CORS — 仅允许本机来源（Vite dev server / 后端自身 / 常见本地端口）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5180",
            "http://127.0.0.1:5180",
            "http://localhost:9731",
            "http://127.0.0.1:9731",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ─── WebSocket 对话 ────────────────────────────────────────────

    @app.websocket("/ws/chat")
    async def ws_chat(ws: WebSocket, session_id: str | None = None) -> None:
        """WebSocket 对话端点。

        查询参数 session_id：前端 localStorage 中保存的会话标识，
        携带时恢复该会话的对话历史（刷新页面不丢上下文）。
        """
        session, restored = session_manager.get_or_create_session(
            session_id, platform="web"
        )
        try:
            await handle_ws_chat(ws, session, session_manager)
        finally:
            session_manager.save_session(session)
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

    @app.get("/api/history")
    async def get_history(session_id: str = "") -> dict:
        """获取会话的持久化历史（供前端刷新后重建日志）。

        返回 user / assistant 的纯文本消息（工具消息不入日志）。
        """
        from .history_store import SessionStore, is_valid_session_id

        if not session_id or not is_valid_session_id(session_id):
            return {"ok": False, "messages": []}

        store: SessionStore | None = getattr(
            session_manager, "_store", None
        )
        if store is None or not store.exists(session_id):
            return {"ok": False, "messages": []}

        from ..llm.types import Role

        history = store.load_history(session_id)
        messages = [
            {"role": str(m.role), "text": m.text}
            for m in history
            if m.role in (Role.USER, Role.ASSISTANT) and m.text.strip()
        ][-100:]
        return {"ok": True, "messages": messages}

    # ─── 市场 API ─────────────────────────────────────────────────

    def _skill_store():
        """取 SessionManager 持有的 SkillStore（可能为 None）。"""
        matcher = getattr(session_manager, "_skill_matcher", None)
        return matcher._store if matcher else None

    @app.get("/api/market/mcp")
    async def market_mcp() -> dict:
        """列出可安装的 MCP 服务器（installed 以 mcp.yaml 为准）。"""
        from .market import MCP_MARKET, sync_installed_states
        sync_installed_states(_skill_store())
        # MCP 配置变更需重启后端才能生效（暂不支持热加载）
        items = [{**m, "needs_restart": True} for m in MCP_MARKET]
        return {"items": items}

    @app.get("/api/market/skills")
    async def market_skills() -> dict:
        """列出可安装的技能包（installed 以 SkillStore 为准）。"""
        from .market import SKILL_MARKET, sync_installed_states
        sync_installed_states(_skill_store())
        return {"items": SKILL_MARKET}

    @app.post("/api/market/install")
    async def market_install(data: dict) -> dict:
        """安装 MCP 服务器或技能。MCP 可携带 env 值。"""
        item_type = data.get("type", "")  # "mcp" | "skill"
        item_id = data.get("id", "")
        if not item_type or not item_id:
            return {"ok": False, "error": "缺少 type 或 id"}

        if item_type == "mcp":
            from .market import install_mcp
            env = data.get("env") if isinstance(data.get("env"), dict) else None
            result = install_mcp(item_id, env)
        elif item_type == "skill":
            from .market import install_skill
            result = await install_skill(item_id, _skill_store())
        else:
            return {"ok": False, "error": f"未知类型: {item_type}"}

        return result

    @app.post("/api/market/uninstall")
    async def market_uninstall(data: dict) -> dict:
        """卸载 MCP 服务器或技能。"""
        item_type = data.get("type", "")  # "mcp" | "skill"
        item_id = data.get("id", "")
        if not item_type or not item_id:
            return {"ok": False, "error": "缺少 type 或 id"}

        if item_type == "mcp":
            from .market import uninstall_mcp
            result = uninstall_mcp(item_id)
        elif item_type == "skill":
            from .market import uninstall_skill
            result = await uninstall_skill(item_id, _skill_store())
        else:
            return {"ok": False, "error": f"未知类型: {item_type}"}

        return result

    # ─── 设置 API ─────────────────────────────────────────────────

    @app.get("/api/settings/keys")
    async def settings_keys() -> dict:
        """API Key 列表（masked，永不回传明文）。"""
        from .settings_api import list_keys
        return {"keys": list_keys()}

    @app.post("/api/settings/keys")
    async def settings_save_key(data: dict) -> dict:
        """保存 API Key 到 .env（重启后端生效）。"""
        from .settings_api import save_key
        var = data.get("var", "")
        key = data.get("key", "")
        if not var or not key:
            return {"ok": False, "error": "缺少 var 或 key"}
        return save_key(var, key)

    @app.get("/api/memory/recent")
    async def memory_recent(limit: int = 5) -> dict:
        """最近 N 条语义记忆（设置页展示用，上限 20）。"""
        memory = session_manager._memory
        facts = memory.semantic.get_all(limit=max(1, min(limit, 20)))
        return {
            "facts": [
                {
                    "content": f["content"],
                    "category": f["category"],
                    "updated_at": f["updated_at"],
                }
                for f in facts
            ]
        }

    # ─── 静态文件（生产模式）────────────────────────────────────────

    if _WEB_DIST.exists():
        app.mount(
            "/",
            StaticFiles(directory=str(_WEB_DIST), html=True),
            name="static",
        )

    return app
