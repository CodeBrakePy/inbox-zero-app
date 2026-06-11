"""HTTP server for the Inbox Zero app."""

from __future__ import annotations

import argparse
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from string import Template
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

from .models import CATEGORIES, PRIORITIES, STATUSES, InboxRepository, Message, group_by_status


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
DEFAULT_DATABASE = PROJECT_ROOT / "data" / "inbox.sqlite3"


class InboxRequestHandler(BaseHTTPRequestHandler):
    repository: InboxRepository

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/static/"):
            self._serve_static(parsed.path)
            return
        if parsed.path == "/health":
            self._send_text("ok")
            return
        if parsed.path == "/":
            self._render_index(parse_qs(parsed.query))
            return
        self._send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        form = self._read_form()

        try:
            if parsed.path == "/messages":
                self._create_message(form)
            elif parsed.path.startswith("/messages/") and parsed.path.endswith("/status"):
                message_id = int(parsed.path.split("/")[2])
                self.repository.update_status(message_id, _single(form, "status", "inbox"))
            elif parsed.path.startswith("/messages/") and parsed.path.endswith("/delete"):
                message_id = int(parsed.path.split("/")[2])
                self.repository.delete_message(message_id)
            else:
                self._send_error(HTTPStatus.NOT_FOUND, "Not found")
                return
        except ValueError as exc:
            self._redirect(f"/?error={exc}")
            return

        self._redirect("/")

    def log_message(self, format: str, *args: Any) -> None:
        """Keep local development logs compact."""
        print(f"{self.address_string()} - {format % args}")

    def _render_index(self, query_params: dict[str, list[str]]) -> None:
        status = _single(query_params, "status", "")
        category = _single(query_params, "category", "")
        search = _single(query_params, "q", "").strip()
        error = _single(query_params, "error", "")

        if status and status not in STATUSES:
            status = ""
        if category and category not in CATEGORIES:
            category = ""

        messages = self.repository.list_messages(
            status=status or None,
            category=category or None,
            query=search,
        )
        grouped = group_by_status(self.repository.list_messages(category=category or None, query=search))
        content = render_template(
            "index.html",
            {
                "active_category": category or "all",
                "active_filter": status or "all",
                "category_counts": self.repository.category_counts(),
                "counts": self.repository.status_counts(),
                "error": error,
                "grouped_messages": grouped,
                "messages": messages,
                "priorities": PRIORITIES,
                "query": search,
                "statuses": STATUSES,
            },
        )
        self._send_html(content)

    def _create_message(self, form: dict[str, list[str]]) -> None:
        sender = _single(form, "sender", "").strip()
        subject = _single(form, "subject", "").strip()
        body = _single(form, "body", "").strip()
        priority = _single(form, "priority", "normal")

        if not sender or not subject or not body:
            raise ValueError("Sender, subject, and message are required.")

        self.repository.create_message(sender, subject, body, priority=priority)

    def _read_form(self) -> dict[str, list[str]]:
        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length).decode("utf-8")
        return parse_qs(raw_body)

    def _serve_static(self, path: str) -> None:
        filename = unquote(path.removeprefix("/static/"))
        static_path = (BASE_DIR / "static" / filename).resolve()
        if not str(static_path).startswith(str((BASE_DIR / "static").resolve())):
            self._send_error(HTTPStatus.FORBIDDEN, "Forbidden")
            return
        if not static_path.is_file():
            self._send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        content_type = mimetypes.guess_type(static_path.name)[0] or "application/octet-stream"
        data = static_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_html(self, content: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_text(self, content: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_error(self, status: HTTPStatus, message: str) -> None:
        self._send_html(render_template("error.html", {"message": message, "status": status.value}), status)

    def _redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        self.end_headers()


def render_template(template_name: str, context: dict[str, Any]) -> str:
    template_path = BASE_DIR / "templates" / template_name
    template = Template(template_path.read_text(encoding="utf-8"))
    html_context = {
        key: value
        for key, value in context.items()
        if isinstance(value, str)
    }

    if template_name == "index.html":
        html_context.update(
            {
                "error_banner": _render_error(context["error"]),
                "filter_tabs": _render_filter_tabs(context["active_filter"], context["counts"], context["query"]),
                "category_tabs": _render_category_tabs(
                    context["active_category"],
                    context["category_counts"],
                    context["query"],
                ),
                "message_cards": _render_message_cards(context["messages"]),
                "workflow_lanes": _render_workflow_lanes(context["grouped_messages"]),
                "priority_options": _render_options(PRIORITIES, "normal"),
            }
        )

    return template.safe_substitute(html_context)


def _render_error(error: str) -> str:
    if not error:
        return ""
    return f'<p class="alert">{_escape(error)}</p>'


def _render_filter_tabs(active_filter: str, counts: dict[str, int], query: str) -> str:
    filters = [("all", "All", sum(counts.values()))] + [
        (status, status.title(), counts[status]) for status in STATUSES
    ]
    tabs = []
    query_part = f"&q={_escape_url(query)}" if query else ""
    for key, label, count in filters:
        href = "/" if key == "all" and not query else f"/?status={key if key != 'all' else ''}{query_part}"
        active = " active" if active_filter == key else ""
        tabs.append(
            f'<a class="tab{active}" href="{href}"><span>{label}</span><strong>{count}</strong></a>'
        )
    return "\n".join(tabs)


def _render_category_tabs(active_category: str, counts: dict[str, int], query: str) -> str:
    categories = [("all", "All Criteria", sum(counts.values()))] + [
        (category, _category_label(category), counts[category]) for category in CATEGORIES
    ]
    tabs = []
    query_part = f"&q={_escape_url(query)}" if query else ""
    for key, label, count in categories:
        href = "/" if key == "all" and not query else f"/?category={key if key != 'all' else ''}{query_part}"
        active = " active" if active_category == key else ""
        tabs.append(
            f'<a class="criterion-tab{active}" href="{href}"><span>{label}</span><strong>{count}</strong></a>'
        )
    return "\n".join(tabs)


def _render_message_cards(messages: list[Message]) -> str:
    if not messages:
        return '<div class="empty-state"><h2>Inbox clear</h2><p>No messages match this view.</p></div>'

    return "\n".join(_render_message_card(message) for message in messages)


def _render_message_card(message: Message) -> str:
    status_buttons = []
    for status in STATUSES:
        disabled = " disabled" if status == message.status else ""
        status_buttons.append(
            f"""
            <form method="post" action="/messages/{message.id}/status">
                <input type="hidden" name="status" value="{status}">
                <button class="icon-button{disabled}" type="submit" title="Move to {status.title()}">{_status_icon(status)}</button>
            </form>
            """
        )

    return f"""
    <article class="message-card priority-{message.priority}">
        <div class="message-topline">
            <span class="priority-dot" title="{message.priority.title()} priority"></span>
            <span class="sender">{_escape(message.sender)}</span>
            <span class="status-pill">{_escape(message.status.title())}</span>
        </div>
        <div class="classification-row">
            <span class="category-pill category-{message.category}">{_escape(_category_label(message.category))}</span>
            <span>{_escape(message.classification_reason)}</span>
        </div>
        <h2>{_escape(message.subject)}</h2>
        <p>{_escape(message.body)}</p>
        <div class="message-actions">
            <div class="status-actions">{"".join(status_buttons)}</div>
            <form method="post" action="/messages/{message.id}/delete">
                <button class="icon-button danger" type="submit" title="Delete">x</button>
            </form>
        </div>
    </article>
    """


def _render_workflow_lanes(grouped_messages: dict[str, list[Message]]) -> str:
    lanes = []
    for status in STATUSES:
        lane_items = grouped_messages[status][:3]
        preview = "".join(
            f'<li><span>{_escape(item.subject)}</span><small>{_escape(item.priority)}</small></li>'
            for item in lane_items
        )
        if not preview:
            preview = "<li><span>Clear</span><small>0</small></li>"
        lanes.append(
            f"""
            <section class="lane">
                <header><h3>{status.title()}</h3><strong>{len(grouped_messages[status])}</strong></header>
                <ul>{preview}</ul>
            </section>
            """
        )
    return "\n".join(lanes)


def _render_options(values: tuple[str, ...], selected: str) -> str:
    return "\n".join(
        f'<option value="{value}"{" selected" if value == selected else ""}>{value.title()}</option>'
        for value in values
    )


def _status_icon(status: str) -> str:
    return {
        "inbox": "I",
        "today": "T",
        "waiting": "W",
        "done": "D",
    }[status]


def _category_label(category: str) -> str:
    return {
        "needs_response": "Needs Response",
        "no_response": "No Response",
        "newsletter": "Newsletter",
        "automated": "Automated",
    }[category]


def _single(values: dict[str, list[str]], key: str, default: str) -> str:
    return values.get(key, [default])[0]


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


def _escape_url(value: str) -> str:
    return quote_plus(value)


def create_server(host: str, port: int, database_path: Path | str = DEFAULT_DATABASE) -> ThreadingHTTPServer:
    repository = InboxRepository(database_path)
    repository.initialize()
    repository.seed_demo_messages()
    handler = type("ConfiguredInboxRequestHandler", (InboxRequestHandler,), {"repository": repository})
    return ThreadingHTTPServer((host, port), handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Inbox Zero local web app.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    parser.add_argument("--database", default=str(DEFAULT_DATABASE))
    args = parser.parse_args()

    server = create_server(args.host, args.port, Path(args.database))
    print(f"Inbox Zero is running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
