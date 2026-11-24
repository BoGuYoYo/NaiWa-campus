"""开学典礼（OpeningCeremonyScene）回归测试。

覆盖两阶段玩法的流程契约：
1. 第 1 天结束（day_index 0→1）在完成"新一天"初始化**之后**自动切礼堂；
2. 礼堂里走动不污染 state.world（出礼堂/读档后主校园落点仍是校门）；
3. 离开礼堂：写 OPENING_CEREMONY_DONE、落 post_ceremony 自动档、回校园且不重复触发；
4. 读档补播：day_end 自动档（pending_day_start=True）读回来会再进礼堂；
5. 礼堂几何：墙体/舞台/看台/出口地垫的碰撞与站位自洽。
"""

from __future__ import annotations

import json

import pytest

from game import config
from game.core.event_bus import TOPIC_DAY_STARTED, EventBus
from game.core.flow import GameFlow, resolve_services
from game.core.save_manager import SaveManager
from game.core.scene_manager import SceneManager
from game.core.state import OPENING_CEREMONY_DONE, GameState, WorldPos, new_state
from game.world.ceremony_scene import (
    CEREMONY_NPCS,
    EXIT_MAT_LOCAL,
    ORIGIN,
    SIZE,
    STAGE_RECT_LOCAL,
    CeremonyScene,
    build_local_colliders,
)


class DummyScene:
    def __init__(self, scene_id, **kwargs):
        self.scene_id = scene_id
        self.kwargs = kwargs

    def on_enter(self, **kwargs):
        pass

    def on_exit(self):
        pass


class DummyApp:
    map_data = None


@pytest.fixture()
def flow(tmp_path):
    bus = EventBus()
    scenes = SceneManager(app=None, factory=lambda sid, kw: DummyScene(sid, **kw), bus=bus,
                          fade_seconds=0.0)
    saves = SaveManager(saves_root=tmp_path / "saves")
    return GameFlow(app=DummyApp(), scenes=scenes, saves=saves, bus=bus,
                    services=resolve_services())


def _finish_first_day(flow: GameFlow) -> None:
    """把第 1 天直接结算掉（不跑行动，只关心换日 → 典礼的衔接）。"""
    state = flow.require_state()
    state.action_slot = config.ACTIONS_PER_DAY
    flow.finish_day()
    flow.scenes.pop()          # 关闭 DaySummary
    flow.close_day_summary()


# --------------------------------------------------------------------------- #
# 1. 换日 → 典礼
# --------------------------------------------------------------------------- #
def test_first_day_end_enters_ceremony_after_day_start(flow):
    flow.new_game(seed=42, skip_intro=True)
    state = flow.require_state()
    starts: list[int] = []
    flow.bus.subscribe(TOPIC_DAY_STARTED, lambda **data: starts.append(data["day_index"]))

    _finish_first_day(flow)

    # 新一天的初始化必须先完成：日期、时段、落点、DAY_STARTED
    assert state.day_index == 1
    assert state.action_slot == 0
    assert state.phase == "campus"
    assert (state.world.x, state.world.y) == (40.0, 5.0)
    assert starts == [1]
    # 然后才切礼堂（基础场景是礼堂，且旗标还没写）
    assert flow.scenes.base_id == "OpeningCeremonyScene"
    assert OPENING_CEREMONY_DONE not in state.flags


def test_ceremony_is_not_triggered_on_later_days(flow):
    flow.new_game(seed=42, skip_intro=True)
    state = flow.require_state()
    state.flags.add(OPENING_CEREMONY_DONE)
    state.day_index = 2
    state.action_slot = config.ACTIONS_PER_DAY

    flow.finish_day()
    flow.scenes.pop()
    flow.close_day_summary()

    assert state.day_index == 3
    assert flow.scenes.base_id == "CampusScene"


# --------------------------------------------------------------------------- #
# 2/3. 离开礼堂
# --------------------------------------------------------------------------- #
def test_leaving_ceremony_returns_to_campus_and_records_flag(flow):
    flow.new_game(seed=42, skip_intro=True)
    state = flow.require_state()
    _finish_first_day(flow)
    assert flow.scenes.base_id == "OpeningCeremonyScene"

    # 礼堂里"走动"过：模拟独立 PlayerMotion 改了落点也不该影响 state.world
    state.world = WorldPos(location_id="loc_auditorium", x=409.0, y=5.0, facing="e")

    flow.finish_opening_ceremony()

    assert OPENING_CEREMONY_DONE in state.flags
    assert flow.scenes.base_id == "CampusScene"
    assert (state.world.x, state.world.y) == (40.0, 5.0)
    assert state.world.location_id == "loc_gate"
    payload = json.loads(flow.saves.path_for("autosave").read_text(encoding="utf-8"))
    assert payload["reason"] == "post_ceremony"
    assert OPENING_CEREMONY_DONE in payload["state"]["flags"]


def test_ceremony_does_not_replay_after_finishing(flow):
    flow.new_game(seed=42, skip_intro=True)
    state = flow.require_state()
    _finish_first_day(flow)
    flow.finish_opening_ceremony()

    # 同一天再结算一次换日（模拟日结算面板重复关闭）也不会回礼堂
    flow._begin_next_day(state)
    assert flow.scenes.base_id == "CampusScene"


# --------------------------------------------------------------------------- #
# 4. 读档补播
# --------------------------------------------------------------------------- #
def test_loading_day_end_autosave_replays_ceremony(tmp_path):
    flow = GameFlow(
        app=DummyApp(),
        scenes=SceneManager(app=None, factory=lambda sid, kw: DummyScene(sid, **kw),
                            bus=EventBus(), fade_seconds=0.0),
        saves=SaveManager(saves_root=tmp_path / "saves"),
        bus=EventBus(),
        services=resolve_services(),
    )
    flow.new_game(seed=42, skip_intro=True)
    state = flow.require_state()
    state.action_slot = config.ACTIONS_PER_DAY
    flow.finish_day()      # day_end 自动档：pending_day_start=True

    resumed = GameFlow(
        app=DummyApp(),
        scenes=SceneManager(app=None, factory=lambda sid, kw: DummyScene(sid, **kw),
                            bus=EventBus(), fade_seconds=0.0),
        saves=flow.saves,
        bus=EventBus(),
        services=resolve_services(),
    )
    loaded = resumed.load_game("autosave")

    assert loaded.day_index == 1
    assert resumed.scenes.base_id == "OpeningCeremonyScene"


def test_loading_a_day1_save_without_flag_replays_ceremony(tmp_path):
    """在礼堂里（暂停菜单）存的档没有典礼旗标：读档应把玩家送回礼堂。"""
    flow = GameFlow(
        app=DummyApp(),
        scenes=SceneManager(app=None, factory=lambda sid, kw: DummyScene(sid, **kw),
                            bus=EventBus(), fade_seconds=0.0),
        saves=SaveManager(saves_root=tmp_path / "saves"),
        bus=EventBus(),
        services=resolve_services(),
    )
    flow.new_game(seed=42, skip_intro=True)
    state = flow.require_state()
    state.day_index = 1
    state.action_slot = 0
    state.world = WorldPos()
    flow.saves.save(state, "slot_1")

    resumed = GameFlow(
        app=DummyApp(),
        scenes=SceneManager(app=None, factory=lambda sid, kw: DummyScene(sid, **kw),
                            bus=EventBus(), fade_seconds=0.0),
        saves=flow.saves,
        bus=EventBus(),
        services=resolve_services(),
    )
    resumed.load_game("slot_1")
    assert resumed.scenes.base_id == "OpeningCeremonyScene"


def test_day1_save_after_ceremony_loads_straight_to_campus(tmp_path):
    flow = GameFlow(
        app=DummyApp(),
        scenes=SceneManager(app=None, factory=lambda sid, kw: DummyScene(sid, **kw),
                            bus=EventBus(), fade_seconds=0.0),
        saves=SaveManager(saves_root=tmp_path / "saves"),
        bus=EventBus(),
        services=resolve_services(),
    )
    flow.new_game(seed=42, skip_intro=True)
    state = flow.require_state()
    state.day_index = 1
    state.flags.add(OPENING_CEREMONY_DONE)
    flow.saves.save(state, "slot_1")

    resumed = GameFlow(
        app=DummyApp(),
        scenes=SceneManager(app=None, factory=lambda sid, kw: DummyScene(sid, **kw),
                            bus=EventBus(), fade_seconds=0.0),
        saves=flow.saves,
        bus=EventBus(),
        services=resolve_services(),
    )
    resumed.load_game("slot_1")
    assert resumed.scenes.base_id == "CampusScene"


# --------------------------------------------------------------------------- #
# 5. 礼堂几何与出口地垫
# --------------------------------------------------------------------------- #
def test_ceremony_colliders_cover_walls_stage_and_benches():
    rects = build_local_colliders()
    w, h = SIZE
    # 北/东/西三面实墙 + 南墙两段（中央留出口）
    assert any(r.x0 == 0.0 and r.y1 == h for r in rects)
    assert any(r.x1 == w and r.y0 == 0.0 for r in rects)
    south = [r for r in rects if r.y0 == 0.0 and r.y1 <= 0.5 and r.x1 - r.x0 > 1.0]
    assert len(south) >= 2
    # 舞台整块拦住（不能走上台穿演讲台/校长）
    assert STAGE_RECT_LOCAL in rects
    # 三位同学各有一块碰撞体
    for spec in CEREMONY_NPCS:
        assert any(abs(r.x0 - (spec.local_x - 0.30)) < 1e-6 for r in rects)


def test_exit_mat_is_inside_the_south_gap_and_reachable():
    scene = CeremonyScene.__new__(CeremonyScene)
    scene.origin = ORIGIN
    scene._exit_cooldown = 0.0
    mx, my, mr = scene.exit_mat_world()
    # 地垫在礼堂本地坐标里、位于南墙豁口正中
    local_x = mx - ORIGIN[0]
    local_y = my - ORIGIN[1]
    assert 7.5 < local_x < 10.5
    assert local_y <= 1.5
    assert (local_x, local_y, mr) == EXIT_MAT_LOCAL
    # 玩家出生点不在出口地垫里（否则一进礼堂立刻被送出去）
    sx, sy, _facing = scene.player_spawn_world()
    assert (sx - mx) ** 2 + (sy - my) ** 2 > mr * mr
    # 站上地垫触发一次，冷却期内不重复触发
    assert scene.update_exit_mat(mx, my, 0.016) is True
    assert scene.update_exit_mat(mx, my, 0.016) is False


def test_ceremony_player_spawn_does_not_overlap_colliders():
    from game.world.collision import PLAYER_HALF, overlap

    scene = CeremonyScene.__new__(CeremonyScene)
    scene.origin = ORIGIN
    x, y, _facing = scene.player_spawn_world()
    pos = type("P", (), {"x": x, "y": y})()
    blocked = [r for r in scene.colliders_world() if overlap(pos, PLAYER_HALF, r)]
    assert blocked == [], f"出生点压在碰撞体里：{blocked}"


def test_ceremony_clears_opening_npcs_even_without_entering_buildings(flow):
    from game.core.state import OPENING_NPCS_ACTIVE

    flow.new_game(seed=42, skip_intro=True)
    state = flow.require_state()
    assert OPENING_NPCS_ACTIVE in state.flags

    _finish_first_day(flow)
    assert OPENING_NPCS_ACTIVE not in state.flags

    flow.finish_opening_ceremony()
    assert OPENING_NPCS_ACTIVE not in state.flags


def test_ceremony_north_wall_clearance_and_bench_aisles_are_walkable():
    from game.world.ceremony_scene import NORTH_WALL_CLEARANCE, WALL_THICKNESS
    from game.world.collision import PLAYER_HALF, Rect
    from game.world.player_controller import PlayerMotion

    rects = build_local_colliders()
    bounds = Rect(0.0, 0.0, SIZE[0], SIZE[1])

    # 1. 北墙留出 2.5D 角色倾斜净空，走到底角色卡片顶端也不能扎进北墙内面
    motion = PlayerMotion(1.0, 6.0, "n")
    for _ in range(240):
        motion.update({"w"}, False, 1 / 60.0, rects, bounds)
    assert motion.y + NORTH_WALL_CLEARANCE <= SIZE[1] - WALL_THICKNESS + 1e-3

    # 2. 长椅与左右墙之间、前后排长椅之间留足 > 2*PLAYER_HALF 宽度，非精确中线也能顺畅通过
    side_motion = PlayerMotion(1.0, 1.2, "n")
    for _ in range(240):
        side_motion.update({"w"}, False, 1 / 60.0, rects, bounds)
    assert side_motion.y > 5.0

    row_motion = PlayerMotion(5.5, 3.18, "w")
    for _ in range(240):
        row_motion.update({"a"}, False, 1 / 60.0, rects, bounds)
    assert row_motion.x < 1.2

    # 3. 出口地垫圆环不压出南侧门框底线 (y >= WALL_THICKNESS)
    _mx, my, mr = EXIT_MAT_LOCAL
    assert my - mr >= WALL_THICKNESS - 1e-6

    # 4. 舞台台阶两侧平地不会在 y=7.2 处过早形成 0.6 m 空气墙（脚点可走到 ~7.20 靠近台沿）
    stage_side = PlayerMotion(4.5, 6.0, "n")
    for _ in range(180):
        stage_side.update({"w"}, False, 1 / 60.0, rects, bounds)
    assert stage_side.y > 7.1
    assert stage_side.y <= STAGE_RECT_LOCAL.y0 - PLAYER_HALF + 1e-3


def test_ceremony_escape_advances_completed_dialogue_page():
    from types import SimpleNamespace

    from game.core.world_scene import OpeningCeremonySceneAdapter

    advanced: list[str] = []
    adapter = OpeningCeremonySceneAdapter.__new__(OpeningCeremonySceneAdapter)
    adapter.app = SimpleNamespace(
        scenes=SimpleNamespace(overlays=(), is_transitioning=lambda: False),
        flow=SimpleNamespace(set_paused=lambda _v: None),
    )
    adapter._state = new_state(seed=1)
    adapter.dialogue = SimpleNamespace(visible=True, advance=lambda: False)
    adapter._active_pages = [{"lines": ["page 1"]}, {"lines": ["page 2"]}]
    adapter._advance_dialogue = lambda: advanced.append("next")

    adapter._on_escape()
    assert advanced == ["next"]
