"""日结算边界用例。

B-T09（低精力扣心情）、B-T18（第一学期事件）、B-T19（毕业事件）已迁入
tests/expected/unit_expect.json，由 test_unit_cases.py 执行。
"""

from __future__ import annotations

import pytest


def test_no_semester_event_on_even_day(state, calendar):
    """每学期第 1 天结束不触发学期事件。"""
    state.day_index = 0
    result = calendar.end_day(state)
    assert result.semester_event_id is None
    assert state.phase == "campus"


def test_end_day_clears_daily_records(state, calendar):
    state.today_counts["eat_canteen"] = 2
    state.talked_today.add("npc_sumo")
    calendar.end_day(state)
    assert state.today_counts == {}
    assert state.talked_today == set()


def test_graduated_state_rejects_actions(state, activity, calendar, events):
    """毕业后（day_index=16）任何活动都返回 E_WRONG_PHASE。"""
    state.day_index = 15
    calendar.end_day(state)
    events.choose(state, "sem_8_graduation_eve", "thesis")
    assert state.day_index == 16
    assert state.phase == "graduation"
    assert activity.can_start(state, "rest_dorm") == (False, "E_WRONG_PHASE")


def test_end_day_guard_rejects_event_phase(state, calendar):
    """事件未结算时重复结算会抛错，且不推进日期（防止日期空转）。"""
    state.day_index = 1
    calendar.end_day(state)
    assert state.phase == "event"
    before = state.to_dict()
    with pytest.raises(RuntimeError, match="pending_event_id"):
        calendar.end_day(state)
    assert state.to_dict() == before


def test_end_day_guard_rejects_after_graduation(state, calendar):
    """毕业（day_index=16）后不再允许日结算。"""
    state.day_index = 16
    with pytest.raises(RuntimeError, match="day_index=16"):
        calendar.end_day(state)
    assert state.day_index == 16
