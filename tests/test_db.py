from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest
import aiosqlite

from db import (
    init_db, log_activity, get_recent_activity,
    upsert_pr_status, get_all_pr_status, get_pr_status,
    create_pr_draft, get_pending_drafts, update_draft_status,
    create_standup, get_standups, get_latest_standup,
    create_reminder, get_active_reminders, dismiss_reminder, snooze_reminder,
    create_review, get_reviews, get_reviews_for_pr,
    create_digest, get_digests, get_latest_digest,
    log_jira_automation, get_jira_automations, get_jira_automations_for_ticket,
    create_metrics_check, get_metrics_checks, update_metrics_check_value,
    log_metrics_history, get_metrics_history,
    create_weekly_summary, get_weekly_summaries, get_latest_weekly_summary,
)


@pytest.fixture
def db_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test.db"


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_init_db_creates_tables(db_path):
    run(init_db(db_path))
    async def check():
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = [row[0] for row in await cursor.fetchall()]
            return tables
    tables = run(check())
    assert "activity_log" in tables
    assert "pr_drafts" in tables
    assert "pr_status" in tables
    assert "standups" in tables
    assert "reminders" in tables


def test_init_db_is_idempotent(db_path):
    run(init_db(db_path))
    run(init_db(db_path))


def test_log_activity_and_retrieve(db_path):
    run(init_db(db_path))
    run(log_activity(db_path, module="test", action="did_thing", detail="some detail"))
    run(log_activity(db_path, module="test", action="did_another", detail="more detail"))
    activities = run(get_recent_activity(db_path, limit=10))
    assert len(activities) == 2
    assert activities[0]["action"] == "did_another"
    assert activities[1]["action"] == "did_thing"
    assert activities[0]["module"] == "test"


def test_get_recent_activity_respects_limit(db_path):
    run(init_db(db_path))
    for i in range(5):
        run(log_activity(db_path, module="test", action=f"action_{i}", detail=""))
    activities = run(get_recent_activity(db_path, limit=3))
    assert len(activities) == 3


def test_upsert_pr_status_insert(db_path):
    run(init_db(db_path))
    run(upsert_pr_status(db_path, pr_url="https://github.com/org/repo/pull/1", repo="org/repo", title="Fix bug", ci_status="pending"))
    prs = run(get_all_pr_status(db_path))
    assert len(prs) == 1
    assert prs[0]["ci_status"] == "pending"
    assert prs[0]["title"] == "Fix bug"


def test_upsert_pr_status_update(db_path):
    run(init_db(db_path))
    run(upsert_pr_status(db_path, pr_url="https://github.com/org/repo/pull/1", repo="org/repo", title="Fix bug", ci_status="pending"))
    run(upsert_pr_status(db_path, pr_url="https://github.com/org/repo/pull/1", repo="org/repo", title="Fix bug", ci_status="success"))
    prs = run(get_all_pr_status(db_path))
    assert len(prs) == 1
    assert prs[0]["ci_status"] == "success"


def test_get_pr_status_single(db_path):
    run(init_db(db_path))
    run(upsert_pr_status(db_path, pr_url="https://github.com/org/repo/pull/1", repo="org/repo", title="Fix", ci_status="success"))
    pr = run(get_pr_status(db_path, pr_url="https://github.com/org/repo/pull/1"))
    assert pr is not None
    assert pr["ci_status"] == "success"


def test_get_pr_status_not_found(db_path):
    run(init_db(db_path))
    pr = run(get_pr_status(db_path, pr_url="https://github.com/org/repo/pull/999"))
    assert pr is None


def test_create_and_get_pending_drafts(db_path):
    run(init_db(db_path))
    run(create_pr_draft(db_path, pr_url="https://github.com/org/repo/pull/1", comment_id="c1", draft_text="Looks good, thanks!"))
    run(create_pr_draft(db_path, pr_url="https://github.com/org/repo/pull/1", comment_id="c2", draft_text="Will fix."))
    drafts = run(get_pending_drafts(db_path))
    assert len(drafts) == 2
    assert drafts[0]["status"] == "pending"


def test_update_draft_status(db_path):
    run(init_db(db_path))
    run(create_pr_draft(db_path, pr_url="https://github.com/org/repo/pull/1", comment_id="c1", draft_text="Thanks!"))
    drafts = run(get_pending_drafts(db_path))
    draft_id = drafts[0]["id"]
    run(update_draft_status(db_path, draft_id=draft_id, status="approved"))
    updated_drafts = run(get_pending_drafts(db_path))
    assert len(updated_drafts) == 0


def test_update_draft_preserves_other_drafts(db_path):
    run(init_db(db_path))
    run(create_pr_draft(db_path, pr_url="https://github.com/org/repo/pull/1", comment_id="c1", draft_text="Reply 1"))
    run(create_pr_draft(db_path, pr_url="https://github.com/org/repo/pull/1", comment_id="c2", draft_text="Reply 2"))
    drafts = run(get_pending_drafts(db_path))
    run(update_draft_status(db_path, draft_id=drafts[0]["id"], status="approved"))
    remaining = run(get_pending_drafts(db_path))
    assert len(remaining) == 1


def test_create_and_get_standups(db_path):
    run(init_db(db_path))
    run(create_standup(db_path, date="2026-03-05", content="Did stuff"))
    run(create_standup(db_path, date="2026-03-04", content="Did other stuff"))
    standups = run(get_standups(db_path, limit=10))
    assert len(standups) == 2
    assert standups[0]["date"] == "2026-03-05"


def test_get_latest_standup(db_path):
    run(init_db(db_path))
    run(create_standup(db_path, date="2026-03-04", content="Yesterday"))
    run(create_standup(db_path, date="2026-03-05", content="Today"))
    latest = run(get_latest_standup(db_path))
    assert latest is not None
    assert latest["content"] == "Today"


def test_get_latest_standup_empty(db_path):
    run(init_db(db_path))
    latest = run(get_latest_standup(db_path))
    assert latest is None


def test_create_and_get_active_reminders(db_path):
    run(init_db(db_path))
    run(create_reminder(db_path, type="morning", content="2 PRs pending review"))
    run(create_reminder(db_path, type="periodic", content="Stale PR #123"))
    reminders = run(get_active_reminders(db_path))
    assert len(reminders) == 2


def test_dismiss_reminder(db_path):
    run(init_db(db_path))
    run(create_reminder(db_path, type="morning", content="Check PRs"))
    reminders = run(get_active_reminders(db_path))
    run(dismiss_reminder(db_path, reminder_id=reminders[0]["id"]))
    active = run(get_active_reminders(db_path))
    assert len(active) == 0


def test_snooze_reminder(db_path):
    run(init_db(db_path))
    run(create_reminder(db_path, type="morning", content="Check PRs"))
    reminders = run(get_active_reminders(db_path))
    run(snooze_reminder(db_path, reminder_id=reminders[0]["id"], until="2026-03-05 14:00:00"))
    active = run(get_active_reminders(db_path))
    assert active[0]["snoozed_until"] == "2026-03-05 14:00:00"


def test_create_and_get_reviews(db_path):
    run(init_db(db_path))
    run(create_review(db_path, pr_url="https://github.com/org/repo/pull/5", review_summary="Looks good, minor nit on line 42", action_taken=""))
    run(create_review(db_path, pr_url="https://github.com/org/repo/pull/6", review_summary="Needs refactor", action_taken=""))
    reviews = run(get_reviews(db_path, limit=10))
    assert len(reviews) == 2


def test_get_reviews_for_pr(db_path):
    run(init_db(db_path))
    run(create_review(db_path, pr_url="https://github.com/org/repo/pull/5", review_summary="First review", action_taken=""))
    run(create_review(db_path, pr_url="https://github.com/org/repo/pull/6", review_summary="Other PR", action_taken=""))
    reviews = run(get_reviews_for_pr(db_path, pr_url="https://github.com/org/repo/pull/5"))
    assert len(reviews) == 1
    assert reviews[0]["review_summary"] == "First review"


def test_create_and_get_digests(db_path):
    run(init_db(db_path))
    run(create_digest(db_path, date="2026-03-05", content="Today's digest", channels="#eng-feed,#ai-news"))
    run(create_digest(db_path, date="2026-03-04", content="Yesterday's digest", channels="#eng-feed"))
    digests = run(get_digests(db_path, limit=10))
    assert len(digests) == 2
    assert digests[0]["date"] == "2026-03-05"


def test_get_latest_digest(db_path):
    run(init_db(db_path))
    run(create_digest(db_path, date="2026-03-04", content="Yesterday"))
    run(create_digest(db_path, date="2026-03-05", content="Today"))
    latest = run(get_latest_digest(db_path))
    assert latest is not None
    assert latest["content"] == "Today"


def test_get_latest_digest_empty(db_path):
    run(init_db(db_path))
    latest = run(get_latest_digest(db_path))
    assert latest is None


def test_log_and_get_jira_automations(db_path):
    run(init_db(db_path))
    run(log_jira_automation(db_path, ticket_key="PROJ-123", action="transitioned to In Progress"))
    run(log_jira_automation(db_path, ticket_key="PROJ-456", action="transitioned to Done"))
    automations = run(get_jira_automations(db_path, limit=10))
    assert len(automations) == 2


def test_get_jira_automations_for_ticket(db_path):
    run(init_db(db_path))
    run(log_jira_automation(db_path, ticket_key="PROJ-123", action="transitioned to In Progress"))
    run(log_jira_automation(db_path, ticket_key="PROJ-123", action="transitioned to Done"))
    run(log_jira_automation(db_path, ticket_key="PROJ-456", action="created subtask"))
    automations = run(get_jira_automations_for_ticket(db_path, ticket_key="PROJ-123"))
    assert len(automations) == 2


def test_create_and_get_metrics_checks(db_path):
    run(init_db(db_path))
    run(create_metrics_check(db_path, name="p99 latency", query="curl -s http://metrics/p99", threshold=500.0))
    run(create_metrics_check(db_path, name="error rate", query="curl -s http://metrics/errors", threshold=0.01))
    checks = run(get_metrics_checks(db_path))
    assert len(checks) == 2


def test_update_metrics_check_value(db_path):
    run(init_db(db_path))
    run(create_metrics_check(db_path, name="p99 latency", query="curl -s http://metrics/p99", threshold=500.0))
    checks = run(get_metrics_checks(db_path))
    run(update_metrics_check_value(db_path, check_id=checks[0]["id"], value=123.4))
    updated = run(get_metrics_checks(db_path))
    assert updated[0]["last_value"] == 123.4


def test_log_and_get_metrics_history(db_path):
    run(init_db(db_path))
    run(create_metrics_check(db_path, name="p99", query="echo 100", threshold=500.0))
    checks = run(get_metrics_checks(db_path))
    check_id = checks[0]["id"]
    run(log_metrics_history(db_path, check_id=check_id, value=100.0, alerted=False))
    run(log_metrics_history(db_path, check_id=check_id, value=600.0, alerted=True))
    history = run(get_metrics_history(db_path, check_id=check_id, limit=10))
    assert len(history) == 2
    assert any(h["alerted"] == 1 for h in history)


def test_create_and_get_weekly_summaries(db_path):
    run(init_db(db_path))
    run(create_weekly_summary(db_path, week_start="2026-03-02", content="Week summary", google_doc_url="https://docs.google.com/doc/123"))
    summaries = run(get_weekly_summaries(db_path, limit=5))
    assert len(summaries) == 1
    assert summaries[0]["google_doc_url"] == "https://docs.google.com/doc/123"


def test_get_latest_weekly_summary(db_path):
    run(init_db(db_path))
    run(create_weekly_summary(db_path, week_start="2026-02-24", content="Last week"))
    run(create_weekly_summary(db_path, week_start="2026-03-02", content="This week"))
    latest = run(get_latest_weekly_summary(db_path))
    assert latest["content"] == "This week"


def test_get_latest_weekly_summary_empty(db_path):
    run(init_db(db_path))
    latest = run(get_latest_weekly_summary(db_path))
    assert latest is None
