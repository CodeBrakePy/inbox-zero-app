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

WAITING_PHRASES = (
    "waiting on",
    "pending",
    "circling back",
    "following up",
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

    if _contains_any(text, NEWSLETTER_PHRASES):
        return EmailClassification(
            category="newsletter",
            priority="low",
            status="inbox",
            reason="Looks like a newsletter, digest, or marketing email.",
        )

    if _contains_any(text, AUTOMATED_PHRASES) or _contains_any(sender_lower, ("no-reply", "noreply")):
        return EmailClassification(
            category="automated",
            priority="low",
            status="inbox",
            reason="Looks automated, transactional, or notification-only.",
        )

    if _contains_any(text, WAITING_PHRASES):
        return EmailClassification(
            category="no_response",
            priority="normal",
            status="waiting",
            reason="Looks like a follow-up or waiting state.",
        )

    if "?" in subject or "?" in body or _contains_any(text, NEEDS_RESPONSE_PHRASES):
        priority = "high" if _contains_any(text, HIGH_PRIORITY_PHRASES) else "normal"
        return EmailClassification(
            category="needs_response",
            priority=priority,
            status="today",
            reason="Contains a question or direct action phrase.",
        )

    return EmailClassification(
        category="no_response",
        priority="low",
        status="inbox",
        reason="No direct reply signal found.",
    )


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)
