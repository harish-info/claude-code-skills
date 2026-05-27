"""Tests for pr-babysit-lock.py — mkdir locking + heartbeat + race handling."""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bin"))
import pr_babysit_lock as lock


def test_fresh_acquire(tmp_path, monkeypatch):
    monkeypatch.setattr(lock, "LOCK_BASE_DIR", str(tmp_path))
    result = lock.acquire("foo", "bar", 1, session_id="sess-A",
                          schedule_seconds=900)
    assert result == "acquired"
    meta = json.loads((tmp_path / "foo__bar__1.lock" / "owner.json").read_text())
    assert meta["session_id"] == "sess-A"


def test_different_session_blocked_when_fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(lock, "LOCK_BASE_DIR", str(tmp_path))
    lock.acquire("foo", "bar", 1, session_id="sess-A", schedule_seconds=900)
    result = lock.acquire("foo", "bar", 1, session_id="sess-B", schedule_seconds=900)
    assert result == "blocked_other_session"


def test_same_session_reentry_blocked_when_fresh(tmp_path, monkeypatch):
    """A second wakeup of the SAME session while a prior fire still owns the
    fresh lock must be refused (overrun detection)."""
    monkeypatch.setattr(lock, "LOCK_BASE_DIR", str(tmp_path))
    lock.acquire("foo", "bar", 1, session_id="sess-A", schedule_seconds=900)
    result = lock.acquire("foo", "bar", 1, session_id="sess-A", schedule_seconds=900)
    assert result == "blocked_overrun"


def test_stale_lock_reclaimed(tmp_path, monkeypatch):
    """A lock with last_fire older than 2× SCHEDULE_SECONDS is reclaimable."""
    monkeypatch.setattr(lock, "LOCK_BASE_DIR", str(tmp_path))
    lock_dir = tmp_path / "foo__bar__1.lock"
    lock_dir.mkdir()
    stale_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    (lock_dir / "owner.json").write_text(json.dumps({
        "session_id": "dead-sess",
        "pid": 99999,
        "started_at": stale_time,
        "last_fire": stale_time,
    }))
    result = lock.acquire("foo", "bar", 1, session_id="sess-B", schedule_seconds=900)
    assert result == "acquired"
    meta = json.loads((lock_dir / "owner.json").read_text())
    assert meta["session_id"] == "sess-B"


def test_metadata_read_race_handled(tmp_path, monkeypatch):
    """If meta_file is missing/empty (race window), the second process yields."""
    monkeypatch.setattr(lock, "LOCK_BASE_DIR", str(tmp_path))
    lock_dir = tmp_path / "foo__bar__1.lock"
    lock_dir.mkdir()  # mkdir succeeded but meta not yet written
    result = lock.acquire("foo", "bar", 1, session_id="sess-B", schedule_seconds=900)
    assert result == "blocked_race"


def test_takeover_reclaims_fresh_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(lock, "LOCK_BASE_DIR", str(tmp_path))
    lock.acquire("foo", "bar", 1, session_id="sess-A", schedule_seconds=900)
    result = lock.acquire("foo", "bar", 1, session_id="sess-B",
                          schedule_seconds=900, takeover=True)
    assert result == "acquired"


def test_heartbeat_updates_last_fire(tmp_path, monkeypatch):
    monkeypatch.setattr(lock, "LOCK_BASE_DIR", str(tmp_path))
    lock.acquire("foo", "bar", 1, session_id="sess-A", schedule_seconds=900)
    meta_path = tmp_path / "foo__bar__1.lock" / "owner.json"
    old_fire = json.loads(meta_path.read_text())["last_fire"]
    time.sleep(0.05)
    lock.heartbeat("foo", "bar", 1)
    new_fire = json.loads(meta_path.read_text())["last_fire"]
    assert new_fire > old_fire


def test_release_removes_lock(tmp_path, monkeypatch):
    """release() removes the lock dir — for fatal/stop/merge cases."""
    monkeypatch.setattr(lock, "LOCK_BASE_DIR", str(tmp_path))
    lock.acquire("foo", "bar", 1, session_id="sess-A", schedule_seconds=900)
    assert (tmp_path / "foo__bar__1.lock").exists()
    lock.release("foo", "bar", 1)
    assert not (tmp_path / "foo__bar__1.lock").exists()


def test_real_subprocess_blocked(tmp_path, monkeypatch):
    """A second subprocess attempting to acquire must be blocked."""
    monkeypatch.setattr(lock, "LOCK_BASE_DIR", str(tmp_path))
    lock.acquire("foo", "bar", 1, session_id="sess-A", schedule_seconds=900)

    bin_dir = os.path.join(os.path.dirname(__file__), "..", "bin")
    script = f"""
import sys
sys.path.insert(0, {bin_dir!r})
import pr_babysit_lock as L
L.LOCK_BASE_DIR = {str(tmp_path)!r}
print(L.acquire("foo", "bar", 1, "sess-B", 900))
"""
    result = subprocess.run([sys.executable, "-c", script],
                            capture_output=True, text=True, timeout=5)
    assert "blocked_other_session" in result.stdout
