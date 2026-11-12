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


def first_enabled_choice(manager: GameFlow, state, event_id: str) -> str:
    """从事件视图里挑第一个可用选项（B 的事件用真实 choice_id，没有 'ok'）。"""
    view = manager.services.event.get_view(state, event_id)
    for choice in view.choices:
        if choice.enabled:
            return choice.choice_id
    raise AssertionError(f"{event_id} 没有可用选项")


def play_one_action(manager: GameFlow, state) -> None:
    """走一个动作：优先上课，没精力就回宿舍休息。"""
    for activity_id in ("attend_class", "rest_dorm"):
        ok, reason = manager.services.activity.can_start(state, activity_id)
        if not ok:
            continue
        result = manager.services.activity.start(state, activity_id)
        manager.handle_activity_result(result)
        manager.close_result_panel(result)
        return
    raise AssertionError(f"没有可执行的活动（phase={state.phase}, slot={state.action_slot}）")


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

    # 日结算先单独显示；学期事件必须等它关闭后再压上来，
    # 否则两块面板重叠、Space 的含义也会互相冲突。
    # CalendarService.end_day 已经把 phase 守卫切到 event，但 EventScene
    # 仍必须等 DaySummary 关闭后才出现。
    assert state.phase == "event"
    assert [sid for sid, _scene in flow.scenes.overlays] == ["DaySummary"]
    assert "pre_event" not in reasons

    flow.scenes.pop()
    flow.close_day_summary()
    assert state.phase == "event"
    assert flow.scenes.top_overlay_id == "EventScene"
    assert "pre_event" in reasons
    event_id = flow.scenes.overlays[-1][1].kwargs["event_id"]
    assert event_id.startswith("sem_1")

    result = flow.services.event.choose(state, event_id, first_enabled_choice(flow, state, event_id))
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
                            triggered_event_id="sem_1_club_fair", day_finished=False)
    flow.handle_activity_result(result)
    assert flow.scenes.top_overlay_id is None  # 面板未关闭前不切场景
    flow.close_result_panel(result)
    assert flow.scenes.top_overlay_id == "EventScene"
    assert state.phase == "event"
    assert seen and seen[0].triggered_event_id == "sem_1_club_fair"


def test_daily_event_is_immediate_and_does_not_lock_the_day(flow):
    """B 的日常事件是立即结算：不推 EventScene、不改 phase，当天照样能结算。

    这条守的是第四周整合踩到的锁死问题：曾经把 daily_* 也当学期事件推场景，
    phase 被置成 event，B 的 end_day 阶段守卫直接拒绝，玩家再也过不去这一天。
    """
    from game.core.results import ActivityResult

    flow.new_game(seed=42, skip_intro=True)
    state = flow.require_state()
    result = ActivityResult(ok=True, activity_id="campus_walk", error_code=None,
                            text_ids=["act.campus_walk.result.1"],
                            triggered_event_id="daily_lost_cat", day_finished=True)
    flow.handle_activity_result(result)
    flow.close_result_panel(result)

    assert "evt.daily_lost_cat.body.1" in result.text_ids  # 文案进结果面板第二行
    assert flow.scenes.top_overlay_id == "DaySummary"      # 直接日结算，没进事件场景
    assert state.day_index == 1
    assert state.phase == "campus"


def test_teleport_to_spawn_leaves_interior_scene(flow):
    """在宿舍床上结束一天后，基础场景必须离开室内。

    只重置 state.world.location_id 会让玩家仍站在宿舍里、床的提示框
    查不到当前场景，最终显示「#ia.ia_bed.name / 内容缺失：ia_bed」。
    """
    flow.new_game(seed=42, skip_intro=True)
    state = flow.require_state()
    state.world.location_id = "loc_dorm"
    state.world.x = 203.0
    state.world.y = 7.0
    flow.scenes.change("InteriorScene", building_id="loc_dorm", state=state)
    assert flow.scenes.current_id == "InteriorScene"

    flow.teleport_to_spawn()

    assert flow.scenes.current_id == "CampusScene"
    assert state.world.location_id == "loc_gate"
    assert (state.world.x, state.world.y) == (40.0, 5.0)


def test_full_run_reaches_graduation(flow):
    flow.new_game(seed=42, skip_intro=True)
    phases = []
    graduated = []
    flow.bus.subscribe(TOPIC_GAME_GRADUATED, lambda **data: graduated.append(data["ending"]))
    state = flow.require_state()

    for _ in range(config.TOTAL_DAYS * config.ACTIONS_PER_DAY + 32):
        state = flow.require_state()
        if flow.scenes.top_overlay_id == "DaySummary":
            flow.scenes.pop()
            flow.close_day_summary()
            continue
        if state.phase == "graduation":
            break
        if state.phase == "event":
            event_id = state.pending_event_id or flow.story_opening_id
            result = flow.services.event.choose(state, event_id, first_enabled_choice(flow, state, event_id))
            flow.handle_event_result(result)
            continue
        if not state.day_finished:
            play_one_action(flow, state)
        else:
            flow.finish_day()
        phases.append(state.phase)

    state = flow.require_state()
    assert state.phase == "graduation"
    # B 的日历在最后一天结算后把 day_index 推到 TOTAL_DAYS（0..15 是游戏内 16 天）
    assert config.TOTAL_DAYS - 1 <= state.day_index <= config.TOTAL_DAYS
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


def test_intro_overlay_waits_until_campus_scene_is_ready(tmp_path):
    """回归：开场事件必须等校园场景淡入结束再 push。

    旧版在 change() 之后立刻 push，淡出结束时主菜单的 on_exit 会把对话框的
    Space / Enter 绑定一并 ignore 掉 —— 对话框按不动、Esc 也没反应。
    """
    bus = EventBus()
    scenes = SceneManager(
        app=None,
        factory=lambda sid, kw: DummyScene(sid, **kw),
        bus=bus,
        fade_seconds=0.25,
    )
    manager = GameFlow(
        app=None,
        scenes=scenes,
        saves=SaveManager(saves_root=tmp_path / "saves"),
        bus=bus,
        services=resolve_services(),
    )
    scenes.start("MainMenu")
    scenes.update(0.3)

    state = manager.new_game(seed=1, skip_intro=False)
    assert scenes.overlays == []
    assert state.phase == "campus"

    scenes.update(0.1)  # 淡出中：旧场景还没退，不能挂覆盖层
    assert scenes.overlays == []
    scenes.update(0.2)  # 校园场景已建立，淡入中
    assert scenes.current_id == "CampusScene"
    assert scenes.overlays == []

    scenes.update(0.3)  # 淡入结束 → on_ready 弹开场
    assert scenes.top_overlay_id == "EventScene"
    assert scenes.overlays[0][1].kwargs["event_id"] == "story_opening"
    assert state.phase == "event"
    assert state.pending_event_id == "story_opening"

