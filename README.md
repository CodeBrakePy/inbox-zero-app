# Inbox Zero

A local-first Python web app for turning a messy inbox into a simple action workflow. It is built with the Python standard library, SQLite, and server-rendered HTML/CSS so the code is easy to run, inspect, and extend.

## Features

- Create inbox items with sender, subject, body, and priority.
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
