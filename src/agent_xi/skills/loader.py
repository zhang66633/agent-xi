"""文件系统 Skill 加载器 — 对标 cc-haha skills/loadSkillsDir.ts。

扫描指定目录下每个子目录的 SKILL.md 文件，
解析 YAML frontmatter，自动注册为 Skill。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# SKILL.md frontmatter 解析正则
_FRONTMATTER_RE = re.compile(r'^---\s*\n(.*?)\n---\s*\n(.*)', re.DOTALL)


def parse_skill_md(content: str) -> dict[str, Any] | None:
    """解析 SKILL.md 文件，提取 frontmatter 和 body。

    对标 cc-haha 的 parseSkillFrontmatterFields。

    Returns:
        {"name": str, "description": str, "steps": str, "keywords": [...], ...}
        如果文件格式不合法返回 None。
    """
    m = _FRONTMATTER_RE.match(content)
    if not m:
        return None

    frontmatter_text = m.group(1)
    body = m.group(2).strip()

    # 极简 YAML 解析（只支持 key: value 和 key: [list]）
    meta: dict[str, Any] = {}
    for line in frontmatter_text.split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if ':' in line:
            key, _, value = line.partition(':')
            key = key.strip()
            value = value.strip()
            if value.startswith('[') and value.endswith(']'):
                # 简单列表: [a, b, c]
                value = [
                    v.strip().strip('"').strip("'")
                    for v in value[1:-1].split(',')
                    if v.strip()
                ]
            else:
                value = value.strip('"').strip("'")
            meta[key] = value

    if 'name' not in meta:
        return None

    return {
        "name": meta.get("name", ""),
        "description": meta.get("description", ""),
        "steps": body,
        "trigger_keywords": meta.get("keywords", []),
        "category": meta.get("category", ""),
        "tags": meta.get("tags", []),
        "model": meta.get("model", ""),
        "allowed_tools": meta.get("allowed-tools", meta.get("allowed_tools", [])),
    }


def discover_skills_from_dir(
    skills_dir: Path,
) -> list[dict[str, Any]]:
    """扫描目录，发现所有 SKILL.md 文件。

    目录结构（对标 cc-haha）：
        skills_dir/
          code-review/
            SKILL.md
          deploy/
            SKILL.md

    Returns:
        每个 SKILL.md 解析后的 dict 列表。
    """
    if not skills_dir.exists() or not skills_dir.is_dir():
        return []

    skills: list[dict[str, Any]] = []

    for entry in sorted(skills_dir.iterdir()):
        if not entry.is_dir():
            continue
        skill_md = entry / "SKILL.md"
        if not skill_md.exists():
            continue

        try:
            content = skill_md.read_text(encoding="utf-8")
            parsed = parse_skill_md(content)
            if parsed:
                # 如果 frontmatter 没有 name，用目录名
                if not parsed.get("name"):
                    parsed["name"] = entry.name
                parsed["id"] = entry.name
                parsed["source"] = str(skill_md)
                skills.append(parsed)
                logger.info("发现技能: %s (%s)", parsed["name"], entry.name)
            else:
                logger.warning("SKILL.md 格式无效: %s", skill_md)
        except Exception as e:
            logger.warning("读取 SKILL.md 失败 %s: %s", skill_md, e)

    return skills


def load_fs_skills_into_store(
    skills_dir: Path,
    store: Any,  # SkillStore
) -> int:
    """扫描 SKILL.md 并写入 SkillStore。返回加载的技能数。

    Args:
        skills_dir: 技能目录路径（如 config/skills/）
        store: SkillStore 实例

    Returns:
        成功加载的技能数量。
    """
    from .models import Skill

    discovered = discover_skills_from_dir(skills_dir)
    count = 0

    for info in discovered:
        try:
            # 检查是否已存在（按 id）
            existing = store.get(info["id"])
            if existing:
                # 更新已有技能
                existing.description = info["description"]
                existing.steps = info["steps"]
                existing.trigger_keywords = info.get("trigger_keywords", [])
                existing.category = info.get("category", "")
                existing.tags = info.get("tags", [])
                # skill.id 不变，调用 save 会 REPLACE
            else:
                skill = Skill(
                    id=info["id"],
                    name=info["name"],
                    description=info["description"],
                    steps=info["steps"],
                    trigger_keywords=info.get("trigger_keywords", []),
                    category=info.get("category", ""),
                    tags=info.get("tags", []),
                )
            # 注意：store.save 是 async 方法，这里在同步上下文中调用
            # 实际使用时由 SkillStore.save() 包装
        except Exception as e:
            logger.warning("加载技能失败 %s: %s", info.get("name"), e)

    return len(discovered)
