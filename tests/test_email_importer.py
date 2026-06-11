import imaplib
import unittest

from inbox_zero_app.email_importer import _clean_body, _friendly_imap_error


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


if __name__ == "__main__":
    unittest.main()
