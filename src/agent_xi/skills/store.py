"""Skill 存储 — SQLite 元数据 + LanceDB 向量。"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from ..memory.embedding import EmbeddingClient
from .models import Skill

_TABLE_NAME = "skills"


class SkillStore:
    """技能持久化存储。

    SQLite: 元数据 CRUD、关键词索引。
    LanceDB: description 向量化，语义检索。
    """

    def __init__(
        self,
        data_dir: Path,
        embedding_client: EmbeddingClient,
    ) -> None:
        self._data_dir = data_dir
        self._embedding = embedding_client

        # SQLite
        db_path = data_dir / "skills.db"
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_db()

        # LanceDB
        import lancedb

        self._lance_db = lancedb.connect(str(data_dir / "skills_lance"))
        self._table: Any = None  # 延迟创建

    def _init_db(self) -> None:
        """初始化 SQLite 表。"""
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS skills (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                steps TEXT NOT NULL,
                trigger_keywords TEXT NOT NULL DEFAULT '[]',
                parameters TEXT NOT NULL DEFAULT '{}',
                created_at REAL NOT NULL,
                last_used REAL NOT NULL DEFAULT 0,
                use_count INTEGER NOT NULL DEFAULT 0
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_skills_name
            ON skills(name)
        """)
        self._conn.commit()

    async def save(self, skill: Skill) -> str:
        """存储技能（SQLite + LanceDB 向量）。"""
        # SQLite
        self._conn.execute(
            """INSERT OR REPLACE INTO skills
               (id, name, description, steps, trigger_keywords,
                parameters, created_at, last_used, use_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                skill.id,
                skill.name,
                skill.description,
                skill.steps,
                json.dumps(skill.trigger_keywords, ensure_ascii=False),
                json.dumps(skill.parameters, ensure_ascii=False),
                skill.created_at,
                skill.last_used,
                skill.use_count,
            ),
        )
        self._conn.commit()

        # LanceDB 向量
        vector = await self._embedding.embed_one(
            f"{skill.name}: {skill.description}"
        )
        record = {
            "id": skill.id,
            "text": f"{skill.name}: {skill.description}",
            "vector": vector,
        }

        if self._table is None:
            self._table = self._lance_db.create_table(
                _TABLE_NAME, data=[record]
            )
        else:
            self._table.add([record])

        return skill.id

    def get(self, skill_id: str) -> Skill | None:
        """按 ID 获取技能。"""
        row = self._conn.execute(
            "SELECT * FROM skills WHERE id = ?", (skill_id,)
        ).fetchone()
        return self._row_to_skill(row) if row else None

    def get_by_name(self, name: str) -> Skill | None:
        """按名称获取技能。"""
        row = self._conn.execute(
            "SELECT * FROM skills WHERE name = ?", (name,)
        ).fetchone()
        return self._row_to_skill(row) if row else None

    def list_all(self) -> list[Skill]:
        """列出所有技能。"""
        rows = self._conn.execute(
            "SELECT * FROM skills ORDER BY use_count DESC"
        ).fetchall()
        return [self._row_to_skill(r) for r in rows]

    def search_by_keywords(self, text: str) -> list[Skill]:
        """关键词匹配（快速过滤）。"""
        all_skills = self.list_all()
        text_lower = text.lower()
        hits = []
        for skill in all_skills:
            for kw in skill.trigger_keywords:
                if kw.lower() in text_lower:
                    hits.append(skill)
                    break
        return hits

    async def semantic_search(
        self, query: str, top_k: int = 5
    ) -> list[tuple[Skill, float]]:
        """语义向量检索。

        Returns:
            (Skill, score) 列表，按相似度降序。
        """
        if self._table is None:
            return []

        query_vector = await self._embedding.embed_one(query)
        results = (
            self._table.search(query_vector, vector_column_name="vector")
            .limit(top_k)
            .to_list()
        )

        hits: list[tuple[Skill, float]] = []
        for row in results:
            skill = self.get(row["id"])
            if skill:
                score = 1.0 - row.get("_distance", 0.0)
                hits.append((skill, score))

        return hits

    def update_usage(self, skill_id: str) -> None:
        """更新技能使用统计。"""
        self._conn.execute(
            """UPDATE skills
               SET last_used = ?, use_count = use_count + 1
               WHERE id = ?""",
            (time.time(), skill_id),
        )
        self._conn.commit()

    def delete(self, skill_id: str) -> bool:
        """删除技能。"""
        cursor = self._conn.execute(
            "DELETE FROM skills WHERE id = ?", (skill_id,)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    @property
    def count(self) -> int:
        """技能总数。"""
        row = self._conn.execute("SELECT COUNT(*) FROM skills").fetchone()
        return row[0] if row else 0

    def close(self) -> None:
        """关闭数据库连接。"""
        self._conn.close()

    @staticmethod
    def _row_to_skill(row: sqlite3.Row) -> Skill:
        """SQLite Row → Skill 对象。"""
        return Skill(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            steps=row["steps"],
            trigger_keywords=json.loads(row["trigger_keywords"]),
            parameters=json.loads(row["parameters"]),
            created_at=row["created_at"],
            last_used=row["last_used"],
            use_count=row["use_count"],
        )
