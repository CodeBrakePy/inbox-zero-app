# Personal Inbox Triage Dashboard

A local-first Python web app for deciding what actually needs your attention. It is not a Gmail clone: it imports email metadata/content, classifies each message, and shows a focused triage dashboard for human decisions.

## Features

- Bulk-import email from an IMAP mailbox.
- Classify imported mail into reply, waiting, archive, unsubscribe, receipt, calendar, and important-no-action buckets.
- Show a "Human Decision Queue" that hides obvious archive/newsletter/receipt noise.
- Apply triage actions: Archive, Mark read, Snooze, Draft reply, Create task, and Unsubscribe.
- Create manual inbox items with sender, subject, body, and priority.
- Search across message content.
- Track "Today's Inbox" counts.
- Store data locally in SQLite.
- Run without third-party runtime dependencies.

## Quick Start

```bash
python3 -m inbox_zero_app.server
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

The app creates `data/inbox.sqlite3` automatically and seeds a few demo messages the first time it runs.

## Import Your Email

The importer uses IMAP and reads credentials from environment variables so secrets never go into the repository.

```bash
export INBOX_ZERO_IMAP_HOST="imap.gmail.com"
export INBOX_ZERO_EMAIL="you@example.com"
export INBOX_ZERO_PASSWORD="your-app-password"

python3 -m inbox_zero_app.email_importer --limit 500
python3 -m inbox_zero_app.server
```

You can import only unread email:

```bash
python3 -m inbox_zero_app.email_importer --limit 200 --unseen-only
```

Common IMAP hosts:

- Gmail: `imap.gmail.com`
- Outlook / Microsoft 365: `outlook.office365.com`
- iCloud Mail: `imap.mail.me.com`
- Yahoo Mail: `imap.mail.yahoo.com`

Many providers require an app password instead of your normal account password.

## Core Dashboard

The main screen summarizes today's inbox like this:

```text
Today's Inbox
-------------
[Needs reply]      4
[Waiting on me]    2
[Can archive]     18
[Receipts]         7
[Newsletters]     21
[Follow up later]  3
```

The killer feature is the Human Decision Queue: it shows only email that appears to require a person to choose an action.

## Classification Criteria

The classifier is intentionally transparent and editable in `inbox_zero_app/classifier.py`.

- Reply now: questions or direct action phrases like "can you", "please", "review", "thoughts", or "let me know".
- Reply later: messages that need a reply but include lower-urgency language.
- Waiting for someone: follow-ups blocked on another person.
- Archive: automated or low-signal mail with no human decision needed.
- Unsubscribe: newsletters, digests, and marketing lists.
- Receipt/document: receipts, invoices, statements, attachments, and records.
- Calendar-related: meeting invites, scheduling, reschedules, and video-call links.
- Important but no action: worth keeping visible but not directly reply-worthy.

## Development

Run tests with:

```bash
python3 -m unittest discover
```

Optional linting and formatting tools can be added later, but the project intentionally starts with no required package installation.

## Project Structure

```text
inbox_zero_app/
  models.py      SQLite repository and data model
  server.py      HTTP routes, form handling, and template rendering
  templates/     HTML templates
  static/        CSS
tests/           Unit tests
```

## Why This Project Showcases Python

This app demonstrates practical Python skills beyond syntax: HTTP routing, safe form handling, SQLite persistence, dataclasses, input validation, tests, and a clean separation between data access and request handling.
