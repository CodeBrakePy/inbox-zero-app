"""HTTP server for the personal inbox triage dashboard."""

from __future__ import annotations

import argparse
import mimetypes
from email.utils import parseaddr
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from string import Template
from typing import Any, Optional
from urllib.parse import parse_qs, quote, quote_plus, unquote, urlencode, urlparse

from .models import CATEGORIES, InboxRepository, Message


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
        if not parsed.path.startswith("/messages/") or not parsed.path.endswith("/action"):
            self._send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        try:
            message_id = int(parsed.path.split("/")[2])
            self.repository.apply_action(message_id, _single(self._read_form(), "action", ""))
        except ValueError as exc:
            self._redirect(f"/?error={_escape_url(str(exc))}")
            return

        self._redirect(self._return_path())

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")

    def _render_index(self, query_params: dict[str, list[str]]) -> None:
        category = _single(query_params, "category", "")
        decision_only = _single(query_params, "decision", "") == "1"
        search = _single(query_params, "q", "").strip()
        error = _single(query_params, "error", "")
        selected_id = _optional_int(_single(query_params, "message", ""))
        draft_open = _single(query_params, "draft", "") == "1"

        if category and category not in CATEGORIES:
            category = ""

        messages = self.repository.list_messages(
            category=category or None,
            decision_only=decision_only,
            query=search,
        )
        selected_message = _selected_message(messages, selected_id)
        view_state = {
            "category": category,
            "decision": "1" if decision_only else "",
            "q": search,
        }
        content = render_template(
            "index.html",
            {
                "active_category": category or "all",
                "category_counts": self.repository.category_counts(),
                "dashboard_counts": self.repository.dashboard_counts(),
                "decision_count": str(self.repository.decision_count()),
                "decision_mode": "active" if decision_only else "",
                "detail_panel": _render_detail_panel(selected_message, view_state, draft_open),
                "error": error,
                "message_list": _render_message_list(messages, selected_message, view_state),
                "query": search,
            },
        )
        self._send_html(content)

    def _read_form(self) -> dict[str, list[str]]:
        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length).decode("utf-8")
        return parse_qs(raw_body)

    def _serve_static(self, path: str) -> None:
        filename = unquote(path.removeprefix("/static/"))
        static_root = (BASE_DIR / "static").resolve()
        static_path = (static_root / filename).resolve()
        if not str(static_path).startswith(str(static_root)):
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
        self._send_html(
            render_template("error.html", {"message": message, "status": str(status.value)}),
            status,
        )

    def _redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        self.end_headers()

    def _return_path(self) -> str:
        referer = self.headers.get("Referer", "/")
        parsed = urlparse(referer)
        if parsed.path != "/":
            return "/"
        return f"/?{parsed.query}" if parsed.query else "/"


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
                "category_tabs": _render_category_tabs(
                    context["active_category"],
                    context["category_counts"],
                    context["query"],
                ),
                "dashboard_rows": _render_dashboard_rows(context["dashboard_counts"]),
                "decision_button_class": f'decision-button {context["decision_mode"]}'.strip(),
                "decision_href": _decision_href(context["query"]),
                "error_banner": _render_error(context["error"]),
            }
        )

    return template.safe_substitute(html_context)


def _selected_message(messages: list[Message], selected_id: Optional[int]) -> Optional[Message]:
    if selected_id is not None:
        for message in messages:
            if message.id == selected_id:
                return message
    return messages[0] if messages else None


def _render_error(error: str) -> str:
    if not error:
        return ""
    return f'<p class="alert">{_escape(error)}</p>'


def _render_dashboard_rows(counts: dict[str, int]) -> str:
    return "\n".join(
        f"""
        <a class="dashboard-row" href="{_summary_href(label)}">
            <span>{_escape(label)}</span>
            <strong>{count}</strong>
        </a>
        """
        for label, count in counts.items()
    )


def _summary_href(label: str) -> str:
    category = {
        "Needs reply": "reply_now",
        "Waiting on me": "reply_later",
        "Can archive": "archive",
        "Receipts": "receipt_document",
        "Newsletters": "unsubscribe",
        "Follow up later": "waiting_for_someone",
    }[label]
    return f"/?category={category}"


def _decision_href(query: str) -> str:
    query_part = f"&q={_escape_url(query)}" if query else ""
    return f"/?decision=1{query_part}"


def _render_category_tabs(active_category: str, counts: dict[str, int], query: str) -> str:
    categories = [("all", "All", sum(counts.values()))] + [
        (category, _category_label(category), counts[category]) for category in CATEGORIES
    ]
    query_part = f"&q={_escape_url(query)}" if query else ""
    tabs = []
    for key, label, count in categories:
        href = "/" if key == "all" and not query else f"/?category={key if key != 'all' else ''}{query_part}"
        active = " active" if active_category == key else ""
        tabs.append(
            f'<a class="criterion-tab{active}" href="{href}"><span>{label}</span><strong>{count}</strong></a>'
        )
    return "\n".join(tabs)


def _render_message_list(
    messages: list[Message],
    selected_message: Optional[Message],
    view_state: dict[str, str],
) -> str:
    if not messages:
        return '<div class="empty-state"><h2>Queue clear</h2><p>No emails match this view.</p></div>'

    selected_id = selected_message.id if selected_message else None
    return "\n".join(
        _render_message_list_item(message, message.id == selected_id, view_state)
        for message in messages
    )


def _render_message_list_item(message: Message, selected: bool, view_state: dict[str, str]) -> str:
    selected_class = " selected" if selected else ""
    unread_class = " unread" if not message.is_read else ""
    return f"""
    <a class="message-row{selected_class}{unread_class}" href="{_view_href(view_state, message_id=message.id)}">
        <span class="row-sender">{_escape(message.sender)}</span>
        <strong>{_escape(message.subject)}</strong>
        <span>{_escape(_preview(message.body))}</span>
        <small>{_escape(_category_label(message.category))}</small>
    </a>
    """


def _render_detail_panel(
    message: Optional[Message],
    view_state: dict[str, str],
    draft_open: bool,
) -> str:
    if message is None:
        return '<section class="detail-panel empty-detail"><h2>No email selected</h2><p>Import email or choose another filter.</p></section>'

    draft_href = _view_href(view_state, message_id=message.id, draft=True)
    return f"""
    <section class="detail-panel">
        <header class="detail-header">
            <div>
                <span class="category-pill category-{message.category}">{_escape(_category_label(message.category))}</span>
                <h2>{_escape(message.subject)}</h2>
            </div>
            <span class="source-pill">{_escape(message.source.title())}</span>
        </header>
        <dl class="email-fields">
            <div><dt>From</dt><dd>{_escape(message.sender)}</dd></div>
            <div><dt>Received</dt><dd>{_escape(message.received_at or "Local")}</dd></div>
            <div><dt>Why</dt><dd>{_escape(message.classification_reason)}</dd></div>
        </dl>
        <article class="email-body">{_escape(message.body)}</article>
        <div class="triage-actions">
            {_render_action_button(message.id, "archive", "Archive")}
            {_render_action_button(message.id, "mark_read", "Mark read")}
            {_render_action_button(message.id, "snooze", "Snooze")}
            <a class="secondary-button" href="{draft_href}">Draft reply</a>
            {_render_action_button(message.id, "create_task", "Create task")}
            {_render_action_button(message.id, "unsubscribe", "Unsubscribe")}
            {_render_unsubscribe_link(message)}
        </div>
        {_render_reply_panel(message) if draft_open else ""}
    </section>
    """


def _render_reply_panel(message: Message) -> str:
    draft = _reply_draft(message)
    mailto = _mailto_href(message, draft)
    return f"""
    <section class="reply-panel">
        <h3>Reply draft</h3>
        <textarea rows="8">{_escape(draft)}</textarea>
        <a class="primary-button" href="{_escape(mailto)}">Open mail client</a>
    </section>
    """


def _render_action_button(message_id: int, action: str, label: str) -> str:
    return f"""
    <form method="post" action="/messages/{message_id}/action">
        <input type="hidden" name="action" value="{action}">
        <button type="submit">{label}</button>
    </form>
    """


def _render_unsubscribe_link(message: Message) -> str:
    if not message.unsubscribe_url:
        return ""
    return (
        f'<a class="danger-button" href="{_escape(message.unsubscribe_url)}" '
        'target="_blank" rel="noopener noreferrer">Open unsubscribe link</a>'
    )


def _reply_draft(message: Message) -> str:
    return (
        "Hi,\n\n"
        "Thanks for your email. I saw this and will take a look.\n\n"
        "Best,\n"
    )


def _mailto_href(message: Message, body: str) -> str:
    _, email_address = parseaddr(message.sender)
    recipient = email_address or message.sender
    subject = message.subject if message.subject.lower().startswith("re:") else f"Re: {message.subject}"
    return f"mailto:{quote(recipient)}?{urlencode({'subject': subject, 'body': body})}"


def _view_href(
    view_state: dict[str, str],
    *,
    message_id: Optional[int] = None,
    draft: bool = False,
) -> str:
    params = {}
    if view_state.get("category"):
        params["category"] = view_state["category"]
    if view_state.get("decision"):
        params["decision"] = view_state["decision"]
    if view_state.get("q"):
        params["q"] = view_state["q"]
    if message_id is not None:
        params["message"] = str(message_id)
    if draft:
        params["draft"] = "1"
    return f"/?{urlencode(params)}" if params else "/"


def _category_label(category: str) -> str:
    return {
        "reply_now": "Reply Now",
        "reply_later": "Reply Later",
        "waiting_for_someone": "Waiting For Someone",
        "archive": "Archive",
        "unsubscribe": "Unsubscribe",
        "receipt_document": "Receipt/Document",
        "calendar_related": "Calendar-Related",
        "important_no_action": "Important, No Action",
    }[category]


def _preview(value: str, limit: int = 120) -> str:
    compact = " ".join(value.split())
    return compact if len(compact) <= limit else f"{compact[: limit - 1]}..."


def _optional_int(value: str) -> Optional[int]:
    try:
        return int(value)
    except ValueError:
        return None


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
    parser = argparse.ArgumentParser(description="Run the personal inbox triage dashboard.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    parser.add_argument("--database", default=str(DEFAULT_DATABASE))
    args = parser.parse_args()

    server = create_server(args.host, args.port, Path(args.database))
    print(f"Inbox triage dashboard is running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
