"""A 的 bug 猎杀回归测试（流程 / 存档 / 地图 / 规则校验）。

对应 reports/review/bughunt_fix.md 里 H1~H4、M1~M8 的编号。
这里刻意不复用 tests/core/test_flow.py 的夹具：需要 map_data 的读档修复
必须能拿到真实地图，而 test_flow 的 app 是 None。
"""

from __future__ import annotations

import json
import shutil

import pytest

from game import config
from game.core.event_bus import EventBus
from game.core.flow import GameFlow, resolve_services
from game.core.results import ActivityResult, EventResult
from game.core.save_manager import SaveManager
from game.core.scene_manager import SceneManager
from game.core.state import GameState, new_state
from game.systems import spec_data
from game.systems.content_db import RULE_FILES, RULES_DIR, ContentDB, ContentError
from game.world.collision import PLAYER_HALF, Rect, overlap
from game.world.map_data import CAMPUS_SCENE, MapData
from game.world.player_controller import PlayerMotion


# --------------------------------------------------------------------------- #
# 夹具
# --------------------------------------------------------------------------- #
class DummyScene:
    def __init__(self, scene_id, **kwargs):
        self.scene_id = scene_id
        self.kwargs = kwargs

    def on_enter(self, **kwargs):
        pass

    def on_exit(self):
        pass


class FakeApp:
    """GameFlow 只用到 app.map_data（读档位置修复）。"""

    def __init__(self, map_data=None):
        self.map_data = map_data


@pytest.fixture(scope="session")
def map_data() -> MapData:
    return MapData.from_content_root(config.resource_root() / "content")


def make_flow(tmp_path, map_data=None, name="saves") -> GameFlow:
    bus = EventBus()
    scenes = SceneManager(app=None, factory=lambda sid, kw: DummyScene(sid, **kw), bus=bus,
                          fade_seconds=0.0)
    saves = SaveManager(saves_root=tmp_path / name)
    return GameFlow(app=FakeApp(map_data), scenes=scenes, saves=saves, bus=bus,
                    services=resolve_services())


def first_enabled_choice(flow: GameFlow, state: GameState, event_id: str) -> str:
    view = flow.services.event.get_view(state, event_id)
    for choice in view.choices:
        if choice.enabled:
            return choice.choice_id
    raise AssertionError(f"{event_id} 没有可用选项")


def replay_pending_event(flow: GameFlow) -> None:
    """把当前压在栈顶的事件结算掉（模拟玩家点完选项）。"""
    state = flow.require_state()
    event_id = state.pending_event_id
    assert event_id, "没有待结算事件"
    result = flow.services.event.choose(state, event_id, first_enabled_choice(flow, state, event_id))
    flow.scenes.pop()
    flow.handle_event_result(result)


# --------------------------------------------------------------------------- #
# H1：当天第 3 个行动触发关系事件 -> 事件结束后日子必须推得下去
# --------------------------------------------------------------------------- #
def test_third_action_relationship_event_still_ends_the_day(tmp_path):
    flow = make_flow(tmp_path)
    flow.new_game(seed=1, skip_intro=True)
    state = flow.state
    state.day_index = 2
    state.relationships["npc_sumo"] = 19   # 第 2 学期、关系 >= 20 触发 stage1
    state.action_slot = 2

    result = flow.services.relationship.talk(state, "npc_sumo")
    assert result.triggered_event_id == "rel_npc_sumo_1"
    assert result.day_finished is True

    flow.handle_activity_result(result)
    flow.close_result_panel(result)
    assert flow.scenes.top_overlay_id == "EventScene"

    replay_pending_event(flow)

    # 事件结束后必须补上日结算：日期推进、行动次数归零、可以继续行动
    assert state.day_index == 3
    assert state.action_slot == 0
    assert flow.scenes.top_overlay_id == "DaySummary"
    assert flow.services.activity.can_start(state, "attend_class")[0] is True


def test_immediate_daily_event_on_last_action_still_ends_the_day(tmp_path):
    flow = make_flow(tmp_path)
    flow.new_game(seed=1, skip_intro=True)
    state = flow.state
    state.action_slot = 3
    result = ActivityResult(ok=True, activity_id="attend_class", error_code=None, deltas={},
                            triggered_event_id="daily_lost_cat", day_finished=True)
    flow.handle_activity_result(result)
    flow.close_result_panel(result)
    assert state.day_index == 1


# --------------------------------------------------------------------------- #
# H2：读档绕过 GameFlow.load_game -> 室内存档卡墙 / 一直暂停 / 暂存数据不清
# --------------------------------------------------------------------------- #
def test_loading_an_indoor_save_lands_outside_and_unpauses(tmp_path, map_data):
    flow = make_flow(tmp_path, map_data)
    flow.new_game(seed=1, skip_intro=True)
    state = flow.require_state()
    state.world.location_id = "loc_dorm"
    state.world.x, state.world.y = 205.0, 3.0    # 室内世界坐标
    state.play_seconds = 0.0
    flow.saves.save(state, "slot_1")
    before_actions = flow.today_activities

    loaded = flow.load_game("slot_1")

    assert loaded.world.location_id.startswith("loc_") and not map_data.has_interior(
        loaded.world.location_id), "读档后地点必须回到室外区域"
    assert (loaded.world.x, loaded.world.y) == pytest.approx(map_data.exit_point("loc_dorm")[:2])
    assert flow.paused is False
    assert flow.today_activities == [] or flow.today_activities is not before_actions
    flow.tick(0.5)   # 暂停时 tick 不累计；这里必须能累计
    assert loaded.play_seconds > 0.0


def test_load_repairs_a_position_inside_a_wall(tmp_path, map_data):
    flow = make_flow(tmp_path, map_data)
    flow.new_game(seed=1, skip_intro=True)
    state = flow.require_state()
    state.world.location_id = "loc_gate"
    # 宿舍楼占地的正中间：一定是阻挡体
    rect = map_data.building("loc_dorm").rect
    state.world.x = (rect.x0 + rect.x1) / 2.0
    state.world.y = (rect.y0 + rect.y1) / 2.0
    flow.saves.save(state, "slot_1")

    loaded = flow.load_game("slot_1")

    assert not map_data.is_blocked(loaded.world.location_id, loaded.world.x, loaded.world.y)
    assert (loaded.world.x, loaded.world.y) == pytest.approx((40.0, 5.0))


# --------------------------------------------------------------------------- #
# H3：学期事件在日结算面板上退出 -> 自动存档里必须留着待处理事件
# --------------------------------------------------------------------------- #
def test_semester_event_survives_quitting_on_the_day_summary(tmp_path):
    flow = make_flow(tmp_path)
    flow.new_game(seed=1, skip_intro=True)
    state = flow.require_state()
    state.day_index = 1          # 第 1 学期第 2 天：结算后触发 sem_1
    state.action_slot = 3
    flow.finish_day()

    raw = json.loads(flow.saves.path_for("autosave").read_text("utf-8"))["state"]
    assert raw["pending_event_id"] == "sem_1_club_fair"
    assert raw["phase"] == "event"

    resumed = make_flow(tmp_path, name="saves")
    loaded = resumed.load_game("autosave")

    assert loaded.pending_event_id == "sem_1_club_fair"
    assert resumed.scenes.top_overlay_id == "EventScene"
    replay_pending_event(resumed)
    # 事件结束后进入新的一天（不是把这一天卡住）
    assert loaded.phase == "campus"
    assert loaded.action_slot == 0


# --------------------------------------------------------------------------- #
# H4：第 16 天的存档不能被钳回第 15 天，读档要走毕业流程
# --------------------------------------------------------------------------- #
def test_day_index_may_reach_total_days():
    state = GameState.from_dict({"day_index": config.TOTAL_DAYS, "phase": "event"})
    assert state.day_index == config.TOTAL_DAYS


def test_loading_a_finished_save_goes_to_graduation(tmp_path):
    flow = make_flow(tmp_path)
    flow.new_game(seed=1, skip_intro=True)
    state = flow.require_state()
    state.day_index = config.TOTAL_DAYS
    state.action_slot = 0
    state.phase = "graduation"
    flow.saves.save(state, "slot_1")

    loaded = flow.load_game("slot_1")

    assert loaded.day_index == config.TOTAL_DAYS
    assert loaded.phase == "graduation"
    assert flow.scenes.base_id == "GraduationScene"
    assert loaded.ending_id


def test_loading_a_save_that_used_up_the_day_ends_it(tmp_path):
    """第 3 个行动触发事件时退出：自动存档停在 slot=3、没有待处理事件。"""
    flow = make_flow(tmp_path)
    flow.new_game(seed=1, skip_intro=True)
    state = flow.require_state()
    state.day_index = 4
    state.action_slot = 3
    flow.saves.save(state, "slot_1")

    loaded = flow.load_game("slot_1")

    assert loaded.day_index == 5
    assert loaded.action_slot == 0
    assert flow.scenes.top_overlay_id == "DaySummary"


# --------------------------------------------------------------------------- #
# M：today_activities 不能跨局泄漏
# --------------------------------------------------------------------------- #
def test_new_game_clears_today_activities(tmp_path):
    flow = make_flow(tmp_path)
    flow.new_game(seed=1, skip_intro=True)
    state = flow.require_state()
    for activity_id in ("attend_class", "library_study"):
        result = flow.services.activity.start(state, activity_id)
        flow.handle_activity_result(result)
        flow.close_result_panel(result)
    assert flow.activity_log_today()

    flow.back_to_main_menu()
    flow.new_game(seed=2, skip_intro=True)
    assert flow.activity_log_today() == []


# --------------------------------------------------------------------------- #
# 低：链式事件、存档版本号、损坏存档的摘要回退
# --------------------------------------------------------------------------- #
def test_chained_event_is_pushed_instead_of_dropped(tmp_path):
    flow = make_flow(tmp_path)
    flow.new_game(seed=1, skip_intro=True)
    state = flow.require_state()
    state.phase = "event"
    next_id = "sem_1_club_fair"

    flow.handle_event_result(EventResult(event_id="story_opening", choice_id="begin",
                                         next_event_id=next_id))

    assert state.pending_event_id == next_id
    assert flow.scenes.top_overlay_id == "EventScene"


def test_save_payload_uses_current_save_version(tmp_path):
    flow = make_flow(tmp_path)
    flow.new_game(seed=1, skip_intro=True)
    path = flow.saves.save(flow.require_state(), "slot_1")
    raw = json.loads(path.read_text("utf-8"))
    assert raw["save_version"] == config.SAVE_VERSION
    assert raw["state"]["save_version"] == config.SAVE_VERSION


def test_peek_falls_back_to_the_backup_file(tmp_path):
    flow = make_flow(tmp_path)
    flow.new_game(seed=1, skip_intro=True)
    state = flow.require_state()
    flow.saves.save(state, "slot_1")
    flow.saves.save(state, "slot_1")          # 第二份 -> .bak 有了内容
    flow.saves.path_for("slot_1").write_text("{ broken", encoding="utf-8")

    summary = flow.saves.peek("slot_1")
    assert summary is not None, "主文件损坏但备份完好时，列表不能显示为空"
    assert summary.summary.get("day_index") == state.day_index
    loaded = flow.load_game("slot_1")
    assert loaded.day_index == state.day_index


# --------------------------------------------------------------------------- #
# M：关系阈值不能只在"交谈"里检查
# --------------------------------------------------------------------------- #
def test_relationship_event_triggers_from_a_non_talk_activity(tmp_path):
    flow = make_flow(tmp_path)
    flow.new_game(seed=1, skip_intro=True)
    state = flow.require_state()
    state.day_index = 2
    state.relationships["npc_sumo"] = 20   # 已过 stage1 阈值，但从没交谈过

    result = flow.services.activity.start(state, "attend_class")
    flow.handle_activity_result(result)

    assert result.triggered_event_id == "rel_npc_sumo_1"
    assert "npc_sumo_stage1" in state.flags


# --------------------------------------------------------------------------- #
# 中：结局回顾里同一事件重复出现
# --------------------------------------------------------------------------- #
def test_highlights_do_not_repeat_the_same_semester_event():
    state = new_state(1)
    state.event_log = ["sem_1_club_fair", "sem_1_club_fair:fair_club",
                       "sem_2_first_exam", "sem_2_first_exam:study"]
    highlights = resolve_services().ending._highlights(state)
    semester = [entry for entry in highlights if entry.startswith("sem_")]
    assert semester == ["sem_1_club_fair:fair_club", "sem_2_first_exam:study"]


# --------------------------------------------------------------------------- #
# 中：卡在墙里时不能把玩家弹回去
# --------------------------------------------------------------------------- #
def test_player_can_walk_out_of_a_wall_instead_of_being_snapped_back(map_data):
    """卡在宿舍楼占地里往南走：旧解算会把整个人弹到楼的北侧（14 米）。"""
    wall = map_data.building("loc_dorm").rect
    rects = map_data.colliders_for(CAMPUS_SCENE)
    start_x = (wall.x0 + wall.x1) / 2.0
    start_y = wall.y0 + 0.1
    motion = PlayerMotion(start_x, start_y)
    assert overlap(motion, PLAYER_HALF, wall), "用例前提：起始位置必须在墙里"

    for _ in range(60):
        motion.update({"s"}, False, 1 / 60, rects, map_data.bounds)

    assert motion.y < start_y - 1.0, (
        f"卡在墙里时按 S 没有走出来（y {start_y:.2f} -> {motion.y:.2f}）")
    assert motion.y < wall.y0, "应该已经离开这栋楼的占地"


# --------------------------------------------------------------------------- #
# 低：规则校验必须能报出拼错的旗标 / 重复优先级 / 全条件选项
# --------------------------------------------------------------------------- #
def _rules_copy(tmp_path):
    rules = tmp_path / "rules"
    rules.mkdir()
    for filename in RULE_FILES.values():
        shutil.copy2(RULES_DIR / filename, rules / filename)
    return rules


def _edit(path, mutate):
    data = json.loads(path.read_text(encoding="utf-8"))
    mutate(data)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def test_unknown_flag_reference_is_rejected(tmp_path):
    rules = _rules_copy(tmp_path)

    def mutate(data):
        data[0]["choices"][0]["conditions"] = [
            {"type": "flag", "key": "accepted_labb"}     # 拼错一个字母
        ]

    _edit(rules / "events.json", mutate)
    with pytest.raises(ContentError, match="accepted_labb"):
        ContentDB(rules)


def test_duplicate_ending_priority_is_rejected(tmp_path):
    rules = _rules_copy(tmp_path)

    def mutate(data):
        data[1]["priority"] = data[0]["priority"]

    _edit(rules / "endings.json", mutate)
    with pytest.raises(ContentError, match="priority"):
        ContentDB(rules)


def test_event_with_only_conditional_choices_is_rejected(tmp_path):
    rules = _rules_copy(tmp_path)

    def mutate(data):
        for event in data:
            if event["id"] == "story_opening":
                event["choices"][0]["conditions"] = [
                    {"type": "stat", "key": "academic", "op": ">=", "value": 100}
                ]

    _edit(rules / "events.json", mutate)
    with pytest.raises(ContentError, match="无条件选项"):
        ContentDB(rules)


def test_valid_rules_still_load():
    db = ContentDB()
    assert db.event("sem_1_club_fair") is not None
    assert spec_data.TOTAL_DAYS == config.TOTAL_DAYS
