"""任务 C4 独立测试：提示范围滞回与最近交互点选择。"""

from __future__ import annotations

import pytest

from game.world.map_data import CAMPUS_SCENE, Interactable
from game.world.trigger_zone import (
    HIDE_MARGIN,
    Candidate,
    PromptTracker,
    candidate_distance,
    make_candidates,
    nearest,
    scene_of,
)

from fixtures.fake_state import FakeState, FakeWorldPos


def _ia(ia_id: str, x: float, y: float, radius: float, kind: str) -> Interactable:
    return Interactable(
        id=ia_id,
        name=ia_id,
        scene=CAMPUS_SCENE,
        location_id="loc_gate",
        x=x,
        y=y,
        radius=radius,
        type=kind,
        target="attend_class",
    )


def test_candidate_distance():
    c = Candidate(_ia("ia_a", 3.0, 4.0, 1.0, "activity"), 3.0, 4.0)
    assert candidate_distance(c, 0.0, 0.0) == pytest.approx(5.0)


def test_make_candidates_converts_interior_to_world(test_map_data):
    interior = make_candidates(test_map_data, "loc_hall")
    by_id = {c.id: c for c in interior}
    assert by_id["ia_test_bed"].x == pytest.approx(104.0)  # 原点 (100, 0) + 本地 (4, 5)
    assert by_id["ia_test_bed"].y == pytest.approx(5.0)


def test_nearest_picks_closest(test_map_data):
    candidates = make_candidates(test_map_data, CAMPUS_SCENE)
    chosen = nearest(candidates, 5.0, 10.5)
    assert chosen is not None and chosen.id == "ia_test_desk"


def test_nearest_breaks_ties_by_priority(test_map_data):
    """距离相同时按 npc > activity > door > save > inspect 选择。"""
    candidates = make_candidates(test_map_data, CAMPUS_SCENE)
    chosen = nearest(candidates, 10.0, 11.0)
    assert chosen is not None
    assert chosen.id == "ia_test_tie_save"  # save 优先于 inspect


def test_nearest_returns_none_out_of_range():
    candidates = [Candidate(_ia("ia_a", 0.0, 0.0, 1.0, "activity"), 0.0, 0.0)]
    assert nearest(candidates, 5.0, 5.0) is None


def test_nearest_includes_candidate_exactly_on_radius():
    candidates = [Candidate(_ia("ia_a", 0.0, 0.0, 1.0, "activity"), 0.0, 0.0)]
    assert nearest(candidates, 1.0, 0.0) is not None


def test_prompt_tracker_appears_within_radius():
    tracker = PromptTracker()
    candidates = [Candidate(_ia("ia_a", 0.0, 0.0, 1.0, "activity"), 0.0, 0.0)]
    assert tracker.update(candidates, 0.0, 5.0) is None
    assert tracker.update(candidates, 0.0, 0.9) is not None
    assert tracker.active_id == "ia_a"


def test_prompt_tracker_hysteresis_keeps_prompt_until_radius_plus_margin():
    tracker = PromptTracker()
    candidates = [Candidate(_ia("ia_a", 0.0, 0.0, 1.0, "activity"), 0.0, 0.0)]
    assert tracker.update(candidates, 0.0, 0.9) is not None
    assert tracker.update(candidates, 0.0, 1.0 + HIDE_MARGIN - 0.01) is not None
    assert tracker.update(candidates, 0.0, 1.0 + HIDE_MARGIN + 0.01) is None


def test_prompt_tracker_hysteresis_only_applies_to_active_prompt():
    tracker = PromptTracker()
    candidates = [Candidate(_ia("ia_a", 0.0, 0.0, 1.0, "activity"), 0.0, 0.0)]
    assert tracker.update(candidates, 0.0, 1.0 + HIDE_MARGIN - 0.01) is None
    assert tracker.active is None


def test_prompt_tracker_does_not_flicker_while_approaching():
    """C-03：在半径附近来回移动不应造成提示闪烁。"""
    tracker = PromptTracker()
    candidates = [Candidate(_ia("ia_a", 0.0, 0.0, 1.2, "activity"), 0.0, 0.0)]
    sequence = [2.0, 1.6, 1.15, 1.25, 1.35, 1.45, 1.4, 1.1]
    states = []
    for d in sequence:
        active = tracker.update(candidates, 0.0, d)
        states.append(None if active is None else active.id)
    assert states[0] is None
    assert states[2] == "ia_a"
    assert states[-1] == "ia_a"
    assert states.count(None) == 2  # 只在前两次未进入半径时隐藏


def test_prompt_tracker_reset():
    tracker = PromptTracker()
    candidates = [Candidate(_ia("ia_a", 0.0, 0.0, 1.0, "activity"), 0.0, 0.0)]
    tracker.update(candidates, 0.0, 0.9)
    tracker.reset()
    assert tracker.active is None


def test_scene_of_uses_building_ids(test_map_data):
    outside = FakeState(world=FakeWorldPos(location_id="loc_yard"))
    inside = FakeState(world=FakeWorldPos(location_id="loc_hall"))
    assert scene_of(outside, test_map_data) == CAMPUS_SCENE
    assert scene_of(inside, test_map_data) == "loc_hall"
