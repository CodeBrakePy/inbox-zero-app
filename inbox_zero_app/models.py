"""SQLite persistence for the Inbox Zero app."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional


STATUSES = ("inbox", "today", "waiting", "done")
PRIORITIES = ("low", "normal", "high")


@dataclass(frozen=True)
class Message:
    id: int
    sender: str
    subject: str
    body: str
    status: str
    priority: str
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
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_messages_status_updated
                ON messages(status, updated_at DESC)
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
            ),
            (
                "Mina Patel",
                "Invoice follow-up",
                "Waiting on confirmation from accounting before this can be closed.",
                "waiting",
                "normal",
            ),
            (
                "Jordan Lee",
                "Weekend reading list",
                "Interesting articles about async workers, SQLite, and product analytics.",
                "inbox",
                "low",
            ),
        ]

        for sender, subject, body, status, priority in examples:
            self.create_message(sender, subject, body, status=status, priority=priority)

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
    ) -> int:
        self._validate_status(status)
        self._validate_priority(priority)
        now = _utc_now()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO messages (sender, subject, body, status, priority, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (sender.strip(), subject.strip(), body.strip(), status, priority, now, now),
            )
            return int(cursor.lastrowid)

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
        query: str = "",
    ) -> list[Message]:
        filters: list[str] = []
        values: list[str] = []

        if status:
            self._validate_status(status)
            filters.append("status = ?")
            values.append(status)

        if query:
            filters.append("(sender LIKE ? OR subject LIKE ? OR body LIKE ?)")
            like_query = f"%{query}%"
            values.extend([like_query, like_query, like_query])

        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        sql = f"""
            SELECT id, sender, subject, body, status, priority, created_at, updated_at
            FROM messages
            {where_clause}
            ORDER BY
                CASE priority WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END,
                updated_at DESC
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

    def _validate_status(self, status: str) -> None:
        if status not in STATUSES:
            raise ValueError(f"Unsupported status: {status}")

    def _validate_priority(self, priority: str) -> None:
        if priority not in PRIORITIES:
            raise ValueError(f"Unsupported priority: {priority}")


def _message_from_row(row: sqlite3.Row) -> Message:
    return Message(
        id=int(row["id"]),
        sender=row["sender"],
        subject=row["subject"],
        body=row["body"],
        status=row["status"],
        priority=row["priority"],
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
