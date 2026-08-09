from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


class ReportRepository:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self._connect() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS reports (
                id TEXT PRIMARY KEY, student_name TEXT NOT NULL, filename TEXT NOT NULL,
                created_at TEXT NOT NULL, maturity_score INTEGER NOT NULL, payload TEXT NOT NULL
            )""")

    def _connect(self):
        return sqlite3.connect(self.path)

    def save(self, report: dict, student_name: str) -> None:
        with self._connect() as connection:
            connection.execute("INSERT INTO reports VALUES (?, ?, ?, ?, ?, ?)", (report["document_id"], student_name, report["filename"], datetime.now(UTC).isoformat(), report["maturity_score"], json.dumps(report, ensure_ascii=False)))

    def get(self, report_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute("SELECT payload FROM reports WHERE id = ?", (report_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def summaries(self) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute("SELECT id, student_name, filename, created_at, maturity_score FROM reports ORDER BY created_at DESC").fetchall()
        return [{"id": row[0], "student_name": row[1], "filename": row[2], "created_at": row[3], "maturity_score": row[4]} for row in rows]
