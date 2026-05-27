#!/usr/bin/env python3
"""mkdir-based atomic locking with heartbeat liveness.

Persists across runs. Only updates last_fire on normal completion; full release
is reserved for fatal errors, PR merge/close.
"""
import json
import os
import shutil
import time
from datetime import datetime, timedelta, timezone

LOCK_BASE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "pr-babysit", "locks")


def _lock_dir(owner, repo, pr):
    return os.path.join(LOCK_BASE_DIR, f"{owner}__{repo}__{pr}.lock")


def _meta_path(owner, repo, pr):
    return os.path.join(_lock_dir(owner, repo, pr), "owner.json")


def _read_meta_with_retry(meta_path, retries=3, delay=0.05):
    """Handle the mkdir/write race window. Returns dict or None if meta never appears."""
    for _ in range(retries):
        if os.path.exists(meta_path):
            try:
                with open(meta_path) as f:
                    content = f.read().strip()
                if content:
                    return json.loads(content)
            except (json.JSONDecodeError, OSError):
                pass
        time.sleep(delay)
    return None


def _write_meta(meta_path, session_id, pid=None, started_at=None, last_fire=None):
    if started_at is None:
        started_at = datetime.now(timezone.utc).isoformat()
    if last_fire is None:
        last_fire = started_at
    if pid is None:
        pid = os.getpid()
    with open(meta_path, "w") as f:
        json.dump({
            "session_id": session_id,
            "pid": pid,
            "started_at": started_at,
            "last_fire": last_fire,
        }, f, indent=2)


def acquire(owner, repo, pr, session_id, schedule_seconds, takeover=False):
    """Try to acquire the lock. Returns one of:
        "acquired", "blocked_other_session", "blocked_overrun", "blocked_race"
    """
    os.makedirs(LOCK_BASE_DIR, exist_ok=True)
    lock_dir = _lock_dir(owner, repo, pr)
    meta_path = _meta_path(owner, repo, pr)

    if takeover and os.path.exists(lock_dir):
        shutil.rmtree(lock_dir, ignore_errors=True)

    try:
        os.mkdir(lock_dir)
        _write_meta(meta_path, session_id=session_id)
        return "acquired"
    except FileExistsError:
        pass

    meta = _read_meta_with_retry(meta_path)
    if meta is None:
        return "blocked_race"

    stale_threshold = timedelta(seconds=2 * schedule_seconds)
    last_fire = datetime.fromisoformat(meta["last_fire"].replace("Z", "+00:00"))
    age = datetime.now(timezone.utc) - last_fire

    if age > stale_threshold:
        shutil.rmtree(lock_dir, ignore_errors=True)
        try:
            os.mkdir(lock_dir)
            _write_meta(meta_path, session_id=session_id)
            return "acquired"
        except FileExistsError:
            return "blocked_other_session"

    if meta["session_id"] == session_id:
        return "blocked_overrun"

    return "blocked_other_session"


def heartbeat(owner, repo, pr):
    """Update last_fire after a normal completion. Lock is NOT removed."""
    meta_path = _meta_path(owner, repo, pr)
    if not os.path.exists(meta_path):
        return
    with open(meta_path) as f:
        meta = json.load(f)
    meta["last_fire"] = datetime.now(timezone.utc).isoformat()
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)


def release(owner, repo, pr):
    """Remove the lock -- for fatal errors, PR merge/close."""
    lock_dir = _lock_dir(owner, repo, pr)
    if os.path.exists(lock_dir):
        shutil.rmtree(lock_dir, ignore_errors=True)
