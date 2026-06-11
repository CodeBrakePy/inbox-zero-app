import unittest

from inbox_zero_app.classifier import classify_email


class ClassifierTest(unittest.TestCase):
    def test_detects_needs_response(self) -> None:
        result = classify_email(
            "manager@example.com",
            "Can you review this today?",
            "Please send me your thoughts before the deadline.",
        )

        self.assertEqual(result.category, "needs_response")
        self.assertEqual(result.status, "today")
        self.assertEqual(result.priority, "high")

    def test_detects_newsletter(self) -> None:
        result = classify_email(
            "updates@example.com",
            "Weekly update",
            "You are receiving this newsletter. Unsubscribe here.",
        )

        self.assertEqual(result.category, "newsletter")
        self.assertEqual(result.priority, "low")

    def test_detects_automated_email(self) -> None:
        result = classify_email(
            "no-reply@example.com",
            "Your receipt",
            "This is a receipt. Do not reply.",
        )

        self.assertEqual(result.category, "automated")


if __name__ == "__main__":
    unittest.main()
