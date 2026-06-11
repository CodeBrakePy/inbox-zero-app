import tempfile
import unittest
from pathlib import Path

from inbox_zero_app.models import InboxRepository
from inbox_zero_app.server import _render_detail_panel, render_template


class ServerTest(unittest.TestCase):
    def test_repository_seed_and_template_render(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "server.sqlite3"
            repository = InboxRepository(database)
            repository.initialize()
            repository.create_message(
                "Newsletter <news@example.com>",
                "Weekly news",
                "Please unsubscribe if you want.",
                category="unsubscribe",
                unsubscribe_url="https://example.com/unsubscribe",
            )

            html = render_template(
                "index.html",
                {
                    "active_category": "all",
                    "category_counts": repository.category_counts(),
                    "dashboard_counts": repository.dashboard_counts(),
                    "detail_panel": "<section>Detail</section>",
                    "decision_count": str(repository.decision_count()),
                    "decision_mode": "",
                    "error": "",
                    "message_list": "<a>Weekly news</a>",
                    "query": "",
                },
            )

            self.assertTrue(database.exists())
            self.assertIn("Today&rsquo;s Inbox", html)
            self.assertIn("Weekly news", html)
            self.assertIn("Human Decision Queue", html)

    def test_detail_panel_shows_unsubscribe_link_when_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = InboxRepository(Path(directory) / "server.sqlite3")
            repository.initialize()
            message_id = repository.create_message(
                "Newsletter <news@example.com>",
                "Weekly news",
                "Please unsubscribe if you want.",
                category="unsubscribe",
                unsubscribe_url="https://example.com/unsubscribe",
            )

            message = repository.get_message(message_id)
            self.assertIsNotNone(message)

            html = _render_detail_panel(message, {"category": "", "decision": "", "q": ""}, False)

            self.assertIn("Open unsubscribe link", html)
            self.assertIn("https://example.com/unsubscribe", html)


if __name__ == "__main__":
    unittest.main()
