"""任务 C7 独立测试：InteractionService 的 query / interact 映射与错误码。"""

from __future__ import annotations

import pytest

from game.world.interaction_service import (
    E_ALREADY_TALKED,
    E_LOW_ENERGY,
    E_UNKNOWN_ID,
    E_WRONG_PHASE,
    REPEAT_LOCK_SECONDS,
    InteractionService,
)
from fixtures.fake_services import (
    FakeActivityService,
    FakeEventBus,
    FakeRelationshipService,
    FakeSceneManager,
    FakeTextDB,
)
from fixtures.fake_state import FakeState, FakeWorldPos


class Clock:
    def __init__(self) -> None:
        self.t = 100.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


@pytest.fixture
def services(test_map_data):
    clock = Clock()
    return {
        "clock": clock,
        "activity": FakeActivityService(),
        "relationship": FakeRelationshipService(),
        "scene": FakeSceneManager(),
        "bus": FakeEventBus(),
        "textdb": FakeTextDB(),
        "service": InteractionService(
            test_map_data,
            activity_service=FakeActivityService(),
            relationship_service=FakeRelationshipService(),
            scene_manager=FakeSceneManager(),
            event_bus=FakeEventBus(),
            clock=clock,
        ),
    }


def make_service(test_map_data, clock, **kwargs) -> InteractionService:
    return InteractionService(
        test_map_data,
        activity_service=kwargs.get("activity", FakeActivityService()),
        relationship_service=kwargs.get("relationship", FakeRelationshipService()),
        scene_manager=kwargs.get("scene", FakeSceneManager()),
        event_bus=kwargs.get("bus", FakeEventBus()),
        clock=clock,
    )


def test_query_activity_uses_activity_service(test_map_data):
    activity = FakeActivityService(costs={"attend_class": {"energy": -15, "mood": -4}})
    service = make_service(test_map_data, Clock(), activity=activity)
    view = service.query(FakeState(location_id="loc_yard"), "ia_test_desk")
    assert view.enabled is True
    assert view.label_text_id == "act.attend_class.name"
    assert view.reason_code is None
    assert view.cost_preview == {"energy": -15, "mood": -4}
    assert activity.can_start_calls == [("loc_yard", "attend_class")]
    assert activity.preview_calls == [("loc_yard", "attend_class")]


def test_query_activity_surfaces_error_code(test_map_data):
    activity = FakeActivityService(blocked={"attend_class": "E_LOW_ENERGY"})
    service = make_service(test_map_data, Clock(), activity=activity)
    view = service.query(FakeState(location_id="loc_yard"), "ia_test_desk")
    assert view.enabled is False
    assert view.reason_code == "E_LOW_ENERGY"


def test_query_npc_blocked_when_already_talked(test_map_data):
    state = FakeState(location_id="loc_yard", talked_today={"npc_sumo"})
    view = make_service(test_map_data, Clock()).query(state, "ia_test_npc")
    assert view.enabled is False
    assert view.reason_code == E_ALREADY_TALKED
    assert view.label_text_id == "npc.sumo.talk_prompt"


def test_query_npc_blocked_by_relationship_service(test_map_data):
    """能否交谈由 B 判定：C 只透传错误码，不读 state.energy。"""
    relationship = FakeRelationshipService(can_talk=lambda state, npc_id: (False, E_LOW_ENERGY))
    view = make_service(test_map_data, Clock(), relationship=relationship).query(
        FakeState(location_id="loc_yard"), "ia_test_npc"
    )
    assert view.enabled is False
    assert view.reason_code == E_LOW_ENERGY


def test_query_npc_enabled(test_map_data):
    relationship = FakeRelationshipService(preview={"npc_sumo": {"energy": -5}})
    view = make_service(test_map_data, Clock(), relationship=relationship).query(
        FakeState(location_id="loc_yard"), "ia_test_npc"
    )
    assert view.enabled is True
    assert view.cost_preview == {"energy": -5}


def test_query_labels_for_door_save_and_inspect(test_map_data):
    service = make_service(test_map_data, Clock())
    state = FakeState(location_id="loc_yard")
    assert service.query(state, "ia_test_door").label_text_id == "ui.prompt.enter"
    assert service.query(state, "ia_test_tie_save").label_text_id == "ui.prompt.save"
    assert service.query(state, "ia_test_notice").label_text_id == "insp.test_notice.name"


def test_query_unknown_id(test_map_data):
    view = make_service(test_map_data, Clock()).query(FakeState(location_id="loc_yard"), "ia_nope")
    assert view.enabled is False
    assert view.reason_code == E_UNKNOWN_ID


def test_query_rejects_interactable_from_another_scene(test_map_data):
    service = make_service(test_map_data, Clock())
    outside = FakeState(location_id="loc_yard")
    inside = FakeState(location_id="loc_hall")

    bed = service.query(outside, "ia_test_bed")
    assert bed.reason_code == E_WRONG_PHASE
    assert bed.label_text_id == "act.rest_dorm.name"  # 不暴露 ia.ia_test_bed.name

    desk = service.query(inside, "ia_test_desk")
    assert desk.reason_code == E_WRONG_PHASE
    assert desk.label_text_id == "act.attend_class.name"

    assert service.query(inside, "ia_test_bed").enabled is True


def test_bed_prompt_never_leaks_internal_id(map_data):
    """宿舍床在地点/场景暂时不一致时也必须显示可读名称，而不是 ia.ia_bed.name。"""
    service = make_service(map_data, Clock())
    view = service.query(FakeState(location_id="loc_gate"), "ia_bed")
    assert view.interactable_id == "ia_bed"
    assert view.label_text_id == "act.rest_dorm.name"
    assert view.reason_code == E_WRONG_PHASE
    assert "ia.ia_bed.name" not in view.label_text_id


def test_interact_activity_calls_only_activity_id(test_map_data):
    clock = Clock()
    activity = FakeActivityService()
    bus = FakeEventBus()
    service = make_service(test_map_data, clock, activity=activity, bus=bus)
    result = service.interact(FakeState(location_id="loc_yard"), "ia_test_desk")
    assert result.kind == "activity"
    assert result.payload.activity_id == "attend_class"
    assert activity.start_calls == [("loc_yard", "attend_class")]
    assert bus.events and bus.events[0][0] == "activity.done"


def test_interact_npc_calls_relationship_service(test_map_data):
    clock = Clock()
    relationship = FakeRelationshipService()
    service = make_service(test_map_data, clock, relationship=relationship)
    result = service.interact(FakeState(location_id="loc_yard"), "ia_test_npc")
    assert result.kind == "npc"
    assert relationship.talk_calls == [("loc_yard", "npc_sumo")]


def test_interact_door_changes_to_interior_scene(test_map_data):
    scene = FakeSceneManager()
    service = make_service(test_map_data, Clock(), scene=scene)
    result = service.interact(FakeState(location_id="loc_yard"), "ia_test_door")
    assert result.kind == "door"
    assert scene.changes == [("InteriorScene", {"building_id": "loc_hall"})]


def test_interact_save_pushes_save_menu(test_map_data):
    scene = FakeSceneManager()
    service = make_service(test_map_data, Clock(), scene=scene)
    result = service.interact(FakeState(location_id="loc_yard"), "ia_test_tie_save")
    assert result.kind == "save"
    assert scene.pushes == [("SaveMenu", {"mode": "save"})]


def test_interact_inspect_pushes_event_scene(test_map_data):
    scene = FakeSceneManager()
    service = make_service(test_map_data, Clock(), scene=scene)
    result = service.interact(FakeState(location_id="loc_yard"), "ia_test_notice")
    assert result.kind == "inspect"
    assert scene.pushes == [("EventScene", {"event_id": None, "text_id": "insp.test_notice.body"})]


def test_interact_blocked_does_not_call_backend(test_map_data):
    clock = Clock()
    activity = FakeActivityService(blocked={"attend_class": "E_NO_SLOT"})
    scene = FakeSceneManager()
    service = make_service(test_map_data, clock, activity=activity, scene=scene)
    result = service.interact(FakeState(location_id="loc_yard"), "ia_test_desk")
    assert result.kind == "blocked"
    assert result.payload == "E_NO_SLOT"
    assert activity.start_calls == []
    assert scene.pushes == [] and scene.changes == []


def test_interact_blocked_for_unknown_id_carries_error_code(test_map_data):
    service = make_service(test_map_data, Clock())
    result = service.interact(FakeState(location_id="loc_yard"), "ia_nope")
    assert result.kind == "blocked"
    assert result.payload == E_UNKNOWN_ID


def test_interact_ignores_repeat_press_within_window(test_map_data):
    clock = Clock()
    activity = FakeActivityService()
    service = make_service(test_map_data, clock, activity=activity)
    state = FakeState(location_id="loc_yard")
    first = service.interact(state, "ia_test_desk")
    clock.advance(REPEAT_LOCK_SECONDS / 2)
    second = service.interact(state, "ia_test_desk")
    assert first.kind == "activity"
    assert second.kind == "blocked" and second.payload is None
    assert len(activity.start_calls) == 1

    clock.advance(REPEAT_LOCK_SECONDS)
    third = service.interact(state, "ia_test_desk")
    assert third.kind == "activity"
    assert len(activity.start_calls) == 2


def test_interact_does_not_lock_out_after_blocked_press(test_map_data):
    clock = Clock()
    activity = FakeActivityService(blocked={"attend_class": "E_NO_SLOT"})
    service = make_service(test_map_data, clock, activity=activity)
    state = FakeState(location_id="loc_yard")
    service.interact(state, "ia_test_desk")
    activity.blocked.clear()
    again = service.interact(state, "ia_test_desk")
    assert again.kind == "activity"


def test_preview_matches_query(test_map_data):
    service = make_service(test_map_data, Clock())
    state = FakeState(location_id="loc_yard")
    assert service.preview_for(state, "ia_test_desk") == service.query(state, "ia_test_desk")
