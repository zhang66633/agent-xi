"""内置工具集 — 支持自动发现。

新增工具只需在此目录下创建 .py 文件，定义一个 Tool 子类即可。
`load_all_builtins()` 会自动扫描并实例化所有 Tool 子类。
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from pathlib import Path

from ..base import Tool

# 显式导出（向后兼容）
from .calculator import CalculatorTool
from .get_time import GetTimeTool
from .http_request import HttpRequestTool
from .list_dir import ListDirTool
from .read_file import ReadFileTool
from .shell import ExecuteShellTool
from .web_search import WebSearchTool
from .write_file import WriteFileTool

__all__ = [
    "CalculatorTool",
    "ExecuteShellTool",
    "GetTimeTool",
    "HttpRequestTool",
    "ListDirTool",
    "ReadFileTool",
    "WebSearchTool",
    "WriteFileTool",
    "load_all_builtins",
]


def load_all_builtins() -> list[Tool]:
    """自动发现并实例化 builtins 目录下所有 Tool 子类。

    扫描当前包下所有 .py 模块，找到 Tool 的具体子类（非抽象），
    无参实例化后返回。

    Returns:
        所有内置工具的实例列表。
    """
    tools: list[Tool] = []
    seen: set[type] = set()

    package_dir = Path(__file__).parent

    for module_info in pkgutil.iter_modules([str(package_dir)]):
        if module_info.name.startswith("_"):
            continue

        module = importlib.import_module(f".{module_info.name}", __package__)

        for _name, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, Tool)
                and obj is not Tool
                and not inspect.isabstract(obj)
                and obj not in seen
            ):
                seen.add(obj)
                tools.append(obj())

    return tools
