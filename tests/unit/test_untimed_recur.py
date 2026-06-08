"""Unit: un-timed recurrence (granularity epic #25, Stage 4).

`recurSchedule.startMin` may be null → an un-timed, Queue-only recurrence with
no timeline projection. The server forces `durationMin` to null in that case,
and defaults it for timed recurs that omit it.
"""

from __future__ import annotations


def test_untimed_recur_accepts_null_start(make_task):
    t = make_task(title="evening walk", recurSchedule={"startMin": None, "days": ["mon", "wed"]})
    rs = t["recurSchedule"]
    assert rs["startMin"] is None
    assert rs["durationMin"] is None
    assert rs["days"] == ["mon", "wed"]


def test_untimed_recur_nulls_duration_even_if_sent(make_task):
    t = make_task(title="x", recurSchedule={"startMin": None, "durationMin": 99, "days": None})
    rs = t["recurSchedule"]
    assert rs["startMin"] is None
    assert rs["durationMin"] is None  # forced null for un-timed
    assert rs["days"] is None


def test_timed_recur_defaults_missing_duration(make_task):
    t = make_task(title="standup", recurSchedule={"startMin": 540, "days": ["mon"]})
    rs = t["recurSchedule"]
    assert rs["startMin"] == 540
    assert rs["durationMin"] == 30  # DEFAULT_DURATION_MIN


def test_timed_recur_keeps_explicit_duration(make_task):
    t = make_task(title="block", recurSchedule={"startMin": 600, "durationMin": 45, "days": None})
    assert t["recurSchedule"]["durationMin"] == 45
