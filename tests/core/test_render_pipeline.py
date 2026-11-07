"""A 的 core 层单元测试：480×270 缩放规则与像素网格对齐（纯函数，无需 panda3d）。"""

from __future__ import annotations

import pytest

from game import config
from game.core.render_pipeline import (
    CHARACTER_CARD_PITCH,
    compute_viewport,
    snap_to_pixel_grid,
)


def test_internal_canvas_constants():
    assert config.INTERNAL_WIDTH == 480
    assert config.INTERNAL_HEIGHT == 270
    assert config.PIXELS_PER_METER == 24
    assert config.FILM_WIDTH_METERS == 20.0
    assert config.FILM_HEIGHT_METERS == 11.25


@pytest.mark.parametrize("size", [(1920, 1080), (3840, 2160), (960, 540)])
def test_integer_scaling_when_close_enough(size):
    viewport = compute_viewport(*size)
    assert viewport.integer is True
    assert viewport.scale == pytest.approx(size[0] / config.INTERNAL_WIDTH)
    assert viewport.offset_x == pytest.approx(0.0)
    assert viewport.offset_y == pytest.approx(0.0)


def test_1080p_is_exactly_4x():
    viewport = compute_viewport(1920, 1080)
    assert viewport.scale == 4.0
    assert viewport.width == 1920
    assert viewport.height == 1080


def test_720p_falls_back_to_fractional_fit():
    # k=2 时 480*2=960 < 0.85*1280=1088，必须改为按比例拉伸
    viewport = compute_viewport(1280, 720)
    assert viewport.integer is False
    assert viewport.scale == pytest.approx(1280 / 480)
    assert viewport.scale == pytest.approx(2.6667, rel=1e-4)


def test_letterbox_offsets_are_centred():
    viewport = compute_viewport(1010, 720)
    assert viewport.offset_x == pytest.approx((1010 - 480 * viewport.scale) / 2)
    assert viewport.offset_y == pytest.approx((720 - 270 * viewport.scale) / 2)
    assert viewport.height <= 720 + 1e-6


def test_tiny_window_never_goes_below_fit():
    viewport = compute_viewport(320, 180)
    assert viewport.scale == pytest.approx(min(320 / 480, 180 / 270))
    assert viewport.width <= 320 + 1e-6
    assert viewport.height <= 180 + 1e-6


def test_odd_sizes_are_safe():
    viewport = compute_viewport(0, 0)
    assert viewport.scale > 0
    viewport = compute_viewport(481, 271)
    assert viewport.scale > 0


def test_snap_to_pixel_grid():
    grid = 1.0 / 24.0
    assert snap_to_pixel_grid(40.0) == pytest.approx(40.0)
    assert snap_to_pixel_grid(40.01) == pytest.approx(40.0)
    assert snap_to_pixel_grid(40.0 + grid * 0.6) == pytest.approx(40.0 + grid)
    assert snap_to_pixel_grid(-3.02) == pytest.approx(-3.0)


def test_character_card_pitch_matches_camera_tilt():
    # 卡片法线必须与视方向反向，因此 P 轴直接取相机俯角（实测正角会让卡片完全侧对相机）
    assert CHARACTER_CARD_PITCH == config.CAMERA_TILT_DEGREES == -40.0
