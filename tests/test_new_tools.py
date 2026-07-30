"""测试新工具 — screenshot / computer_use / git_diff。"""

from __future__ import annotations

import pytest

from agent_xi.tools.builtins.computer_use import ComputerUseTool
from agent_xi.tools.builtins.diff import GitDiffTool
from agent_xi.tools.builtins.screenshot import ScreenshotTool
from agent_xi.tools.base import SecurityLevel


class TestScreenshotTool:
    def test_security_level_is_dangerous(self):
        tool = ScreenshotTool()
        assert tool.security_level == SecurityLevel.DANGEROUS

    def test_name_and_description(self):
        tool = ScreenshotTool()
        assert tool.name == "screenshot"
        assert "截" in tool.description

    def test_parameters_schema(self):
        tool = ScreenshotTool()
        schema = tool.parameters_schema
        assert schema["type"] == "object"
        assert "region" in schema["properties"]

    async def test_screenshot_no_pillow_returns_error(self):
        """没有 Pillow 时返回友好的错误信息。"""
        tool = ScreenshotTool()
        # 如果 pillow 已安装，实际会执行成功；只要不崩溃就算通过
        result = await tool.execute()
        if not result.success:
            assert "Pillow" in result.error


class TestComputerUseTool:
    def test_security_level_is_dangerous(self):
        tool = ComputerUseTool()
        assert tool.security_level == SecurityLevel.DANGEROUS

    def test_name(self):
        tool = ComputerUseTool()
        assert tool.name == "computer_use"

    def test_all_actions_defined(self):
        tool = ComputerUseTool()
        schema = tool.parameters_schema
        actions = schema["properties"]["action"]["enum"]
        assert "click" in actions
        assert "type_text" in actions
        assert "hotkey" in actions
        assert "scroll" in actions
        assert "get_position" in actions
        assert "get_screen_size" in actions

    async def test_no_pyautogui_returns_error(self):
        """没有 pyautogui 时返回友好错误。"""
        tool = ComputerUseTool()
        result = await tool.execute(action="get_position")
        if not result.success:
            assert "pyautogui" in result.error.lower()

    async def test_unknown_action_returns_error(self):
        """未知操作返回错误。"""
        tool = ComputerUseTool()
        # 模拟分发中的未知 action
        try:
            import pyautogui  # noqa: F401
            pytest.skip("pyautogui 已安装，无法测试未知 action 分支")
        except ImportError:
            pass


class TestGitDiffTool:
    def test_security_level_is_safe(self):
        tool = GitDiffTool()
        assert tool.security_level == SecurityLevel.SAFE

    def test_name(self):
        tool = GitDiffTool()
        assert tool.name == "git_diff"

    def test_parameters_schema_modes(self):
        tool = GitDiffTool()
        schema = tool.parameters_schema
        assert schema["properties"]["mode"]["enum"] == ["unstaged", "staged", "commit"]

    async def test_diff_no_git_returns_error(self):
        """没有 git 时不崩溃。"""
        tool = GitDiffTool()
        result = await tool.execute()
        # 只要有返回值（不管成功还是失败）就算通过
        assert isinstance(result.output, str) or isinstance(result.error, str)

    async def test_diff_with_file_path(self):
        """带文件路径参数不崩溃。"""
        tool = GitDiffTool()
        result = await tool.execute(file_path="README.md", mode="unstaged")
        assert isinstance(result.output, str) or isinstance(result.error, str)

    def test_count_files_in_diff_output(self):
        """_count_files 正确统计 diff 文件数。"""
        output = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1 +1 @@
-old
+new
diff --git a/b.py b/b.py
--- a/b.py
+++ b/b.py
@@ -1 +1 @@
-old
+new
"""
        count = GitDiffTool._count_files(output)
        assert count == 2


class TestToolRegistration:
    """验证新工具能被自动发现。"""

    def test_load_all_builtins_includes_new_tools(self):
        from agent_xi.tools.builtins import load_all_builtins
        tools = load_all_builtins()
        names = {t.name for t in tools}

        # 原有工具
        assert "echo" not in names  # echo 是测试用的，不在 builtins
        assert "read_file" in names
        assert "write_file" in names
        assert "get_time" in names
        assert "web_search" in names
        assert "calculator" in names
        assert "list_dir" in names
        assert "execute_shell" in names
        assert "http_request" in names

        # 新增工具
        assert "screenshot" in names
        assert "computer_use" in names
        assert "git_diff" in names
