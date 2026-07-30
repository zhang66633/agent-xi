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
        "category": "文件系统",
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
        "category": "开发工具",
    },
    {
        "id": "sqlite",
        "name": "SQLite",
        "description": "查询 SQLite 数据库，执行 SQL",
        "icon": "▦",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-sqlite", "--db-path", "/path.db"],
        "installed": False,
        "category": "数据库",
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
        "category": "搜索",
    },
    {
        "id": "puppeteer",
        "name": "Puppeteer",
        "description": "浏览器自动化：截图、点击、表单填写",
        "icon": "▣",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-puppeteer"],
        "installed": False,
        "category": "浏览器",
    },
    {
        "id": "memory",
        "name": "Memory Graph",
        "description": "知识图谱记忆：实体关系存储与检索",
        "icon": "✦",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-memory"],
        "installed": False,
        "category": "记忆",
    },
    {
        "id": "postgres",
        "name": "PostgreSQL",
        "description": "查询 PostgreSQL 数据库",
        "icon": "▥",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-postgres"],
        "env": {"DATABASE_URL": ""},
        "installed": False,
        "category": "数据库",
    },
    {
        "id": "slack",
        "name": "Slack",
        "description": "Slack 消息发送与频道管理",
        "icon": "⧈",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-slack"],
        "env": {"SLACK_BOT_TOKEN": ""},
        "installed": False,
        "category": "通讯",
    },
    {
        "id": "fetch",
        "name": "Fetch",
        "description": "HTTP 请求获取网页内容",
        "icon": "⇱",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-fetch"],
        "installed": False,
        "category": "网络",
    },
    {
        "id": "docker",
        "name": "Docker",
        "description": "管理 Docker 容器与镜像",
        "icon": "⬡",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-docker"],
        "installed": False,
        "category": "运维",
    },
]

# ─── 技能市场 ─────────────────────────────────────────────────

SKILL_MARKET: list[dict] = [
    {
        "id": "code-review",
        "name": "代码审查",
        "description": "自动审查代码质量、安全性、性能问题，输出结构化报告",
        "icon": "▸",
        "keywords": ["代码", "审查", "review", "质量", "安全"],
        "steps": "1. 读取目标文件\n2. 分析代码结构\n3. 检查常见问题（安全/性能/风格）\n4. 输出结构化审查报告",
        "installed": False,
        "category": "开发",
    },
    {
        "id": "summarize",
        "name": "文档摘要",
        "description": "将长文档压缩为结构化摘要，支持中英文",
        "icon": "≡",
        "keywords": ["摘要", "总结", "文档", "压缩", "summarize"],
        "steps": "1. 读取文档内容\n2. 提取关键信息\n3. 生成结构化摘要\n4. 输出 markdown",
        "installed": False,
        "category": "办公",
    },
    {
        "id": "translate",
        "name": "翻译助手",
        "description": "中英互译，保持专业术语准确",
        "icon": "⇄",
        "keywords": ["翻译", "translate", "中文", "英文"],
        "steps": "1. 识别源语言\n2. 翻译为目标语言\n3. 校验术语一致性\n4. 输出译文",
        "installed": False,
        "category": "办公",
    },
    {
        "id": "data-analysis",
        "name": "数据分析",
        "description": "分析 CSV/JSON 数据，生成统计报告和图表建议",
        "icon": "▩",
        "keywords": ["数据", "分析", "统计", "CSV", "JSON"],
        "steps": "1. 加载数据文件\n2. 基础统计描述\n3. 发现异常值\n4. 给出可视化建议",
        "installed": False,
        "category": "数据",
    },
    {
        "id": "git-commit",
        "name": "Git 提交助手",
        "description": "分析变更自动生成规范的 commit message",
        "icon": "◈",
        "keywords": ["git", "commit", "提交", "变更"],
        "steps": "1. 运行 git diff 查看变更\n2. 分析变更内容\n3. 生成符合 Conventional Commits 规范的消息\n4. 按用户确认执行 git commit",
        "installed": False,
        "category": "开发",
    },
    {
        "id": "refactor",
        "name": "代码重构",
        "description": "识别代码坏味道，提出重构方案并执行",
        "icon": "↻",
        "keywords": ["重构", "refactor", "优化", "clean code"],
        "steps": "1. 分析目标代码\n2. 识别坏味道（长函数/重复代码/耦合）\n3. 提出重构方案\n4. 按方案执行重构",
        "installed": False,
        "category": "开发",
    },
    {
        "id": "test-gen",
        "name": "测试生成",
        "description": "为函数/模块自动生成单元测试用例",
        "icon": "✓",
        "keywords": ["测试", "test", "用例", "unittest", "pytest"],
        "steps": "1. 读取目标代码\n2. 识别可测试的单元\n3. 生成测试用例（含边界/异常）\n4. 写入测试文件",
        "installed": False,
        "category": "开发",
    },
    {
        "id": "api-doc",
        "name": "API 文档生成",
        "description": "从代码中提取 API 定义，生成接口文档",
        "icon": "⎔",
        "keywords": ["API", "接口", "文档", "swagger", "openapi"],
        "steps": "1. 扫描路由定义\n2. 提取请求/响应模型\n3. 生成 OpenAPI 文档\n4. 输出 markdown/HTML",
        "installed": False,
        "category": "开发",
    },
    {
        "id": "error-debug",
        "name": "错误排查",
        "description": "分析错误日志/堆栈，定位根因并给出修复方案",
        "icon": "⚡",
        "keywords": ["错误", "debug", "bug", "日志", "error", "异常"],
        "steps": "1. 读取错误日志/堆栈\n2. 定位错误源头\n3. 分析根因\n4. 给出修复方案",
        "installed": False,
        "category": "开发",
    },
    {
        "id": "config-setup",
        "name": "项目初始化",
        "description": "为新项目生成合理的配置文件（ESLint/Prettier/Git hooks 等）",
        "icon": "⚙",
        "keywords": ["配置", "初始化", "setup", "config", "项目"],
        "steps": "1. 识别项目类型\n2. 生成推荐配置\n3. 安装依赖\n4. 验证配置生效",
        "installed": False,
        "category": "工具",
    },
    {
        "id": "db-migration",
        "name": "数据库迁移",
        "description": "生成数据库 schema 变更的迁移脚本",
        "icon": "▥",
        "keywords": ["数据库", "迁移", "migration", "schema", "表"],
        "steps": "1. 对比新旧 schema\n2. 生成迁移 SQL\n3. 添加回滚脚本\n4. 验证迁移可行",
        "installed": False,
        "category": "数据库",
    },
    {
        "id": "search-optimize",
        "name": "搜索优化",
        "description": "优化搜索查询或搜索引擎配置",
        "icon": "◎",
        "keywords": ["搜索", "search", "优化", "索引", "ES"],
        "steps": "1. 分析当前搜索表现\n2. 识别瓶颈\n3. 优化查询/索引\n4. 对比优化前后效果",
        "installed": False,
        "category": "数据",
    },
    {
        "id": "diagram",
        "name": "架构图生成",
        "description": "根据项目结构生成架构图（Mermaid/PlantUML）",
        "icon": "◈",
        "keywords": ["架构", "图", "diagram", "mermaid", "flowchart"],
        "steps": "1. 扫描项目结构\n2. 识别模块关系\n3. 生成 Mermaid 图\n4. 输出可渲染的代码",
        "installed": False,
        "category": "设计",
    },
    {
        "id": "deploy-check",
        "name": "部署检查",
        "description": "部署前检查清单：环境变量、依赖、配置文件",
        "icon": "✓",
        "keywords": ["部署", "deploy", "检查", "上线", "生产"],
        "steps": "1. 检查环境变量完整性\n2. 验证依赖版本\n3. 检查配置文件\n4. 输出检查报告",
        "installed": False,
        "category": "运维",
    },
    {
        "id": "security-audit",
        "name": "安全审计",
        "description": "扫描依赖漏洞、检查敏感信息泄露、审查权限",
        "icon": "⚠",
        "keywords": ["安全", "security", "漏洞", "审计", "audit"],
        "steps": "1. 扫描依赖漏洞\n2. 检查硬编码密钥\n3. 审查权限配置\n4. 输出安全报告",
        "installed": False,
        "category": "安全",
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
