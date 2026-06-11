# Personal Inbox Triage Dashboard

A local-first Python dashboard that imports email from IMAP, classifies each message, and shows only the emails that need a human decision. It is intentionally not a Gmail clone.

## What It Does

- Imports email into a local SQLite database.
- Classifies messages into:
  - Reply now
  - Reply later
  - Waiting for someone
  - Archive
  - Unsubscribe
  - Receipt/document
  - Calendar-related
  - Important but no action
- Shows a `Human Decision Queue` that hides obvious archive, receipt, and newsletter noise.
- Lets you triage each message with:
  - Archive
  - Mark read
  - Snooze
  - Draft reply
  - Create task
  - Unsubscribe

## Requirements

- Python 3.9 or newer
- An email account with IMAP enabled
- An app password for providers that require it

No Python package installation is required. The app uses only the Python standard library.

## 1. Clone And Enter The Project

```bash
git clone https://github.com/CodeBrakePy/inbox-zero-app.git
cd inbox-zero-app
```

If you already have the project locally, just `cd` into the project folder.

## 2. Run The Demo Dashboard

```bash
python3 -m inbox_zero_app.server
```

Open:

```text
http://127.0.0.1:8000
```

On first run, the app creates `data/inbox.sqlite3` and adds a few demo messages.

Stop the server with `Control-C`.

## 3. Configure Email Import

Set these environment variables before you run the importer. You do not need the dashboard server running while importing.

```bash
export INBOX_ZERO_IMAP_HOST="imap.gmail.com"
export INBOX_ZERO_EMAIL="you@example.com"
export INBOX_ZERO_PASSWORD="your-app-password"
```

Common IMAP hosts:

| Provider | IMAP host |
| --- | --- |
| Gmail | `imap.gmail.com` |
| Outlook / Microsoft 365 | `outlook.office365.com` |
| iCloud Mail | `imap.mail.me.com` |
| Yahoo Mail | `imap.mail.yahoo.com` |

Most providers do not allow your normal account password for IMAP apps. Use an app password instead.

Provider notes:

- Gmail: enable IMAP in Gmail settings. Then turn on 2-Step Verification, open [Google App Passwords](https://myaccount.google.com/apppasswords), create an app password, and use that 16-character app password for `INBOX_ZERO_PASSWORD`. Your normal Gmail password will fail with `Application-specific password required`.
- iCloud: create an app-specific password from Apple Account settings.
- Yahoo: create an app password from Yahoo account security.
- Outlook / Microsoft 365: IMAP access may need to be enabled by the account or organization.

## 4. Import Email

Run the import command in the same terminal where you exported the variables.

Import the latest 500 messages:

```bash
python3 -m inbox_zero_app.email_importer --limit 500
```

Import only unread messages:

```bash
python3 -m inbox_zero_app.email_importer --limit 200 --unseen-only
```

Import from a different mailbox:

```bash
python3 -m inbox_zero_app.email_importer --mailbox "Archive" --limit 500
```

The importer skips messages it has already imported, so you can run it more than once.

## 5. Open The Dashboard

After import finishes, start the local web app:

```bash
python3 -m inbox_zero_app.server
```

Open:

```text
http://127.0.0.1:8000
```

Use `Human Decision Queue` to focus on messages that likely need your attention.

## Reset Local Data

Your imported email is stored locally in `data/inbox.sqlite3`. To start over:

```bash
rm data/inbox.sqlite3
python3 -m inbox_zero_app.server
```

## Run Tests

```bash
python3 -m unittest discover -s tests -v
```

## Project Structure

```text
inbox_zero_app/
  classifier.py      Rule-based email classification
  email_importer.py  IMAP import command
  models.py          SQLite persistence
  server.py          Local web dashboard
  templates/         HTML templates
  static/            CSS
tests/               Unit tests
```

## Privacy

Credentials are read from environment variables and are not stored in the repository. Imported email content is stored only in your local SQLite database under `data/`, which is ignored by Git.
