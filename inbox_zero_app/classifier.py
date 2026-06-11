"""Local rule-based email classifier.

The goal is not to pretend this is perfect AI. It gives clear, editable rules
that are useful immediately and easy to improve as a Python portfolio project.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EmailClassification:
    category: str
    priority: str
    status: str
    reason: str


NEEDS_RESPONSE_PHRASES = (
    "can you",
    "could you",
    "would you",
    "please",
    "let me know",
    "thoughts",
    "what do you think",
    "do you have",
    "are you able",
    "need your",
    "review",
    "approve",
    "send me",
    "follow up",
    "get back to me",
)

REPLY_LATER_PHRASES = (
    "when you have time",
    "not urgent",
    "next week",
    "later this week",
    "by end of week",
    "whenever you can",
)

WAITING_PHRASES = (
    "waiting on",
    "pending",
    "circling back",
    "following up",
    "checking in",
)

NEWSLETTER_PHRASES = (
    "unsubscribe",
    "view in browser",
    "manage preferences",
    "newsletter",
    "digest",
    "weekly update",
)

AUTOMATED_PHRASES = (
    "no-reply",
    "noreply",
    "do not reply",
    "receipt",
    "invoice",
    "verification code",
    "security alert",
    "password reset",
    "your order",
    "statement",
)

RECEIPT_PHRASES = (
    "receipt",
    "invoice",
    "statement",
    "document",
    "attachment",
    "tax",
    "payment confirmation",
)

CALENDAR_PHRASES = (
    "calendar",
    "invite",
    "invitation",
    "meeting",
    "rescheduled",
    "schedule",
    "zoom",
    "google meet",
    "teams meeting",
)

HIGH_PRIORITY_PHRASES = (
    "urgent",
    "asap",
    "today",
    "deadline",
    "blocked",
    "important",
)


def classify_email(sender: str, subject: str, body: str) -> EmailClassification:
    text = f"{sender} {subject} {body}".lower()
    sender_lower = sender.lower()

    if _contains_any(text, CALENDAR_PHRASES):
        return EmailClassification(
            category="calendar_related",
            priority="normal",
            status="today",
            reason="Looks calendar-related and may need a scheduling decision.",
        )

    if _contains_any(text, NEWSLETTER_PHRASES):
        return EmailClassification(
            category="unsubscribe",
            priority="low",
            status="inbox",
            reason="Looks like a newsletter or mailing list.",
        )

    if _contains_any(text, RECEIPT_PHRASES):
        return EmailClassification(
            category="receipt_document",
            priority="low",
            status="inbox",
            reason="Looks like a receipt, invoice, statement, or document.",
        )

    if _contains_any(text, AUTOMATED_PHRASES) or _contains_any(sender_lower, ("no-reply", "noreply")):
        return EmailClassification(
            category="archive",
            priority="low",
            status="inbox",
            reason="Looks automated, transactional, or notification-only.",
        )

    if _contains_any(text, WAITING_PHRASES):
        return EmailClassification(
            category="waiting_for_someone",
            priority="normal",
            status="waiting",
            reason="Looks like follow-up is blocked on someone else.",
        )

    if _contains_any(text, REPLY_LATER_PHRASES):
        return EmailClassification(
            category="reply_later",
            priority="normal",
            status="waiting",
            reason="Needs a reply, but language suggests it can wait.",
        )

    if "?" in subject or "?" in body or _contains_any(text, NEEDS_RESPONSE_PHRASES):
        priority = "high" if _contains_any(text, HIGH_PRIORITY_PHRASES) else "normal"
        return EmailClassification(
            category="reply_now",
            priority=priority,
            status="today",
            reason="Contains a question or direct action phrase.",
        )

    return EmailClassification(
        category="archive",
        priority="low",
        status="inbox",
        reason="No human decision signal found.",
    )


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)
