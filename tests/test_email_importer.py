import imaplib
import unittest

from email.message import EmailMessage

from inbox_zero_app.email_importer import (
    _clean_body,
    _friendly_imap_error,
    _unsubscribe_target,
)


class EmailImporterTest(unittest.TestCase):
    def test_gmail_auth_error_points_to_app_password(self) -> None:
        message = _friendly_imap_error(
            "imap.gmail.com",
            "you@gmail.com",
            imaplib.IMAP4.error(
                b"[ALERT] Application-specific password required: https://support.google.com/accounts/answer/185833 (Failure)"
            ),
        )

        self.assertIn("Google app password", message)
        self.assertIn("https://myaccount.google.com/apppasswords", message)
        self.assertIn("INBOX_ZERO_PASSWORD", message)

    def test_clean_body_preserves_paragraphs(self) -> None:
        body = _clean_body("Hello   there,\n\nPlease   review this.\nThanks")

        self.assertEqual(body, "Hello there,\n\nPlease review this.\nThanks")

    def test_unsubscribe_target_prefers_https_header(self) -> None:
        message = EmailMessage()
        message["List-Unsubscribe"] = (
            "<mailto:unsubscribe@example.com>, <https://example.com/unsubscribe?id=123>"
        )

        self.assertEqual(_unsubscribe_target(message), "https://example.com/unsubscribe?id=123")

    def test_unsubscribe_target_falls_back_to_html_link(self) -> None:
        message = EmailMessage()
        message.set_content(
            '<html><body><a href="https://example.com/unsubscribe">Unsubscribe</a></body></html>',
            subtype="html",
        )

        self.assertEqual(_unsubscribe_target(message), "https://example.com/unsubscribe")


if __name__ == "__main__":
    unittest.main()
