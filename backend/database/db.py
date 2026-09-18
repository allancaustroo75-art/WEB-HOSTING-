from __future__ import annotations

import sqlite3
import time
import uuid
from contextlib import contextmanager
from typing import Any, Iterator


def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def utc_now() -> float:
    return time.time()


class Database:
    def __init__(self, path: str) -> None:
        self.path = path

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    slug TEXT NOT NULL UNIQUE,
                    main_file TEXT,
                    status TEXT NOT NULL DEFAULT 'stopped',
                    pid INTEGER,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    runtime TEXT DEFAULT 'python',
                    language TEXT DEFAULT 'python',
                    description TEXT DEFAULT ''
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    filename TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    uploaded_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS login_tokens (
                    token TEXT PRIMARY KEY,
                    owner_id INTEGER NOT NULL,
                    expires_at REAL NOT NULL,
                    used INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS activity_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    project_id INTEGER,
                    details TEXT,
                    created_at REAL NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS admins (
                    user_id INTEGER PRIMARY KEY,
                    added_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS active_users (
                    user_id INTEGER PRIMARY KEY,
                    first_seen REAL NOT NULL
                )
                """
            )
            # Telegram user profiles - stores only username + photo_url, not exposing numeric ID in UI
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS telegram_users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    language_code TEXT,
                    is_premium INTEGER DEFAULT 0,
                    photo_url TEXT DEFAULT '',
                    last_seen REAL NOT NULL
                )
                """
            )

        # Safe migrations for existing DB
        self._migrate()

    def _migrate(self) -> None:
        """Add missing columns if DB was created with old schema"""
        try:
            with self._conn() as conn:
                # Projects table
                try:
                    cols = [r[1] for r in conn.execute("PRAGMA table_info(projects)").fetchall()]
                except Exception:
                    cols = []
                if cols:
                    for col, default in [
                        ("runtime", "TEXT DEFAULT 'python'"),
                        ("language", "TEXT DEFAULT 'python'"),
                        ("description", "TEXT DEFAULT ''"),
                    ]:
                        if col not in cols:
                            try:
                                conn.execute(f"ALTER TABLE projects ADD COLUMN {col} {default}")
                            except Exception:
                                pass

                # telegram_users table
                try:
                    tu_cols = [r[1] for r in conn.execute("PRAGMA table_info(telegram_users)").fetchall()]
                except Exception:
                    tu_cols = []
                if tu_cols:
                    if "photo_url" not in tu_cols:
                        try:
                            conn.execute("ALTER TABLE telegram_users ADD COLUMN photo_url TEXT DEFAULT ''")
                        except Exception:
                            pass
        except Exception:
            pass

    # ---- admins ----
    def seed_admins(self, user_ids: set[int]) -> None:
        with self._conn() as conn:
            for uid in user_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO admins (user_id, added_at) VALUES (?, ?)", (uid, utc_now())
                )

    def add_admin(self, user_id: int) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO admins (user_id, added_at) VALUES (?, ?)", (user_id, utc_now())
            )

    def remove_admin(self, user_id: int) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
        return cur.rowcount > 0

    def list_admins(self) -> set[int]:
        with self._conn() as conn:
            rows = conn.execute("SELECT user_id FROM admins").fetchall()
        return {int(r["user_id"]) for r in rows}

    def is_admin(self, user_id: int) -> bool:
        with self._conn() as conn:
            row = conn.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,)).fetchone()
        return row is not None

    # ---- active users (for broadcast) ----
    def record_active_user(self, user_id: int) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO active_users (user_id, first_seen) VALUES (?, ?)", (user_id, utc_now())
            )

    def list_active_users(self) -> list[int]:
        with self._conn() as conn:
            rows = conn.execute("SELECT user_id FROM active_users").fetchall()
        return [int(r["user_id"]) for r in rows]

    # ---- telegram users ----
    def upsert_telegram_user(
        self,
        user_id: int,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        language_code: str | None = None,
        is_premium: bool = False,
        photo_url: str | None = None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO telegram_users (user_id, username, first_name, last_name, language_code, is_premium, photo_url, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username=COALESCE(excluded.username, username),
                    first_name=COALESCE(excluded.first_name, first_name),
                    last_name=COALESCE(excluded.last_name, last_name),
                    language_code=COALESCE(excluded.language_code, language_code),
                    is_premium=excluded.is_premium,
                    photo_url=COALESCE(NULLIF(excluded.photo_url, ''), photo_url, telegram_users.photo_url),
                    last_seen=excluded.last_seen
                """,
                (user_id, username, first_name, last_name, language_code, 1 if is_premium else 0, photo_url or '', utc_now()),
            )

    def get_telegram_user(self, user_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            return _row(conn.execute("SELECT * FROM telegram_users WHERE user_id = ?", (user_id,)).fetchone())

    def list_telegram_users(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM telegram_users ORDER BY last_seen DESC").fetchall()
        return [dict(r) for r in rows]

    def list_all_users_with_stats(self) -> list[dict[str, Any]]:
        """For owner panel: list all users with project counts, only username + photo"""
        with self._conn() as conn:
            # Get all telegram users
            users = conn.execute("SELECT * FROM telegram_users ORDER BY last_seen DESC").fetchall()
            result = []
            for u in users:
                uid = u["user_id"]
                # Count projects for this user
                count_row = conn.execute("SELECT COUNT(*) as c FROM projects WHERE owner_id = ?", (uid,)).fetchone()
                total = count_row["c"] if count_row else 0
                running_row = conn.execute("SELECT COUNT(*) as c FROM projects WHERE owner_id = ? AND status='running'", (uid,)).fetchone()
                running = running_row["c"] if running_row else 0

                # Also include users who have projects but maybe not in telegram_users yet
                result.append({
                    "user_id": uid,  # internal, not to be displayed as profile but needed for API
                    "username": u["username"] or None,
                    "photo_url": u["photo_url"] or "",
                    "first_name": u["first_name"],  # stored but not displayed per requirements
                    "last_name": u["last_name"],
                    "last_seen": u["last_seen"],
                    "total_projects": total,
                    "running_projects": running,
                })

            # Also include active_users who might not have telegram_users entry (fallback)
            active_ids = conn.execute("SELECT user_id FROM active_users").fetchall()
            existing_ids = {r["user_id"] for r in result}
            for row in active_ids:
                aid = row["user_id"]
                if aid not in existing_ids:
                    count_row = conn.execute("SELECT COUNT(*) as c FROM projects WHERE owner_id = ?", (aid,)).fetchone()
                    total = count_row["c"] if count_row else 0
                    running_row = conn.execute("SELECT COUNT(*) as c FROM projects WHERE owner_id = ? AND status='running'", (aid,)).fetchone()
                    running = running_row["c"] if running_row else 0
                    result.append({
                        "user_id": aid,
                        "username": None,
                        "photo_url": "",
                        "first_name": None,
                        "last_name": None,
                        "last_seen": 0,
                        "total_projects": total,
                        "running_projects": running,
                    })

            # Also include users who have projects but are in neither table (edge case)
            proj_owners = conn.execute("SELECT DISTINCT owner_id FROM projects").fetchall()
            for row in proj_owners:
                oid = row["owner_id"]
                if oid not in existing_ids and oid not in {r["user_id"] for r in result}:
                    count_row = conn.execute("SELECT COUNT(*) as c FROM projects WHERE owner_id = ?", (oid,)).fetchone()
                    total = count_row["c"] if count_row else 0
                    result.append({
                        "user_id": oid,
                        "username": None,
                        "photo_url": "",
                        "first_name": None,
                        "last_name": None,
                        "last_seen": 0,
                        "total_projects": total,
                        "running_projects": 0,
                    })

            return result

    # ---- projects ----
    def create_project(self, owner_id: int, name: str, slug: str, runtime: str = "python", description: str = "") -> dict[str, Any]:
        with self._conn() as conn:
            now = utc_now()
            cur = conn.execute(
                "INSERT INTO projects (owner_id, name, slug, status, created_at, updated_at, runtime, description) VALUES (?, ?, ?, 'stopped', ?, ?, ?, ?)",
                (owner_id, name, slug, now, now, runtime, description),
            )
            pid = cur.lastrowid
        return self.get_project(pid)  # type: ignore[arg-type]

    def get_project(self, project_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            return _row(conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone())

    def get_project_by_slug(self, slug: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            return _row(conn.execute("SELECT * FROM projects WHERE slug = ?", (slug,)).fetchone())

    def list_projects(self, owner_id: int) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM projects WHERE owner_id = ? ORDER BY created_at DESC", (owner_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    def list_all_projects(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

    def list_projects_by_user(self, owner_id: int) -> list[dict[str, Any]]:
        return self.list_projects(owner_id)

    def count_projects(self, owner_id: int) -> int:
        with self._conn() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM projects WHERE owner_id = ?", (owner_id,)).fetchone()
        return int(row["c"])

    def count_all_projects(self) -> int:
        with self._conn() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM projects").fetchone()
        return int(row["c"])

    def get_global_stats(self) -> dict[str, Any]:
        with self._conn() as conn:
            total_users = conn.execute("SELECT COUNT(*) as c FROM telegram_users").fetchone()["c"]
            # Also count distinct owners from projects
            distinct_owners = conn.execute("SELECT COUNT(DISTINCT owner_id) as c FROM projects").fetchone()["c"]
            # Use max of both as total users
            total_users = max(total_users, distinct_owners)

            total_projects = conn.execute("SELECT COUNT(*) as c FROM projects").fetchone()["c"]
            running = conn.execute("SELECT COUNT(*) as c FROM projects WHERE status='running'").fetchone()["c"]
            stopped = total_projects - running

            # Recent activity across all
            recent = conn.execute("SELECT * FROM activity_logs ORDER BY created_at DESC LIMIT 20").fetchall()

        return {
            "total_users": total_users,
            "total_projects": total_projects,
            "running_projects": running,
            "stopped_projects": stopped,
            "recent_activity": [dict(r) for r in recent],
        }

    def update_project(self, project_id: int, **changes: Any) -> dict[str, Any] | None:
        if changes:
            changes["updated_at"] = utc_now()
            assignments = ", ".join(f"{k} = ?" for k in changes)
            with self._conn() as conn:
                conn.execute(f"UPDATE projects SET {assignments} WHERE id = ?", (*changes.values(), project_id))
        return self.get_project(project_id)

    def delete_project(self, project_id: int) -> dict[str, Any] | None:
        record = self.get_project(project_id)
        if record:
            with self._conn() as conn:
                conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        return record

    # ---- files ----
    def add_file(self, project_id: int, filename: str, size: int) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO files (project_id, filename, size, uploaded_at) VALUES (?, ?, ?, ?)",
                (project_id, filename, size, utc_now()),
            )

    def list_files(self, project_id: int) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM files WHERE project_id = ? ORDER BY filename", (project_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ---- login tokens ----
    def create_login_token(self, owner_id: int, ttl_seconds: int) -> str:
        token = uuid.uuid4().hex + uuid.uuid4().hex
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO login_tokens (token, owner_id, expires_at, used) VALUES (?, ?, ?, 0)",
                (token, owner_id, utc_now() + ttl_seconds),
            )
        return token

    def revoke_all_tokens(self, owner_id: int) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE login_tokens SET used = 1 WHERE owner_id = ? AND used = 0", (owner_id,)
            )
        return cur.rowcount

    def consume_login_token(self, token: str) -> int | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM login_tokens WHERE token = ? AND used = 0 AND expires_at > ?",
                (token, utc_now()),
            ).fetchone()
            if row is None:
                return None
            conn.execute("UPDATE login_tokens SET used = 1 WHERE token = ?", (token,))
        return int(row["owner_id"])

    # ---- activity ----
    def add_activity(self, action: str, actor: str, project_id: int | None = None, details: str = "") -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO activity_logs (action, actor, project_id, details, created_at) VALUES (?, ?, ?, ?, ?)",
                (action, actor, project_id, details, utc_now()),
            )

    def list_activity(self, limit: int = 50, offset: int = 0, owner_id: int | None = None) -> list[dict[str, Any]]:
        with self._conn() as conn:
            if owner_id is not None:
                rows = conn.execute(
                    "SELECT * FROM activity_logs WHERE actor = ? ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
                    (str(owner_id), limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM activity_logs ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
        return [dict(r) for r in rows]

    def get_user_stats(self, owner_id: int) -> dict[str, Any]:
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) as c FROM projects WHERE owner_id = ?", (owner_id,)).fetchone()["c"]
            running_stored = conn.execute("SELECT COUNT(*) as c FROM projects WHERE owner_id = ? AND status='running'", (owner_id,)).fetchone()["c"]
            stopped_stored = total - running_stored
            recent_activity = conn.execute(
                "SELECT * FROM activity_logs WHERE actor = ? ORDER BY created_at DESC LIMIT 10", (str(owner_id),)
            ).fetchall()
        return {
            "total": total,
            "running_stored": running_stored,
            "stopped_stored": stopped_stored,
            "recent_activity": [dict(r) for r in recent_activity],
        }
