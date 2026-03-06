"""Metrics module: run checks, compare thresholds, alert."""
from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

from db import (
    get_metrics_checks, update_metrics_check_value,
    log_metrics_history, log_activity,
)
from modules.notifier import notify

logger = logging.getLogger("daily_automate.metrics")

NUMBER_PATTERN = re.compile(r"[-+]?\d*\.?\d+")


async def _run_shell(command: str) -> str:
    """Run a shell command and return stdout."""
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.warning("Check command failed: %s\n%s", command, stderr.decode())
        return ""
    return stdout.decode().strip()


async def run_check_command(command: str) -> str:
    """Run a metrics check command."""
    return await _run_shell(command)


def parse_numeric_output(output: str) -> float | None:
    """Extract a numeric value from command output."""
    if not output or not output.strip():
        return None
    match = NUMBER_PATTERN.search(output.strip())
    return float(match.group()) if match else None


def evaluate_threshold(value: float, threshold: float) -> bool:
    """Returns True if value exceeds threshold."""
    return value > threshold


async def run_metrics_checks(db_path: Path, config: dict) -> None:
    """Run all configured metrics checks."""
    checks = await get_metrics_checks(db_path)

    if not checks:
        logger.info("No metrics checks configured")
        return

    for check in checks:
        check_id = check["id"]
        name = check["name"]
        query = check["query"]
        threshold = check["threshold"]

        output = await run_check_command(query)
        value = parse_numeric_output(output)

        if value is None:
            logger.warning("Check '%s' returned no numeric value: %s", name, output)
            continue

        # Update latest value
        await update_metrics_check_value(db_path, check_id=check_id, value=value)

        # Check threshold
        alerted = evaluate_threshold(value, threshold) if threshold is not None else False
        await log_metrics_history(db_path, check_id=check_id, value=value, alerted=alerted)

        if alerted:
            msg = f"*Metrics Alert* — {name}: {value} (threshold: {threshold})"
            await log_activity(db_path, module="metrics", action="alert", detail=msg)
            await notify(config, message=msg)
            logger.warning("Alert: %s = %s (threshold %s)", name, value, threshold)

    await log_activity(db_path, module="metrics", action="check_complete",
                       detail=f"Ran {len(checks)} checks")
