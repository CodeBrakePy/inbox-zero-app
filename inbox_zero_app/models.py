"""SQLite persistence for the inbox triage dashboard."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


STATUSES = ("inbox", "today", "waiting", "done")
PRIORITIES = ("low", "normal", "high")
CATEGORIES = (
    "reply_now",
    "reply_later",
    "waiting_for_someone",
    "archive",
    "unsubscribe",
    "receipt_document",
    "calendar_related",
    "important_no_action",
)
DECISION_CATEGORIES = (
    "reply_now",
    "reply_later",
    "waiting_for_someone",
    "calendar_related",
    "important_no_action",
)


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
    unsubscribe_url: Optional[str]
    is_read: bool
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
            if not self._messages_table_exists(connection):
                self._create_messages_table(connection)
            elif self._schema_needs_rebuild(connection):
                self._rebuild_messages_table(connection)
            self._ensure_current_columns(connection)
            self._reactivate_unprocessed_imports(connection)
            self._create_indexes(connection)

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
                "reply_now",
                "Direct task request.",
            ),
            (
                "Mina Patel",
                "Invoice follow-up",
                "Waiting on confirmation from accounting before this can be closed.",
                "waiting",
                "normal",
                "waiting_for_someone",
                "Waiting on someone else.",
            ),
            (
                "Jordan Lee",
                "Weekend reading list",
                "Interesting articles about async workers, SQLite, and product analytics.",
                "inbox",
                "low",
                "unsubscribe",
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
        category: str = "archive",
        classification_reason: str = "Added manually.",
        source: str = "manual",
        external_id: Optional[str] = None,
        received_at: Optional[str] = None,
        unsubscribe_url: Optional[str] = None,
        is_read: bool = False,
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
                    classification_reason, source, external_id, received_at,
                    unsubscribe_url, is_read, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    unsubscribe_url,
                    int(is_read),
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
        unsubscribe_url: Optional[str] = None,
        is_read: bool = False,
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
                unsubscribe_url=unsubscribe_url,
                is_read=is_read,
            )
        except sqlite3.IntegrityError:
            return False
        return True

    def apply_action(self, message_id: int, action: str) -> None:
        updates = {
            "archive": ("done", "archive", "Archived from the triage dashboard.", 1, None),
            "mark_read": ("done", None, "Marked read locally.", 1, None),
            "snooze": ("waiting", "reply_later", "Snoozed out of today's active queue.", 1, None),
            "create_task": ("done", "important_no_action", "Converted into a task candidate.", 1, "high"),
            "unsubscribe": ("done", "unsubscribe", "Marked for unsubscribe.", 1, "low"),
        }
        if action not in updates:
            raise ValueError(f"Unsupported action: {action}")

        status, category, reason, is_read, priority = updates[action]
        assignments = ["classification_reason = ?", "updated_at = ?"]
        values: list[str | int] = [reason, _utc_now()]
        if status is not None:
            self._validate_status(status)
            assignments.append("status = ?")
            values.append(status)
        if category is not None:
            self._validate_category(category)
            assignments.append("category = ?")
            values.append(category)
        if is_read is not None:
            assignments.append("is_read = ?")
            values.append(is_read)
        if priority is not None:
            self._validate_priority(priority)
            assignments.append("priority = ?")
            values.append(priority)

        values.append(message_id)
        with self.connect() as connection:
            connection.execute(
                f"UPDATE messages SET {', '.join(assignments)} WHERE id = ?",
                values,
            )

    def get_message(self, message_id: int) -> Optional[Message]:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT
                    id, sender, subject, body, status, priority, category,
                    classification_reason, source, external_id, received_at,
                    unsubscribe_url, is_read, created_at, updated_at
                FROM messages
                WHERE id = ?
                """,
                (message_id,),
            ).fetchone()
        return _message_from_row(row) if row else None

    def list_messages(
        self,
        *,
        category: Optional[str] = None,
        decision_only: bool = False,
        active_only: bool = True,
        query: str = "",
    ) -> list[Message]:
        filters: list[str] = []
        values: list[str] = []

        if active_only:
            filters.append("status != 'done'")
            filters.append("is_read = 0")

        if category:
            self._validate_category(category)
            filters.append("category = ?")
            values.append(category)

        if decision_only:
            placeholders = ", ".join("?" for _ in DECISION_CATEGORIES)
            filters.append(f"category IN ({placeholders})")
            values.extend(DECISION_CATEGORIES)

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
                classification_reason, source, external_id, received_at,
                unsubscribe_url, is_read, created_at, updated_at
            FROM messages
            {where_clause}
            ORDER BY
                CASE category
                    WHEN 'reply_now' THEN 1
                    WHEN 'reply_later' THEN 2
                    WHEN 'waiting_for_someone' THEN 3
                    WHEN 'calendar_related' THEN 4
                    WHEN 'important_no_action' THEN 5
                    ELSE 6
                END,
                CASE priority WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END,
                COALESCE(received_at, updated_at) DESC
        """

        with self.connect() as connection:
            rows = connection.execute(sql, values).fetchall()
            return [_message_from_row(row) for row in rows]

    def category_counts(self, *, active_only: bool = True) -> dict[str, int]:
        counts = {category: 0 for category in CATEGORIES}
        where_clause = "WHERE status != 'done' AND is_read = 0" if active_only else ""
        with self.connect() as connection:
            rows = connection.execute(
                f"SELECT category, COUNT(*) AS total FROM messages {where_clause} GROUP BY category"
            ).fetchall()
        for row in rows:
            counts[row["category"]] = int(row["total"])
        return counts

    def dashboard_counts(self) -> dict[str, int]:
        category_counts = self.category_counts(active_only=True)
        return {
            "Needs reply": category_counts["reply_now"],
            "Waiting on me": category_counts["reply_later"],
            "Can archive": category_counts["archive"],
            "Receipts": category_counts["receipt_document"],
            "Newsletters": category_counts["unsubscribe"],
            "Follow up later": category_counts["waiting_for_someone"],
        }

    def decision_count(self) -> int:
        return sum(self.category_counts(active_only=True)[category] for category in DECISION_CATEGORIES)

    def _messages_table_exists(self, connection: sqlite3.Connection) -> bool:
        row = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'messages'"
        ).fetchone()
        return row is not None

    def _schema_needs_rebuild(self, connection: sqlite3.Connection) -> bool:
        row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'messages'"
        ).fetchone()
        sql = row["sql"] if row else ""
        columns = self._table_columns(connection)
        return "reply_now" not in sql or "is_read" not in columns

    def _table_columns(self, connection: sqlite3.Connection) -> set[str]:
        return {
            row["name"]
            for row in connection.execute("PRAGMA table_info(messages)").fetchall()
        }

    def _create_messages_table(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender TEXT NOT NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('inbox', 'today', 'waiting', 'done')),
                priority TEXT NOT NULL CHECK(priority IN ('low', 'normal', 'high')),
                category TEXT NOT NULL DEFAULT 'archive'
                    CHECK(category IN (
                        'reply_now', 'reply_later', 'waiting_for_someone', 'archive',
                        'unsubscribe', 'receipt_document', 'calendar_related', 'important_no_action'
                    )),
                classification_reason TEXT NOT NULL DEFAULT 'Added manually.',
                source TEXT NOT NULL DEFAULT 'manual',
                external_id TEXT,
                received_at TEXT,
                unsubscribe_url TEXT,
                is_read INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

    def _rebuild_messages_table(self, connection: sqlite3.Connection) -> None:
        columns = self._table_columns(connection)
        connection.execute("ALTER TABLE messages RENAME TO messages_legacy")
        self._create_messages_table(connection)
        legacy_select = {
            "category": "category" if "category" in columns else "'archive'",
            "classification_reason": (
                "classification_reason" if "classification_reason" in columns else "'Added manually.'"
            ),
            "source": "source" if "source" in columns else "'manual'",
            "external_id": "external_id" if "external_id" in columns else "NULL",
            "received_at": "received_at" if "received_at" in columns else "NULL",
            "unsubscribe_url": "unsubscribe_url" if "unsubscribe_url" in columns else "NULL",
            "is_read": "is_read" if "is_read" in columns else "0",
        }
        connection.execute(
            f"""
            INSERT INTO messages (
                id, sender, subject, body, status, priority, category,
                classification_reason, source, external_id, received_at,
                unsubscribe_url, is_read, created_at, updated_at
            )
            SELECT
                id,
                sender,
                subject,
                body,
                status,
                priority,
                CASE {legacy_select["category"]}
                    WHEN 'needs_response' THEN 'reply_now'
                    WHEN 'no_response' THEN 'archive'
                    WHEN 'newsletter' THEN 'unsubscribe'
                    WHEN 'automated' THEN 'receipt_document'
                    WHEN 'reply_now' THEN 'reply_now'
                    WHEN 'reply_later' THEN 'reply_later'
                    WHEN 'waiting_for_someone' THEN 'waiting_for_someone'
                    WHEN 'archive' THEN 'archive'
                    WHEN 'unsubscribe' THEN 'unsubscribe'
                    WHEN 'receipt_document' THEN 'receipt_document'
                    WHEN 'calendar_related' THEN 'calendar_related'
                    WHEN 'important_no_action' THEN 'important_no_action'
                    ELSE 'archive'
                END,
                {legacy_select["classification_reason"]},
                {legacy_select["source"]},
                {legacy_select["external_id"]},
                {legacy_select["received_at"]},
                {legacy_select["unsubscribe_url"]},
                {legacy_select["is_read"]},
                created_at,
                updated_at
            FROM messages_legacy
            """
        )
        connection.execute("DROP TABLE messages_legacy")

    def _ensure_current_columns(self, connection: sqlite3.Connection) -> None:
        if "unsubscribe_url" not in self._table_columns(connection):
            connection.execute("ALTER TABLE messages ADD COLUMN unsubscribe_url TEXT")

    def _create_indexes(self, connection: sqlite3.Connection) -> None:
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

    def _reactivate_unprocessed_imports(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            UPDATE messages
            SET status = 'inbox'
            WHERE source = 'imap'
                AND is_read = 0
                AND status = 'done'
                AND category IN ('archive', 'unsubscribe', 'receipt_document')
            """
        )

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
        unsubscribe_url=row["unsubscribe_url"],
        is_read=bool(row["is_read"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
