"""用量统计 & 成本追踪 — Token 使用记录与趋势分析。

参考 cc-haha 的 cost-tracker 设计。

存储：SQLite（.data/usage.db）
- 每次 LLM 调用完成后记录 model、input_tokens、output_tokens、timestamp
- 提供按日/周/月汇总查询
- 成本估算（按 model 定价）
"""

from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 模型定价（USD / 1M tokens）
# 价格仅供参考，实际以官网为准
_MODEL_PRICING: dict[str, dict[str, float]] = {
    "deepseek-chat": {"input": 0.27, "output": 1.10},
    "deepseek-reasoner": {"input": 0.55, "output": 2.19},
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "claude-opus-4-20250514": {"input": 15.00, "output": 75.00},
    "claude-haiku-3-5-20241022": {"input": 0.80, "output": 4.00},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    # Ollama 本地模型免费
    "default": {"input": 0, "output": 0},
}


@dataclass(slots=True)
class UsageRecord:
    """单次调用用量记录。"""

    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    timestamp: float = field(default_factory=time.time)
    estimated_cost_usd: float = 0.0


@dataclass(slots=True)
class UsageSummary:
    """用量汇总。"""

    total_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    by_model: dict[str, dict[str, Any]] = field(default_factory=dict)


class UsageTracker:
    """Token 用量追踪器。

    用法：
        tracker = UsageTracker(data_dir)
        tracker.record("deepseek-chat", "deepseek", 1500, 800)
        summary = tracker.get_summary(days=7)
    """

    def __init__(self, data_dir: Path) -> None:
        self._db_path = data_dir / "usage.db"
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        """初始化表结构。"""
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model TEXT NOT NULL,
                provider TEXT NOT NULL DEFAULT '',
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                estimated_cost_usd REAL NOT NULL DEFAULT 0.0,
                timestamp REAL NOT NULL
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_usage_timestamp
            ON usage(timestamp)
        """)
        self._conn.commit()

    def record(
        self,
        model: str,
        provider: str,
        input_tokens: int,
        output_tokens: int,
        timestamp: float | None = None,
    ) -> None:
        """记录一次 LLM 调用。"""
        if input_tokens == 0 and output_tokens == 0:
            return  # 不记录空调用

        cost = self._estimate_cost(model, input_tokens, output_tokens)
        ts = timestamp or time.time()

        self._conn.execute(
            """INSERT INTO usage (model, provider, input_tokens, output_tokens, estimated_cost_usd, timestamp)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (model, provider, input_tokens, output_tokens, cost, ts),
        )
        self._conn.commit()

    def get_summary(self, days: int = 7) -> UsageSummary:
        """获取最近 N 天的用量汇总。"""
        cutoff = time.time() - days * 86400

        row = self._conn.execute(
            """SELECT
                 COUNT(*) as total_calls,
                 COALESCE(SUM(input_tokens), 0) as total_input,
                 COALESCE(SUM(output_tokens), 0) as total_output,
                 COALESCE(SUM(estimated_cost_usd), 0.0) as total_cost
               FROM usage WHERE timestamp >= ?""",
            (cutoff,),
        ).fetchone()

        summary = UsageSummary(
            total_calls=row["total_calls"] or 0,
            total_input_tokens=row["total_input"] or 0,
            total_output_tokens=row["total_output"] or 0,
            total_cost_usd=row["total_cost"] or 0.0,
        )

        # 按 model 分组
        model_rows = self._conn.execute(
            """SELECT
                 model,
                 COUNT(*) as calls,
                 COALESCE(SUM(input_tokens), 0) as input_tok,
                 COALESCE(SUM(output_tokens), 0) as output_tok,
                 COALESCE(SUM(estimated_cost_usd), 0.0) as cost
               FROM usage WHERE timestamp >= ?
               GROUP BY model""",
            (cutoff,),
        ).fetchall()

        for r in model_rows:
            summary.by_model[r["model"]] = {
                "calls": r["calls"],
                "input_tokens": r["input_tok"],
                "output_tokens": r["output_tok"],
                "cost_usd": r["cost"],
            }

        return summary

    def get_daily_breakdown(self, days: int = 7) -> list[dict[str, Any]]:
        """按天汇总用量（用于前端图表）。"""
        cutoff = time.time() - days * 86400

        rows = self._conn.execute(
            """SELECT
                 DATE(timestamp, 'unixepoch') as day,
                 COUNT(*) as calls,
                 COALESCE(SUM(input_tokens), 0) as input_tok,
                 COALESCE(SUM(output_tokens), 0) as output_tok,
                 COALESCE(SUM(estimated_cost_usd), 0.0) as cost
               FROM usage WHERE timestamp >= ?
               GROUP BY day ORDER BY day""",
            (cutoff,),
        ).fetchall()

        return [dict(r) for r in rows]

    def get_recent_calls(self, limit: int = 20) -> list[dict[str, Any]]:
        """最近 N 次调用记录。"""
        rows = self._conn.execute(
            """SELECT * FROM usage ORDER BY timestamp DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_total_summary(self) -> UsageSummary:
        """获取全部历史汇总。"""
        row = self._conn.execute(
            """SELECT
                 COUNT(*) as total_calls,
                 COALESCE(SUM(input_tokens), 0) as total_input,
                 COALESCE(SUM(output_tokens), 0) as total_output,
                 COALESCE(SUM(estimated_cost_usd), 0.0) as total_cost
               FROM usage""",
        ).fetchone()

        return UsageSummary(
            total_calls=row["total_calls"] or 0,
            total_input_tokens=row["total_input"] or 0,
            total_output_tokens=row["total_output"] or 0,
            total_cost_usd=row["total_cost"] or 0.0,
        )

    def _estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """估算成本（USD）。"""
        pricing = _MODEL_PRICING.get(model, _MODEL_PRICING["default"])
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        return round(input_cost + output_cost, 6)

    def close(self) -> None:
        self._conn.close()