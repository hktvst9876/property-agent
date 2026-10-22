"""
Approval queue: identical requests aren't stacked, each approval reaches
Telegram once, and a decided approval can't be flipped by a stale tap.
Uses a throwaway SQLite file so the demo DB is untouched.
"""

import tempfile
from pathlib import Path
from unittest import mock

import pytest

from db import store


@pytest.fixture(autouse=True)
def temp_db():
    with tempfile.TemporaryDirectory() as tmp:
        with mock.patch.object(store, "DB_PATH", Path(tmp) / "t.db"):
            store.init_db()
            yield


def test_identical_pending_request_is_not_duplicated():
    a = store.queue_approval("issue_notice", {"stage": "BREACH"}, case_id=None)
    b = store.queue_approval("issue_notice", {"stage": "BREACH"}, case_id=None)
    assert a == b
    assert len(store.pending_approvals()) == 1


def test_different_payload_is_a_separate_request():
    a = store.queue_approval("escalate_human", {"reason": "safety"})
    b = store.queue_approval("escalate_human", {"reason": "legal question"})
    assert a != b


def test_each_approval_is_pushed_once():
    a = store.queue_approval("raise_rent", {"pct": 3})
    assert [r["id"] for r in store.unpushed_approvals()] == [a]
    store.mark_approval_pushed(a)
    assert store.unpushed_approvals() == []
    assert [r["id"] for r in store.pending_approvals()] == [a]   # still open


def test_stale_tap_cannot_flip_a_decision():
    a = store.queue_approval("deposit_claim", {"amount_sgd": 400})
    assert store.resolve_approval(a, "approved", "op") is True
    assert store.resolve_approval(a, "rejected", "op") is False
    conn = store.connect()
    status = conn.execute("SELECT status FROM approvals WHERE id=?", (a,)).fetchone()["status"]
    conn.close()
    assert status == "approved"


def test_orchestrator_push_only_sends_new_approvals():
    from approvals import telegram_bot
    store.queue_approval("approve_repair", {"amount_sgd": 600})
    with mock.patch.object(telegram_bot, "_telegram_enabled", return_value=True), \
         mock.patch.object(telegram_bot, "push_approval") as push:
        assert telegram_bot.push_pending_approvals() == 1
        assert telegram_bot.push_pending_approvals() == 0   # next inbound message
    assert push.call_count == 1
