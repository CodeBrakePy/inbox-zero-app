import tempfile
import unittest
from pathlib import Path

from inbox_zero_app.models import InboxRepository


class InboxRepositoryTest(unittest.TestCase):
    def test_create_and_filter_messages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = InboxRepository(Path(directory) / "test.sqlite3")
            repository.initialize()

            first_id = repository.create_message(
                "Grace Hopper",
                "Compiler notes",
                "Please review the parser idea.",
                priority="high",
            )
            repository.create_message(
                "Katherine Johnson",
                "Launch checklist",
                "Waiting on final numbers.",
                status="waiting",
            )

            archive_messages = repository.list_messages(category="archive")
            search_results = repository.list_messages(query="parser")

            self.assertGreater(first_id, 0)
            self.assertEqual([message.subject for message in archive_messages], ["Compiler notes", "Launch checklist"])
            self.assertEqual([message.sender for message in search_results], ["Grace Hopper"])

    def test_rejects_unknown_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = InboxRepository(Path(directory) / "test.sqlite3")
            repository.initialize()

            with self.assertRaises(ValueError):
                repository.create_message("Sender", "Subject", "Body", status="later")

    def test_create_imported_message_deduplicates_by_external_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = InboxRepository(Path(directory) / "test.sqlite3")
            repository.initialize()

            first = repository.create_imported_message(
                sender="Person <person@example.com>",
                subject="Can you review this today?",
                body="Can you review this today?",
                status="today",
                priority="high",
                category="reply_now",
                classification_reason="Contains a direct action phrase.",
                source="imap",
                external_id="<message-1@example.com>",
                received_at="2026-06-11T12:00:00+00:00",
                unsubscribe_url="https://example.com/unsubscribe",
            )
            second = repository.create_imported_message(
                sender="Person <person@example.com>",
                subject="Can you review this today?",
                body="Can you review this today?",
                status="today",
                priority="high",
                category="reply_now",
                classification_reason="Contains a direct action phrase.",
                source="imap",
                external_id="<message-1@example.com>",
                received_at="2026-06-11T12:00:00+00:00",
            )

            self.assertTrue(first)
            self.assertFalse(second)
            self.assertEqual(repository.category_counts()["reply_now"], 1)
            self.assertEqual(
                repository.list_messages()[0].unsubscribe_url,
                "https://example.com/unsubscribe",
            )

    def test_dashboard_counts_and_actions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = InboxRepository(Path(directory) / "test.sqlite3")
            repository.initialize()
            message_id = repository.create_message(
                "Teammate",
                "Can you send this?",
                "Can you send this today?",
                category="reply_now",
                status="today",
            )

            self.assertEqual(repository.dashboard_counts()["Needs reply"], 1)
            self.assertEqual(repository.decision_count(), 1)

            repository.apply_action(message_id, "archive")
            message = repository.get_message(message_id)

            self.assertIsNotNone(message)
            self.assertEqual(message.category, "archive")
            self.assertEqual(message.status, "done")
            self.assertTrue(message.is_read)
            self.assertEqual(repository.dashboard_counts()["Can archive"], 0)
            self.assertEqual(repository.list_messages(), [])

    def test_mark_read_removes_message_from_active_counts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = InboxRepository(Path(directory) / "test.sqlite3")
            repository.initialize()
            message_id = repository.create_message(
                "Teammate",
                "Can you review this?",
                "Can you review this?",
                category="reply_now",
                status="today",
            )

            self.assertEqual(repository.dashboard_counts()["Needs reply"], 1)

            repository.apply_action(message_id, "mark_read")

            self.assertEqual(repository.dashboard_counts()["Needs reply"], 0)
            self.assertEqual(repository.decision_count(), 0)

    def test_initialize_reactivates_unread_old_imports(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = InboxRepository(Path(directory) / "test.sqlite3")
            repository.initialize()
            message_id = repository.create_message(
                "Receipt Bot",
                "Your receipt",
                "Receipt attached.",
                status="done",
                category="receipt_document",
                source="imap",
                is_read=False,
            )

            repository.initialize()
            message = repository.get_message(message_id)

            self.assertIsNotNone(message)
            self.assertEqual(message.status, "inbox")
            self.assertEqual(repository.dashboard_counts()["Receipts"], 1)


if __name__ == "__main__":
    unittest.main()
