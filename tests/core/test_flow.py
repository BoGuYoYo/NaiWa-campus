"""A 的 core 层单元测试：GameFlow 主流程（使用 A 的替身服务，不依赖 B/C/D）。"""

from __future__ import annotations

import json

import pytest

from game import config
from game.core.event_bus import (
    TOPIC_ACTIVITY_DONE,
    TOPIC_DAY_ENDED,
    TOPIC_DAY_STARTED,
    TOPIC_GAME_GRADUATED,
    TOPIC_SAVE_WRITTEN,
    EventBus,
)
from game.core.flow import GameFlow, resolve_services
from game.core.save_manager import SaveManager
from game.core.scene_manager import SceneManager
from game.core.state import GameState


class DummyScene:
    def __init__(self, scene_id, **kwargs):
        self.scene_id = scene_id
        self.kwargs = kwargs

    def on_enter(self, **kwargs):
        pass

    def on_exit(self):
        pass


@pytest.fixture()
def flow(tmp_path):
    bus = EventBus()
    scenes = SceneManager(app=None, factory=lambda sid, kw: DummyScene(sid, **kw), bus=bus,
                          fade_seconds=0.0)
    saves = SaveManager(saves_root=tmp_path / "saves")
    manager = GameFlow(app=None, scenes=scenes, saves=saves, bus=bus, services=resolve_services())
    return manager


def run_day(manager: GameFlow, activity_ids=("attend_class", "library_study", "campus_walk")):
    """替玩家点完当天的 3 个活动并关闭结果面板。"""
    state = manager.require_state()
    for activity_id in activity_ids:
        result = manager.services.activity.start(state, activity_id)
        assert result.ok, result.error_code
        manager.handle_activity_result(result)
        manager.close_result_panel(result)
    return result


def test_new_game_defaults_and_events(flow):
    seen = []
    flow.bus.subscribe(TOPIC_DAY_STARTED, lambda **data: seen.append(data["day_index"]))
    state = flow.new_game(seed=42, skip_intro=True)
    assert isinstance(state, GameState)
    assert state.seed == 42
    assert state.day_index == 0
    assert state.phase == "campus"
    assert flow.scenes.current_id == "CampusScene"
    assert seen == [0]


def test_new_game_with_intro_pushes_story_opening(flow):
    state = flow.new_game(seed=1, skip_intro=False)
    assert state.phase == "event"
    assert flow.scenes.top_overlay_id == "EventScene"
    assert flow.scenes.overlays[0][1].kwargs["event_id"] == "story_opening"


def test_three_activities_finish_day_and_autosave(flow, tmp_path):
    flow.new_game(seed=42, skip_intro=True)
    state = flow.require_state()
    saved = []
    flow.bus.subscribe(TOPIC_SAVE_WRITTEN, lambda **data: saved.append(data))

    run_day(flow)
    assert state.day_index == 1
    assert state.action_slot == 0
    assert state.phase == "campus"
    assert flow.saves.path_for("autosave").exists()
    assert saved and saved[0]["reason"] == "day_end"
    payload = json.loads(flow.saves.path_for("autosave").read_text(encoding="utf-8"))
    assert payload["reason"] == "day_end"


def test_day_end_emits_event_and_resets_counters(flow):
    flow.new_game(seed=42, skip_intro=True)
    state = flow.require_state()
    seen = []
    flow.bus.subscribe(TOPIC_DAY_ENDED, lambda **data: seen.append(data["result"]))
    state.today_counts["eat_canteen"] = 2
    state.talked_today.add("npc_sumo")

    run_day(flow)
    assert seen and seen[0].new_day_index == 1
    assert state.today_counts == {}
    assert state.talked_today == set()


def test_semester_event_pushes_overlay_and_autosaves_twice(flow):
    flow.new_game(seed=42, skip_intro=True)
    state = flow.require_state()
    reasons = []
    flow.bus.subscribe(TOPIC_SAVE_WRITTEN, lambda **data: reasons.append(data["reason"]))

    run_day(flow)  # day_index 0 -> 1
    run_day(flow)  # day_index 1 -> 2，触发 sem_1
    assert state.phase == "event"
    assert flow.scenes.top_overlay_id == "EventScene"
    assert "pre_event" in reasons
    event_id = flow.scenes.overlays[-1][1].kwargs["event_id"]
    assert event_id.startswith("sem_1")

    result = flow.services.event.choose(state, event_id, "ok")
    flow.handle_event_result(result)
    assert state.phase == "campus"
    assert "post_event" in reasons


def test_activity_event_is_pushed_on_result_panel_close(flow):
    flow.new_game(seed=42, skip_intro=True)
    state = flow.require_state()
    seen = []
    flow.bus.subscribe(TOPIC_ACTIVITY_DONE, lambda **data: seen.append(data["result"]))

    from game.core.results import ActivityResult

    result = ActivityResult(ok=True, activity_id="attend_class", error_code=None,
                            triggered_event_id="daily_lost_cat", day_finished=False)
    flow.handle_activity_result(result)
    assert flow.scenes.top_overlay_id is None  # 面板未关闭前不切场景
    flow.close_result_panel(result)
    assert flow.scenes.top_overlay_id == "EventScene"
    assert state.phase == "event"
    assert seen and seen[0].triggered_event_id == "daily_lost_cat"


def test_full_run_reaches_graduation(flow):
    flow.new_game(seed=42, skip_intro=True)
    phases = []
    graduated = []
    flow.bus.subscribe(TOPIC_GAME_GRADUATED, lambda **data: graduated.append(data["ending"]))
    state = flow.require_state()

    for _ in range(config.TOTAL_DAYS * config.ACTIONS_PER_DAY + 32):
        state = flow.require_state()
        if state.phase == "graduation":
            break
        if state.phase == "event":
            event_id = state.pending_event_id or flow.story_opening_id
            result = flow.services.event.choose(state, event_id, "ok")
            flow.handle_event_result(result)
            continue
        if not state.day_finished:
            result = flow.services.activity.start(state, "attend_class")
            flow.handle_activity_result(result)
            flow.close_result_panel(result)
        else:
            flow.finish_day()
        phases.append(state.phase)

    state = flow.require_state()
    assert state.phase == "graduation"
    assert state.day_index == config.TOTAL_DAYS - 1
    assert state.ending_id
    assert graduated and graduated[0].ending_id == state.ending_id

    flow.finish_graduation()
    assert flow.state is None
    assert flow.scenes.current_id == "MainMenu"


def test_play_seconds_only_accumulates_unpaused(flow):
    flow.new_game(seed=42, skip_intro=True)
    state = flow.require_state()
    flow.tick(0.5)
    assert state.play_seconds == pytest.approx(0.5)
    flow.set_paused(True)
    flow.tick(0.5)
    assert state.play_seconds == pytest.approx(0.5)
    flow.set_paused(False)
    flow.tick(0.25)
    assert state.play_seconds == pytest.approx(0.75)


def test_manual_save_respects_phase(flow):
    flow.new_game(seed=42, skip_intro=True)
    state = flow.require_state()
    assert flow.request_save("slot_1") is True
    assert flow.saves.path_for("slot_1").exists()
    state.phase = "event"
    assert flow.request_save("slot_2") is False
    assert not flow.saves.path_for("slot_2").exists()


def test_load_game_restores_and_enters_campus(flow):
    flow.new_game(seed=5, skip_intro=True)
    state = flow.require_state()
    state.day_index = 4
    state.stats["social"] = 33
    flow.request_save("slot_1")
    flow.state = None

    loaded = flow.load_game("slot_1")
    assert loaded.day_index == 4
    assert loaded.stats["social"] == 33
    assert loaded.phase == "campus"
    assert flow.scenes.current_id == "CampusScene"


def test_teleport_to_spawn_resets_position(flow):
    flow.new_game(seed=42, skip_intro=True)
    state = flow.require_state()
    state.world.x = 12.5
    state.world.y = -3.0
    state.world.facing = "e"
    flow.teleport_to_spawn()
    assert (state.world.x, state.world.y, state.world.facing) == (40.0, 5.0, "n")
    assert state.world.location_id == "loc_gate"


def test_require_state_without_game_raises(flow):
    with pytest.raises(RuntimeError):
        flow.require_state()
