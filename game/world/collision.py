"""任务 C2：纯 Python 轴分离扫掠碰撞。

不使用 Panda3D 物理引擎，以便在无界面测试（tests/world/test_collision.py）中直接复用。
矩形统一用 Rect(x0, y0, x1, y1) 表示，坐标为世界坐标或房间本地坐标。
"""

from __future__ import annotations

import math
from typing import NamedTuple, Sequence

PLAYER_HALF = 0.35  # 玩家碰撞体 0.7 x 0.7 米（半宽 0.35），以脚点为中心
EPS = 1e-4


class Rect(NamedTuple):
    x0: float
    y0: float
    x1: float
    y1: float


def make_rect(x0: float, y0: float, x1: float, y1: float) -> Rect:
    """构造矩形，自动把两个角点排序为 (x0<=x1, y0<=y1)。"""
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    return Rect(float(x0), float(y0), float(x1), float(y1))


def overlap(pos, half: float, r: Rect) -> bool:
    """以 pos 为脚点的 half x half 方框是否与矩形 r 相交。"""
    return (
        pos.x + half > r.x0
        and pos.x - half < r.x1
        and pos.y + half > r.y0
        and pos.y - half < r.y1
    )


def move_and_collide(pos, delta, rects: Sequence[Rect], half: float = PLAYER_HALF):
    """轴分离扫掠：先 X 后 Y，保证贴墙滑动。

    pos / delta 需要带有可读写的 x、y 属性（WorldPos 满足要求）；pos 被就地修改并返回。

    起始位置**已经压着**的矩形不参与本帧解算：这种状态来自旧存档、传送或调试跳转，
    按「朝哪边走就贴哪条边」解算只会把人瞬间弹到墙的另一侧（表现就是「往某个方向走
    被推回原处」）。忽略这些矩形，人可以向任意方向直接走出来；离开后它们恢复阻挡。
    """
    steps = max(1, math.ceil(max(abs(delta.x), abs(delta.y)) / (half * 0.5)))
    step_x = delta.x / steps
    step_y = delta.y / steps
    inside = {id(r) for r in rects if overlap(pos, half, r)}
    active = [r for r in rects if id(r) not in inside]
    for _ in range(steps):
        pos.x += step_x
        for r in active:
            if overlap(pos, half, r):
                pos.x = r.x0 - half - EPS if delta.x > 0 else r.x1 + half + EPS
        pos.y += step_y
        for r in active:
            if overlap(pos, half, r):
                pos.y = r.y0 - half - EPS if delta.y > 0 else r.y1 + half + EPS
    return pos


def clamp_to_bounds(pos, bounds: Rect, half: float = PLAYER_HALF):
    """把脚点钳制在可通行区域内（兜底，正常由四周围墙保证）。"""
    pos.x = min(max(pos.x, bounds.x0 + half), bounds.x1 - half)
    pos.y = min(max(pos.y, bounds.y0 + half), bounds.y1 - half)
    return pos
