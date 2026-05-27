#!/usr/bin/env python3
"""Escalation dispatch, backoff, and cooldown helpers."""
import subprocess
from datetime import datetime, timedelta, timezone


def escalation_key(kind, name):
    """check:<gh_check_name> | comment:<thread_id> | merge_conflict:<owner>/<repo>#<pr>"""
    return f"{kind}:{name}"


def backoff_due(state, key, backoff_minutes, now=None):
    """Per-item backoff + 24h cooldown floor."""
    if now is None:
        now = datetime.now(timezone.utc)
    entry = next((e for e in state.get("escalated", []) if e["key"] == key), None)
    if entry is None:
        return True
    last_notified = datetime.fromisoformat(entry["last_notified"].replace("Z", "+00:00"))
    elapsed = now - last_notified
    ping_count = entry.get("ping_count", 1)
    if ping_count <= len(backoff_minutes):
        required = timedelta(minutes=backoff_minutes[ping_count - 1])
    else:
        required = timedelta(hours=24)
    return elapsed >= required


def record_escalation(state, key, reason, now=None):
    if now is None:
        now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    entry = next((e for e in state.setdefault("escalated", []) if e["key"] == key), None)
    if entry is None:
        state["escalated"].append({
            "key": key,
            "first_seen": now_iso,
            "last_notified": now_iso,
            "ping_count": 1,
            "reason": reason,
        })
    else:
        entry["last_notified"] = now_iso
        entry["ping_count"] = entry.get("ping_count", 0) + 1


def is_in_cooldown(audit, thread_id, now=None):
    """Cooldown check -- prevents re-fixing the same thread too soon."""
    if now is None:
        now = datetime.now(timezone.utc)
    for e in audit:
        if e.get("comment_thread_id") == thread_id and e.get("in_cooldown_until"):
            until = datetime.fromisoformat(e["in_cooldown_until"].replace("Z", "+00:00"))
            if until > now:
                return True
    return False


def format_escalation(owner, repo, pr_number, kind, reason, files=None, url=None):
    label = kind.replace("_", " ").title()
    header = f"**{label}** -- {repo} #{pr_number}"
    lines = [header, ""]
    lines.append(reason)
    if files:
        lines.append("")
        for f in files[:5]:
            lines.append(f"- `{f}`")
        if len(files) > 5:
            lines.append(f"- +{len(files) - 5} more")
    if url:
        lines.append("")
        lines.append(url)
    return "\n".join(lines)


def macos_notify(title, message):
    """Display a macOS notification (non-fatal if it fails)."""
    try:
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{message}" with title "{title}"'],
            capture_output=True, check=False, timeout=5)
    except Exception:
        pass
