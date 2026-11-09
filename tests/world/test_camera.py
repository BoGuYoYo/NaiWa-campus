"""任务 C6 独立测试：相机数学（死区、平滑、边界、1/24 米对齐）。

对应 C-ST-05：室外与室内边界移动相机时，死区、边界、平滑、1/24 米对齐正确。
本文件只验证 game/world/camera_controller.py 中不依赖 Panda3D 的数学部分。
"""

from __future__ import annotations

import math
import random

import pytest

from game.world.camera_controller import (
    CAMERA_HPR,
    CAMERA_OFFSET,
    CameraRig,
    FILM_HEIGHT,
    FILM_WIDTH,
    OUTDOOR_TARGET_MAX,
    OUTDOOR_TARGET_MIN,
    PIXEL,
    SMOOTH_LAMBDA,
    align_pixel,
    camera_position,
    clamp_target,
    deadzone_desired,
    smooth,
)


# ------------------------------------------------------------------ 规格常量


def test_film_size_is_24_pixels_per_metre():
    assert FILM_WIDTH * 24 == 480
    assert FILM_HEIGHT * 24 == 270


def test_camera_hpr_is_fixed():
    assert CAMERA_HPR == (0.0, -40.0, 0.0)


def test_camera_offset_is_30m_at_40deg():
    assert CAMERA_OFFSET[0] == 0.0
    assert CAMERA_OFFSET[1] == pytest.approx(-30.0 * math.cos(math.radians(40.0)), abs=0.01)
    assert CAMERA_OFFSET[2] == pytest.approx(30.0 * math.sin(math.radians(40.0)), abs=0.01)


def test_outdoor_target_bounds_match_half_view():
    assert OUTDOOR_TARGET_MIN == (10.0, 8.75)
    assert OUTDOOR_TARGET_MAX == (70.0, 51.25)


# ------------------------------------------------------------------ 死区


@pytest.mark.parametrize(
    "player",
    [
        (0.0, 0.0),
        (1.0, 1.0),
        (-2.0, -1.5),
        (2.0, 1.5),
    ],
)
def test_deadzone_keeps_target_when_player_inside(player):
    assert deadzone_desired((0.0, 0.0), player) == (0.0, 0.0)


@pytest.mark.parametrize(
    "player, expected",
    [
        ((5.0, 0.0), (3.0, 0.0)),
        ((-5.0, 0.0), (-3.0, 0.0)),
        ((0.0, 5.0), (0.0, 3.5)),
        ((0.0, -5.0), (0.0, -3.5)),
        ((5.0, 5.0), (3.0, 3.5)),
    ],
)
def test_deadzone_pushes_target_to_edge(player, expected):
    assert deadzone_desired((0.0, 0.0), player) == pytest.approx(expected)


def test_deadzone_axes_are_independent():
    # 玩家只在 X 方向越界时，Y 方向的 target 不动
    assert deadzone_desired((10.0, 20.0), (20.0, 20.0)) == (18.0, 20.0)


# ------------------------------------------------------------------ 平滑


def test_smooth_zero_dt_does_not_move():
    assert smooth((0.0, 0.0), (10.0, 10.0), 0.0) == (0.0, 0.0)


def test_smooth_converges_with_large_dt():
    x, y = smooth((0.0, 0.0), (10.0, 20.0), 100.0)
    assert (x, y) == pytest.approx((10.0, 20.0), abs=1e-9)


def test_smooth_uses_expected_lambda():
    dt = 1.0 / 60.0
    k = 1.0 - math.exp(-SMOOTH_LAMBDA * dt)
    assert smooth((0.0, 0.0), (1.0, 1.0), dt)[0] == pytest.approx(k)


def test_smooth_is_frame_rate_independent():
    dt = 1.0 / 60.0
    one = smooth((0.0, 0.0), (5.0, 5.0), dt)
    half = smooth(smooth((0.0, 0.0), (5.0, 5.0), dt / 2.0), (5.0, 5.0), dt / 2.0)
    assert one == pytest.approx(half, abs=1e-9)


def test_smooth_moves_monotonically_toward_desired():
    current = (0.0, 0.0)
    previous = 0.0
    for _ in range(30):
        current = smooth(current, (100.0, 100.0), 1.0 / 60.0)
        assert current[0] > previous
        assert current[0] < 100.0
        previous = current[0]


# ------------------------------------------------------------------ 边界


@pytest.mark.parametrize(
    "pos, expected",
    [
        ((-5.0, -5.0), OUTDOOR_TARGET_MIN),
        ((100.0, 100.0), OUTDOOR_TARGET_MAX),
        ((40.0, 30.0), (40.0, 30.0)),
    ],
)
def test_clamp_target(pos, expected):
    assert clamp_target(pos) == expected


# ------------------------------------------------------------------ 像素对齐


def test_align_pixel_rounds_to_1_24():
    assert align_pixel(0.0) == 0.0
    assert align_pixel(0.019) == 0.0
    assert align_pixel(0.021) == pytest.approx(PIXEL)
    assert align_pixel(1.0) == 1.0


def test_align_pixel_is_within_half_a_pixel():
    rng = random.Random(1234)
    for _ in range(200):
        value = rng.uniform(-50.0, 50.0)
        aligned = align_pixel(value)
        assert aligned * 24 == pytest.approx(round(aligned * 24))
        assert abs(aligned - value) <= PIXEL / 2.0 + 1e-12


# ------------------------------------------------------------------ 相机位置


def test_camera_position_applies_offset():
    assert camera_position((10.0, 20.0)) == pytest.approx((10.0, 20.0 - 22.98, 19.28))


def test_camera_position_supports_height():
    x, y, z = camera_position((0.0, 0.0), z=5.0)
    assert (x, y, z) == pytest.approx((0.0, -22.98, 24.28))


# ------------------------------------------------------------------ CameraRig


def test_rig_default_target_is_spawn():
    assert CameraRig().target == (40.0, 5.0)


def test_rig_set_outdoor_clamps_target():
    rig = CameraRig()
    rig.set_outdoor((0.0, 0.0))
    assert rig.target == OUTDOOR_TARGET_MIN


def test_rig_camera_xyz_is_pixel_aligned():
    rig = CameraRig(target=(10.13, 8.99))
    x, y, z = rig.camera_xyz()
    assert x * 24 == pytest.approx(round(x * 24))
    assert y * 24 == pytest.approx(round(y * 24))
    assert z == pytest.approx(19.28)


def test_rig_outdoor_follow_reaches_corner_within_bounds():
    """C-ST-05：玩家走到地图角落，target 不越界。"""
    rig = CameraRig()
    for _ in range(600):
        rig.update((0.0, 0.0), 1.0 / 60.0)
    assert rig.target == pytest.approx(OUTDOOR_TARGET_MIN)

    for _ in range(600):
        rig.update((80.0, 60.0), 1.0 / 60.0)
    assert rig.target == pytest.approx(OUTDOOR_TARGET_MAX)

    # 相机位置 = target + (0, -22.98, 19.28)，再做像素对齐
    wx, wy, _wz = camera_position(rig.target)
    x, y, _z = rig.camera_xyz()
    assert (x, y) == pytest.approx((align_pixel(wx), align_pixel(wy)))


def test_rig_outdoor_keeps_player_inside_deadzone():
    rig = CameraRig(target=(40.0, 30.0))
    for _ in range(600):
        rig.update((60.0, 30.0), 1.0 / 60.0)
    # 稳定后玩家应停在死区边缘（X 方向 ±2.0 米）
    assert rig.target[0] == pytest.approx(60.0 - 2.0, abs=1e-6)
    assert rig.target[1] == pytest.approx(30.0, abs=1e-9)


def test_rig_interior_is_fixed_and_ignores_player():
    """C-ST-05：室内房间小于视野，target 固定在房间中心，不跟随。"""
    rig = CameraRig()
    rig.set_interior((248.0, 5.0))
    before = rig.target
    for _ in range(120):
        rig.update((300.0, 5.0), 1.0 / 60.0)
    assert rig.target == before == (248.0, 5.0)

    wx, wy, _wz = camera_position(rig.target)
    x, y, _z = rig.camera_xyz()
    assert (x, y) == pytest.approx((align_pixel(wx), align_pixel(wy)))


def test_rig_set_outdoor_resumes_following_after_interior():
    rig = CameraRig()
    rig.set_interior((248.0, 5.0))
    rig.set_outdoor((40.0, 30.0))
    assert rig.interior is False
    assert rig.target == (40.0, 30.0)
