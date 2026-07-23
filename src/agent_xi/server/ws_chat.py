"""WebSocket 对话处理。

核心职责：
- 接收客户端消息 → 调用 Brain.chat() → 逐事件推送 JSON
- 工具确认：推送 confirm_request → 等待客户端回复 → asyncio.Event 唤醒
- 命令处理（/clear, /history 等）
- 会话持久化：连接建立时下发 session_init（含 session_id），
  每轮对话结束后通过 SessionManager 落盘历史
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

from fastapi import WebSocket, WebSocketDisconnect

from ..llm.types import StreamEventType
from .session import Session

if TYPE_CHECKING:
    from .session import SessionManager

logger = logging.getLogger(__name__)


async def handle_ws_chat(
    ws: WebSocket,
    session: Session,
    session_manager: SessionManager | None = None,
) -> None:
    """处理单个 WS 连接的对话循环。

    协议：
    客户端 → 服务端：
      {"type": "chat", "content": "你好"}
      {"type": "chat", "content": "看看这个", "attachments": [
          {"file_id": "abc123", "name": "a.png", "size": 1024, "mime": "image/png"}]}
      {"type": "confirm_tool", "tool_id": "xxx", "allowed": true}
      {"type": "command", "content": "/clear"}

    服务端 → 客户端：
      {"type": "session_init", "session_id": "...", "restored": true, "turns": 3}
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

    # 下发会话标识（前端存入 localStorage，重连时上报以恢复历史）
    brain = session.brain
    await ws.send_json({
        "type": "session_init",
        "session_id": session.id,
        "restored": brain.turn_count > 0 if brain else False,
        "turns": brain.turn_count if brain else 0,
    })

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
                await _handle_command(
                    ws, brain, msg.get("content", ""), session, session_manager
                )
                continue

            # ─── 对话消息 ───
            if msg_type == "chat":
                content = msg.get("content", "").strip()
                raw_attachments = msg.get("attachments")
                attachments = raw_attachments if isinstance(raw_attachments, list) else []

                if not content and not attachments:
                    continue

                # 检查是否是斜杠命令
                if content.startswith("/"):
                    await _handle_command(
                        ws, brain, content, session, session_manager
                    )
                    continue

                if not brain:
                    await ws.send_json({
                        "type": "error",
                        "message": "会话未初始化",
                    })
                    continue

                # 附件上下文注入（校验 file_id 存在 → 拼入用户消息）
                attach_ctx = _build_attachment_context(session.id, attachments)
                if attach_ctx:
                    content = f"{content}\n\n{attach_ctx}" if content else attach_ctx

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

                # 持久化会话历史（刷新 / 重连后可恢复）
                if session_manager:
                    session_manager.save_session(session)

    except WebSocketDisconnect:
        logger.info("WS disconnected: session=%s", session.id)
    except Exception as e:
        logger.error("WS error: %s", e)
    finally:
        # 会话结束 → LLM 深度提取语义记忆（与 CLI 行为对齐）
        await _extract_on_close(brain)


async def _extract_on_close(brain: Any) -> None:
    """连接关闭时触发深度记忆提取，失败不影响清理流程。"""
    memory = getattr(brain, "_memory", None) if brain else None
    if not memory or brain.turn_count < 1:
        return
    try:
        extracted = await memory.on_conversation_end(brain.history)
        if extracted:
            logger.info("会话结束提取：%d 条新记忆", len(extracted))
    except Exception:
        logger.exception("会话结束记忆提取失败")


def _build_attachment_context(session_id: str, attachments: list) -> str:
    """校验附件并构建上下文注入文本（拼入用户消息交给 Brain）。

    - file_id 不存在于会话上传目录的附件直接跳过（记 warning）
    - 图片：说明路径 + 暂不支持图片理解
    - 其他文件：说明路径 + 可用 read_file 工具查看
    """
    from .uploads import resolve_attachment

    lines: list[str] = []
    for att in attachments:
        if not isinstance(att, dict):
            continue
        file_id = str(att.get("file_id", ""))
        info = resolve_attachment(session_id, file_id)
        if not info:
            logger.warning("附件不存在，已跳过: file_id=%s", file_id)
            continue
        name = att.get("name") or info["name"]
        mime = str(att.get("mime") or info["mime"])
        if mime.startswith("image/"):
            lines.append(
                f"[附件] 用户上传了图片 {name}（路径 {info['path']}），"
                "当前暂不支持图片理解，请告知用户图片已保存但暂无法识别内容。"
            )
        else:
            lines.append(
                f"[附件] 用户上传了文件 {name}（路径 {info['path']}），"
                "可用 read_file 工具查看内容。"
            )
    return "\n".join(lines)


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
    ws: WebSocket,
    brain: Any,
    command: str,
    session: Session | None = None,
    session_manager: SessionManager | None = None,
) -> None:
    """处理斜杠命令。"""
    parts = command.split(maxsplit=1)
    cmd = parts[0].lower()

    match cmd:
        case "/clear":
            if brain:
                brain.clear_history()
            # 同步清空持久化历史，避免刷新后"复活"
            if session and session_manager:
                session_manager.save_session(session)
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

        case "/memory":
            memory = getattr(brain, "_memory", None) if brain else None
            if not memory:
                await ws.send_json({
                    "type": "system",
                    "message": "记忆系统未初始化",
                })
                return
            ep = memory.episodic.count
            profile = memory.get_profile_summary()
            lines = [f"记忆统计：情景记忆 {ep} 条"]
            if profile:
                lines.append(f"用户画像：\n{profile}")
            else:
                lines.append("（还没有建立对你的认知）")
            await ws.send_json({
                "type": "system",
                "message": "\n".join(lines),
            })

        case "/skills":
            matcher = getattr(brain, "_skill_matcher", None) if brain else None
            store = getattr(matcher, "_store", None) if matcher else None
            if not store:
                await ws.send_json({
                    "type": "system",
                    "message": "技能系统未初始化",
                })
                return
            skills = store.list_all()
            if skills:
                lines = [f"已装技能：{len(skills)} 个"]
                lines.extend(
                    f"- {s.name}（使用 {s.use_count} 次）" for s in skills
                )
            else:
                lines = ["还没有安装任何技能"]
            await ws.send_json({
                "type": "system",
                "message": "\n".join(lines),
            })

        case "/remember":
            content = parts[1].strip() if len(parts) > 1 else ""
            memory = getattr(brain, "_memory", None) if brain else None
            if not content:
                await ws.send_json({
                    "type": "system",
                    "message": "用法：/remember <要记住的内容>",
                })
                return
            if not memory:
                await ws.send_json({
                    "type": "system",
                    "message": "记忆系统未初始化",
                })
                return
            try:
                await memory.remember_episode(content, tags=["user_explicit"])
                await ws.send_json({
                    "type": "system",
                    "message": f"已记住：{content}",
                })
            except Exception as e:
                logger.error("remember_episode failed: %s", e)
                await ws.send_json({
                    "type": "system",
                    "message": f"记忆失败：{e}",
                })

        case "/help":
            await ws.send_json({
                "type": "system",
                "message": (
                    "可用命令：/clear（清空）、/history（轮次）、"
                    "/memory（记忆统计）、/skills（技能列表）、"
                    "/remember <内容>（记住某事）、/help"
                ),
            })

        case _:
            await ws.send_json({
                "type": "system",
                "message": f"未知命令：{cmd}",
            })
