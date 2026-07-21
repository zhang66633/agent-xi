"""插件市场注册表 — MCP 服务器 + 技能包。

提供可安装项的元数据列表和安装逻辑。
安装 MCP = 写入 config/mcp.yaml；安装 Skill = 写入 skills 数据库。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from ..skills.store import SkillStore

logger = logging.getLogger(__name__)

# ─── MCP 市场 ─────────────────────────────────────────────────

MCP_MARKET: list[dict] = [
    {
        "id": "filesystem",
        "name": "Filesystem",
        "description": "读写本地文件系统，支持目录浏览、文件搜索",
        "icon": "▤",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"],
        "installed": False,
    },
    {
        "id": "github",
        "name": "GitHub",
        "description": "操作 GitHub 仓库：PR、Issue、代码搜索",
        "icon": "◈",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env": {"GITHUB_TOKEN": ""},
        "installed": False,
    },
    {
        "id": "sqlite",
        "name": "SQLite",
        "description": "查询 SQLite 数据库，执行 SQL",
        "icon": "▦",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-sqlite", "--db-path", "/path.db"],
        "installed": False,
    },
    {
        "id": "brave-search",
        "name": "Brave Search",
        "description": "网页搜索（Brave Search API）",
        "icon": "◎",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-brave-search"],
        "env": {"BRAVE_API_KEY": ""},
        "installed": False,
    },
    {
        "id": "puppeteer",
        "name": "Puppeteer",
        "description": "浏览器自动化：截图、点击、表单填写",
        "icon": "▣",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-puppeteer"],
        "installed": False,
    },
    {
        "id": "memory",
        "name": "Memory Graph",
        "description": "知识图谱记忆：实体关系存储与检索",
        "icon": "✦",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-memory"],
        "installed": False,
    },
]

# ─── 技能市场 ─────────────────────────────────────────────────

SKILL_MARKET: list[dict] = [
    {
        "id": "code-review",
        "name": "代码审查",
        "description": "自动审查代码质量、安全性、性能问题",
        "icon": "▸",
        "keywords": ["代码", "审查", "review", "质量"],
        "steps": "1. 读取目标文件\n2. 分析代码结构\n3. 检查常见问题\n4. 输出审查报告",
        "installed": False,
    },
    {
        "id": "summarize",
        "name": "文档摘要",
        "description": "将长文档压缩为结构化摘要",
        "icon": "≡",
        "keywords": ["摘要", "总结", "文档", "压缩"],
        "steps": "1. 读取文档内容\n2. 提取关键信息\n3. 生成结构化摘要\n4. 输出 markdown",
        "installed": False,
    },
    {
        "id": "translate",
        "name": "翻译助手",
        "description": "中英互译，保持专业术语准确",
        "icon": "⇄",
        "keywords": ["翻译", "translate", "中文", "英文"],
        "steps": "1. 识别源语言\n2. 翻译为目标语言\n3. 校验术语一致性\n4. 输出译文",
        "installed": False,
    },
    {
        "id": "data-analysis",
        "name": "数据分析",
        "description": "分析 CSV/JSON 数据，生成统计报告和图表建议",
        "icon": "▩",
        "keywords": ["数据", "分析", "统计", "CSV"],
        "steps": "1. 加载数据文件\n2. 基础统计描述\n3. 发现异常值\n4. 给出可视化建议",
        "installed": False,
    },
]


# ─── 配置读写 ─────────────────────────────────────────────────

_CONFIG_DIR = Path(__file__).parent.parent.parent.parent / "config"


def _load_mcp_config() -> dict:
    """读取 config/mcp.yaml。

    注意：servers 键下只有注释时 safe_load 得到 {"servers": None}，
    必须归一化成列表，否则 append 会 AttributeError。
    """
    mcp_yaml = _CONFIG_DIR / "mcp.yaml"
    if mcp_yaml.exists():
        with open(mcp_yaml, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    else:
        config = {}
    if not isinstance(config.get("servers"), list):
        config["servers"] = []
    return config


def _save_mcp_config(config: dict) -> None:
    with open(_CONFIG_DIR / "mcp.yaml", "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)


# ─── 安装 / 卸载逻辑 ──────────────────────────────────────────


def install_mcp(item_id: str, env: dict | None = None) -> dict:
    """将 MCP 服务器配置写入 config/mcp.yaml。

    env: 客户端填入的环境变量值（如 GITHUB_TOKEN），
         与市场默认 env 键合并后写入。
    """
    item = next((m for m in MCP_MARKET if m["id"] == item_id), None)
    if not item:
        return {"ok": False, "error": f"未找到 MCP: {item_id}"}

    config = _load_mcp_config()
    servers: list = config["servers"]

    # 检查是否已安装
    if any(s.get("name") == item_id for s in servers):
        return {"ok": False, "error": f"{item['name']} 已安装"}

    # 写入新服务器配置
    new_entry: dict = {
        "name": item_id,
        "command": item["command"],
        "args": item["args"],
    }
    if "env" in item:
        merged = dict(item["env"])          # 默认键（空值）
        if env:
            merged.update({k: v for k, v in env.items() if v})
        new_entry["env"] = merged

    servers.append(new_entry)
    _save_mcp_config(config)

    item["installed"] = True
    logger.info("MCP installed: %s", item_id)
    return {"ok": True, "message": f"{item['name']} 已安装，重启后生效"}


def uninstall_mcp(item_id: str) -> dict:
    """从 config/mcp.yaml 移除 MCP 服务器条目。"""
    item = next((m for m in MCP_MARKET if m["id"] == item_id), None)
    if not item:
        return {"ok": False, "error": f"未找到 MCP: {item_id}"}

    config = _load_mcp_config()
    servers: list = config["servers"]
    before = len(servers)
    config["servers"] = [s for s in servers if s.get("name") != item_id]

    if len(config["servers"]) == before:
        return {"ok": False, "error": f"{item['name']} 未安装"}

    _save_mcp_config(config)
    item["installed"] = False
    logger.info("MCP uninstalled: %s", item_id)
    return {"ok": True, "message": f"{item['name']} 已卸载，重启后生效"}


async def install_skill(item_id: str, store: SkillStore | None) -> dict:
    """将技能写入 skills 数据库。

    store 由调用方注入（SessionManager 持有的同一实例），
    避免重复打开 SQLite/LanceDB 连接。
    """
    item = next((s for s in SKILL_MARKET if s["id"] == item_id), None)
    if not item:
        return {"ok": False, "error": f"未找到技能: {item_id}"}
    if store is None:
        return {"ok": False, "error": "技能存储不可用（embedding 未配置？）"}

    # 延迟导入避免循环依赖
    try:
        from ..skills.models import Skill

        if store.get(item_id) is not None:
            return {"ok": False, "error": f"{item['name']} 已安装"}

        skill = Skill(
            id=item_id,
            name=item["name"],
            description=item["description"],
            trigger_keywords=item["keywords"],
            steps=item["steps"],
        )
        await store.save(skill)
        item["installed"] = True
        logger.info("Skill installed: %s", item_id)
        return {"ok": True, "message": f"{item['name']} 已安装"}
    except Exception as e:
        logger.error("Skill install failed: %s", e)
        return {"ok": False, "error": str(e)}


async def uninstall_skill(item_id: str, store: SkillStore | None) -> dict:
    """从 skills 数据库删除技能（即时生效）。"""
    item = next((s for s in SKILL_MARKET if s["id"] == item_id), None)
    if not item:
        return {"ok": False, "error": f"未找到技能: {item_id}"}
    if store is None:
        return {"ok": False, "error": "技能存储不可用（embedding 未配置？）"}

    try:
        if store.get(item_id) is None:
            return {"ok": False, "error": f"{item['name']} 未安装"}
        store.delete(item_id)
        item["installed"] = False
        logger.info("Skill uninstalled: %s", item_id)
        return {"ok": True, "message": f"{item['name']} 已卸载"}
    except Exception as e:
        logger.error("Skill uninstall failed: %s", e)
        return {"ok": False, "error": str(e)}


def sync_installed_states(store: SkillStore | None) -> None:
    """从磁盘/数据库恢复 installed 标记（进程重启后内存标记会丢失）。

    GET /api/market/* 每次调用时先过一遍这里，保证前端看到真实状态。
    """
    # MCP：以 config/mcp.yaml 为准
    try:
        installed_mcps = {
            s.get("name") for s in _load_mcp_config()["servers"]
        }
        for m in MCP_MARKET:
            m["installed"] = m["id"] in installed_mcps
    except Exception as e:
        logger.warning("sync MCP installed states failed: %s", e)

    # 技能：以 SkillStore 为准
    if store is not None:
        try:
            for s in SKILL_MARKET:
                s["installed"] = store.get(s["id"]) is not None
        except Exception as e:
            logger.warning("sync skill installed states failed: %s", e)
