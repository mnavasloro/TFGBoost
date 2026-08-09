from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from app.auth.contracts import User


class Database:
    """Small SQLite persistence layer; migrations are deliberately additive."""
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._migrate()

    def _connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _migrate(self) -> None:
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('student', 'tutor')), password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY, student_name TEXT NOT NULL, filename TEXT NOT NULL,
                    created_at TEXT NOT NULL, maturity_score INTEGER NOT NULL, payload TEXT NOT NULL
                );
            """)
            existing_columns = {row["name"] for row in connection.execute("PRAGMA table_info(reports)")}
            if "student_id" not in existing_columns:
                connection.execute("ALTER TABLE reports ADD COLUMN student_id TEXT REFERENCES users(id)")
            connection.execute("CREATE INDEX IF NOT EXISTS reports_student_id_idx ON reports(student_id)")
            connection.execute("CREATE INDEX IF NOT EXISTS sessions_expiry_idx ON sessions(expires_at)")

    def find_user_by_email(self, email: str):
        with self._connect() as connection:
            return connection.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

    def find_user_by_id(self, user_id: str):
        with self._connect() as connection:
            return connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    def create_user(self, user: User, password_hash: str) -> None:
        with self._connect() as connection:
            connection.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)", (user.id, user.email, user.display_name, user.role, password_hash, datetime.now(UTC).isoformat()))

    def create_session(self, token_hash: str, user_id: str, expires_at: datetime) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (datetime.now(UTC).isoformat(),))
            connection.execute("INSERT INTO sessions VALUES (?, ?, ?)", (token_hash, user_id, expires_at.isoformat()))

    def user_id_for_session(self, token_hash: str, now: datetime) -> str | None:
        with self._connect() as connection:
            row = connection.execute("SELECT user_id FROM sessions WHERE token_hash = ? AND expires_at > ?", (token_hash, now.isoformat())).fetchone()
        return row["user_id"] if row else None

    def delete_session(self, token_hash: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
