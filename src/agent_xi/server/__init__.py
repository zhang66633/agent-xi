"""Agent Xi WebSocket Server。

FastAPI + WebSocket，将 Brain 的流式事件推送给浏览器前端。
"""

from .app import create_app

__all__ = ["create_app"]
