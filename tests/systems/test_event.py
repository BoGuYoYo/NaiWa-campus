"""事件系统边界用例。

B-T12（日常事件掷骰）、B-T20（锁定原因）已迁入 tests/expected/unit_expect.json；
24 个学期选项的正向覆盖见 test_content_coverage.py。
"""

from __future__ import annotations

import json
import shutil

import pytest

from game.systems.content_db import RULES_DIR, ContentDB, ContentError
from game.systems.event_service import EventService


def test_choice_applies_effects_and_flags(state, events):
    view = events.get_view(state, "sem_1_club_fair")
    assert [c.choice_id for c in view.choices] == ["fair_club", "fair_lab", "fair_game"]
    result = events.choose(state, "sem_1_club_fair", "fair_lab")
    assert state.stats["academic"] == 14
    assert state.relationships["npc_chenlang"] == 10
    assert "lab_visited" in state.flags
    assert result.added_flags == ["lab_visited"]
    assert "sem_1_club_fair:fair_lab" in state.event_log
    assert state.pending_event_id is None
    assert state.phase == "campus"


def test_locked_choice_cannot_be_chosen(state, events):
    """条件不满足时调用 choose 会明确拒绝，而不是静默生效。"""
    state.day_index = 8
    with pytest.raises(ContentError, match="E_CHOICE_LOCKED"):
        events.choose(state, "sem_5_club_election", "run_election")
    assert "ran_for_president" not in state.flags


def test_daily_event_immediate_effect(state, activity):
    """日常事件立即结算并写入 event_log（B6）。"""
    activity.start(state, "campus_walk")
    activity.start(state, "campus_walk")
    before = (state.mood, state.stats["social"])
    result = activity.start(state, "campus_walk")
    assert result.triggered_event_id == "daily_old_friend"
    assert state.event_log[-1] == "daily_old_friend"
    # 闲逛本身 +5 心情，daily_old_friend 再 +2 心情 / +2 社交
    assert (state.mood, state.stats["social"]) == (before[0] + 7, before[1] + 2)


def test_relationship_event_view(state, events):
    """关系事件只有 1 个无条件选项，展示时永远可选。"""
    view = events.get_view(state, "rel_npc_sumo_1")
    assert view.kind == "relationship"
    assert view.speaker == "npc_sumo"
    assert view.page_text_ids == ["evt.rel_npc_sumo_1.body.1"]
    assert [c.choice_id for c in view.choices] == ["continue"]
    assert view.choices[0].enabled is True
    assert view.choices[0].lock_reason_id is None


def _copy_rules_with_chain(tmp_path, target_event: str) -> ContentDB:
    rules = tmp_path / "rules"
    shutil.copytree(RULES_DIR, rules)
    path = rules / "events.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for event in data:
        if event["id"] == "sem_1_club_fair":
            for choice in event["choices"]:
                if choice["id"] == "fair_lab":
                    choice["next_event_id"] = target_event
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return ContentDB(rules)


def test_chained_event_is_enqueued_by_choose(tmp_path, state):
    """next_event_id 由 choose 统一入队，GameFlow 与模拟器只需看 pending_event_id。"""
    service = EventService(_copy_rules_with_chain(tmp_path, "rel_npc_sumo_1"))
    result = service.choose(state, "sem_1_club_fair", "fair_lab")

    assert result.next_event_id == "rel_npc_sumo_1"
    assert state.pending_event_id == "rel_npc_sumo_1"
    assert state.phase == "event"

    service.choose(state, "rel_npc_sumo_1", "continue")
    assert state.pending_event_id is None
    assert state.phase == "campus"


def test_chain_to_unknown_event_is_rejected_at_load(tmp_path):
    """链到不存在的事件在加载期就报错，运行期不会再出现半完成状态。"""
    with pytest.raises(ContentError, match="rel_not_exists"):
        _copy_rules_with_chain(tmp_path, "rel_not_exists")


def test_event_cannot_be_settled_twice(state, events):
    """同一事件重复结算被拒绝，且拒绝不产生任何属性变化。"""
    events.choose(state, "sem_1_club_fair", "fair_lab")
    after_first = state.to_dict()

    with pytest.raises(ContentError, match="已经结算过"):
        events.choose(state, "sem_1_club_fair", "fair_club")

    assert state.to_dict() == after_first


def test_relationship_event_cannot_be_settled_twice(state, events):
    """重复交谈触发的关系事件同样只结算一次。"""
    events.choose(state, "rel_npc_sumo_1", "continue")
    after_first = state.to_dict()

    with pytest.raises(ContentError, match="已经结算过"):
        events.choose(state, "rel_npc_sumo_1", "continue")

    assert state.to_dict() == after_first
