"""Tests for pr-babysit-notify.py — escalation dispatch + backoff + cooldown."""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bin"))
import pr_babysit_notify as n


def test_escalation_key_for_check():
    assert n.escalation_key(kind="check", name="lint-and-detekt") == "check:lint-and-detekt"


def test_escalation_key_for_comment():
    assert n.escalation_key(kind="comment", name="PRRT_kwDOA1b2c3") == "comment:PRRT_kwDOA1b2c3"


def test_escalation_key_for_merge_conflict():
    assert n.escalation_key(kind="merge_conflict",
                            name="acme/web_app#42") \
        == "merge_conflict:acme/web_app#42"


def test_backoff_due_first_time():
    state = {"escalated": []}
    assert n.backoff_due(state, key="check:detekt",
                         backoff_minutes=[15, 60, 240]) is True


def test_backoff_blocks_within_window():
    now = datetime.now(timezone.utc)
    state = {"escalated": [
        {"key": "check:detekt",
         "last_notified": (now - timedelta(minutes=5)).isoformat(),
         "ping_count": 1, "first_seen": now.isoformat(), "reason": ""},
    ]}
    assert n.backoff_due(state, key="check:detekt",
                         backoff_minutes=[15, 60, 240], now=now) is False


def test_backoff_allows_after_window():
    now = datetime.now(timezone.utc)
    state = {"escalated": [
        {"key": "check:detekt",
         "last_notified": (now - timedelta(minutes=20)).isoformat(),
         "ping_count": 1, "first_seen": now.isoformat(), "reason": ""},
    ]}
    assert n.backoff_due(state, key="check:detekt",
                         backoff_minutes=[15, 60, 240], now=now) is True


def test_cooldown_floor_24h_after_backoff_exhausted():
    """After [15,60,240] is exhausted, 24h floor applies."""
    now = datetime.now(timezone.utc)
    state = {"escalated": [
        {"key": "check:detekt",
         "last_notified": (now - timedelta(hours=6)).isoformat(),
         "ping_count": 4, "first_seen": now.isoformat(), "reason": ""},
    ]}
    assert n.backoff_due(state, key="check:detekt",
                         backoff_minutes=[15, 60, 240], now=now) is False


def test_record_escalation_increments_ping_count():
    state = {"escalated": []}
    n.record_escalation(state, key="check:detekt", reason="untouched file")
    assert state["escalated"][0]["ping_count"] == 1
    n.record_escalation(state, key="check:detekt", reason="untouched file")
    assert state["escalated"][0]["ping_count"] == 2


def test_cooldown_suppresses_all_channels():
    now = datetime.now(timezone.utc)
    audit = [{"comment_thread_id": "T1",
              "in_cooldown_until": (now + timedelta(hours=1)).isoformat()}]
    assert n.is_in_cooldown(audit, thread_id="T1", now=now) is True
    assert n.is_in_cooldown(audit, thread_id="T1",
                            now=now + timedelta(hours=2)) is False
    assert n.is_in_cooldown(audit, thread_id="T2", now=now) is False
