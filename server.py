#!/usr/bin/env python3
"""daily_automate: Personal automation daemon.

Usage:
    python server.py run     # Run in foreground
    python server.py start   # Start as background daemon
    python server.py stop    # Stop background daemon
"""
from __future__ import annotations

import logging
import os
import signal
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import load_config, CONFIG_DIR
from db import init_db, log_activity, get_recent_activity
import asyncio
from db import get_all_pr_status, get_pending_drafts, update_draft_status
from modules.pr_manager import poll_prs
from modules.notifier import notify
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).parent
DB_PATH = CONFIG_DIR / "data.db"
PID_FILE = CONFIG_DIR / "pid"
LOG_DIR = CONFIG_DIR / "logs"
LOG_FILE = LOG_DIR / "server.log"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("daily_automate")

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

_start_time: float = time.time()
_config: dict = {}

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _config, _start_time
    _start_time = time.time()

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    _config = load_config()
    await init_db(DB_PATH)
    await log_activity(DB_PATH, module="server", action="started", detail="Daemon started")
    logger.info(
        "daily_automate started on http://%s:%s",
        _config["server"]["host"],
        _config["server"]["port"],
    )

    # Start scheduler
    scheduler = AsyncIOScheduler()

    async def _poll_prs_job():
        config = load_config()
        async def _notify(msg, pr_url, event):
            await notify(config, msg, pr_url, event)
        await poll_prs(DB_PATH, config, notify_fn=_notify)

    app.state.poll_prs_job = _poll_prs_job
    scheduler.add_job(_poll_prs_job, "interval", minutes=5, id="pr_poll")
    scheduler.start()
    app.state.scheduler = scheduler

    yield

    scheduler.shutdown()
    await log_activity(DB_PATH, module="server", action="stopped", detail="Daemon stopped")
    logger.info("daily_automate stopped")


app = FastAPI(title="daily_automate", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health():
    uptime = int(time.time() - _start_time)
    return {"status": "ok", "uptime": uptime}


@app.get("/api/activity")
async def activity():
    entries = await get_recent_activity(DB_PATH, limit=50)
    return entries


@app.get("/api/activity/html", response_class=HTMLResponse)
async def activity_html(request: Request):
    entries = await get_recent_activity(DB_PATH, limit=20)
    html = '<h2>Recent Activity</h2>\n'
    if entries:
        for item in entries:
            ts = item["timestamp"][:16] if item.get("timestamp") else ""
            html += (
                f'<div class="activity-item">'
                f'<span class="activity-time">{ts}</span>'
                f'<span class="activity-module">{item["module"]}</span>'
                f'<span class="activity-text">{item["action"]}'
            )
            if item.get("detail"):
                html += f' &mdash; {item["detail"]}'
            html += '</span></div>\n'
    else:
        html += '<div class="activity-item"><span class="activity-text">No activity yet. Trigger an automation to get started.</span></div>'
    return HTMLResponse(html)


@app.post("/api/trigger/{module}")
async def trigger(module: str):
    await log_activity(DB_PATH, module=module, action="triggered", detail="Manual trigger from UI")
    if module == "pr_manager" and hasattr(app.state, "poll_prs_job"):
        asyncio.create_task(app.state.poll_prs_job())
    return {"message": f"{module} triggered", "status": "queued"}


@app.get("/api/prs")
async def api_prs():
    prs = await get_all_pr_status(DB_PATH)
    return prs


@app.get("/api/drafts")
async def api_drafts():
    drafts = await get_pending_drafts(DB_PATH)
    return drafts


@app.get("/api/drafts/html", response_class=HTMLResponse)
async def drafts_html():
    drafts = await get_pending_drafts(DB_PATH)
    if not drafts:
        return HTMLResponse('<div class="placeholder" style="min-height: 120px;"><p>No pending drafts. New review comments will appear here.</p></div>')
    html = ""
    for draft in drafts:
        pr_short = draft["pr_url"].replace("https://github.com/", "")
        html += f'''<div class="card draft-card" id="draft-{draft["id"]}">
            <div class="card-title"><a href="{draft["pr_url"]}" target="_blank">{pr_short}</a></div>
            <div class="draft-text">{draft["draft_text"]}</div>
            <div class="draft-actions">
                <button class="btn btn-primary" hx-post="/api/drafts/{draft["id"]}/approve" hx-target="#draft-{draft["id"]}" hx-swap="outerHTML">Approve</button>
                <button class="btn" hx-post="/api/drafts/{draft["id"]}/reject" hx-target="#draft-{draft["id"]}" hx-swap="outerHTML">Reject</button>
            </div>
        </div>\n'''
    return HTMLResponse(html)


@app.post("/api/drafts/{draft_id}/approve")
async def approve_draft(draft_id: int):
    await update_draft_status(DB_PATH, draft_id=draft_id, status="approved")
    await log_activity(DB_PATH, module="pr_manager", action="draft_approved", detail=f"Draft #{draft_id} approved")
    return HTMLResponse(f'<div class="card draft-card" style="opacity: 0.5;"><div class="card-detail">Draft #{draft_id} approved</div></div>')


@app.post("/api/drafts/{draft_id}/reject")
async def reject_draft(draft_id: int):
    await update_draft_status(DB_PATH, draft_id=draft_id, status="rejected")
    await log_activity(DB_PATH, module="pr_manager", action="draft_rejected", detail=f"Draft #{draft_id} rejected")
    return HTMLResponse(f'<div class="card draft-card" style="opacity: 0.5;"><div class="card-detail">Draft #{draft_id} rejected</div></div>')


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

PAGES = [
    ("Dashboard", "/"),
    ("PRs", "/prs"),
    ("Reviews", "/reviews"),
    ("Standup", "/standup"),
    ("Digest", "/digest"),
    ("JIRA", "/jira"),
    ("Metrics", "/metrics"),
    ("Reminders", "/reminders"),
    ("Weekly", "/weekly"),
    ("Config", "/config"),
]


def _render(request: Request, template: str, **kwargs):
    return templates.TemplateResponse(
        request,
        template,
        {"pages": PAGES, "current_path": str(request.url.path), **kwargs},
    )


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    act = await get_recent_activity(DB_PATH, limit=20)
    return _render(request, "dashboard.html", activity=act)


@app.get("/prs", response_class=HTMLResponse)
async def prs_page(request: Request):
    prs = await get_all_pr_status(DB_PATH)
    drafts = await get_pending_drafts(DB_PATH)
    return _render(request, "prs.html", prs=prs, drafts=drafts)


@app.get("/reviews", response_class=HTMLResponse)
async def reviews_page(request: Request):
    return _render(request, "placeholder.html", title="Reviews", description="PR reviews coming in Phase 4")


@app.get("/standup", response_class=HTMLResponse)
async def standup_page(request: Request):
    return _render(request, "placeholder.html", title="Standup", description="Standup generation coming in Phase 3")


@app.get("/digest", response_class=HTMLResponse)
async def digest_page(request: Request):
    return _render(request, "placeholder.html", title="Digest", description="Slack digest coming in Phase 4")


@app.get("/jira", response_class=HTMLResponse)
async def jira_page(request: Request):
    return _render(request, "placeholder.html", title="JIRA", description="JIRA automation coming in Phase 5")


@app.get("/metrics", response_class=HTMLResponse)
async def metrics_page(request: Request):
    return _render(request, "placeholder.html", title="Metrics", description="Metrics checks coming in Phase 6")


@app.get("/reminders", response_class=HTMLResponse)
async def reminders_page(request: Request):
    return _render(request, "placeholder.html", title="Reminders", description="Reminders coming in Phase 3")


@app.get("/weekly", response_class=HTMLResponse)
async def weekly_page(request: Request):
    return _render(request, "placeholder.html", title="Weekly", description="Weekly summary coming in Phase 6")


@app.get("/config", response_class=HTMLResponse)
async def config_page(request: Request):
    return _render(request, "placeholder.html", title="Config", description="Configuration coming soon")


# ---------------------------------------------------------------------------
# Daemon management
# ---------------------------------------------------------------------------


def _daemonize():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    pid = os.fork()
    if pid > 0:
        print(f"daily_automate started (PID {pid})")
        sys.exit(0)

    os.setsid()

    log_fd = open(LOG_FILE, "a")
    os.dup2(log_fd.fileno(), sys.stdout.fileno())
    os.dup2(log_fd.fileno(), sys.stderr.fileno())

    PID_FILE.write_text(str(os.getpid()))


def _stop():
    if not PID_FILE.exists():
        print("No running daemon found.")
        sys.exit(1)

    pid = int(PID_FILE.read_text().strip())
    try:
        os.kill(pid, signal.SIGTERM)
        print(f"Stopped daily_automate (PID {pid})")
    except ProcessLookupError:
        print(f"Process {pid} not found (stale PID file).")
    PID_FILE.unlink(missing_ok=True)


def _run(daemon: bool = False):
    if daemon:
        _daemonize()

    config = load_config()
    uvicorn.run(
        app,
        host=config["server"]["host"],
        port=config["server"]["port"],
        log_level="info",
    )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python server.py [run|start|stop]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "run":
        _run(daemon=False)
    elif cmd == "start":
        _run(daemon=True)
    elif cmd == "stop":
        _stop()
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
