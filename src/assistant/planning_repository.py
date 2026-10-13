
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "personalised_planning" / "planning.db"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class PlanningRepository:
    """Small SQLite repository for profiles, commitments, chats, and saved plans."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.db_path), timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS fan_profiles (
                    profile_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL DEFAULT '',
                    preferences_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS commitments (
                    commitment_id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    commitment_type TEXT NOT NULL DEFAULT 'other',
                    start_time_local TEXT NOT NULL,
                    end_time_local TEXT NOT NULL,
                    timezone TEXT NOT NULL DEFAULT 'Asia/Kolkata',
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(profile_id) REFERENCES fan_profiles(profile_id)
                        ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_commitments_profile_start
                    ON commitments(profile_id, start_time_local);

                CREATE TABLE IF NOT EXISTS conversation_sessions (
                    session_id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT 'Personalised Planning',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(profile_id) REFERENCES fan_profiles(profile_id)
                        ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS conversation_messages (
                    message_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('system','user','assistant','tool')),
                    content TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES conversation_sessions(session_id)
                        ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_messages_session_created
                    ON conversation_messages(session_id, created_at);

                CREATE TABLE IF NOT EXISTS saved_plans (
                    plan_id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL,
                    session_id TEXT,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    plan_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(profile_id) REFERENCES fan_profiles(profile_id)
                        ON DELETE CASCADE,
                    FOREIGN KEY(session_id) REFERENCES conversation_sessions(session_id)
                        ON DELETE SET NULL
                );
                """
            )
            # Backward-compatible migration for databases created by earlier versions.
            columns = {row[1] for row in conn.execute("PRAGMA table_info(commitments)").fetchall()}
            if "commitment_type" not in columns:
                conn.execute("ALTER TABLE commitments ADD COLUMN commitment_type TEXT NOT NULL DEFAULT 'other'")

    def create_profile(
        self,
        display_name: str = "",
        preferences: dict[str, Any] | None = None,
        profile_id: str | None = None,
    ) -> dict[str, Any]:
        if preferences is not None and not isinstance(preferences, dict):
            raise ValueError("preferences must be a dictionary")
        now = _utc_now()
        pid = profile_id or str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO fan_profiles
                   (profile_id, display_name, preferences_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (pid, display_name.strip(), _json_dump(preferences or {}), now, now),
            )
        return self.get_profile(pid)  # type: ignore[return-value]

    def get_latest_profile(self) -> dict[str, Any] | None:
        """Return the most recently updated local profile for single-user mode."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT profile_id FROM fan_profiles ORDER BY updated_at DESC, created_at DESC LIMIT 1"
            ).fetchone()
        return self.get_profile(row["profile_id"]) if row else None

    def get_profile(self, profile_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM fan_profiles WHERE profile_id = ?", (profile_id,)
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["preferences"] = json.loads(result.pop("preferences_json"))
        return result

    def update_profile(
        self, profile_id: str, display_name: str | None = None,
        preferences: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        existing = self.get_profile(profile_id)
        if existing is None:
            raise KeyError(f"Profile not found: {profile_id}")
        if preferences is not None and not isinstance(preferences, dict):
            raise ValueError("preferences must be a dictionary")
        new_name = existing["display_name"] if display_name is None else display_name.strip()
        new_preferences = existing["preferences"] if preferences is None else preferences
        with self._connect() as conn:
            conn.execute(
                """UPDATE fan_profiles SET display_name = ?, preferences_json = ?,
                   updated_at = ? WHERE profile_id = ?""",
                (new_name, _json_dump(new_preferences), _utc_now(), profile_id),
            )
        return self.get_profile(profile_id)  # type: ignore[return-value]

    def add_commitment(
        self, profile_id: str, title: str, start_time_local: str,
        end_time_local: str, timezone: str = "Asia/Kolkata", notes: str = "",
        commitment_id: str | None = None, commitment_type: str = "other",
    ) -> dict[str, Any]:
        if not self.get_profile(profile_id):
            raise KeyError(f"Profile not found: {profile_id}")
        if not title.strip():
            raise ValueError("Commitment title is required")
        if not start_time_local.strip() or not end_time_local.strip():
            raise ValueError("Commitment start and end times are required")
        if not timezone.strip():
            raise ValueError("Timezone is required")
        cid = commitment_id or str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO commitments
                   (commitment_id, profile_id, title, commitment_type, start_time_local,
                    end_time_local, timezone, notes, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (cid, profile_id, title.strip(), (commitment_type or "other").strip().lower(),
                 start_time_local, end_time_local, timezone.strip(), notes.strip(), _utc_now()),
            )
        return self.get_commitment(cid)  # type: ignore[return-value]

    def get_commitment(self, commitment_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM commitments WHERE commitment_id = ?", (commitment_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_commitments(
        self, profile_id: str, start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM commitments WHERE profile_id = ?"
        params: list[Any] = [profile_id]
        if start_date is not None:
            query += " AND substr(start_time_local, 1, 10) >= ?"
            params.append(start_date)
        if end_date is not None:
            query += " AND substr(start_time_local, 1, 10) <= ?"
            params.append(end_date)
        query += " ORDER BY start_time_local"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def delete_commitment(self, commitment_id: str, profile_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM commitments WHERE commitment_id = ? AND profile_id = ?",
                (commitment_id, profile_id),
            )
        return cursor.rowcount > 0

    def create_session(
        self, profile_id: str, title: str = "Personalised Planning",
        session_id: str | None = None,
    ) -> dict[str, Any]:
        if not self.get_profile(profile_id):
            raise KeyError(f"Profile not found: {profile_id}")
        sid = session_id or str(uuid.uuid4())
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO conversation_sessions
                   (session_id, profile_id, title, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (sid, profile_id, title.strip() or "Personalised Planning", now, now),
            )
        return self.get_session(sid)  # type: ignore[return-value]

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM conversation_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_sessions(self, profile_id: str) -> list[dict[str, Any]]:
        """Return this profile's conversations, newest activity first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM conversation_sessions WHERE profile_id = ? ORDER BY updated_at DESC, created_at DESC",
                (profile_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_session_title(self, session_id: str, profile_id: str, title: str) -> bool:
        clean_title = " ".join((title or "").split())[:80] or "New conversation"
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE conversation_sessions SET title = ?, updated_at = ? WHERE session_id = ? AND profile_id = ?",
                (clean_title, _utc_now(), session_id, profile_id),
            )
        return cursor.rowcount > 0

    def delete_session(self, session_id: str, profile_id: str) -> bool:
        """Delete a conversation and its messages; saved plans remain with a null session."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM conversation_sessions WHERE session_id = ? AND profile_id = ?",
                (session_id, profile_id),
            )
        return cursor.rowcount > 0

    def add_message(
        self, session_id: str, role: str, content: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if role not in {"system", "user", "assistant", "tool"}:
            raise ValueError("role must be system, user, assistant, or tool")
        if not isinstance(content, str):
            raise ValueError("message content must be a string")
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError("metadata must be a dictionary")
        if not self.get_session(session_id):
            raise KeyError(f"Session not found: {session_id}")
        message = {
            "message_id": str(uuid.uuid4()), "session_id": session_id,
            "role": role, "content": content, "metadata": metadata or {},
            "created_at": _utc_now(),
        }
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO conversation_messages
                   (message_id, session_id, role, content, metadata_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (message["message_id"], session_id, role, content,
                 _json_dump(message["metadata"]), message["created_at"]),
            )
            conn.execute(
                "UPDATE conversation_sessions SET updated_at = ? WHERE session_id = ?",
                (_utc_now(), session_id),
            )
        return message

    def list_messages(self, session_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM conversation_messages WHERE session_id = ?
                   ORDER BY created_at, rowid""", (session_id,)
            ).fetchall()
        messages = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(item.pop("metadata_json"))
            messages.append(item)
        return messages

    def save_plan(
        self, profile_id: str, start_date: str, end_date: str,
        plan: list[dict[str, Any]], session_id: str | None = None,
        plan_id: str | None = None,
    ) -> dict[str, Any]:
        if not self.get_profile(profile_id):
            raise KeyError(f"Profile not found: {profile_id}")
        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")
        if not isinstance(plan, list) or any(not isinstance(item, dict) for item in plan):
            raise ValueError("plan must be a list of dictionaries")
        if session_id is not None:
            session = self.get_session(session_id)
            if not session or session["profile_id"] != profile_id:
                raise ValueError("session must exist and belong to this profile")
        pid = plan_id or str(uuid.uuid4())
        saved_at = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO saved_plans
                   (plan_id, profile_id, session_id, start_date, end_date,
                    plan_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (pid, profile_id, session_id, start_date, end_date,
                 _json_dump(plan), saved_at),
            )
        return self.get_saved_plan(pid)  # type: ignore[return-value]

    def get_saved_plan(self, plan_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM saved_plans WHERE plan_id = ?", (plan_id,)
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["plan"] = json.loads(result.pop("plan_json"))
        return result

    def list_saved_plans(self, profile_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM saved_plans WHERE profile_id = ?
                   ORDER BY created_at DESC""", (profile_id,)
            ).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            item["plan"] = json.loads(item.pop("plan_json"))
            output.append(item)
        return output
