"""任务 C5 独立测试：移动、速度积分、8 方向朝向、碰撞集成与脚步声。

对应 C-ST-01（测试地图四边移动撞墙）与 C-ST-02（30 个方向各随机移动 10 秒）。
只覆盖 game/world/player_controller.py 中不依赖 Panda3D 的部分：
- PlayerMotion 为纯数学；
- PlayerController 通过注入的 key_down / animator / audio 与假节点驱动。
"""

from __future__ import annotations

import math
import random

import pytest

from game.world.collision import make_rect
from game.world.input_map import DT_MAX, RUN_SPEED, WALK_SPEED
from game.world.player_controller import (
    FACING_HEADING,
    IDLE_ASSET,
    IDLE_FPS,
    PlayerController,
    PlayerMotion,
    SFX_FOOTSTEP_FLOOR,
    SFX_FOOTSTEP_GROUND,
    WALK_ASSET,
    WALK_FPS,
)

from fixtures.fake_state import FakeState

DT = 1.0 / 60.0
DIRECTIONS = ({"w"}, {"s"}, {"a"}, {"d"}, {"w", "d"}, {"w", "a"}, {"s", "d"}, {"s", "a"})


# ------------------------------------------------------------------ 假对象


class FakeNode:
    def __init__(self) -> None:
        self.pos = None
        self.h = None

    def setPos(self, x, y, z):  # noqa: N802 - 模仿 Panda3D 命名
        self.pos = (x, y, z)

    def setH(self, h):  # noqa: N802
        self.h = h


class FakeAnimator:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, float]] = []

    def play(self, asset, row=None, fps=None):
        self.calls.append((asset, row, fps))


class FakeAudio:
    def __init__(self) -> None:
        self.played: list[str] = []

    def play(self, sfx):
        self.played.append(sfx)


def _key_down_for(*keys):
    keys = set(keys)
    return lambda key: key in keys


# ------------------------------------------------------------------ PlayerMotion


def test_motion_starts_still():
    m = PlayerMotion(3.0, 4.0)
    assert m.speed == 0.0
    assert m.moving is False
    assert m.facing == "n"


@pytest.mark.parametrize(
    "keys, expected_facing",
    [
        ({"w"}, "n"),
        ({"d"}, "e"),
        ({"s"}, "s"),
        ({"a"}, "w"),
        ({"w", "d"}, "ne"),
        ({"w", "a"}, "nw"),
        ({"s", "d"}, "se"),
        ({"s", "a"}, "sw"),
    ],
)
def test_motion_facing_matches_direction(keys, expected_facing):
    m = PlayerMotion(0.0, 0.0, facing="s")
    for _ in range(5):
        m.update(keys, False, DT)
    assert m.facing == expected_facing
    assert m.moving is True


def test_motion_opposite_keys_cancel():
    m = PlayerMotion(0.0, 0.0)
    for _ in range(5):
        moved = m.update({"w", "s"}, False, DT)
    assert moved is False
    assert m.speed == 0.0
    assert (m.x, m.y) == (0.0, 0.0)


def test_motion_does_not_turn_below_speed_threshold():
    m = PlayerMotion(0.0, 0.0, facing="s")
    m.update({"w"}, False, 0.001)  # 速度仅 0.03 < 0.1
    assert m.facing == "s"
    assert m.moving is False
    assert m.y == 0.0


def test_motion_keeps_facing_after_stop():
    m = PlayerMotion(0.0, 0.0)
    for _ in range(30):
        m.update({"d"}, False, DT)
    assert m.facing == "e"
    for _ in range(30):
        m.update(set(), False, DT)
    assert m.facing == "e"
    assert m.speed == 0.0


def test_motion_accelerates_to_walk_speed():
    m = PlayerMotion(0.0, 0.0)
    for _ in range(120):
        m.update({"w"}, False, DT)
    assert m.speed == pytest.approx(WALK_SPEED)


def test_motion_run_speed_is_faster():
    m = PlayerMotion(0.0, 0.0)
    for _ in range(120):
        m.update({"w"}, True, DT)
    assert m.speed == pytest.approx(RUN_SPEED)


def test_motion_clamps_dt_to_max():
    m = PlayerMotion(0.0, 0.0)
    m.update({"w"}, False, 5.0)
    # 加速度 30、dt 上限 0.0333 -> 本帧速度 0.999，位移 = 速度 * 上限
    assert m.speed == pytest.approx(30.0 * DT_MAX)
    assert m.y == pytest.approx(30.0 * DT_MAX * DT_MAX)


def test_motion_snap_resets_speed_and_sets_facing():
    m = PlayerMotion(0.0, 0.0)
    for _ in range(30):
        m.update({"w"}, True, DT)
    m.snap(7.0, 8.0, "sw")
    assert (m.x, m.y, m.facing, m.speed, m.moving) == (7.0, 8.0, "sw", 0.0, False)


# ------------------------------------------------------------------ 碰撞集成


def test_motion_stops_at_wall():
    wall = make_rect(1.0, -50.0, 2.0, 50.0)
    m = PlayerMotion(0.0, 0.0)
    for _ in range(200):
        m.update({"d"}, False, DT, (wall,))
    assert m.x == pytest.approx(1.0 - 0.35 - 1e-4, abs=1e-4)
    assert m.x < 1.0 - 0.35


def test_motion_slides_along_wall():
    wall = make_rect(1.0, -50.0, 2.0, 50.0)
    m = PlayerMotion(0.0, 0.0)
    for _ in range(200):
        m.update({"d", "w"}, False, DT, (wall,))
    assert m.x == pytest.approx(1.0 - 0.35 - 1e-4, abs=1e-4)
    assert m.y > 1.0  # 沿墙向上滑动


def test_motion_clamped_to_bounds():
    bounds = make_rect(0.0, 0.0, 10.0, 10.0)
    m = PlayerMotion(5.0, 5.0)
    for _ in range(400):
        m.update({"d"}, False, DT, (), bounds)
    assert m.x == pytest.approx(10.0 - 0.35)


def test_motion_stays_inside_test_map(test_map_data):
    """C-ST-01：测试地图四边移动撞墙，位置始终在边界内。"""
    bounds = test_map_data.bounds
    rects = test_map_data.colliders_for("campus")
    for keys in ({"w"}, {"s"}, {"a"}, {"d"}, {"w", "a"}, {"s", "d"}):
        m = PlayerMotion(10.0, 10.0)
        for _ in range(600):
            m.update(keys, False, DT, rects, bounds)
        assert 0.35 - 1e-6 <= m.x <= 20.0 - 0.35 + 1e-6
        assert 0.35 - 1e-6 <= m.y <= 20.0 - 0.35 + 1e-6


def test_motion_random_directions_fuzz(map_data):
    """C-ST-02：30 个方向各移动 10 秒，无 NaN、无越界、无异常。"""
    bounds = map_data.bounds
    rects = map_data.colliders_for("campus")
    spawn = map_data.spawn[0]
    rng = random.Random(20261109)
    keys_pool = ("w", "s", "a", "d")
    for i in range(30):
        pressed = {k for k in keys_pool if rng.random() < 0.5}
        if not pressed:
            pressed = {rng.choice(keys_pool)}
        running = bool(i % 2)
        m = PlayerMotion(*spawn)
        for _ in range(600):  # 10 秒
            m.update(pressed, running, DT, rects, bounds)
        assert math.isfinite(m.x) and math.isfinite(m.y)
        assert 0.35 - 1e-6 <= m.x <= 80.0 - 0.35 + 1e-6
        assert 0.35 - 1e-6 <= m.y <= 60.0 - 0.35 + 1e-6
        assert math.isfinite(m.speed)


# ------------------------------------------------------------------ PlayerController


def _controller(map_data, **kw):
    state = FakeState()
    node = FakeNode()
    animator = kw.pop("animator", FakeAnimator())
    audio = kw.pop("audio", FakeAudio())
    ctrl = PlayerController(map_data, state, node, animator=animator, audio=audio, **kw)
    return ctrl, state, node, animator, audio


def test_controller_writes_world_and_transform(map_data):
    ctrl, state, node, animator, _audio = _controller(map_data, key_down=_key_down_for("d"))
    ctrl.update(DT)
    assert state.world.x == pytest.approx(ctrl.motion.x)
    assert state.world.y == pytest.approx(ctrl.motion.y)
    assert state.world.facing == "e"
    assert node.pos == (ctrl.motion.x, ctrl.motion.y, 0.0)
    assert node.h == FACING_HEADING["e"]


def test_controller_locked_ignores_input(map_data):
    ctrl, _state, node, animator, _audio = _controller(map_data, key_down=_key_down_for("d"))
    ctrl.input_locked = True
    ctrl.update(DT)
    assert (ctrl.motion.x, ctrl.motion.y) == (40.0, 5.0)
    assert animator.calls[-1][0] == IDLE_ASSET


def test_controller_animation_switches_asset_and_fps(map_data):
    ctrl, _state, _node, animator, _audio = _controller(map_data, key_down=_key_down_for("w"))
    for _ in range(10):
        ctrl.update(DT)
    assert animator.calls[-1] == (WALK_ASSET, "n", WALK_FPS)

    idle_ctrl, _s, _n, idle_anim, _a = _controller(map_data, key_down=_key_down_for())
    idle_ctrl.update(DT)
    assert idle_anim.calls[-1] == (IDLE_ASSET, "n", IDLE_FPS)


def test_controller_footstep_uses_ground_outdoors(map_data):
    ctrl, _state, _node, _animator, audio = _controller(map_data, key_down=_key_down_for("w"))
    for _ in range(60):  # 1 秒
        ctrl.update(DT)
    assert audio.played.count(SFX_FOOTSTEP_GROUND) >= 2
    assert SFX_FOOTSTEP_FLOOR not in audio.played


def test_controller_footstep_uses_floor_indoors(map_data):
    ctrl, _state, node, _animator, audio = _controller(map_data, key_down=_key_down_for("w"))
    ctrl.set_scene("loc_dorm")
    ctrl.teleport(208.0, 3.0, "n")
    for _ in range(60):
        ctrl.update(DT)
    assert audio.played.count(SFX_FOOTSTEP_FLOOR) >= 2
    assert SFX_FOOTSTEP_GROUND not in audio.played


def test_controller_teleport_updates_world_and_position(map_data):
    ctrl, state, node, _animator, _audio = _controller(map_data, key_down=_key_down_for())
    ctrl.teleport(12.0, 20.0, "sw")
    assert (ctrl.motion.x, ctrl.motion.y, ctrl.motion.facing) == (12.0, 20.0, "sw")
    assert (state.world.x, state.world.y, state.world.facing) == (12.0, 20.0, "sw")
    assert node.pos == (12.0, 20.0, 0.0)


def test_controller_interior_scene_translates_colliders(map_data):
    ctrl, _state, _node, _animator, _audio = _controller(map_data, key_down=_key_down_for())
    ctrl.set_scene("loc_dorm")
    origin = map_data.interior("loc_dorm").origin
    assert ctrl._bounds == pytest.approx(
        (origin[0], origin[1], origin[0] + 16.0, origin[1] + 10.0)
    )
    # 本地家具矩形已平移到世界坐标
    local = map_data.colliders_for("loc_dorm")
    assert all(
        world.x0 == pytest.approx(local[i].x0 + origin[0]) for i, world in enumerate(ctrl._rects)
    )


def test_controller_read_input_ignores_unknown_keys(map_data):
    ctrl, _state, _node, _animator, _audio = _controller(
        map_data, key_down=_key_down_for("w", "shift", "z")
    )
    pressed, running = ctrl.read_input()
    assert pressed == {"w"}
    assert running is True
