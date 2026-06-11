"""SQLite persistence for the Inbox Zero app."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional


STATUSES = ("inbox", "today", "waiting", "done")
PRIORITIES = ("low", "normal", "high")
CATEGORIES = ("needs_response", "no_response", "newsletter", "automated")


@dataclass(frozen=True)
class Message:
    id: int
    sender: str
    subject: str
    body: str
    status: str
    priority: str
    category: str
    classification_reason: str
    source: str
    external_id: Optional[str]
    received_at: Optional[str]
    created_at: str
    updated_at: str


class InboxRepository:
    """Small repository wrapper around SQLite.

    The app intentionally keeps persistence simple and explicit so it is easy to
    read in a portfolio review.
    """

    def __init__(self, database_path: Path | str) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    body TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('inbox', 'today', 'waiting', 'done')),
                    priority TEXT NOT NULL CHECK(priority IN ('low', 'normal', 'high')),
                    category TEXT NOT NULL DEFAULT 'no_response'
                        CHECK(category IN ('needs_response', 'no_response', 'newsletter', 'automated')),
                    classification_reason TEXT NOT NULL DEFAULT 'Added manually.',
                    source TEXT NOT NULL DEFAULT 'manual',
                    external_id TEXT,
                    received_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._migrate_messages_table(connection)
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_messages_status_updated
                ON messages(status, updated_at DESC)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_messages_category_updated
                ON messages(category, updated_at DESC)
                """
            )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_external_id
                ON messages(external_id)
                WHERE external_id IS NOT NULL
                """
            )

    def seed_demo_messages(self) -> None:
        if self.count_messages() > 0:
            return

        examples = [
            (
                "Avery Chen",
                "Portfolio review notes",
                "Capture the strongest Python projects and add short architecture notes.",
                "today",
                "high",
                "needs_response",
                "Direct task request.",
            ),
            (
                "Mina Patel",
                "Invoice follow-up",
                "Waiting on confirmation from accounting before this can be closed.",
                "waiting",
                "normal",
                "no_response",
                "Waiting on someone else.",
            ),
            (
                "Jordan Lee",
                "Weekend reading list",
                "Interesting articles about async workers, SQLite, and product analytics.",
                "inbox",
                "low",
                "newsletter",
                "Reading material, not a direct request.",
            ),
        ]

        for sender, subject, body, status, priority, category, reason in examples:
            self.create_message(
                sender,
                subject,
                body,
                status=status,
                priority=priority,
                category=category,
                classification_reason=reason,
            )

    def count_messages(self) -> int:
        with self.connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS total FROM messages").fetchone()
            return int(row["total"])

    def create_message(
        self,
        sender: str,
        subject: str,
        body: str,
        *,
        status: str = "inbox",
        priority: str = "normal",
        category: str = "no_response",
        classification_reason: str = "Added manually.",
        source: str = "manual",
        external_id: Optional[str] = None,
        received_at: Optional[str] = None,
    ) -> int:
        self._validate_status(status)
        self._validate_priority(priority)
        self._validate_category(category)
        now = _utc_now()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO messages (
                    sender, subject, body, status, priority, category,
                    classification_reason, source, external_id, received_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sender.strip(),
                    subject.strip(),
                    body.strip(),
                    status,
                    priority,
                    category,
                    classification_reason,
                    source,
                    external_id,
                    received_at,
                    now,
                    now,
                ),
            )
            return int(cursor.lastrowid)

    def create_imported_message(
        self,
        sender: str,
        subject: str,
        body: str,
        *,
        status: str,
        priority: str,
        category: str,
        classification_reason: str,
        source: str,
        external_id: str,
        received_at: Optional[str],
    ) -> bool:
        try:
            self.create_message(
                sender,
                subject,
                body,
                status=status,
                priority=priority,
                category=category,
                classification_reason=classification_reason,
                source=source,
                external_id=external_id,
                received_at=received_at,
            )
        except sqlite3.IntegrityError:
            return False
        return True

    def update_status(self, message_id: int, status: str) -> None:
        self._validate_status(status)
        with self.connect() as connection:
            connection.execute(
                "UPDATE messages SET status = ?, updated_at = ? WHERE id = ?",
                (status, _utc_now(), message_id),
            )

    def delete_message(self, message_id: int) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM messages WHERE id = ?", (message_id,))

    def list_messages(
        self,
        *,
        status: Optional[str] = None,
        category: Optional[str] = None,
        query: str = "",
    ) -> list[Message]:
        filters: list[str] = []
        values: list[str] = []

        if status:
            self._validate_status(status)
            filters.append("status = ?")
            values.append(status)

        if category:
            self._validate_category(category)
            filters.append("category = ?")
            values.append(category)

        if query:
            filters.append(
                "(sender LIKE ? OR subject LIKE ? OR body LIKE ? OR classification_reason LIKE ?)"
            )
            like_query = f"%{query}%"
            values.extend([like_query, like_query, like_query, like_query])

        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        sql = f"""
            SELECT
                id, sender, subject, body, status, priority, category,
                classification_reason, source, external_id, received_at, created_at, updated_at
            FROM messages
            {where_clause}
            ORDER BY
                CASE category WHEN 'needs_response' THEN 1 WHEN 'no_response' THEN 2 ELSE 3 END,
                CASE priority WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END,
                COALESCE(received_at, updated_at) DESC
        """

        with self.connect() as connection:
            rows = connection.execute(sql, values).fetchall()
            return [_message_from_row(row) for row in rows]

    def status_counts(self) -> dict[str, int]:
        counts = {status: 0 for status in STATUSES}
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT status, COUNT(*) AS total FROM messages GROUP BY status"
            ).fetchall()
        for row in rows:
            counts[row["status"]] = int(row["total"])
        return counts

    def category_counts(self) -> dict[str, int]:
        counts = {category: 0 for category in CATEGORIES}
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT category, COUNT(*) AS total FROM messages GROUP BY category"
            ).fetchall()
        for row in rows:
            counts[row["category"]] = int(row["total"])
        return counts

    def _migrate_messages_table(self, connection: sqlite3.Connection) -> None:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(messages)").fetchall()
        }
        migrations = {
            "category": "ALTER TABLE messages ADD COLUMN category TEXT NOT NULL DEFAULT 'no_response'",
            "classification_reason": (
                "ALTER TABLE messages ADD COLUMN classification_reason TEXT NOT NULL DEFAULT 'Added manually.'"
            ),
            "source": "ALTER TABLE messages ADD COLUMN source TEXT NOT NULL DEFAULT 'manual'",
            "external_id": "ALTER TABLE messages ADD COLUMN external_id TEXT",
            "received_at": "ALTER TABLE messages ADD COLUMN received_at TEXT",
        }
        for column, sql in migrations.items():
            if column not in columns:
                connection.execute(sql)

    def _validate_status(self, status: str) -> None:
        if status not in STATUSES:
            raise ValueError(f"Unsupported status: {status}")

    def _validate_priority(self, priority: str) -> None:
        if priority not in PRIORITIES:
            raise ValueError(f"Unsupported priority: {priority}")

    def _validate_category(self, category: str) -> None:
        if category not in CATEGORIES:
            raise ValueError(f"Unsupported category: {category}")


def _message_from_row(row: sqlite3.Row) -> Message:
    return Message(
        id=int(row["id"]),
        sender=row["sender"],
        subject=row["subject"],
        body=row["body"],
        status=row["status"],
        priority=row["priority"],
        category=row["category"],
        classification_reason=row["classification_reason"],
        source=row["source"],
        external_id=row["external_id"],
        received_at=row["received_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def group_by_status(messages: Iterable[Message]) -> dict[str, list[Message]]:
    grouped = {status: [] for status in STATUSES}
    for message in messages:
        grouped[message.status].append(message)
    return grouped
