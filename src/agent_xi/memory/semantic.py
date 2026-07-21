"""语义记忆 — 基于 SQLite 的永久事实/偏好存储。

存储通过规则捕获或 LLM 提取的用户偏好、事实、习惯。
例如："用户喜欢简洁回答"、"用户的项目在 ~/work/foo"。

提取方式（两者结合）：
1. 规则快捕：对话中匹配"我喜欢/记住/我的..."等模式，即时写入
2. LLM 深度提取：对话结束时，用 LLM 总结本轮新发现的偏好/事实
"""

from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path
from typing import Any

# 规则快捕的正则模式
_CAPTURE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"我(?:比较)?喜欢(.{2,50})"), "preference"),
    (re.compile(r"我(?:不太?|不)喜欢(.{2,50})"), "dislike"),
    (re.compile(r"记住[，,：:]?\s*(.{2,100})"), "fact"),
    (re.compile(r"我的(.{2,50}?(?:在|是|叫).{2,50})"), "fact"),
    (re.compile(r"我(?:通常|一般|习惯)(.{2,50})"), "habit"),
    (re.compile(r"我(?:正在|在做|在搞)(.{2,50})"), "current_project"),
]


class SemanticMemory:
    """语义记忆：SQLite 存储用户事实与偏好。"""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        """初始化表结构。"""
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT DEFAULT 'rule',
                confidence REAL DEFAULT 1.0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_facts_category ON facts(category);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_facts_content ON facts(content);
            """
        )
        self._conn.commit()

    def store(
        self,
        content: str,
        category: str = "fact",
        source: str = "rule",
        confidence: float = 1.0,
    ) -> bool:
        """存储一条语义记忆。

        如果内容已存在则更新 confidence 和 updated_at。

        Returns:
            True 表示新增，False 表示更新已有条目。
        """
        now = time.time()
        try:
            self._conn.execute(
                """INSERT INTO facts (category, content, source, confidence, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (category, content, source, confidence, now, now),
            )
            self._conn.commit()
            return True
        except sqlite3.IntegrityError:
            # 已存在，更新
            self._conn.execute(
                """UPDATE facts SET confidence = MAX(confidence, ?), updated_at = ?
                   WHERE content = ?""",
                (confidence, now, content),
            )
            self._conn.commit()
            return False

    def query(
        self,
        keyword: str = "",
        category: str = "",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """查询语义记忆。

        支持按关键词模糊搜索和按类别过滤。
        """
        sql = "SELECT * FROM facts WHERE 1=1"
        params: list[Any] = []

        if keyword:
            sql += " AND content LIKE ?"
            params.append(f"%{keyword}%")
        if category:
            sql += " AND category = ?"
            params.append(category)

        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_all(self, limit: int = 50) -> list[dict[str, Any]]:
        """获取所有语义记忆（按更新时间倒序）。"""
        rows = self._conn.execute(
            "SELECT * FROM facts ORDER BY updated_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]

    def extract_from_text(self, text: str) -> list[tuple[str, str]]:
        """规则快捕：从用户输入中提取偏好/事实。

        Returns:
            (content, category) 元组列表。
        """
        captures: list[tuple[str, str]] = []
        for pattern, category in _CAPTURE_PATTERNS:
            for match in pattern.finditer(text):
                content = match.group(0).strip()
                if len(content) >= 4:  # 过滤太短的匹配
                    captures.append((content, category))
        return captures

    def format_for_prompt(self, limit: int = 10) -> str:
        """将语义记忆格式化为可注入 system prompt 的文本。"""
        facts = self.get_all(limit=limit)
        if not facts:
            return ""

        lines = ["[用户画像 — 来自历史对话的记忆]"]
        for f in facts:
            lines.append(f"- {f['content']}")
        return "\n".join(lines)

    @property
    def count(self) -> int:
        """当前存储的事实条数。"""
        row = self._conn.execute("SELECT COUNT(*) FROM facts").fetchone()
        return row[0]

    def close(self) -> None:
        self._conn.close()
