"""Computer Use 工具 — 鼠标点击、键盘输入、窗口操作。

安全分级：全部 DANGEROUS（桌面控制涉及最高安全风险）。
每个操作都需要用户确认才能执行。

依赖：pyautogui（跨平台桌面自动化）
"""

from __future__ import annotations

import logging
from typing import Any

from ..base import SecurityLevel, Tool, ToolResult

logger = logging.getLogger(__name__)


class ComputerUseTool(Tool):
    """桌面控制：鼠标点击、键盘输入、窗口操作。

    基于 pyautogui 的跨平台桌面自动化。
    所有操作均为 DANGEROUS 级别，需要用户确认。
    """

    @property
    def name(self) -> str:
        return "computer_use"

    @property
    def description(self) -> str:
        return (
            "控制桌面操作：鼠标移动/点击、键盘输入、按键组合、"
            "获取屏幕尺寸和鼠标位置。所有操作需要用户确认。"
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "操作类型",
                    "enum": [
                        "move_mouse",
                        "click",
                        "double_click",
                        "right_click",
                        "type_text",
                        "press_key",
                        "hotkey",
                        "scroll",
                        "get_position",
                        "get_screen_size",
                    ],
                },
                "x": {
                    "type": "integer",
                    "description": "X 坐标（move_mouse、click 时使用）",
                },
                "y": {
                    "type": "integer",
                    "description": "Y 坐标（move_mouse、click 时使用）",
                },
                "text": {
                    "type": "string",
                    "description": "要输入的文本（type_text 时使用）",
                },
                "key": {
                    "type": "string",
                    "description": "按键名称（press_key 时使用），如 'enter', 'esc', 'tab'",
                },
                "keys": {
                    "type": "string",
                    "description": "组合键（hotkey 时使用），用 + 连接，如 'ctrl+c', 'alt+tab'",
                },
                "scroll_amount": {
                    "type": "integer",
                    "description": "滚动量（scroll 时使用），正数向上，负数向下",
                },
            },
            "required": ["action"],
        }

    @property
    def security_level(self) -> SecurityLevel:
        return SecurityLevel.DANGEROUS

    async def execute(self, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "")

        try:
            import pyautogui

            # 安全设置：操作间有短暂延迟，给用户反应时间
            pyautogui.PAUSE = 0.5
            pyautogui.FAILSAFE = True  # 鼠标移到左上角时中止

        except ImportError:
            return ToolResult(
                success=False,
                output="",
                error="Computer Use 需要 pyautogui 库。请运行: pip install pyautogui",
            )

        try:
            result = await self._dispatch(pyautogui, action, kwargs)
            return result
        except pyautogui.FailSafeException:
            return ToolResult(
                success=False,
                output="",
                error="操作被 Failsafe 中断（鼠标移到了屏幕左上角）",
            )
        except Exception as e:
            logger.exception("Computer Use 操作失败: %s", action)
            return ToolResult(
                success=False,
                output="",
                error=f"操作失败 ({action}): {e}",
            )

    async def _dispatch(
        self, pg: Any, action: str, kwargs: dict[str, Any]
    ) -> ToolResult:
        """分发执行具体操作。"""
        match action:
            case "move_mouse":
                x, y = kwargs.get("x", 0), kwargs.get("y", 0)
                pg.moveTo(x, y, duration=0.3)
                return ToolResult(
                    success=True,
                    output=f"鼠标已移动到 ({x}, {y})",
                )

            case "click":
                x = kwargs.get("x")
                y = kwargs.get("y")
                if x is not None and y is not None:
                    pg.click(x, y)
                    return ToolResult(
                        success=True,
                        output=f"已点击 ({x}, {y})",
                    )
                pg.click()
                return ToolResult(
                    success=True,
                    output="已点击当前位置",
                )

            case "double_click":
                x = kwargs.get("x")
                y = kwargs.get("y")
                if x is not None and y is not None:
                    pg.doubleClick(x, y)
                    return ToolResult(
                        success=True,
                        output=f"已双击 ({x}, {y})",
                    )
                pg.doubleClick()
                return ToolResult(
                    success=True,
                    output="已双击当前位置",
                )

            case "right_click":
                x = kwargs.get("x")
                y = kwargs.get("y")
                if x is not None and y is not None:
                    pg.rightClick(x, y)
                    return ToolResult(
                        success=True,
                        output=f"已右键点击 ({x}, {y})",
                    )
                pg.rightClick()
                return ToolResult(
                    success=True,
                    output="已右键点击当前位置",
                )

            case "type_text":
                text = kwargs.get("text", "")
                if not text:
                    return ToolResult(
                        success=False,
                        output="",
                        error="type_text 需要提供 text 参数",
                    )
                pg.typewrite(text, interval=0.05)
                return ToolResult(
                    success=True,
                    output=f"已输入文本（{len(text)} 字符）",
                )

            case "press_key":
                key = kwargs.get("key", "")
                if not key:
                    return ToolResult(
                        success=False,
                        output="",
                        error="press_key 需要提供 key 参数",
                    )
                pg.press(key)
                return ToolResult(
                    success=True,
                    output=f"已按下按键: {key}",
                )

            case "hotkey":
                keys = kwargs.get("keys", "")
                if not keys:
                    return ToolResult(
                        success=False,
                        output="",
                        error="hotkey 需要提供 keys 参数（如 'ctrl+c'）",
                    )
                key_list = [k.strip() for k in keys.split("+")]
                pg.hotkey(*key_list)
                return ToolResult(
                    success=True,
                    output=f"已执行组合键: {keys}",
                )

            case "scroll":
                amount = kwargs.get("scroll_amount", 0)
                pg.scroll(amount)
                direction = "上" if amount > 0 else "下"
                return ToolResult(
                    success=True,
                    output=f"已滚动 {abs(amount)} 步（{direction}）",
                )

            case "get_position":
                pos = pg.position()
                return ToolResult(
                    success=True,
                    output=f"当前鼠标位置: ({pos.x}, {pos.y})",
                )

            case "get_screen_size":
                size = pg.size()
                return ToolResult(
                    success=True,
                    output=f"屏幕尺寸: {size.width}x{size.height}",
                )

            case _:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"未知操作: {action}",
                )