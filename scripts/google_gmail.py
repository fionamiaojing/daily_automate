"""Fetch unread emails via Gmail API."""
from __future__ import annotations

import base64
import json
import sys

from googleapiclient.discovery import build

from google_auth import get_credentials

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def fetch_unread_emails(max_results: int = 20) -> dict:
    """Return unread email count and message summaries."""
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
            userId="me", id=msg_meta["id"], format="metadata",
            metadataHeaders=["From", "Subject", "Date"],
        ).execute()

        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        messages.append({
            "id": msg["id"],
            "from": headers.get("From", ""),
            "subject": headers.get("Subject", "(No subject)"),
            "date": headers.get("Date", ""),
            "snippet": msg.get("snippet", ""),
        })

    return {"unread_count": unread_count, "messages": messages}


if __name__ == "__main__":
    data = fetch_unread_emails()
    json.dump(data, sys.stdout, indent=2)
    print()
