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

            inbox_messages = repository.list_messages(status="inbox")
            waiting_messages = repository.list_messages(status="waiting")
            search_results = repository.list_messages(query="parser")

            self.assertGreater(first_id, 0)
            self.assertEqual([message.subject for message in inbox_messages], ["Compiler notes"])
            self.assertEqual([message.sender for message in waiting_messages], ["Katherine Johnson"])
            self.assertEqual([message.sender for message in search_results], ["Grace Hopper"])

    def test_update_status_and_counts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = InboxRepository(Path(directory) / "test.sqlite3")
            repository.initialize()
            message_id = repository.create_message("Ada Lovelace", "Analytical Engine", "Ship it.")

            repository.update_status(message_id, "done")

            counts = repository.status_counts()
            self.assertEqual(counts["inbox"], 0)
            self.assertEqual(counts["done"], 1)

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
                category="needs_response",
                classification_reason="Contains a direct action phrase.",
                source="imap",
                external_id="<message-1@example.com>",
                received_at="2026-06-11T12:00:00+00:00",
            )
            second = repository.create_imported_message(
                sender="Person <person@example.com>",
                subject="Can you review this today?",
                body="Can you review this today?",
                status="today",
                priority="high",
                category="needs_response",
                classification_reason="Contains a direct action phrase.",
                source="imap",
                external_id="<message-1@example.com>",
                received_at="2026-06-11T12:00:00+00:00",
            )

            self.assertTrue(first)
            self.assertFalse(second)
            self.assertEqual(repository.category_counts()["needs_response"], 1)


if __name__ == "__main__":
    unittest.main()
