"""Fetch unread emails via Gmail API."""
from __future__ import annotations

import base64
import json
import re
import sys

from googleapiclient.discovery import build

from google_auth import get_credentials

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def _extract_body(payload: dict) -> str:
    """Extract plain text body from a Gmail message payload."""
    # Simple message with body directly
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")

    # Multipart — recurse into parts, prefer text/plain
    parts = payload.get("parts", [])
    for part in parts:
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")

    # Fallback: try text/html, strip tags
    for part in parts:
        if part.get("mimeType") == "text/html" and part.get("body", {}).get("data"):
            html = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
            return re.sub(r"<[^>]+>", "", html).strip()

    # Nested multipart (e.g. multipart/alternative inside multipart/mixed)
    for part in parts:
        if part.get("parts"):
            result = _extract_body(part)
            if result:
                return result

    return ""


def fetch_unread_emails(max_results: int = 20) -> dict:
    """Return unread email count and message details including body."""
    creds = get_credentials(SCOPES, "gmail")
    service = build("gmail", "v1", credentials=creds)

    # Get unread count from INBOX
    label = service.users().labels().get(userId="me", id="INBOX").execute()
    unread_count = label.get("messagesUnread", 0)

    # Fetch recent unread messages
    result = service.users().messages().list(
        userId="me",
        labelIds=["INBOX", "UNREAD"],
        maxResults=max_results,
    ).execute()

    messages = []
    for msg_meta in result.get("messages", []):
        msg = service.users().messages().get(
            userId="me", id=msg_meta["id"], format="full",
        ).execute()

        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        body = _extract_body(msg.get("payload", {}))
        # Truncate very long bodies for the dashboard
        if len(body) > 3000:
            body = body[:3000] + "\n\n[... truncated]"

        thread_id = msg.get("threadId", "")

        messages.append({
            "id": msg["id"],
            "thread_id": thread_id,
            "from": headers.get("From", ""),
            "subject": headers.get("Subject", "(No subject)"),
            "date": headers.get("Date", ""),
            "snippet": msg.get("snippet", ""),
            "body": body,
        })

    return {"unread_count": unread_count, "messages": messages}


if __name__ == "__main__":
    data = fetch_unread_emails()
    json.dump(data, sys.stdout, indent=2)
    print()
