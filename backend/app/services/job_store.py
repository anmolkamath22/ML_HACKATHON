import json
import sqlite3
import threading
from collections.abc import Iterable
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

_JSON_FIELDS = ("options", "error", "result", "timings")
_FIELDS = ("job_id", "input_id", "source", "status", "stage", "progress", "message", "prompt", *_JSON_FIELDS,
           "created_at", "started_at", "completed_at", "updated_at")
_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    input_id TEXT NOT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    stage TEXT NOT NULL,
    progress INTEGER,
    message TEXT NOT NULL,
    prompt TEXT,
    options TEXT NOT NULL,
    error TEXT,
    result TEXT,
    timings TEXT NOT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status, created_at);
"""
ACTIVE_STATUSES = ("queued", "preprocessing", "generating", "postprocessing", "exporting")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    """SQLite-backed job records, safe to use from the API and worker threads."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        with closing(self._connect()) as connection, connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _encode(fields: dict) -> dict:
        unknown = set(fields) - set(_FIELDS)
        if unknown:
            raise KeyError(f"Unknown job fields: {sorted(unknown)}")
        return {key: json.dumps(value) if key in _JSON_FIELDS and value is not None else value for key, value in fields.items()}

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict:
        job = dict(row)
        for key in _JSON_FIELDS:
            job[key] = json.loads(job[key]) if job[key] is not None else None
        return job

    def create(self, job: dict) -> dict:
        record = {"progress": None, "error": None, "result": None, "timings": {}, "started_at": None,
                  "completed_at": None, **job, "updated_at": now()}
        encoded = self._encode(record)
        columns = ", ".join(encoded)
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute(f"INSERT INTO jobs ({columns}) VALUES ({', '.join('?' * len(encoded))})", tuple(encoded.values()))
        return self.get(job["job_id"])

    def get(self, job_id: str) -> dict | None:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        return self._decode(row) if row else None

    def update(self, job_id: str, *, only_if_status: Iterable[str] | None = None, **fields) -> bool:
        """Update a job; with only_if_status the change applies atomically only from those statuses."""
        encoded = self._encode({**fields, "updated_at": now()})
        query = f"UPDATE jobs SET {', '.join(f'{key} = ?' for key in encoded)} WHERE job_id = ?"
        params: list = [*encoded.values(), job_id]
        if only_if_status is not None:
            allowed = tuple(only_if_status)
            query += f" AND status IN ({', '.join('?' * len(allowed))})"
            params.extend(allowed)
        with self._lock, closing(self._connect()) as connection, connection:
            return connection.execute(query, params).rowcount == 1

    def recent(self, limit: int = 20) -> list[dict]:
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [self._decode(row) for row in rows]

    def active(self) -> list[dict]:
        placeholders = ", ".join("?" * len(ACTIVE_STATUSES))
        with closing(self._connect()) as connection:
            rows = connection.execute(f"SELECT * FROM jobs WHERE status IN ({placeholders}) ORDER BY created_at",
                                      ACTIVE_STATUSES).fetchall()
        return [self._decode(row) for row in rows]

    def count_active(self) -> int:
        placeholders = ", ".join("?" * len(ACTIVE_STATUSES))
        with closing(self._connect()) as connection:
            return connection.execute(f"SELECT COUNT(*) FROM jobs WHERE status IN ({placeholders})", ACTIVE_STATUSES).fetchone()[0]

    def queue_position(self, job_id: str, created_at: str) -> int:
        """1-based position among queued jobs, counting a running job as ahead of everyone."""
        with closing(self._connect()) as connection:
            ahead = connection.execute(
                "SELECT COUNT(*) FROM jobs WHERE status = 'queued' AND (created_at < ? OR (created_at = ? AND job_id < ?))",
                (created_at, created_at, job_id)).fetchone()[0]
            running = connection.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('preprocessing', 'generating', 'postprocessing', 'exporting')").fetchone()[0]
        return ahead + running + 1
