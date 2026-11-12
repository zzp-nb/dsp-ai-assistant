"""SQLite persistence for conversations, classroom questions, materials and usage."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    LOCAL_TZ = ZoneInfo("Asia/Shanghai")
except ZoneInfoNotFoundError:  # Windows without the IANA database
    LOCAL_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS api_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    session_id TEXT NOT NULL,
    student_key TEXT NOT NULL DEFAULT '',
    feature TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    cache_hit_tokens INTEGER NOT NULL DEFAULT 0,
    cache_miss_tokens INTEGER NOT NULL DEFAULT 0,
    cost_cny REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    error_code TEXT,
    error_message TEXT,
    latency_ms INTEGER,
    request_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_usage_created ON api_usage(created_at);
CREATE INDEX IF NOT EXISTS idx_usage_student_created ON api_usage(student_key, created_at);
CREATE INDEX IF NOT EXISTS idx_usage_session_created ON api_usage(session_id, created_at);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    feature TEXT NOT NULL,
    role TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    citations_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_session ON chat_messages(session_id, id);

CREATE TABLE IF NOT EXISTS classroom_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    student_key TEXT NOT NULL,
    student_name TEXT NOT NULL,
    question TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    ai_answer TEXT,
    ai_citations_json TEXT NOT NULL DEFAULT '[]',
    show_ai_answer INTEGER NOT NULL DEFAULT 0,
    is_displayed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    answered_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_questions_created ON classroom_questions(created_at);
CREATE INDEX IF NOT EXISTS idx_questions_status ON classroom_questions(status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_one_displayed_question
    ON classroom_questions(is_displayed) WHERE is_displayed = 1;

CREATE TABLE IF NOT EXISTS materials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL UNIQUE,
    file_path TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    doc_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    page_count INTEGER NOT NULL DEFAULT 0,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    image_page_count INTEGER NOT NULL DEFAULT 0,
    ocr_used INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT,
    indexed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

DEFAULT_SETTINGS = {
    "daily_student_limit": "30",
    "daily_global_limit": "300",
    "max_input_chars": "1200",
    "max_output_tokens": "2400",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def local_day_bounds_utc(now: datetime | None = None) -> tuple[str, str]:
    local_now = (now or datetime.now(timezone.utc)).astimezone(LOCAL_TZ)
    start_local = datetime.combine(local_now.date(), time.min, tzinfo=LOCAL_TZ)
    end_local = datetime.combine(local_now.date(), time.max, tzinfo=LOCAL_TZ)
    return (
        start_local.astimezone(timezone.utc).isoformat(timespec="seconds"),
        end_local.astimezone(timezone.utc).isoformat(timespec="seconds"),
    )


@dataclass(frozen=True)
class QuotaDecision:
    allowed: bool
    reservation_id: int | None
    reason: str
    student_calls: int
    global_calls: int
    student_limit: int
    global_limit: int


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=20)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 20000")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(SCHEMA)
            now = utc_now()
            conn.execute(
                "INSERT OR IGNORE INTO settings(key, value, updated_at) VALUES (?, ?, ?)",
                ("schema_version", "1", now),
            )

    # ------------------------------------------------------------------ settings
    def get_settings(self) -> dict[str, str]:
        with self.connect() as conn:
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
        values = dict(DEFAULT_SETTINGS)
        values.update({row["key"]: row["value"] for row in rows})
        return values

    def seed_default_settings(self, values: dict[str, Any]) -> None:
        """Fill missing settings without overwriting teacher choices."""

        now = utc_now()
        with self.connect() as conn:
            for key, value in values.items():
                conn.execute(
                    "INSERT OR IGNORE INTO settings(key, value, updated_at) VALUES (?, ?, ?)",
                    (key, str(value), now),
                )

    def get_int_setting(self, key: str, default: int, minimum: int = 1) -> int:
        values = self.get_settings()
        try:
            return max(minimum, int(values.get(key, default)))
        except (TypeError, ValueError):
            return default

    def set_setting(self, key: str, value: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO settings(key, value, updated_at) VALUES (?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
                (key, str(value), utc_now()),
            )

    def set_settings(self, values: dict[str, Any]) -> None:
        now = utc_now()
        with self.connect() as conn:
            for key, value in values.items():
                conn.execute(
                    """INSERT INTO settings(key, value, updated_at) VALUES (?, ?, ?)
                       ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
                    (key, str(value), now),
                )

    # ------------------------------------------------------------------- usage
    def count_calls_since(self, start_utc: str, student_key_value: str | None = None) -> int:
        with self.connect() as conn:
            if student_key_value is None:
                row = conn.execute(
                    """SELECT COUNT(*) AS n FROM api_usage
                       WHERE created_at >= ? AND status != 'stale'""",
                    (start_utc,),
                ).fetchone()
            else:
                row = conn.execute(
                    """SELECT COUNT(*) AS n FROM api_usage
                       WHERE created_at >= ? AND student_key = ? AND status != 'stale'""",
                    (start_utc, student_key_value),
                ).fetchone()
        return int(row["n"] if row else 0)

    def reserve_api_call(
        self,
        *,
        session_id: str,
        student_key: str,
        feature: str,
        model: str,
        student_limit: int,
        global_limit: int,
    ) -> QuotaDecision:
        """Atomically reserve one call before hitting the paid API."""

        start, _ = local_day_bounds_utc()
        stale_before = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat(timespec="seconds")
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """UPDATE api_usage SET status='stale', completed_at=?,
                       error_code='stale_pending', error_message='进程中断，预留已释放'
                   WHERE status='pending' AND created_at < ?""",
                (utc_now(), stale_before),
            )
            student_calls = int(
                conn.execute(
                    """SELECT COUNT(*) AS n FROM api_usage
                       WHERE created_at >= ? AND student_key = ? AND status != 'stale'""",
                    (start, student_key),
                ).fetchone()["n"]
            )
            global_calls = int(
                conn.execute(
                    """SELECT COUNT(*) AS n FROM api_usage
                       WHERE created_at >= ? AND status != 'stale'""",
                    (start,),
                ).fetchone()["n"]
            )
            if student_calls >= student_limit:
                conn.rollback()
                return QuotaDecision(False, None, "student_daily_limit", student_calls, global_calls, student_limit, global_limit)
            if global_calls >= global_limit:
                conn.rollback()
                return QuotaDecision(False, None, "class_daily_limit", student_calls, global_calls, student_limit, global_limit)
            cursor = conn.execute(
                """INSERT INTO api_usage(
                       created_at, session_id, student_key, feature, model, status
                   ) VALUES (?, ?, ?, ?, ?, 'pending')""",
                (utc_now(), session_id, student_key, feature, model),
            )
            reservation_id = int(cursor.lastrowid)
            conn.commit()
            return QuotaDecision(True, reservation_id, "ok", student_calls + 1, global_calls + 1, student_limit, global_limit)

    def complete_api_call(
        self,
        reservation_id: int,
        *,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        cache_hit_tokens: int,
        cache_miss_tokens: int,
        cost_cny: float,
        latency_ms: int,
        request_id: str = "",
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """UPDATE api_usage SET
                       completed_at=?, prompt_tokens=?, completion_tokens=?, total_tokens=?,
                       cache_hit_tokens=?, cache_miss_tokens=?, cost_cny=?, status='success',
                       latency_ms=?, request_id=?
                   WHERE id=?""",
                (
                    utc_now(),
                    int(prompt_tokens),
                    int(completion_tokens),
                    int(total_tokens),
                    int(cache_hit_tokens),
                    int(cache_miss_tokens),
                    float(cost_cny),
                    int(latency_ms),
                    request_id[:120],
                    reservation_id,
                ),
            )

    def fail_api_call(
        self,
        reservation_id: int,
        *,
        error_code: str,
        error_message: str,
        latency_ms: int = 0,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """UPDATE api_usage SET completed_at=?, status='error', error_code=?,
                       error_message=?, latency_ms=? WHERE id=?""",
                (utc_now(), error_code[:80], error_message[:500], int(latency_ms), reservation_id),
            )

    def usage_summary(self, start_utc: str | None = None, end_utc: str | None = None) -> dict[str, Any]:
        clauses = ["status IN ('success', 'error', 'pending')"]
        params: list[Any] = []
        if start_utc:
            clauses.append("created_at >= ?")
            params.append(start_utc)
        if end_utc:
            clauses.append("created_at <= ?")
            params.append(end_utc)
        where = " AND ".join(clauses)
        with self.connect() as conn:
            row = conn.execute(
                f"""SELECT COUNT(*) AS calls,
                           SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) AS success_calls,
                           SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) AS error_calls,
                           COALESCE(SUM(total_tokens), 0) AS total_tokens,
                           COALESCE(SUM(cost_cny), 0) AS cost_cny,
                           COALESCE(AVG(CASE WHEN status='success' THEN latency_ms END), 0) AS avg_latency_ms
                    FROM api_usage WHERE {where}""",
                params,
            ).fetchone()
        return dict(row) if row else {}

    def usage_by_student(self, start_utc: str | None = None) -> list[dict[str, Any]]:
        where = "WHERE created_at >= ?" if start_utc else ""
        params: tuple[Any, ...] = (start_utc,) if start_utc else ()
        with self.connect() as conn:
            rows = conn.execute(
                f"""SELECT student_key, COUNT(*) AS calls,
                           COALESCE(SUM(total_tokens), 0) AS total_tokens,
                           COALESCE(SUM(cost_cny), 0) AS cost_cny
                    FROM api_usage {where}
                    GROUP BY student_key ORDER BY calls DESC LIMIT 50""",
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def usage_by_feature(self, start_utc: str | None = None) -> list[dict[str, Any]]:
        where = "WHERE created_at >= ?" if start_utc else ""
        params: tuple[Any, ...] = (start_utc,) if start_utc else ()
        with self.connect() as conn:
            rows = conn.execute(
                f"""SELECT feature, COUNT(*) AS calls,
                           COALESCE(SUM(total_tokens), 0) AS total_tokens,
                           COALESCE(SUM(cost_cny), 0) AS cost_cny
                    FROM api_usage {where}
                    GROUP BY feature ORDER BY calls DESC""",
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def recent_calls(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT id, created_at, student_key, feature, model, total_tokens,
                          cost_cny, status, error_code, latency_ms
                   FROM api_usage ORDER BY id DESC LIMIT ?""",
                (max(1, min(limit, 200)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def active_learners_today(self) -> int:
        start, _ = local_day_bounds_utc()
        with self.connect() as conn:
            row = conn.execute(
                """SELECT COUNT(DISTINCT key) AS n FROM (
                       SELECT session_id AS key FROM api_usage WHERE created_at >= ?
                       UNION
                       SELECT session_id AS key FROM classroom_questions WHERE created_at >= ?
                   )""",
                (start, start),
            ).fetchone()
        return int(row["n"] if row else 0)

    # --------------------------------------------------------------- chat memory
    def add_chat_message(
        self,
        *,
        session_id: str,
        feature: str,
        role: str,
        content: str,
        mode: str = "",
        citations: list[dict[str, Any]] | None = None,
    ) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """INSERT INTO chat_messages(session_id, feature, role, mode, content, citations_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    feature,
                    role,
                    mode,
                    content,
                    json.dumps(citations or [], ensure_ascii=False),
                    utc_now(),
                ),
            )
            return int(cursor.lastrowid)

    def get_chat_messages(self, session_id: str, feature: str = "qa", limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT role, mode, content, citations_json, created_at FROM (
                       SELECT id, role, mode, content, citations_json, created_at
                       FROM chat_messages WHERE session_id=? AND feature=? ORDER BY id DESC LIMIT ?
                   ) ORDER BY id ASC""",
                (session_id, feature, max(1, min(limit, 50))),
            ).fetchall()
        messages: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            try:
                item["citations"] = json.loads(item.pop("citations_json") or "[]")
            except json.JSONDecodeError:
                item["citations"] = []
            messages.append(item)
        return messages

    def clear_chat_messages(self, session_id: str, feature: str = "qa") -> None:
        with self.connect() as conn:
            conn.execute(
                "DELETE FROM chat_messages WHERE session_id=? AND feature=?",
                (session_id, feature),
            )

    # ------------------------------------------------------------- class questions
    def add_classroom_question(
        self, *, session_id: str, student_key_value: str, student_name: str, question: str
    ) -> int:
        now = utc_now()
        with self.connect() as conn:
            cursor = conn.execute(
                """INSERT INTO classroom_questions(
                       session_id, student_key, student_name, question, created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (session_id, student_key_value, student_name, question, now, now),
            )
            return int(cursor.lastrowid)

    def list_classroom_questions(
        self, *, limit: int = 100, status: str | None = None
    ) -> list[dict[str, Any]]:
        with self.connect() as conn:
            if status:
                rows = conn.execute(
                    """SELECT * FROM classroom_questions WHERE status=?
                       ORDER BY id DESC LIMIT ?""",
                    (status, max(1, min(limit, 300))),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM classroom_questions ORDER BY id DESC LIMIT ?",
                    (max(1, min(limit, 300)),),
                ).fetchall()
        return [self._question_row(row) for row in rows]

    def get_classroom_question(self, question_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM classroom_questions WHERE id=?", (question_id,)
            ).fetchone()
        return self._question_row(row) if row else None

    def list_classroom_questions_for_session(self, session_id: str, limit: int = 30) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT * FROM classroom_questions WHERE session_id=?
                   ORDER BY id DESC LIMIT ?""",
                (session_id, max(1, min(limit, 100))),
            ).fetchall()
        return [self._question_row(row) for row in rows]

    @staticmethod
    def _question_row(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        try:
            item["ai_citations"] = json.loads(item.pop("ai_citations_json") or "[]")
        except json.JSONDecodeError:
            item["ai_citations"] = []
        item["show_ai_answer"] = bool(item.get("show_ai_answer"))
        item["is_displayed"] = bool(item.get("is_displayed"))
        return item

    def save_question_answer(
        self,
        question_id: int,
        *,
        answer: str,
        citations: list[dict[str, Any]],
        show_answer: bool,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """UPDATE classroom_questions SET status='answered', ai_answer=?,
                       ai_citations_json=?, show_ai_answer=?, answered_at=?, updated_at=?
                   WHERE id=?""",
                (
                    answer,
                    json.dumps(citations, ensure_ascii=False),
                    1 if show_answer else 0,
                    utc_now(),
                    utc_now(),
                    question_id,
                ),
            )

    def set_question_display(
        self, question_id: int | None, *, show_ai_answer: bool | None = None
    ) -> None:
        """Display at most one question; ``None`` clears the projection."""

        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("UPDATE classroom_questions SET is_displayed=0 WHERE is_displayed=1")
            if question_id is not None:
                if show_ai_answer is None:
                    conn.execute(
                        "UPDATE classroom_questions SET is_displayed=1, updated_at=? WHERE id=?",
                        (utc_now(), question_id),
                    )
                else:
                    conn.execute(
                        """UPDATE classroom_questions SET is_displayed=1, show_ai_answer=?,
                               updated_at=? WHERE id=?""",
                        (1 if show_ai_answer else 0, utc_now(), question_id),
                    )
            conn.commit()

    def set_question_show_answer(self, question_id: int, show: bool) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE classroom_questions SET show_ai_answer=?, updated_at=? WHERE id=?",
                (1 if show else 0, utc_now(), question_id),
            )

    def get_displayed_question(self) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM classroom_questions WHERE is_displayed=1 LIMIT 1"
            ).fetchone()
        return self._question_row(row) if row else None

    def set_question_status(self, question_id: int, status: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE classroom_questions SET status=?, updated_at=? WHERE id=?",
                (status, utc_now(), question_id),
            )

    # ---------------------------------------------------------------- materials
    def upsert_material(self, record: dict[str, Any]) -> None:
        now = utc_now()
        columns = (
            "source_name",
            "file_path",
            "file_hash",
            "doc_type",
            "size_bytes",
            "page_count",
            "chunk_count",
            "image_page_count",
            "ocr_used",
            "status",
            "error",
            "indexed_at",
        )
        values = [record.get(column) for column in columns]
        with self.connect() as conn:
            conn.execute(
                f"""INSERT INTO materials({", ".join(columns)}, created_at, updated_at)
                    VALUES ({", ".join("?" for _ in columns)}, ?, ?)
                    ON CONFLICT(source_name) DO UPDATE SET
                        file_path=excluded.file_path, file_hash=excluded.file_hash,
                        doc_type=excluded.doc_type, size_bytes=excluded.size_bytes,
                        page_count=excluded.page_count, chunk_count=excluded.chunk_count,
                        image_page_count=excluded.image_page_count, ocr_used=excluded.ocr_used,
                        status=excluded.status, error=excluded.error,
                        indexed_at=excluded.indexed_at, updated_at=excluded.updated_at""",
                (*values, now, now),
            )

    def list_materials(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM materials ORDER BY source_name").fetchall()
        return [dict(row) for row in rows]

    def get_material(self, source_name: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM materials WHERE source_name=?", (source_name,)
            ).fetchone()
        return dict(row) if row else None

    def delete_material(self, source_name: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM materials WHERE source_name=?", (source_name,))
