"""任务 C5 独立测试：输入映射、8 方向朝向、速度积分与脚步计时的纯逻辑。"""

from __future__ import annotations

import math

import pytest

from game.world.input_map import (
    ACCEL,
    DECEL,
    DT_MAX,
    FACING_SPEED_EPS,
    FOOTSTEP_RUN_INTERVAL,
    FOOTSTEP_WALK_INTERVAL,
    RUN_SPEED,
    SECTOR_FACINGS,
    WALK_SPEED,
    FootstepTimer,
    approach_speed,
    clamp_dt,
    facing_for,
    input_vector,
    step_position,
    target_speed,
)


# ------------------------------------------------------------------ input_vector

def test_input_vector_single_keys():
    assert input_vector(["w"]) == (0.0, 1.0)
    assert input_vector(["s"]) == (0.0, -1.0)
    assert input_vector(["a"]) == (-1.0, 0.0)
    assert input_vector(["d"]) == (1.0, 0.0)


def test_input_vector_arrow_keys_match_wasd():
    assert input_vector(["up"]) == input_vector(["w"])
    assert input_vector(["down"]) == input_vector(["s"])
    assert input_vector(["left"]) == input_vector(["a"])
    assert input_vector(["right"]) == input_vector(["d"])


def test_input_vector_opposite_keys_cancel():
    assert input_vector(["w", "s"]) == (0.0, 0.0)
    assert input_vector(["a", "d"]) == (0.0, 0.0)


def test_input_vector_diagonal_is_normalised():
    dx, dy = input_vector(["w", "d"])
    assert dx == pytest.approx(math.sqrt(0.5))
    assert dy == pytest.approx(math.sqrt(0.5))
    assert math.hypot(dx, dy) == pytest.approx(1.0)


def test_input_vector_ignores_unknown_and_case():
    assert input_vector(["space", "f1"]) == (0.0, 0.0)
    assert input_vector(["W"]) == (0.0, 1.0)


# -------------------------------------------------------------------- facing_for

@pytest.mark.parametrize(
    "dx,dy,expected",
    [
        (1.0, 0.0, "e"),
        (1.0, 1.0, "ne"),
        (0.0, 1.0, "n"),
        (-1.0, 1.0, "nw"),
        (-1.0, 0.0, "w"),
        (-1.0, -1.0, "sw"),
        (0.0, -1.0, "s"),
        (1.0, -1.0, "se"),
    ],
)
def test_facing_for_eight_directions(dx, dy, expected):
    assert facing_for(dx, dy) == expected


def test_facing_for_rounds_to_nearest_sector():
    # 略微偏离正东仍归入 e
    assert facing_for(1.0, 0.2) == "e"
    # 超过 22.5° 归入 ne
    assert facing_for(1.0, 0.6) == "ne"


def test_facing_for_zero_speed_returns_none():
    assert facing_for(0.0, 0.0) is None
    assert facing_for(FACING_SPEED_EPS * 0.5, 0.0) is None
    assert facing_for(0.0, FACING_SPEED_EPS * 0.5) is None


def test_sector_facings_order():
    assert SECTOR_FACINGS == ("e", "ne", "n", "nw", "w", "sw", "s", "se")


# ------------------------------------------------------------------ speed & step

def test_target_speed_switches_between_walk_and_run():
    assert target_speed(False) == WALK_SPEED
    assert target_speed(True) == RUN_SPEED


def test_approach_speed_accelerates_up_to_target():
    # 加速：ACCEL * dt
    assert approach_speed(0.0, WALK_SPEED, 0.1) == pytest.approx(ACCEL * 0.1)


def test_approach_speed_decelerates_faster_than_accelerates():
    assert approach_speed(RUN_SPEED, 0.0, 0.1) == pytest.approx(RUN_SPEED - DECEL * 0.1)


def test_approach_speed_snaps_when_close():
    assert approach_speed(WALK_SPEED - 0.01, WALK_SPEED, 0.1) == WALK_SPEED
    assert approach_speed(0.01, 0.0, 0.1) == 0.0


def test_clamp_dt_limits_frame_time():
    assert clamp_dt(0.016) == pytest.approx(0.016)
    assert clamp_dt(0.5) == DT_MAX
    assert clamp_dt(-1.0) == 0.0


def test_step_position_applies_orientation_and_speed():
    assert step_position(0.0, 0.0, 1.0, 0.0, WALK_SPEED, 0.5) == pytest.approx((2.0, 0.0))
    assert step_position(1.0, 2.0, 0.0, 1.0, RUN_SPEED, 0.25) == pytest.approx((1.0, 3.5))


# ----------------------------------------------------------------- FootstepTimer

def test_footstep_timer_fires_on_walk_interval():
    timer = FootstepTimer()
    assert timer.tick(0.2, moving=True) is False
    assert timer.tick(0.2, moving=True) is True
    assert timer.elapsed == pytest.approx(0.4 - FOOTSTEP_WALK_INTERVAL)


def test_footstep_timer_run_interval_is_shorter():
    timer = FootstepTimer()
    assert timer.tick(0.2, moving=True, running=True) is False
    assert timer.tick(0.1, moving=True, running=True) is True
    assert timer.elapsed == pytest.approx(0.3 - FOOTSTEP_RUN_INTERVAL)


def test_footstep_timer_resets_when_standing_still():
    timer = FootstepTimer()
    timer.tick(0.3, moving=True)
    assert timer.elapsed > 0.0
    assert timer.tick(0.1, moving=False) is False
    assert timer.elapsed == 0.0


def test_footstep_timer_reset_method():
    timer = FootstepTimer()
    timer.tick(0.3, moving=True)
    timer.reset()
    assert timer.elapsed == 0.0
