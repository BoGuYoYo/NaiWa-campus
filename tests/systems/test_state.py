"""状态与派生属性（边界用例）。

B-T01（初始值）与 B-T10（精力上限）已迁入 tests/expected/unit_expect.json，
由 test_unit_cases.py 统一执行。
"""

from __future__ import annotations

import json

import pytest

from game.core.state import GameState


def test_derived_calendar_fields():
    """day_index 是唯一权威字段，其余为派生属性。"""
    cases = {
        0: (1, 1, 1, 1),
        1: (1, 1, 2, 1),
        3: (1, 2, 2, 2),
        4: (2, 1, 1, 3),
        15: (4, 2, 2, 8),
    }
    for day_index, (year, semester, day, semester_no) in cases.items():
        state = GameState(day_index=day_index)
        assert (state.year, state.semester, state.day, state.semester_no) == (
            year, semester, day, semester_no
        )


def test_to_dict_from_dict_roundtrip(state):
    """set 序列化为排序 list，往返后完全一致（B-T22 的基础）。"""
    state.flags.update({"club_member", "accepted_lab"})
    state.talked_today.add("npc_sumo")
    state.counters["library_count"] = 3
    state.event_log.append("sem_1_club_fair:fair_lab")
    payload = state.to_dict()
    assert payload["flags"] == sorted(payload["flags"])
    restored = GameState.from_dict(json.loads(json.dumps(payload)))
    assert restored.to_dict() == payload


def test_validate_accepts_new_game(state):
    """新游戏状态满足全部不变量。"""
    state.validate()


def test_validate_rejects_energy_over_limit(state):
    state.energy = state.max_energy() + 1
    with pytest.raises(ValueError, match="energy="):
        state.validate()


def test_validate_rejects_stat_out_of_range(state):
    state.stats["academic"] = 101
    with pytest.raises(ValueError, match=r"stats\.academic=101"):
        state.validate()


def test_validate_rejects_unknown_phase(state):
    state.phase = "boss"
    with pytest.raises(ValueError, match="phase='boss'"):
        state.validate()


def test_validate_reports_field_and_allowed_range(state):
    """错误消息要能直接定位：带字段名、实际值与允许范围。"""
    state.relationships["npc_sumo"] = 120
    with pytest.raises(ValueError) as excinfo:
        state.validate()
    message = str(excinfo.value)
    assert "relationships.npc_sumo=120" in message
    assert "0..100" in message


def test_validate_rejects_slot_out_of_range(state):
    state.action_slot = 4
    with pytest.raises(ValueError, match="action_slot=4"):
        state.validate()


def test_validate_rejects_day_index_out_of_range(state):
    state.day_index = 17
    with pytest.raises(ValueError, match="day_index=17"):
        state.validate()


def test_copy_is_deep(state):
    """copy() 走 to_dict/from_dict，改副本不影响原状态（存档回放依赖这点）。"""
    state.flags.add("accepted_lab")
    clone = state.copy()

    clone.stats["academic"] = 90
    clone.flags.add("club_member")
    clone.relationships["npc_sumo"] = 50

    assert state.stats["academic"] == 10
    assert state.flags == {"accepted_lab"}
    assert state.relationships["npc_sumo"] == 0
    assert clone.to_dict() != state.to_dict()
