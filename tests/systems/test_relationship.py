"""交谈与关系阶段边界用例。

B-T06、B-T07、B-T17 已迁入 tests/expected/unit_expect.json，
由 test_unit_cases.py 执行。
"""

from __future__ import annotations


def test_talk_requires_energy(state, relationship):
    state.energy = 4
    result = relationship.talk(state, "npc_sumo")
    assert result.error_code == "E_LOW_ENERGY"


def test_talk_consumes_slot_and_respects_limit(state, relationship):
    for npc in ("npc_sumo", "npc_chenlang", "npc_xiaoyou"):
        assert relationship.talk(state, npc).ok
    assert state.action_slot == 3
    result = relationship.talk(state, "npc_sumo")
    assert result.error_code in ("E_NO_SLOT", "E_ALREADY_TALKED")


def test_only_one_relation_stage_per_talk(state, relationship):
    """一次交谈最多触发一段：关系 70 时只触发阶段 1。"""
    state.day_index = 8  # semester_no = 5
    state.relationships["npc_sumo"] = 70
    result = relationship.talk(state, "npc_sumo")
    assert state.relationships["npc_sumo"] == 81  # 70 + 交谈 6 + 阶段 1 奖励 5
    assert result.triggered_event_id == "rel_npc_sumo_1"
    assert "npc_sumo_stage1" in state.flags
    assert "npc_sumo_stage2" not in state.flags
