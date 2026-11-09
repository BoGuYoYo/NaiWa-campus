"""任务 C3：室内房间（白模）与入口地垫。

每个室内都是 16 × 10 米，本地 (0,0) 位于西南角，世界坐标 = 房间原点 + 本地坐标。
房间在远离室外地图的独立坐标区（原点见 map.json），因此碰撞矩形会整体平移到世界坐标。

规格（任务分工手册 3.0 · C3）：
- 入口地垫位于本地 (8, 0.6)，半径 0.8：玩家走入后自动返回室外（不需要按 E）
- 返回位置 = 门外触发点再向外 1 米处，朝向背离建筑
- 进入室内后出生在本地 (8, 1.6)，朝向 n
- 退出后有 1 秒冷却，冷却期间不会再次触发门
"""

from __future__ import annotations

from game.world.campus_scene import (
    BUILDING_COLOR,
    make_box,
    make_circle_lines,
    make_ground,
)
from game.world.collision import Rect

INTERIOR_SCENE_ID = "InteriorScene"

FLOOR_COLOR = (0.64, 0.62, 0.57, 1.0)
FURNITURE_COLOR = (0.50, 0.45, 0.40, 1.0)
MAT_COLOR = (0.90, 0.30, 0.25, 1.0)
NPC_MARK_COLOR = (0.25, 0.60, 0.90, 1.0)
WALL_HEIGHT = 3.0
FURNITURE_HEIGHT = 1.0
EXIT_COOLDOWN = 1.0

Z_FLOOR = 0.0


class InteriorScene:
    """一栋建筑的室内房间；scene_id = "InteriorScene"，building_id 为目标建筑。"""

    scene_id = INTERIOR_SCENE_ID

    def __init__(self, map_data, building_id: str, parent, *, dev: bool = False):
        self.map_data = map_data
        self.building_id = building_id
        self.interior = map_data.interior(building_id)
        self.origin = self.interior.origin
        self.size = self.interior.size
        self.dev = dev
        self.root = parent.attachNewNode(f"InteriorScene_{building_id}")
        self._cooldown = 0.0
        self._build()

    # ------------------------------------------------------------------ 构建
    def _build(self) -> None:
        ox, oy = self.origin
        w, h = self.size
        make_ground(self.root, ox, oy, ox + w, oy + h, Z_FLOOR, FLOOR_COLOR)

        for r in self.map_data.interior_walls(self.building_id):
            make_box(self.root, ox + r.x0, oy + r.y0, ox + r.x1, oy + r.y1, 0.0, WALL_HEIGHT, BUILDING_COLOR)

        for furn in self.interior.furniture:
            r = furn.rect
            make_box(self.root, ox + r.x0, oy + r.y0, ox + r.x1, oy + r.y1, 0.0, FURNITURE_HEIGHT, FURNITURE_COLOR)

        mx, my, mr = self.mat_world()
        make_circle_lines(self.root, mx, my, mr, 0.05, MAT_COLOR, thickness=3.0)

        for mark in self.interior.npc_marks:
            make_circle_lines(self.root, ox + mark.x, oy + mark.y, 0.4, 0.05, NPC_MARK_COLOR, segments=16)

        self.root.flattenStrong()

    # ------------------------------------------------------------------ 查询
    def colliders_local(self) -> tuple[Rect, ...]:
        return self.map_data.colliders_for(self.building_id)

    def colliders_world(self) -> tuple[Rect, ...]:
        ox, oy = self.origin
        return tuple(
            Rect(r.x0 + ox, r.y0 + oy, r.x1 + ox, r.y1 + oy) for r in self.colliders_local()
        )

    def bounds_world(self) -> Rect:
        ox, oy = self.origin
        w, h = self.size
        return Rect(ox, oy, ox + w, oy + h)

    def entry_world(self) -> tuple[float, float, str]:
        """出生点（世界坐标 + 朝向）。"""
        lx, ly, facing = self.map_data.interior_entry(self.building_id)
        return (self.origin[0] + lx, self.origin[1] + ly, facing)

    def mat_world(self) -> tuple[float, float, float]:
        mx, my, mr = self.map_data.entry_mat(self.building_id)
        return (self.origin[0] + mx, self.origin[1] + my, mr)

    def exit_world(self) -> tuple[float, float, str]:
        """回到室外时的位置（世界坐标 + 朝向）。"""
        return self.map_data.exit_point(self.building_id)

    # ------------------------------------------------------------------ 地垫
    def update_mat(self, x: float, y: float, dt: float) -> bool:
        """玩家脚点在 (x, y)；踩到地垫且不在冷却中时返回 True（应返回室外）。"""
        if self._cooldown > 0.0:
            self._cooldown = max(0.0, self._cooldown - max(dt, 0.0))
            return False
        mx, my, mr = self.mat_world()
        if (x - mx) ** 2 + (y - my) ** 2 <= mr * mr:
            self._cooldown = EXIT_COOLDOWN
            return True
        return False

    def reset_cooldown(self) -> None:
        self._cooldown = 0.0

    def destroy(self) -> None:
        self.root.removeNode()
