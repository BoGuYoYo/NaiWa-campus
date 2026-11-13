"""A 的 core 层单元测试：GameState 与派生属性。"""

from __future__ import annotations

import json

import pytest

from game.core.state import (
    ACTIONS_PER_DAY,
    DEFAULT_SPAWN_LOCATION,
    GameState,
    WorldPos,
    new_state,
)


def test_defaults_match_spec():
    state = new_state(seed=42)
    assert state.save_version == 2
    assert state.seed == 42
    assert state.day_index == 0
    assert state.action_slot == 0
    assert state.stats == {"academic": 10, "stamina": 20, "social": 10, "interest": 10}
    assert state.mood == 60
    assert state.energy == state.max_energy() == 84
    assert state.relationships == {"npc_sumo": 0, "npc_chenlang": 0, "npc_xiaoyou": 0}
    assert state.world.location_id == DEFAULT_SPAWN_LOCATION
    assert (state.world.x, state.world.y) == (40.0, 5.0)
    assert state.world.facing == "n"
    assert state.phase == "campus"
    assert state.play_seconds == 0.0


@pytest.mark.parametrize(
    "day_index,year,semester,day,semester_no",
    [
        (0, 1, 1, 1, 1),
        (1, 1, 1, 2, 1),
        (2, 1, 2, 1, 2),
        (3, 1, 2, 2, 2),
        (4, 2, 1, 1, 3),
        (7, 2, 2, 2, 4),
        (8, 3, 1, 1, 5),
        (15, 4, 2, 2, 8),
    ],
)
def test_derived_date_fields(day_index, year, semester, day, semester_no):
    state = GameState(day_index=day_index)
    assert (state.year, state.semester, state.day, state.semester_no) == (year, semester, day, semester_no)


def test_max_energy_formula():
    state = GameState()
    state.stats["stamina"] = 75
    assert state.max_energy() == 95
    state.stats["stamina"] = 0
    assert state.max_energy() == 80


def test_actions_left_and_day_finished():
    state = GameState(action_slot=0)
    assert state.actions_left == ACTIONS_PER_DAY
    assert not state.day_finished
    state.action_slot = 2
    assert state.actions_left == 1
    state.action_slot = 3
    assert state.actions_left == 0
    assert state.day_finished


def test_to_dict_serializes_sets_as_sorted_lists():
    state = GameState()
    state.flags = {"b_flag", "a_flag"}
    state.talked_today = {"npc_sumo"}
    state.tutorial_done = {"t2", "t1"}
    payload = state.to_dict()
    assert payload["flags"] == ["a_flag", "b_flag"]
    assert payload["tutorial_done"] == ["t1", "t2"]
    assert isinstance(payload["world"], dict)
    # 必须是 JSON 可序列化的
    json.dumps(payload)


def test_roundtrip_preserves_state():
    state = GameState(day_index=9, action_slot=2, mood=44, energy=30, phase="campus")
    state.stats = {"academic": 55, "stamina": 33, "social": 21, "interest": 66}
    state.relationships["npc_sumo"] = 4
    state.flags = {"accepted_lab"}
    state.counters = {"library_count": 3}
    state.today_counts = {"eat_canteen": 1}
    state.event_log = ["sem_1_club_fair:fair_lab"]
    state.world = WorldPos(location_id="loc_library", x=12.5, y=-3.25, facing="e")
    state.play_seconds = 128.5

    restored = GameState.from_dict(state.to_dict())
    assert restored.to_dict() == state.to_dict()


def test_from_dict_tolerates_garbage_and_clamps():
    payload = {
        "day_index": 99,
        "action_slot": -5,
        "mood": 500,
        "stats": {"academic": "x", "stamina": 400},
        "energy": 999,
        "phase": "nonsense",
        "world": {"x": "bad", "facing": "up"},
    }
    state = GameState.from_dict(payload)
    # day_index 的上界是 TOTAL_DAYS（第 16 天读完就是 16），不是 TOTAL_DAYS-1：
    # 钳到 15 会把"已经读完"的存档送回最后一天，再结算一次就是重复触发学期事件。
    assert state.day_index == 16
    assert state.action_slot == 0
    assert state.mood == 100
    assert state.stats["academic"] == 10  # 非法值回落默认
    assert state.stats["stamina"] == 100
    assert state.energy <= state.max_energy()
    assert state.phase == "campus"
    assert state.world.facing == "n"


def test_from_dict_rejects_non_object():
    with pytest.raises(ValueError):
        GameState.from_dict([])  # type: ignore[arg-type]


def test_clamp_energy_uses_max_energy():
    state = GameState()
    state.stats["stamina"] = 100
    state.energy = 1000
    state.clamp()
    assert state.energy == state.max_energy() == 100


def test_snapshot_is_deep_copy():
    state = GameState()
    clone = state.snapshot()
    clone.stats["academic"] = 99
    clone.flags.add("x")
    assert state.stats["academic"] == 10
    assert state.flags == set()


def test_summary_fields():
    state = GameState(day_index=5)
    summary = state.summary()
    assert summary["day_index"] == 5
    assert summary["year"] == 2
    assert summary["semester_no"] == 3
    assert set(summary["stats"]) == {"academic", "stamina", "social", "interest"}
