"""Import email from an IMAP mailbox into the local triage database."""

from __future__ import annotations

import argparse
import email
import imaplib
import os
from dataclasses import dataclass
from email.header import decode_header, make_header
from email.message import Message as EmailMessage
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional

from .classifier import classify_email
from .models import InboxRepository
from .server import DEFAULT_DATABASE


@dataclass(frozen=True)
class ImportSummary:
    scanned: int = 0
    imported: int = 0
    skipped: int = 0


class _HTMLTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        cleaned = data.strip()
        if cleaned:
            self.parts.append(cleaned)

    def text(self) -> str:
        return " ".join(self.parts)


def import_from_imap(
    repository: InboxRepository,
    *,
    host: str,
    username: str,
    password: str,
    mailbox: str = "INBOX",
    limit: int = 100,
    unseen_only: bool = False,
    port: int = 993,
) -> ImportSummary:
    repository.initialize()
    search_query = "UNSEEN" if unseen_only else "ALL"
    scanned = imported = skipped = 0

    with imaplib.IMAP4_SSL(host, port) as client:
        client.login(username, password)
        client.select(mailbox)
        _, search_data = client.search(None, search_query)
        message_ids = search_data[0].split()[-limit:]

        for message_id in reversed(message_ids):
            scanned += 1
            _, fetch_data = client.fetch(message_id, "(RFC822)")
            raw_message = _extract_raw_message(fetch_data)
            if raw_message is None:
                skipped += 1
                continue

            parsed = email.message_from_bytes(raw_message)
            imported += _save_message(repository, parsed, username)

    return ImportSummary(scanned=scanned, imported=imported, skipped=scanned - imported)


def _save_message(repository: InboxRepository, parsed: EmailMessage, username: str) -> int:
    sender = _decode_header(parsed.get("From", "Unknown sender"))
    subject = _decode_header(parsed.get("Subject", "(No subject)"))
    body = _message_body(parsed)
    message_id = parsed.get("Message-ID") or f"{username}:{parsed.get('Date', '')}:{subject}:{sender}"
    received_at = _received_at(parsed)
    classification = classify_email(sender, subject, body)

    imported = repository.create_imported_message(
        sender=sender,
        subject=subject,
        body=body[:4000],
        status=classification.status,
        priority=classification.priority,
        category=classification.category,
        classification_reason=classification.reason,
        source="imap",
        external_id=message_id,
        received_at=received_at,
    )
    return 1 if imported else 0


def _extract_raw_message(fetch_data: list[bytes | tuple[bytes, bytes]]) -> Optional[bytes]:
    for item in fetch_data:
        if isinstance(item, tuple) and len(item) == 2:
            return item[1]
    return None


def _decode_header(value: str) -> str:
    try:
        return str(make_header(decode_header(value))).strip()
    except (LookupError, UnicodeDecodeError, ValueError):
        return value.strip()


def _message_body(message: EmailMessage) -> str:
    plain_text = ""
    html_text = ""

    if message.is_multipart():
        for part in message.walk():
            content_type = part.get_content_type()
            disposition = part.get_content_disposition()
            if disposition == "attachment":
                continue
            decoded = _decode_payload(part)
            if content_type == "text/plain" and decoded:
                plain_text += f"\n{decoded}"
            elif content_type == "text/html" and decoded:
                html_text += f"\n{_html_to_text(decoded)}"
    else:
        decoded = _decode_payload(message)
        if message.get_content_type() == "text/html":
            html_text = _html_to_text(decoded)
        else:
            plain_text = decoded

    body = plain_text.strip() or html_text.strip()
    return " ".join(body.split())


def _decode_payload(part: EmailMessage) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        raw_payload = part.get_payload()
        return raw_payload if isinstance(raw_payload, str) else ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def _html_to_text(html: str) -> str:
    parser = _HTMLTextParser()
    parser.feed(html)
    return parser.text()


def _received_at(message: EmailMessage) -> Optional[str]:
    date_header = message.get("Date")
    if not date_header:
        return None
    try:
        parsed = parsedate_to_datetime(date_header)
    except (TypeError, ValueError):
        return None
    return parsed.isoformat()


def main() -> None:
    parser = argparse.ArgumentParser(description="Import email into the inbox triage dashboard.")
    parser.add_argument("--host", default=os.getenv("INBOX_ZERO_IMAP_HOST"))
    parser.add_argument("--username", default=os.getenv("INBOX_ZERO_EMAIL"))
    parser.add_argument("--password", default=os.getenv("INBOX_ZERO_PASSWORD"))
    parser.add_argument("--mailbox", default=os.getenv("INBOX_ZERO_MAILBOX", "INBOX"))
    parser.add_argument("--port", default=int(os.getenv("INBOX_ZERO_IMAP_PORT", "993")), type=int)
    parser.add_argument("--limit", default=100, type=int)
    parser.add_argument("--unseen-only", action="store_true")
    parser.add_argument("--database", default=str(DEFAULT_DATABASE))
    args = parser.parse_args()

    missing = [
        name
        for name, value in {
            "INBOX_ZERO_IMAP_HOST": args.host,
            "INBOX_ZERO_EMAIL": args.username,
            "INBOX_ZERO_PASSWORD": args.password,
        }.items()
        if not value
    ]
    if missing:
        raise SystemExit(f"Missing required settings: {', '.join(missing)}")

    repository = InboxRepository(Path(args.database))
    try:
        summary = import_from_imap(
            repository,
            host=args.host,
            username=args.username,
            password=args.password,
            mailbox=args.mailbox,
            limit=args.limit,
            unseen_only=args.unseen_only,
            port=args.port,
        )
    except imaplib.IMAP4.error as exc:
        raise SystemExit(_friendly_imap_error(args.host, args.username, exc)) from exc
    print(
        "Import complete: "
        f"scanned={summary.scanned}, imported={summary.imported}, skipped={summary.skipped}"
    )


def _friendly_imap_error(host: str, username: str, error: imaplib.IMAP4.error) -> str:
    message = _decode_imap_error(error)
    help_text = [
        f"IMAP login failed for {username} on {host}.",
        f"Server response: {message}",
    ]

    if "Application-specific password required" in message or "gmail" in host.lower():
        help_text.extend(
            [
                "",
                "For Gmail, use a Google app password instead of your normal password:",
                "1. Turn on 2-Step Verification for your Google Account.",
                "2. Open https://myaccount.google.com/apppasswords",
                "3. Create an app password for this local dashboard.",
                "4. Set INBOX_ZERO_PASSWORD to that 16-character app password.",
                "",
                "Example:",
                "export INBOX_ZERO_IMAP_HOST=\"imap.gmail.com\"",
                "export INBOX_ZERO_EMAIL=\"you@gmail.com\"",
                "export INBOX_ZERO_PASSWORD=\"your-16-character-app-password\"",
                "python3 -m inbox_zero_app.email_importer --limit 50",
            ]
        )
    else:
        help_text.extend(
            [
                "",
                "Check that IMAP is enabled for the account and that your username, password, host, and mailbox are correct.",
                "Some providers require an app password instead of your normal account password.",
            ]
        )

    return "\n".join(help_text)


def _decode_imap_error(error: imaplib.IMAP4.error) -> str:
    raw = error.args[0] if error.args else error
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return str(raw)


if __name__ == "__main__":
    main()
