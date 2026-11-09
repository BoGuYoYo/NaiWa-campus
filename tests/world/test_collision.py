"""任务 C2 独立测试：碰撞矩形、轴分离扫掠、贴墙滑动与模糊测试。"""

from __future__ import annotations

import math
import random

import pytest

from game.world.collision import PLAYER_HALF, Rect, clamp_to_bounds, make_rect, move_and_collide, overlap


class Pos:
    """测试用的最小可写坐标（正式代码用 A 的 WorldPos）。"""

    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y


def _make_rect(x0, y0, x1, y1) -> Rect:
    return make_rect(x0, y0, x1, y1)


def test_make_rect_normalises_corners():
    assert make_rect(10, 10, 2, 4) == Rect(2, 4, 10, 10)


def test_overlap_detects_touching_box():
    r = _make_rect(0, 0, 1, 1)
    assert overlap(Pos(0.5, 0.5), 0.35, r) is True
    assert overlap(Pos(1.4, 0.5), 0.35, r) is False


def test_move_and_collide_returns_same_object():
    pos = Pos(5.0, 5.0)
    delta = Pos(0.0, 0.0)
    assert move_and_collide(pos, delta, []) is pos


def test_cannot_cross_wall_positive_x():
    walls = [_make_rect(10, 0, 12, 20)]
    pos = Pos(5.0, 10.0)
    move_and_collide(pos, Pos(20.0, 0.0), walls)
    assert pos.x == pytest.approx(10.0 - PLAYER_HALF, abs=1e-3)
    assert pos.y == pytest.approx(10.0)


def test_cannot_cross_wall_negative_x():
    walls = [_make_rect(0, 0, 2, 20)]
    pos = Pos(8.0, 10.0)
    move_and_collide(pos, Pos(-20.0, 0.0), walls)
    assert pos.x == pytest.approx(2.0 + PLAYER_HALF, abs=1e-3)


def test_cannot_cross_wall_positive_y_and_negative_y():
    walls = [_make_rect(0, 10, 20, 12)]
    up = Pos(5.0, 2.0)
    move_and_collide(up, Pos(0.0, 20.0), walls)
    assert up.y == pytest.approx(10.0 - PLAYER_HALF, abs=1e-3)

    down = Pos(5.0, 18.0)
    move_and_collide(down, Pos(0.0, -20.0), walls)
    assert down.y == pytest.approx(12.0 + PLAYER_HALF, abs=1e-3)


def test_slide_along_wall_keeps_other_axis():
    """斜向撞墙时被挡住的轴停住，另一轴继续推进（贴墙滑动）。"""
    walls = [_make_rect(10, 0, 12, 20)]
    pos = Pos(5.0, 5.0)
    move_and_collide(pos, Pos(8.0, 3.0), walls)
    assert pos.x == pytest.approx(10.0 - PLAYER_HALF, abs=1e-3)
    assert pos.y == pytest.approx(8.0, abs=1e-3)


def test_no_tunneling_at_high_speed():
    """单帧位移远大于障碍物尺寸时也不能穿过去。"""
    walls = [_make_rect(10, 0, 10.6, 20)]
    pos = Pos(0.0, 10.0)
    move_and_collide(pos, Pos(80.0, 0.0), walls)
    assert pos.x <= 10.0 - PLAYER_HALF + 1e-3


def test_clamp_to_bounds():
    pos = Pos(-5.0, 99.0)
    clamp_to_bounds(pos, make_rect(0, 0, 80, 60))
    assert pos.x == pytest.approx(PLAYER_HALF)
    assert pos.y == pytest.approx(60.0 - PLAYER_HALF)


def test_collision_fuzz_30_directions_10_seconds(map_data):
    """C-ST-02：30 个方向各持续移动 10 秒，不出现 NaN / 越界 / 卡死。"""
    walls = map_data.colliders_for("campus")
    bounds = map_data.bounds
    rng = random.Random(20261108)
    dt = 1.0 / 60.0
    speed = 6.0
    for i in range(30):
        angle = 2.0 * math.pi * i / 30.0
        pos = Pos(40.0, 5.0)
        for _ in range(int(10.0 / dt)):
            delta = Pos(math.cos(angle) * speed * dt, math.sin(angle) * speed * dt)
            move_and_collide(pos, delta, walls)
            assert math.isfinite(pos.x) and math.isfinite(pos.y)
            assert bounds.x0 + PLAYER_HALF - 1e-6 <= pos.x <= bounds.x1 - PLAYER_HALF + 1e-6
            assert bounds.y0 + PLAYER_HALF - 1e-6 <= pos.y <= bounds.y1 - PLAYER_HALF + 1e-6
            for r in walls:
                assert not overlap(pos, PLAYER_HALF, r)
            angle += rng.uniform(-0.05, 0.05)


def test_collision_fuzz_random_walk_never_inside_obstacle(map_data):
    walls = map_data.colliders_for("campus")
    rng = random.Random(7)
    dt = 1.0 / 60.0
    pos = Pos(40.0, 5.0)
    for _ in range(6000):
        angle = rng.uniform(0.0, 2.0 * math.pi)
        move_and_collide(pos, Pos(math.cos(angle) * 6.0 * dt, math.sin(angle) * 6.0 * dt), walls)
        for r in walls:
            assert not overlap(pos, PLAYER_HALF, r)
