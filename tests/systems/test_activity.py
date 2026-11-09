"""活动服务边界用例。

B-T02～B-T05、B-T08、B-T11、B-T15、B-T16 已迁入 tests/expected/unit_expect.json；
九个活动的接口矩阵见 test_activity_matrix.py。
"""

from __future__ import annotations


def test_rest_dorm_always_available(state, activity):
    """宿舍休息是兜底活动：零精力也能执行，保证不会软锁。"""
    state.energy = 0
    state.mood = 0
    ok, code = activity.can_start(state, "rest_dorm")
    assert (ok, code) == (True, None)
    assert activity.start(state, "rest_dorm").ok


def test_result_text_rotates_three(state, activity):
    """结果文案按 (count-1)%3+1 轮换，连续四次回到 1。"""
    seen = []
    for _ in range(4):
        state.action_slot = 0
        state.energy = 84
        result = activity.start(state, "library_study")
        seen.append(result.text_ids[0].rsplit(".", 1)[-1])
    assert seen == ["1", "2", "3", "1"]


def test_unknown_activity_code(state, activity):
    assert activity.can_start(state, "no_such_activity") == (False, "E_UNKNOWN_ID")
    assert activity.preview(state, "no_such_activity") == {}
    result = activity.start(state, "no_such_activity")
    assert result.ok is False
    assert result.error_code == "E_UNKNOWN_ID"


def test_wrong_phase_blocks_activity(state, activity):
    """phase 不是 campus 时返回 E_WRONG_PHASE，且不消耗时段。"""
    state.phase = "event"
    state.pending_event_id = "sem_1_club_fair"
    assert activity.can_start(state, "rest_dorm") == (False, "E_WRONG_PHASE")
    result = activity.start(state, "rest_dorm")
    assert result.ok is False
    assert state.action_slot == 0
