from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.auth.contracts import User

SUMMARY_COLUMNS = "id, student_name, filename, created_at, maturity_score, student_id, status, progress, model, submitted_at, error, payload"


def _now() -> str:
    return datetime.now(UTC).isoformat()


class Database:
    """Persistencia SQLite. Las migraciones son aditivas: nunca borran columnas ni datos."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._migrate()

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _migrate(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
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
                CREATE TABLE IF NOT EXISTS tutor_reviews (
                    id TEXT PRIMARY KEY, report_id TEXT NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
                    tutor_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    comments TEXT NOT NULL, annotated_filename TEXT,
                    stored_filename TEXT, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS item_responses (
                    id TEXT PRIMARY KEY, report_id TEXT NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
                    item_id TEXT NOT NULL, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    status TEXT NOT NULL CHECK(status IN ('corregido', 'no_aplica', 'pendiente')),
                    note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
                );
            """)
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(reports)")}
            for name, definition in (
                ("student_id", "TEXT REFERENCES users(id)"),
                ("status", "TEXT NOT NULL DEFAULT 'done'"),
                ("progress", "TEXT"),
                ("model", "TEXT"),
                ("submitted_at", "TEXT"),
                ("error", "TEXT"),
            ):
                if name not in columns:
                    connection.execute(f"ALTER TABLE reports ADD COLUMN {name} {definition}")
            connection.execute("CREATE INDEX IF NOT EXISTS reports_student_id_idx ON reports(student_id, created_at DESC)")
            connection.execute("CREATE INDEX IF NOT EXISTS sessions_expiry_idx ON sessions(expires_at)")
            connection.execute("CREATE INDEX IF NOT EXISTS tutor_reviews_report_idx ON tutor_reviews(report_id, created_at DESC)")
            connection.execute("CREATE INDEX IF NOT EXISTS item_responses_report_idx ON item_responses(report_id, item_id, created_at DESC)")

    # --- Usuarios y sesiones ---------------------------------------------------

    def find_user_by_email(self, email: str):
        with self._connect() as connection:
            return connection.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

    def find_user_by_id(self, user_id: str):
        with self._connect() as connection:
            return connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    def create_user(self, user: User, password_hash: str) -> None:
        with self._connect() as connection:
            connection.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)", (user.id, user.email, user.display_name, user.role, password_hash, _now()))

    def create_session(self, token_hash: str, user_id: str, expires_at: datetime) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (_now(),))
            connection.execute("INSERT INTO sessions VALUES (?, ?, ?)", (token_hash, user_id, expires_at.isoformat()))

    def user_id_for_session(self, token_hash: str, now: datetime) -> str | None:
        with self._connect() as connection:
            row = connection.execute("SELECT user_id FROM sessions WHERE token_hash = ? AND expires_at > ?", (token_hash, now.isoformat())).fetchone()
        return row["user_id"] if row else None

    def delete_session(self, token_hash: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))

    # --- Informes --------------------------------------------------------------

    def create_pending_report(self, report_id: str, student: User, filename: str, model: str) -> str:
        created_at = _now()
        payload = {"document_id": report_id, "filename": filename, "model": model}
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO reports (id, student_name, filename, created_at, maturity_score, payload, student_id, status, progress, model) VALUES (?, ?, ?, ?, 0, ?, ?, 'processing', ?, ?)",
                (report_id, student.display_name, filename, created_at, json.dumps(payload), student.id, json.dumps({"done": 0, "total": 0, "label": "En cola"}), model),
            )
        return created_at

    def update_progress(self, report_id: str, done: int, total: int, label: str) -> None:
        with self._connect() as connection:
            connection.execute("UPDATE reports SET progress = ? WHERE id = ?", (json.dumps({"done": done, "total": total, "label": label}, ensure_ascii=False), report_id))

    def complete_report(self, report_id: str, payload: dict) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE reports SET payload = ?, maturity_score = ?, status = 'done', progress = NULL, error = NULL WHERE id = ?",
                (json.dumps(payload, ensure_ascii=False), payload["maturity_score"], report_id),
            )

    def fail_report(self, report_id: str, error: str) -> None:
        with self._connect() as connection:
            connection.execute("UPDATE reports SET status = 'error', error = ?, progress = NULL WHERE id = ?", (error, report_id))

    def mark_interrupted_reports(self) -> int:
        """Al arrancar, los análisis que estaban en curso ya no se completarán."""
        with self._connect() as connection:
            return connection.execute("UPDATE reports SET status = 'error', error = 'Análisis interrumpido al reiniciar el servidor. Vuelve a subir el borrador.', progress = NULL WHERE status = 'processing'").rowcount

    @staticmethod
    def _summary(row: sqlite3.Row) -> dict:
        payload = json.loads(row["payload"] or "{}")
        return {
            "id": row["id"], "student_name": row["student_name"], "filename": row["filename"], "created_at": row["created_at"],
            "maturity_score": row["maturity_score"], "student_id": row["student_id"], "status": row["status"],
            "progress": json.loads(row["progress"]) if row["progress"] else None, "model": row["model"] or payload.get("model"),
            "submitted_at": row["submitted_at"], "error": row["error"],
            "traffic_light": payload.get("traffic_light"), "categories": payload.get("categories"),
            "blocking_items": payload.get("blocking_items", []), "evolution": payload.get("evolution"),
            "schema_version": payload.get("schema_version", 1),
            "ai_text_status": next((item["status"] for item in payload.get("items", []) if item["id"] == "A1"), None),
        }

    def get_report(self, report_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(f"SELECT {SUMMARY_COLUMNS} FROM reports WHERE id = ?", (report_id,)).fetchone()
        if not row:
            return None
        report = json.loads(row["payload"])
        report.update({key: value for key, value in self._summary(row).items() if key not in ("categories", "evolution", "traffic_light", "blocking_items")})
        report.setdefault("document_id", row["id"])
        return report

    def summaries(self, student_id: str | None = None) -> list[dict]:
        query = f"SELECT {SUMMARY_COLUMNS} FROM reports"
        params: tuple = ()
        if student_id:
            query += " WHERE student_id = ?"
            params = (student_id,)
        with self._connect() as connection:
            rows = connection.execute(query + " ORDER BY created_at DESC", params).fetchall()
        return [self._summary(row) for row in rows]

    def previous_completed_report(self, student_id: str, before: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute("SELECT id FROM reports WHERE student_id = ? AND created_at < ? AND status = 'done' ORDER BY created_at DESC LIMIT 1", (student_id, before)).fetchone()
        return self.get_report(row["id"]) if row else None

    def count_remote_analyses_today(self, student_id: str) -> int:
        today = datetime.now(UTC).date().isoformat()
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS total FROM reports WHERE student_id = ? AND created_at >= ? AND (model LIKE 'anthropic:%' OR model LIKE 'openrouter:%')", (student_id, today)).fetchone()
        return row["total"]

    def delete_report(self, report_id: str) -> list[str]:
        """Borra el informe y devuelve los ficheros de revisiones del tutor que hay que eliminar."""
        with self._connect() as connection:
            files = [row["stored_filename"] for row in connection.execute("SELECT stored_filename FROM tutor_reviews WHERE report_id = ? AND stored_filename IS NOT NULL", (report_id,))]
            connection.execute("DELETE FROM reports WHERE id = ?", (report_id,))
        return files

    def mark_submitted(self, report_id: str) -> str:
        submitted_at = _now()
        with self._connect() as connection:
            connection.execute("UPDATE reports SET submitted_at = ? WHERE id = ?", (submitted_at, report_id))
        return submitted_at

    # --- Respuestas del estudiante a los avisos ----------------------------------

    def save_item_response(self, report_id: str, item_id: str, user_id: str, status: str, note: str) -> dict:
        response = {"id": str(uuid4()), "report_id": report_id, "item_id": item_id, "user_id": user_id, "status": status, "note": note.strip(), "created_at": _now()}
        with self._connect() as connection:
            connection.execute("INSERT INTO item_responses VALUES (:id, :report_id, :item_id, :user_id, :status, :note, :created_at)", response)
        return response

    def item_responses(self, report_id: str) -> dict[str, dict]:
        """Última respuesta del estudiante a cada punto (el historial completo se conserva)."""
        with self._connect() as connection:
            rows = connection.execute("SELECT item_id, status, note, created_at FROM item_responses WHERE report_id = ? ORDER BY created_at", (report_id,)).fetchall()
        return {row["item_id"]: dict(row) for row in rows}

    # --- Revisiones del tutor ------------------------------------------------------

    def create_tutor_review(self, report_id: str, tutor_id: str, comments: str, annotated_filename: str | None, stored_filename: str | None) -> dict:
        review = {"id": str(uuid4()), "report_id": report_id, "tutor_id": tutor_id, "comments": comments.strip(), "annotated_filename": annotated_filename, "stored_filename": stored_filename, "created_at": _now()}
        with self._connect() as connection:
            connection.execute("INSERT INTO tutor_reviews VALUES (:id, :report_id, :tutor_id, :comments, :annotated_filename, :stored_filename, :created_at)", review)
        return review

    def latest_tutor_review(self, report_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM tutor_reviews WHERE report_id = ? ORDER BY created_at DESC LIMIT 1", (report_id,)).fetchone()
        return dict(row) if row else None
