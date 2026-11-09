"""任务 C5 的纯逻辑部分：输入映射、8 方向朝向、速度积分与脚步计时。

本模块不依赖 Panda3D，tests/world/test_input_map.py 直接覆盖。
"""

from __future__ import annotations

import math

# 键位 -> 该轴的分量：W/↑ = +Y，S/↓ = -Y，A/← = -X，D/→ = +X
KEY_AXES: dict[str, tuple[float, float]] = {
    "w": (0.0, 1.0),
    "up": (0.0, 1.0),
    "s": (0.0, -1.0),
    "down": (0.0, -1.0),
    "a": (-1.0, 0.0),
    "left": (-1.0, 0.0),
    "d": (1.0, 0.0),
    "right": (1.0, 0.0),
}

WALK_SPEED = 4.0
RUN_SPEED = 6.0
ACCEL = 30.0
DECEL = 40.0
DT_MAX = 0.0333
FACING_SPEED_EPS = 0.1

FOOTSTEP_WALK_INTERVAL = 0.35
FOOTSTEP_RUN_INTERVAL = 0.25

# 索引 = round(atan2(dy, dx) / 45°) mod 8
SECTOR_FACINGS = ("e", "ne", "n", "nw", "w", "sw", "s", "se")


def input_vector(pressed) -> tuple[float, float]:
    """把当前按下的按键集合转换为归一化的移动方向；相反方向同时按下时该轴为 0。"""
    x = 0.0
    y = 0.0
    for key in pressed:
        axes = KEY_AXES.get(str(key).lower())
        if axes is None:
            continue
        x += axes[0]
        y += axes[1]
    length = math.hypot(x, y)
    if length == 0.0:
        return (0.0, 0.0)
    return (x / length, y / length)


def facing_for(dx: float, dy: float) -> str | None:
    """8 方向朝向；速度为 0 时返回 None（调用方保持上一次朝向）。"""
    if math.hypot(dx, dy) <= FACING_SPEED_EPS:
        return None
    index = int(round(math.atan2(dy, dx) / (math.pi / 4.0))) % 8
    return SECTOR_FACINGS[index]


def target_speed(running: bool) -> float:
    return RUN_SPEED if running else WALK_SPEED


def approach_speed(current: float, target: float, dt: float) -> float:
    """按加速度 30 / 减速度 40 米/秒² 把当前速度推向目标速度。"""
    rate = ACCEL if abs(target) >= abs(current) else DECEL
    step = rate * dt
    if abs(target - current) <= step:
        return target
    return current + math.copysign(step, target - current)


def clamp_dt(dt: float) -> float:
    """帧时间上限 0.0333 秒；由调用方在积分前使用。"""
    return min(max(dt, 0.0), DT_MAX)


def step_position(x: float, y: float, dx: float, dy: float, speed: float, dt: float):
    """由朝向与速度得到本帧位移。"""
    return (x + dx * speed * dt, y + dy * speed * dt)


class FootstepTimer:
    """移动时每 0.35 秒（快走 0.25 秒）触发一次脚步声；停下即重置。"""

    def __init__(self) -> None:
        self._elapsed = 0.0

    @property
    def elapsed(self) -> float:
        return self._elapsed

    def reset(self) -> None:
        self._elapsed = 0.0

    def tick(self, dt: float, moving: bool, running: bool = False) -> bool:
        if not moving:
            self._elapsed = 0.0
            return False
        self._elapsed += max(dt, 0.0)
        interval = FOOTSTEP_RUN_INTERVAL if running else FOOTSTEP_WALK_INTERVAL
        if self._elapsed >= interval:
            self._elapsed -= interval
            return True
        return False
