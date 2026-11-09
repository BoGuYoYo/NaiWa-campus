"""任务 C6：固定 40° 俯角的正交跟随相机。

本模块的数学部分（CameraRig）不依赖 Panda3D，可直接在 tests/world/test_camera.py 中验证；
CameraController 只是把结果套用到 Panda3D 相机节点上。

规格（任务分工手册 3.0 · C6）：
- 正交镜头，film = (20.0, 11.25)，每米 24 像素
- camera.hpr 固定 (0, -40, 0)，禁止任何代码修改
- camera.pos = target + (0, -22.98, 19.28)
- 死区：玩家相对 target 的偏移在 ±2.0 米（X）、±1.5 米（Y）内时 target 不动
- 平滑：target += (desired - target) * (1 - exp(-8.0 * dt))
- 边界：室外 target.x ∈ [10, 70]，target.y ∈ [8.75, 51.25]
        室内房间小于视野，target 固定在房间中心，不跟随
- 像素对齐：camera.pos 的 x、y 四舍五入到 1/24 米
"""

from __future__ import annotations

import math

FILM_WIDTH = 20.0
FILM_HEIGHT = 11.25  # 480 / 20 = 270 / 11.25 = 24 像素每米
PIXEL = 1.0 / 24.0

CAMERA_HPR = (0.0, -40.0, 0.0)
CAMERA_OFFSET = (0.0, -22.98, 19.28)  # (0, -30*cos40°, +30*sin40°)

DEADZONE_X = 2.0
DEADZONE_Y = 1.5
SMOOTH_LAMBDA = 8.0

OUTDOOR_TARGET_MIN = (10.0, 8.75)  # 半视宽 10 米；半视深 11.25/2/sin40° ≈ 8.75 米
OUTDOOR_TARGET_MAX = (70.0, 51.25)

DEFAULT_TARGET = (40.0, 5.0)


def deadzone_desired(target, player, dzx: float = DEADZONE_X, dzy: float = DEADZONE_Y):
    """返回死区规则下的期望 target：玩家在死区内时 target 不动。"""
    tx, ty = target
    px, py = player
    if px > tx + dzx:
        tx = px - dzx
    elif px < tx - dzx:
        tx = px + dzx
    if py > ty + dzy:
        ty = py - dzy
    elif py < ty - dzy:
        ty = py + dzy
    return (tx, ty)


def smooth(current, desired, dt: float, lam: float = SMOOTH_LAMBDA):
    """帧率无关的指数平滑：target += (desired - target) * (1 - exp(-lam * dt))。"""
    k = 1.0 - math.exp(-lam * max(dt, 0.0))
    return (
        current[0] + (desired[0] - current[0]) * k,
        current[1] + (desired[1] - current[1]) * k,
    )


def clamp_target(pos, low=OUTDOOR_TARGET_MIN, high=OUTDOOR_TARGET_MAX):
    """把室外 target 钳制在边界内。"""
    return (
        min(max(pos[0], low[0]), high[0]),
        min(max(pos[1], low[1]), high[1]),
    )


def align_pixel(value: float, pixel: float = PIXEL) -> float:
    """把坐标四舍五入到 1/24 米。"""
    return round(value / pixel) * pixel


def camera_position(target, z: float = 0.0):
    """由 target 求未对齐的相机位置。"""
    return (
        target[0] + CAMERA_OFFSET[0],
        target[1] + CAMERA_OFFSET[1],
        z + CAMERA_OFFSET[2],
    )


class CameraRig:
    """纯数学的相机跟随：死区 -> 平滑 -> 边界 -> 像素对齐。"""

    def __init__(self, target=DEFAULT_TARGET, interior: bool = False):
        self.target = (float(target[0]), float(target[1]))
        self.interior = bool(interior)

    # ------------------------------------------------------------------ 场景
    def set_outdoor(self, target=None) -> None:
        self.interior = False
        if target is not None:
            self.target = clamp_target((float(target[0]), float(target[1])))

    def set_interior(self, world_center) -> None:
        """室内视野固定在房间中心（世界坐标），不跟随。"""
        self.interior = True
        self.target = (float(world_center[0]), float(world_center[1]))

    # ------------------------------------------------------------------ 推进
    def update(self, player_xy, dt: float):
        """推进一帧并返回像素对齐后的相机 (x, y, z)。"""
        if self.interior:
            return self.camera_xyz()
        desired = deadzone_desired(self.target, player_xy)
        self.target = clamp_target(smooth(self.target, desired, dt))
        return self.camera_xyz()

    def camera_xyz(self):
        x, y, z = camera_position(self.target)
        return (align_pixel(x), align_pixel(y), z)


class CameraController:
    """把 CameraRig 的结果套用到 Panda3D 相机节点；朝向永远固定，禁止旋转与缩放。"""

    def __init__(self, camera_node_path, rig: CameraRig | None = None):
        self.camera = camera_node_path
        self.rig = rig if rig is not None else CameraRig()
        self._setup_ortho_lens()
        self.apply()

    def _setup_ortho_lens(self) -> None:
        from panda3d.core import OrthographicLens

        lens = OrthographicLens()
        lens.setFilmSize(FILM_WIDTH, FILM_HEIGHT)
        lens.setNearFar(1.0, 300.0)
        self.camera.node().setLens(lens)

    def apply(self) -> None:
        x, y, z = self.rig.camera_xyz()
        self.camera.setPos(x, y, z)
        self.camera.setHpr(*CAMERA_HPR)

    def update(self, player_xy, dt: float) -> None:
        self.rig.update(player_xy, dt)
        self.apply()
