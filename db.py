"""SQLite database layer for daily_automate."""
from __future__ import annotations

from pathlib import Path

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    module TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS pr_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pr_url TEXT NOT NULL,
    comment_id TEXT,
    draft_text TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    source TEXT DEFAULT 'system',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pr_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pr_url TEXT NOT NULL UNIQUE,
    repo TEXT NOT NULL,
    title TEXT DEFAULT '',
    ci_status TEXT DEFAULT 'unknown',
    last_checked DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS standups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    content TEXT NOT NULL,
    posted_to_slack INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS digests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    content TEXT NOT NULL,
    channels TEXT DEFAULT '',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pr_url TEXT NOT NULL,
    review_summary TEXT NOT NULL,
    action_taken TEXT DEFAULT '',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS metrics_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    query TEXT NOT NULL,
    threshold REAL,
    schedule TEXT DEFAULT '*/30 * * * *',
    last_value REAL,
    last_checked DATETIME
);

CREATE TABLE IF NOT EXISTS metrics_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    check_id INTEGER NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    value REAL NOT NULL,
    alerted INTEGER DEFAULT 0,
    FOREIGN KEY (check_id) REFERENCES metrics_checks(id)
);

CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    content TEXT NOT NULL,
    due_at DATETIME,
    snoozed_until DATETIME,
    dismissed INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS weekly_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start DATE NOT NULL,
    content TEXT NOT NULL,
    google_doc_url TEXT DEFAULT '',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS jira_automations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_key TEXT NOT NULL,
    action TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""


async def init_db(db_path: Path) -> None:
    async with aiosqlite.connect(db_path) as conn:
        await conn.executescript(SCHEMA)
        await conn.commit()


async def log_activity(db_path: Path, module: str, action: str, detail: str = "") -> None:
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(
            "INSERT INTO activity_log (module, action, detail) VALUES (?, ?, ?)",
            (module, action, detail),
        )
        await conn.commit()


async def get_recent_activity(db_path: Path, limit: int = 20) -> list[dict]:
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM activity_log ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def upsert_pr_status(db_path: Path, pr_url: str, repo: str, title: str, ci_status: str) -> None:
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(
            """INSERT INTO pr_status (pr_url, repo, title, ci_status, last_checked)
               VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(pr_url) DO UPDATE SET
                 ci_status = excluded.ci_status,
                 title = excluded.title,
                 last_checked = CURRENT_TIMESTAMP""",
            (pr_url, repo, title, ci_status),
        )
        await conn.commit()


async def get_all_pr_status(db_path: Path) -> list[dict]:
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM pr_status ORDER BY last_checked DESC")
        return [dict(row) for row in await cursor.fetchall()]


async def get_pr_status(db_path: Path, pr_url: str) -> dict | None:
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM pr_status WHERE pr_url = ?", (pr_url,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def create_pr_draft(db_path: Path, pr_url: str, comment_id: str, draft_text: str) -> int:
    async with aiosqlite.connect(db_path) as conn:
        cursor = await conn.execute(
            "INSERT INTO pr_drafts (pr_url, comment_id, draft_text) VALUES (?, ?, ?)",
            (pr_url, comment_id, draft_text),
        )
        await conn.commit()
        return cursor.lastrowid


async def get_pending_drafts(db_path: Path) -> list[dict]:
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM pr_drafts WHERE status = 'pending' ORDER BY created_at DESC"
        )
        return [dict(row) for row in await cursor.fetchall()]


async def update_draft_status(db_path: Path, draft_id: int, status: str) -> None:
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(
            "UPDATE pr_drafts SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, draft_id),
        )
        await conn.commit()
