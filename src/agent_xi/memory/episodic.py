"""情景记忆 — 基于 LanceDB 的跨会话向量检索。

存储用户显式要求"记住"的对话片段，通过 embedding 向量做语义相似度检索。
Phase 5 可扩展：时间衰减、重要性加权、自动归档。
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

import lancedb

from .embedding import EmbeddingClient

_TABLE_NAME = "episodes"


class EpisodicMemory:
    """情景记忆：LanceDB 向量存储 + 语义检索。"""

    def __init__(
        self,
        db_path: Path,
        embedding_client: EmbeddingClient,
    ) -> None:
        self._db_path = db_path
        self._embedding = embedding_client
        self._db = lancedb.connect(str(db_path))
        self._table: Any | None = self._open_existing_table()

    def _open_existing_table(self) -> Any | None:
        """尝试打开已有表，不存在则返回 None（首次写入时创建）。"""
        if _TABLE_NAME in self._db.table_names():
            return self._db.open_table(_TABLE_NAME)
        return None

    async def remember(
        self,
        content: str,
        summary: str = "",
        tags: list[str] | None = None,
    ) -> str:
        """存储一条情景记忆。

        Args:
            content: 原始对话内容或用户要求记住的信息。
            summary: 可选的摘要（若为空则用 content 本身做 embedding）。
            tags: 可选标签列表。

        Returns:
            记忆条目的 UUID。
        """
        memory_id = str(uuid.uuid4())
        # 用 summary 或 content 做 embedding
        embed_text = summary if summary else content
        vector = await self._embedding.embed_one(embed_text)

        record = {
            "id": memory_id,
            "content": content,
            "summary": summary or content[:200],
            "timestamp": time.time(),
            "tags": json.dumps(tags or [], ensure_ascii=False),
            "vector": vector,
        }

        if self._table is None:
            # 首次写入：从数据自动推断 schema（含向量维度）
            self._table = self._db.create_table(_TABLE_NAME, data=[record])
        else:
            self._table.add([record])

        return memory_id

    async def recall(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """语义检索相关记忆。

        Args:
            query: 检索查询文本。
            top_k: 返回最相关的 K 条。

        Returns:
            记忆条目列表，每条含 id, content, summary, timestamp, tags, score。
        """
        if self._table is None or self._table.count_rows() == 0:
            return []

        query_vector = await self._embedding.embed_one(query)

        results = (
            self._table.search(query_vector, vector_column_name="vector")
            .limit(top_k)
            .to_list()
        )

        episodes = []
        for row in results:
            episodes.append(
                {
                    "id": row["id"],
                    "content": row["content"],
                    "summary": row["summary"],
                    "timestamp": row["timestamp"],
                    "tags": json.loads(row["tags"]) if row.get("tags") else [],
                    "score": 1.0 - row.get("_distance", 0.0),  # 转为相似度
                }
            )
        return episodes

    @property
    def count(self) -> int:
        """当前存储的记忆条数。"""
        if self._table is None:
            return 0
        return self._table.count_rows()
