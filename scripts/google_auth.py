"""Shared Google OAuth helper — reuses the google-drive credentials file."""
from __future__ import annotations

import pickle
from pathlib import Path

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

CREDENTIALS_FILE = Path.home() / ".claude" / "google-drive-credentials.json"
TOKEN_DIR = Path.home() / ".daily-automate"


def get_credentials(scopes: list[str], token_name: str):
    """Get or refresh OAuth credentials for the given scopes.

    Uses the same client credentials as the google-drive skill but stores
    a separate token file per service (calendar, gmail) so scopes don't clash.
    """
    token_path = TOKEN_DIR / f"{token_name}-token.pickle"
    creds = None

    if token_path.exists():
        with open(token_path, "rb") as f:
            creds = pickle.load(f)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), scopes)
        creds = flow.run_local_server(port=0)

    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    with open(token_path, "wb") as f:
        pickle.dump(creds, f)

    return creds
