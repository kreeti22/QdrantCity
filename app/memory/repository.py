import json
import logging
from pathlib import Path
import sqlite3
import threading
from typing import Any, Dict, List, Optional

from app.memory.models import (
    BookmarkItem,
    InteractionEvent,
    InteractionType,
    UserPreferenceProfile,
)

logger = logging.getLogger("qdrant_edge.memory.repository")


class MemoryRepository:
    """Local SQLite repository for user memory, bookmarks, and interaction history."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        """Initializes SQLite schema for bookmarks, interaction logs, and user preference profiles."""
        with self._lock:
            with self._conn:
                self._conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS bookmarks (
                        user_id TEXT NOT NULL,
                        experience_id TEXT NOT NULL,
                        title TEXT,
                        category TEXT,
                        price REAL,
                        created_at TEXT NOT NULL,
                        PRIMARY KEY (user_id, experience_id)
                    )
                    """
                )
                try:
                    self._conn.execute("ALTER TABLE bookmarks ADD COLUMN title TEXT")
                except Exception:
                    pass
                try:
                    self._conn.execute("ALTER TABLE bookmarks ADD COLUMN category TEXT")
                except Exception:
                    pass
                try:
                    self._conn.execute("ALTER TABLE bookmarks ADD COLUMN price REAL")
                except Exception:
                    pass

                self._conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS interactions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        experience_id TEXT,
                        query TEXT,
                        metadata TEXT,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                self._conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_profiles (
                        user_id TEXT PRIMARY KEY,
                        profile_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                self._conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_interactions_user ON interactions(user_id, created_at DESC)"
                )
                self._conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_bookmarks_user ON bookmarks(user_id, created_at DESC)"
                )

    def add_bookmark(
        self,
        user_id: str,
        experience_id: Any,
        title: Optional[str] = None,
        category: Optional[str] = None,
        price: Optional[float] = None,
    ) -> bool:
        """Saves an experience to bookmarks. Returns True if inserted, False if already saved."""
        import datetime
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        exp_id_str = str(experience_id)
        with self._lock:
            try:
                with self._conn:
                    cursor = self._conn.execute(
                        """
                        INSERT OR REPLACE INTO bookmarks (user_id, experience_id, title, category, price, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (user_id.strip(), exp_id_str, title, category, price, now_iso),
                    )
                    return cursor.rowcount > 0
            except Exception as e:
                logger.error(f"Failed to add bookmark: {e}")
                return False

    def remove_bookmark(self, user_id: str, experience_id: Any) -> bool:
        """Removes an experience from bookmarks. Returns True if removed, False if not found."""
        exp_id_str = str(experience_id)
        with self._lock:
            try:
                with self._conn:
                    cursor = self._conn.execute(
                        "DELETE FROM bookmarks WHERE user_id = ? AND experience_id = ?",
                        (user_id.strip(), exp_id_str),
                    )
                    return cursor.rowcount > 0
            except Exception as e:
                logger.error(f"Failed to remove bookmark: {e}")
                return False

    def is_bookmarked(self, user_id: str, experience_id: Any) -> bool:
        """Checks if an experience is bookmarked by the user."""
        exp_id_str = str(experience_id)
        with self._lock:
            cursor = self._conn.execute(
                "SELECT 1 FROM bookmarks WHERE user_id = ? AND experience_id = ?",
                (user_id.strip(), exp_id_str),
            )
            return cursor.fetchone() is not None

    def get_bookmarks(self, user_id: str) -> List[Any]:
        """Returns ordered list of bookmarked experience IDs (most recent first)."""
        with self._lock:
            cursor = self._conn.execute(
                "SELECT experience_id FROM bookmarks WHERE user_id = ? ORDER BY created_at DESC",
                (user_id.strip(),),
            )
            results = []
            for row in cursor.fetchall():
                val = row["experience_id"]
                results.append(int(val) if str(val).isdigit() else val)
            return results

    def get_bookmarks_detailed(self, user_id: str) -> List[Dict[str, Any]]:
        """Returns list of bookmarked records with metadata."""
        with self._lock:
            cursor = self._conn.execute(
                "SELECT experience_id, title, category, price, created_at FROM bookmarks WHERE user_id = ? ORDER BY created_at DESC",
                (user_id.strip(),),
            )
            results = []
            for row in cursor.fetchall():
                val = row["experience_id"]
                exp_id = int(val) if str(val).isdigit() else val
                results.append({
                    "experience_id": exp_id,
                    "title": row["title"],
                    "category": row["category"],
                    "price": row["price"],
                    "created_at": row["created_at"],
                })
            return results

    def record_interaction(
        self,
        user_id: str,
        event_type: str,
        experience_id: Optional[Any] = None,
        query: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> InteractionEvent:
        """Appends an interaction event to user history with bounded trimming."""
        import datetime
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        meta_json = json.dumps(metadata or {})
        exp_id_str = str(experience_id) if experience_id is not None else None

        with self._lock:
            with self._conn:
                cursor = self._conn.execute(
                    """
                    INSERT INTO interactions (user_id, event_type, experience_id, query, metadata, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (user_id.strip(), event_type.strip(), exp_id_str, query, meta_json, now_iso),
                )
                event_id = cursor.lastrowid

                # Trim old interactions beyond 200 per user to maintain bounded local storage
                self._conn.execute(
                    """
                    DELETE FROM interactions
                    WHERE user_id = ? AND id NOT IN (
                        SELECT id FROM interactions
                        WHERE user_id = ?
                        ORDER BY created_at DESC, id DESC
                        LIMIT 200
                    )
                    """,
                    (user_id.strip(), user_id.strip()),
                )

        exp_ret = int(exp_id_str) if (exp_id_str and exp_id_str.isdigit()) else exp_id_str
        return InteractionEvent(
            id=event_id,
            user_id=user_id,
            event_type=event_type,
            experience_id=exp_ret,
            query=query,
            metadata=metadata or {},
            created_at=now_iso,
        )

    def get_recent_interactions(self, user_id: str, limit: int = 100) -> List[InteractionEvent]:
        """Retrieves recent user interactions ordered by timestamp descending."""
        with self._lock:
            cursor = self._conn.execute(
                """
                SELECT id, user_id, event_type, experience_id, query, metadata, created_at
                FROM interactions
                WHERE user_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (user_id.strip(), limit),
            )
            events: List[InteractionEvent] = []
            for row in cursor.fetchall():
                try:
                    meta = json.loads(row["metadata"]) if row["metadata"] else {}
                except Exception:
                    meta = {}
                exp_raw = row["experience_id"]
                exp_ret = int(exp_raw) if (exp_raw and str(exp_raw).isdigit()) else exp_raw
                events.append(
                    InteractionEvent(
                        id=row["id"],
                        user_id=row["user_id"],
                        event_type=row["event_type"],
                        experience_id=exp_ret,
                        query=row["query"],
                        metadata=meta,
                        created_at=row["created_at"],
                    )
                )
            return events

    def get_interactions(self, user_id: str, limit: int = 100) -> List[InteractionEvent]:
        """Alias for get_recent_interactions."""
        return self.get_recent_interactions(user_id, limit=limit)

    def save_profile(self, profile: UserPreferenceProfile) -> None:
        """Caches computed preference profile in SQLite."""
        prof_json = profile.model_dump_json()
        with self._lock:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO user_profiles (user_id, profile_json, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        profile_json = excluded.profile_json,
                        updated_at = excluded.updated_at
                    """,
                    (profile.user_id.strip(), prof_json, profile.updated_at),
                )

    def get_profile(self, user_id: str) -> Optional[UserPreferenceProfile]:
        """Retrieves cached user preference profile if present."""
        with self._lock:
            cursor = self._conn.execute(
                "SELECT profile_json FROM user_profiles WHERE user_id = ?",
                (user_id.strip(),),
            )
            row = cursor.fetchone()
            if not row:
                return None
            try:
                data = json.loads(row["profile_json"])
                return UserPreferenceProfile(**data)
            except Exception as e:
                logger.warning(f"Failed to deserialize user profile: {e}")
                return None

    def get_user_profile(self, user_id: str) -> UserPreferenceProfile:
        """Retrieves user preference profile or returns a default empty profile."""
        prof = self.get_profile(user_id)
        if prof is None:
            return UserPreferenceProfile(user_id=user_id)
        return prof

    def reset_user_memory(self, user_id: str) -> None:
        """Clears all bookmarks, interaction history, and profile for a specific user."""
        uid = user_id.strip()
        with self._lock:
            with self._conn:
                self._conn.execute("DELETE FROM bookmarks WHERE user_id = ?", (uid,))
                self._conn.execute("DELETE FROM interactions WHERE user_id = ?", (uid,))
                self._conn.execute("DELETE FROM user_profiles WHERE user_id = ?", (uid,))

    def close(self) -> None:
        """Closes SQLite database connection."""
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass
