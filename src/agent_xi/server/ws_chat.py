"""WebSocket 对话处理。

核心职责：
- 接收客户端消息 → 调用 Brain.chat() → 逐事件推送 JSON
- 工具确认：推送 confirm_request → 等待客户端回复 → asyncio.Event 唤醒
- 命令处理（/clear, /history 等）
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from ..llm.types import StreamEventType
from .session import Session

logger = logging.getLogger(__name__)


async def handle_ws_chat(
    ws: WebSocket,
    session: Session,
) -> None:
    """处理单个 WS 连接的对话循环。

    协议：
    客户端 → 服务端：
      {"type": "chat", "content": "你好"}
      {"type": "confirm_tool", "tool_id": "xxx", "allowed": true}
      {"type": "command", "content": "/clear"}

    服务端 → 客户端：
      {"type": "text_delta", "text": "你"}
      {"type": "tool_use_start", "tool_name": "get_time"}
      {"type": "tool_result", "tool_name": "get_time", "preview": "..."}
      {"type": "tool_confirm_request", "tool_id": "...", "tool_name": "...", "args": {...}}
      {"type": "done"}
      {"type": "error", "message": "..."}
      {"type": "system", "message": "..."}
    """
    await ws.accept()
    logger.info("WS connected: session=%s", session.id)

    # 工具确认机制
    confirm_event = asyncio.Event()
    confirm_result: dict[str, bool] = {}

    async def ws_confirm_callback(
        tool_name: str, arguments: dict[str, Any]
    ) -> bool:
        """通过 WS 推送确认请求，等待客户端回复。"""
        confirm_event.clear()
        confirm_result.clear()

        await ws.send_json({
            "type": "tool_confirm_request",
            "tool_name": tool_name,
            "args": arguments,
        })

        # 等待客户端回复（超时 60s 自动拒绝）
        try:
            await asyncio.wait_for(confirm_event.wait(), timeout=60)
        except asyncio.TimeoutError:
            return False

        return confirm_result.get("allowed", False)

    # 注入 confirm_callback 到 Brain
    brain = session.brain
    if brain:
        brain._confirm_callback = ws_confirm_callback

    try:
        while True:
            # 接收客户端消息
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({
                    "type": "error",
                    "message": "无效的 JSON 格式",
                })
                continue

            msg_type = msg.get("type", "")

            # ─── 工具确认回复 ───
            if msg_type == "confirm_tool":
                confirm_result["allowed"] = msg.get("allowed", False)
                confirm_event.set()
                continue

            # ─── 命令处理 ───
            if msg_type == "command":
                await _handle_command(ws, brain, msg.get("content", ""))
                continue

            # ─── 对话消息 ───
            if msg_type == "chat":
                content = msg.get("content", "").strip()
                if not content:
                    continue

                # 检查是否是斜杠命令
                if content.startswith("/"):
                    await _handle_command(ws, brain, content)
                    continue

                if not brain:
                    await ws.send_json({
                        "type": "error",
                        "message": "会话未初始化",
                    })
                    continue

                # 流式调用 Brain，逐事件推送
                try:
                    async for event in brain.chat(content):
                        ws_msg = _event_to_ws_message(event)
                        if ws_msg:
                            await ws.send_json(ws_msg)
                except Exception as e:
                    logger.exception("Brain.chat error")
                    await ws.send_json({
                        "type": "error",
                        "message": f"处理失败：{e}",
                    })

                # 发送 done 标记
                await ws.send_json({"type": "done"})

    except WebSocketDisconnect:
        logger.info("WS disconnected: session=%s", session.id)
    except Exception as e:
        logger.error("WS error: %s", e)


def _event_to_ws_message(event: Any) -> dict[str, Any] | None:
    """将 StreamEvent 转换为 WS JSON 消息。"""
    match event.type:
        case StreamEventType.TEXT_DELTA:
            return {"type": "text_delta", "text": event.text}

        case StreamEventType.TOOL_USE_START:
            return {"type": "tool_use_start", "tool_name": event.tool_name}

        case StreamEventType.TOOL_EXECUTING:
            return {
                "type": "tool_executing",
                "tool_name": event.tool_name,
            }

        case StreamEventType.TOOL_RESULT:
            return {
                "type": "tool_result",
                "tool_name": event.tool_name,
                "preview": event.text,
            }

        case StreamEventType.TOOL_CONFIRM_DENIED:
            return {
                "type": "tool_denied",
                "tool_name": event.tool_name,
            }

        case StreamEventType.ERROR:
            return {"type": "error", "message": event.error}

        case StreamEventType.DONE:
            # Brain 内部的 DONE 不直接转发，由外层统一发
            return None

        case _:
            return None


async def _handle_command(
    ws: WebSocket, brain: Any, command: str
) -> None:
    """处理斜杠命令。"""
    parts = command.split(maxsplit=1)
    cmd = parts[0].lower()

    match cmd:
        case "/clear":
            if brain:
                brain.clear_history()
            await ws.send_json({
                "type": "system",
                "message": "对话已清空",
            })

        case "/history":
            turns = brain.turn_count if brain else 0
            await ws.send_json({
                "type": "system",
                "message": f"当前对话：{turns} 轮",
            })

        case "/help":
            await ws.send_json({
                "type": "system",
                "message": (
                    "可用命令：/clear（清空）、/history（轮次）、"
                    "/memory（记忆统计）、/skills（技能列表）、/help"
                ),
            })

        case _:
            await ws.send_json({
                "type": "system",
                "message": f"未知命令：{cmd}",
            })
