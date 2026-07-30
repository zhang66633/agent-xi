"""截图工具 — 捕获屏幕截图。

支持 Windows、macOS、Linux。
安全分级：DANGEROUS（涉及屏幕捕获隐私）。
"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from ..base import SecurityLevel, Tool, ToolResult

logger = logging.getLogger(__name__)

_SYSTEM = platform.system()


class ScreenshotTool(Tool):
    """捕获当前屏幕截图。

    截图保存到临时文件，返回路径供 LLM 分析。
    注意：当前 LLM 需要支持图片理解才能分析截图内容。
    """

    @property
    def name(self) -> str:
        return "screenshot"

    @property
    def description(self) -> str:
        return "捕获当前屏幕截图，保存为 PNG 文件。返回截图文件路径。"

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "region": {
                    "type": "string",
                    "description": "截取区域：'full'（全屏，默认）或 'active'（当前活动窗口）",
                    "enum": ["full", "active"],
                },
            },
            "required": [],
        }

    @property
    def security_level(self) -> SecurityLevel:
        return SecurityLevel.DANGEROUS

    async def execute(self, **kwargs: Any) -> ToolResult:
        region = kwargs.get("region", "full")

        try:
            import time

            timestamp = int(time.time())
            output_dir = Path(tempfile.gettempdir()) / "agent_xi_screenshots"
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"screenshot_{timestamp}.png"

            if _SYSTEM == "Windows":
                await self._screenshot_windows(output_path, region)
            elif _SYSTEM == "Darwin":
                await self._screenshot_macos(output_path, region)
            else:
                await self._screenshot_linux(output_path, region)

            return ToolResult(
                success=True,
                output=(
                    f"截图已保存到: {output_path}\n"
                    f"文件大小: {output_path.stat().st_size} bytes\n"
                    f"注意: 当前模型可能需要图片理解能力来分析截图内容。"
                ),
                metadata={
                    "path": str(output_path),
                    "size": output_path.stat().st_size,
                    "region": region,
                },
            )
        except ImportError:
            return ToolResult(
                success=False,
                output="",
                error="截图功能需要 Pillow 库。请运行: pip install Pillow",
            )
        except Exception as e:
            logger.exception("Screenshot failed")
            return ToolResult(
                success=False,
                output="",
                error=f"截图失败: {e}",
            )

    async def _screenshot_windows(self, path: Path, region: str) -> None:
        """Windows 截图：使用 Pillow + pyautogui 或直接调用 Win32 API。"""
        try:
            from PIL import ImageGrab

            if region == "active":
                import subprocess
                import sys

                # 尝试使用 pygetwindow 获取活动窗口
                try:
                    import pygetwindow as gw

                    win = gw.getActiveWindow()
                    if win:
                        bbox = (win.left, win.top, win.right, win.bottom)
                        img = ImageGrab.grab(bbox)
                        img.save(str(path), "PNG")
                        return
                except ImportError:
                    pass

            # 默认全屏
            img = ImageGrab.grab()
            img.save(str(path), "PNG")
        except ImportError:
            raise ImportError("需要 Pillow: pip install Pillow")

    async def _screenshot_macos(self, path: Path, region: str) -> None:
        """macOS 截图：使用 screencapture 命令。"""
        args = ["screencapture", "-x"]  # -x 不播放快门声
        if region == "active":
            args.append("-w")  # 只截活动窗口
        args.append(str(path))
        subprocess.run(args, check=True, capture_output=True)

    async def _screenshot_linux(self, path: Path, region: str) -> None:
        """Linux 截图：尝试多种截图工具。"""
        for cmd in [
            ["gnome-screenshot", "-f", str(path)],
            ["import", "-window", "root", str(path)],  # ImageMagick
            ["scrot", str(path)],
        ]:
            try:
                subprocess.run(cmd, check=True, capture_output=True, timeout=10)
                if path.exists() and path.stat().st_size > 0:
                    return
            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                continue

        raise RuntimeError(
            "未找到可用的截图工具。请安装: gnome-screenshot、imagemagick 或 scrot"
        )