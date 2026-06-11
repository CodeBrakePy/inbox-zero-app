import tempfile
import unittest
from pathlib import Path

from inbox_zero_app.models import InboxRepository
from inbox_zero_app.server import render_template


class ServerTest(unittest.TestCase):
    def test_repository_seed_and_template_render(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "server.sqlite3"
            repository = InboxRepository(database)
            repository.initialize()
            repository.seed_demo_messages()

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
                    "message_list": "<a>Portfolio review notes</a>",
                    "query": "",
                },
            )

            self.assertTrue(database.exists())
            self.assertIn("Today&rsquo;s Inbox", html)
            self.assertIn("Portfolio review notes", html)
            self.assertIn("Human Decision Queue", html)


if __name__ == "__main__":
    unittest.main()
