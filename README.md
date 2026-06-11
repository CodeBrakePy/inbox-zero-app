# Inbox Zero

A local-first Python web app for turning a messy inbox into a simple action workflow. It is built with the Python standard library, SQLite, and server-rendered HTML/CSS so the code is easy to run, inspect, and extend.

## Features

- Create inbox items with sender, subject, body, and priority.
- Bulk-import email from an IMAP mailbox.
- Classify imported mail as Needs Response, No Response, Newsletter, or Automated.
- Move messages through Inbox, Today, Waiting, and Done states.
- Search across message content.
- Track status counts and compact workflow previews.
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

## Classification Criteria

The classifier is intentionally transparent and editable in `inbox_zero_app/classifier.py`.

- Needs Response: questions or direct action phrases like "can you", "please", "review", "thoughts", or "let me know".
- No Response: messages without a direct reply signal, or messages that look like waiting/follow-up states.
- Newsletter: digests, marketing mail, unsubscribe links, and preference-management language.
- Automated: no-reply senders, receipts, verification codes, security alerts, and transactional notices.

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
