"""Tests for pr-babysit-state.py — per-PR state file CRUD."""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bin"))
import pr_babysit_state as st


def test_state_path_construction(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "STATE_DIR", str(tmp_path))
    p = st.state_path("acme", "web_app", 42)
    assert p.endswith("acme__web_app__42.json")


def test_load_empty_returns_fresh_state(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "STATE_DIR", str(tmp_path))
    s = st.load_state("foo", "bar", 1)
    assert s["head_sha"] is None
    assert s["pr_diff_files"] == []
    assert s["handled_comment_ids"] == []
    assert s["audit"] == []
    assert s["escalated"] == []


def test_save_then_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "STATE_DIR", str(tmp_path))
    s = st.load_state("foo", "bar", 1)
    s["head_sha"] = "abc123"
    s["pr_diff_files"] = ["x.kt", "y.kt"]
    s["handled_comment_ids"] = [42]
    st.save_state("foo", "bar", 1, s)
    s2 = st.load_state("foo", "bar", 1)
    assert s2["head_sha"] == "abc123"
    assert s2["pr_diff_files"] == ["x.kt", "y.kt"]
    assert s2["handled_comment_ids"] == [42]


def test_audit_filter_24h():
    """filter_audit_24h keeps entries < 24h old, drops older."""
    now = datetime(2026, 5, 27, 14, 0, tzinfo=timezone.utc)
    fresh = (now - timedelta(hours=1)).isoformat()
    stale = (now - timedelta(hours=30)).isoformat()
    audit = [
        {"comment_id": 1, "fix_pushed_at": fresh},
        {"comment_id": 2, "fix_pushed_at": stale},
    ]
    filtered = st.filter_audit_24h(audit, now=now)
    assert len(filtered) == 1
    assert filtered[0]["comment_id"] == 1


def test_delete_state(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "STATE_DIR", str(tmp_path))
    st.save_state("foo", "bar", 1, st.load_state("foo", "bar", 1))
    assert os.path.exists(st.state_path("foo", "bar", 1))
    st.delete_state("foo", "bar", 1)
    assert not os.path.exists(st.state_path("foo", "bar", 1))
