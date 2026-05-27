#!/usr/bin/env python3
"""PR Babysit state file CRUD — per-PR JSON state, audit filtering, deletion."""
import json
import os
from datetime import datetime, timedelta, timezone

STATE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "pr-babysit", "state")


def state_path(owner, repo, pr_number):
    return os.path.join(STATE_DIR, f"{owner}__{repo}__{pr_number}.json")


def load_state(owner, repo, pr_number):
    path = state_path(owner, repo, pr_number)
    if not os.path.exists(path):
        return {
            "session_id": None,
            "pid": None,
            "started_at": None,
            "last_fire": None,
            "base_sha": None,
            "head_sha": None,
            "pr_diff_files": [],
            "handled_comment_ids": [],
            "escalated": [],
            "audit": [],
        }
    with open(path) as f:
        return json.load(f)


def save_state(owner, repo, pr_number, state):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(state_path(owner, repo, pr_number), "w") as f:
        json.dump(state, f, indent=2)


def delete_state(owner, repo, pr_number):
    path = state_path(owner, repo, pr_number)
    if os.path.exists(path):
        os.remove(path)


def filter_audit_24h(audit, now=None):
    if now is None:
        now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)
    return [e for e in audit if datetime.fromisoformat(
        e["fix_pushed_at"].replace("Z", "+00:00")) > cutoff]
