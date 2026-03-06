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
from db import get_standups, get_latest_standup, get_active_reminders, dismiss_reminder, snooze_reminder
from db import get_reviews, get_digests, get_latest_digest
from db import get_metrics_checks, get_metrics_history, get_weekly_summaries, create_metrics_check
from modules.pr_manager import poll_prs
from modules.notifier import notify
from modules.standup import generate_standup
from modules.reminders import morning_summary, periodic_nudge
from modules.pr_reviewer import review_prs
from modules.slack_digest import generate_digest
from modules.metrics import run_metrics_checks
from modules.weekly import generate_weekly_summary
from modules.meetings import poll_meetings, format_time, meetings_summary
from modules.gmail import poll_gmail
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

    async def _standup_job():
        config = load_config()
        await generate_standup(DB_PATH, config)

    async def _morning_job():
        config = load_config()
        await morning_summary(DB_PATH, config)

    async def _periodic_job():
        config = load_config()
        await periodic_nudge(DB_PATH, config)

    app.state.standup_job = _standup_job
    app.state.morning_job = _morning_job
    app.state.periodic_job = _periodic_job

    scheduler.add_job(_standup_job, "cron", hour=9, minute=0, day_of_week="mon-fri", id="standup")
    scheduler.add_job(_morning_job, "cron", hour=7, minute=0, day_of_week="mon-fri", id="morning_reminder")
    scheduler.add_job(_periodic_job, "interval", hours=2, id="periodic_reminder")

    async def _review_prs_job():
        config = load_config()
        await review_prs(DB_PATH, config)

    async def _digest_job():
        config = load_config()
        await generate_digest(DB_PATH, config)

    app.state.review_prs_job = _review_prs_job
    app.state.digest_job = _digest_job

    scheduler.add_job(_review_prs_job, "interval", hours=1, id="pr_review")
    scheduler.add_job(_digest_job, "cron", hour=8, minute=0, day_of_week="mon-fri", id="slack_digest")

    async def _metrics_job():
        config = load_config()
        await run_metrics_checks(DB_PATH, config)

    async def _weekly_job():
        config = load_config()
        await generate_weekly_summary(DB_PATH, config)

    async def _meetings_job():
        config = load_config()
        meetings = await poll_meetings(DB_PATH, config)
        app.state.meetings = meetings

    async def _gmail_job():
        config = load_config()
        data = await poll_gmail(DB_PATH, config)
        app.state.gmail_data = data

    app.state.metrics_job = _metrics_job
    app.state.weekly_job = _weekly_job
    app.state.meetings_job = _meetings_job
    app.state.gmail_job = _gmail_job
    # In-memory cache for latest data (refreshed by jobs)
    app.state.meetings = []
    app.state.gmail_data = {"unread_count": 0, "messages": []}

    scheduler.add_job(_metrics_job, "interval", minutes=30, id="metrics")
    scheduler.add_job(_weekly_job, "cron", hour=16, minute=0, day_of_week="fri", id="weekly_summary")
    scheduler.add_job(_meetings_job, "cron", hour=7, minute=30, day_of_week="mon-fri", id="meetings")
    scheduler.add_job(_gmail_job, "interval", minutes=30, id="gmail")

    scheduler.start()
    app.state.scheduler = scheduler

    yield

    scheduler.shutdown()
    await log_activity(DB_PATH, module="server", action="stopped", detail="Daemon stopped")
    logger.info("daily_automate stopped")


app = FastAPI(title="daily_automate", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.globals["format_time"] = format_time

# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health():
    uptime = int(time.time() - _start_time)
    return {"status": "ok", "uptime": uptime}


@app.get("/api/dashboard/stats")
async def dashboard_stats():
    prs = await get_all_pr_status(DB_PATH)
    drafts = await get_pending_drafts(DB_PATH)
    return {
        "prs_open": len(prs),
        "drafts_pending": len(drafts),
    }


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
    if module == "standup" and hasattr(app.state, "standup_job"):
        asyncio.create_task(app.state.standup_job())
    elif module == "reminders" and hasattr(app.state, "morning_job"):
        asyncio.create_task(app.state.morning_job())
    elif module == "pr_manager" and hasattr(app.state, "poll_prs_job"):
        asyncio.create_task(app.state.poll_prs_job())
    elif module == "review_prs" and hasattr(app.state, "review_prs_job"):
        asyncio.create_task(app.state.review_prs_job())
    elif module == "digest" and hasattr(app.state, "digest_job"):
        asyncio.create_task(app.state.digest_job())
    elif module == "metrics" and hasattr(app.state, "metrics_job"):
        asyncio.create_task(app.state.metrics_job())
    elif module == "weekly" and hasattr(app.state, "weekly_job"):
        asyncio.create_task(app.state.weekly_job())
    elif module == "meetings" and hasattr(app.state, "meetings_job"):
        asyncio.create_task(app.state.meetings_job())
    elif module == "gmail" and hasattr(app.state, "gmail_job"):
        asyncio.create_task(app.state.gmail_job())
    return {"message": f"{module} triggered", "status": "queued"}


@app.get("/api/prs")
async def api_prs():
    prs = await get_all_pr_status(DB_PATH)
    return prs


@app.get("/api/meetings")
async def api_meetings():
    return getattr(app.state, "meetings", [])


@app.get("/api/gmail")
async def api_gmail():
    return getattr(app.state, "gmail_data", {"unread_count": 0, "messages": []})


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


@app.get("/api/standups")
async def api_standups():
    return await get_standups(DB_PATH, limit=10)


@app.get("/api/reminders")
async def api_reminders():
    return await get_active_reminders(DB_PATH)


@app.get("/api/reviews")
async def api_reviews():
    return await get_reviews(DB_PATH, limit=20)


@app.get("/api/digests")
async def api_digests():
    return await get_digests(DB_PATH, limit=10)




@app.get("/api/metrics")
async def api_metrics():
    checks = await get_metrics_checks(DB_PATH)
    return checks


@app.get("/api/metrics/{check_id}/history")
async def api_metrics_history(check_id: int):
    return await get_metrics_history(DB_PATH, check_id=check_id, limit=50)


@app.post("/api/metrics/add")
async def api_add_metrics_check(request: Request):
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        data = await request.json()
    else:
        form = await request.form()
        data = dict(form)
    check_id = await create_metrics_check(
        DB_PATH,
        name=data["name"],
        query=data["query"],
        threshold=float(data["threshold"]),
    )
    await log_activity(DB_PATH, module="metrics", action="check_added", detail=f"Added check: {data['name']}")
    return {"id": check_id, "status": "created"}


@app.get("/api/weekly")
async def api_weekly():
    return await get_weekly_summaries(DB_PATH, limit=10)


@app.post("/api/reminders/{reminder_id}/dismiss")
async def api_dismiss_reminder(reminder_id: int):
    await dismiss_reminder(DB_PATH, reminder_id=reminder_id)
    await log_activity(DB_PATH, module="reminders", action="dismissed", detail=f"Reminder #{reminder_id}")
    return HTMLResponse(f'<div class="card" style="opacity: 0.5;"><div class="card-detail">Dismissed</div></div>')


@app.post("/api/reminders/{reminder_id}/snooze")
async def api_snooze_reminder(reminder_id: int):
    from datetime import datetime, timedelta
    until = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    await snooze_reminder(DB_PATH, reminder_id=reminder_id, until=until)
    await log_activity(DB_PATH, module="reminders", action="snoozed", detail=f"Reminder #{reminder_id} until {until}")
    return HTMLResponse(f'<div class="card" style="opacity: 0.7;"><div class="card-detail">Snoozed until {until}</div></div>')


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

PAGES = [
    ("Dashboard", "/"),
    ("Meetings", "/meetings"),
    ("Gmail", "/gmail"),
    ("PRs", "/prs"),
    ("Reviews", "/reviews"),
    ("Standup", "/standup"),
    ("Digest", "/digest"),
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
    prs = await get_all_pr_status(DB_PATH)
    drafts = await get_pending_drafts(DB_PATH)
    return _render(request, "dashboard.html", activity=act, prs_open=len(prs), drafts_pending=len(drafts))


@app.get("/meetings", response_class=HTMLResponse)
async def meetings_page(request: Request):
    meetings = getattr(app.state, "meetings", [])
    return _render(request, "meetings.html", meetings=meetings)


@app.get("/gmail", response_class=HTMLResponse)
async def gmail_page(request: Request):
    gmail_data = getattr(app.state, "gmail_data", {"unread_count": 0, "messages": []})
    return _render(request, "gmail.html", gmail_data=gmail_data)


@app.get("/prs", response_class=HTMLResponse)
async def prs_page(request: Request):
    prs = await get_all_pr_status(DB_PATH)
    drafts = await get_pending_drafts(DB_PATH)
    # Group drafts by PR URL so the template can show them under each PR
    drafts_by_pr: dict[str, list[dict]] = {}
    for d in drafts:
        drafts_by_pr.setdefault(d["pr_url"], []).append(d)
    return _render(request, "prs.html", prs=prs, drafts_by_pr=drafts_by_pr)


@app.get("/reviews", response_class=HTMLResponse)
async def reviews_page(request: Request):
    reviews = await get_reviews(DB_PATH, limit=20)
    return _render(request, "reviews.html", reviews=reviews)


@app.get("/standup", response_class=HTMLResponse)
async def standup_page(request: Request):
    standups = await get_standups(DB_PATH, limit=10)
    return _render(request, "standup.html", standups=standups)


@app.get("/digest", response_class=HTMLResponse)
async def digest_page(request: Request):
    digests = await get_digests(DB_PATH, limit=10)
    return _render(request, "digest.html", digests=digests)




@app.get("/metrics", response_class=HTMLResponse)
async def metrics_page(request: Request):
    checks = await get_metrics_checks(DB_PATH)
    return _render(request, "metrics.html", checks=checks)


@app.get("/reminders", response_class=HTMLResponse)
async def reminders_page(request: Request):
    reminders = await get_active_reminders(DB_PATH)
    return _render(request, "reminders.html", reminders=reminders)


@app.get("/weekly", response_class=HTMLResponse)
async def weekly_page(request: Request):
    summaries = await get_weekly_summaries(DB_PATH, limit=10)
    return _render(request, "weekly.html", summaries=summaries)


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
