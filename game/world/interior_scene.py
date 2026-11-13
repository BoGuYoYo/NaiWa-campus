"""任务 C3：室内房间与入口地垫。

每个室内都是 16 × 10 米，本地 (0,0) 位于西南角，世界坐标 = 房间原点 + 本地坐标。
房间在远离室外地图的独立坐标区（原点见 map.json），因此碰撞矩形会整体平移到世界坐标。

规格（任务分工手册 3.0 · C3）：
- 入口地垫位于本地 (8, 0.6)，半径 0.8：玩家走入后自动返回室外（不需要按 E）
- 返回位置 = 门外触发点再向外 1.8 米处，朝向背离建筑
- 进入室内后出生在本地 (8, 1.6)，朝向 n
- 退出后有 1 秒冷却，冷却期间不会再次触发门

材质：地板 / 墙面由用户提供的建筑材质（`tools/import_interior_art.py`）贴上去；
没给贴图时退回纯色白模，保证缺资源也能进房间。
"""

from __future__ import annotations

import math

from game import config
from game.world.campus_scene import (
    make_box,
    make_circle_lines,
    make_ground,
    make_prop_card,
    make_wall_panel,
)
from game.world.collision import Rect

INTERIOR_SCENE_ID = "InteriorScene"

FLOOR_COLOR = (0.64, 0.62, 0.57, 1.0)
FURNITURE_COLOR = (0.50, 0.45, 0.40, 1.0)
MAT_COLOR = (0.90, 0.30, 0.25, 1.0)
NPC_MARK_COLOR = (0.25, 0.60, 0.90, 1.0)
WALL_HEIGHT = 3.0
#: 南墙（正对镜头的一侧）只留一道矮墙：镜头在北侧俯视 40°，
#: 3 米高的南墙会把房间南侧约 1.9 米地面整块挡住（入口地垫整个埋进墙里）。
#: 剖切矮墙是 2.5D 房间的常规做法，也让贴在墙上的材质只出现在"看得见的那面"。
SOUTH_WALL_HEIGHT = 0.35
#: 墙体的颜色（剖切面）：南墙矮墙、其余墙的墙顶与外墙
WALL_COLOR = (0.36, 0.37, 0.42, 1.0)
#: 室内墙面与墙体之间留的偏移，避免共面闪烁
WALL_PANEL_INSET = 0.02
FURNITURE_HEIGHT = 1.0
EXIT_COOLDOWN = 1.0
#: 家具正面卡按镜头俯角后倒的"倒伏系数"：顶端比底边后退 height × CARD_LEAN_SIN
CARD_LEAN_SIN = abs(math.sin(math.radians(config.CAMERA_TILT_DEGREES)))
#: 地板贴图一次平铺覆盖的米数（96 px / 4 m = 24 px/m，与游戏像素密度一致）
FLOOR_TILE_M = 4.0
#: 墙面贴图一次平铺覆盖的米数；实际由 manifest 的 tile_m 覆盖
WALL_TILE_M = 3.0

Z_FLOOR = 0.0


def wall_side(rect: Rect, size: tuple[float, float], thickness: float) -> str:
    """判断这面墙在房间的哪一侧（n / s / e / w）。

    墙体矩形是"厚 0.5 米的长条"，所以先看哪个方向的跨度只有墙厚。
    """
    width, depth = rect.x1 - rect.x0, rect.y1 - rect.y0
    if width <= thickness + 1e-6:
        return "w" if rect.x0 <= 1e-6 else "e"
    if depth <= thickness + 1e-6:
        return "s" if rect.y0 <= 1e-6 else "n"
    return "n" if depth < width else "e"


class InteriorScene:
    """一栋建筑的室内房间；scene_id = "InteriorScene"，building_id 为目标建筑。"""

    scene_id = INTERIOR_SCENE_ID

    def __init__(
        self,
        map_data,
        building_id: str,
        parent,
        *,
        dev: bool = False,
        floor_texture=None,
        wall_texture=None,
        floor_tile_m: float = FLOOR_TILE_M,
        wall_tile_m: float = WALL_TILE_M,
        furniture_color=None,
        furniture_art=None,
    ):
        self.map_data = map_data
        self.building_id = building_id
        self.interior = map_data.interior(building_id)
        self.origin = self.interior.origin
        self.size = self.interior.size
        self.dev = dev
        self.floor_texture = floor_texture
        self.wall_texture = wall_texture
        self.floor_tile_m = floor_tile_m
        self.wall_tile_m = wall_tile_m
        self.furniture_color = furniture_color or FURNITURE_COLOR
        #: {furniture_id: (texture, 高度米)}；没给到的家具仍画成盒子
        self.furniture_art = furniture_art or {}
        self.root = parent.attachNewNode(f"InteriorScene_{building_id}")
        self._cooldown = 0.0
        self._build()

    # ------------------------------------------------------------------ 构建
    def _build(self) -> None:
        ox, oy = self.origin
        w, h = self.size
        make_ground(self.root, ox, oy, ox + w, oy + h, Z_FLOOR, FLOOR_COLOR,
                    texture=self.floor_texture, tile_m=self.floor_tile_m)

        thickness = self.map_data.interior_wall_thickness
        #: 北墙内侧（世界坐标）。家具正面卡按 −40° 后倒 height×sin40°，
        #: 贴墙摆的家具顶端会扎进墙里被吃掉（打饭窗口只剩台座），
        #: 所以底边要往前让出倒伏量——见下面的 base_y。
        back_face = oy + h
        for r in self.map_data.interior_walls(self.building_id):
            side = wall_side(r, (w, h), thickness)
            height = SOUTH_WALL_HEIGHT if side == "s" else WALL_HEIGHT
            make_box(self.root, ox + r.x0, oy + r.y0, ox + r.x1, oy + r.y1, 0.0, height,
                     WALL_COLOR)
            if side != "s" and self.wall_texture is not None:
                px0, py0, px1, py1 = self._panel_edge(r, side, w, h)
                make_wall_panel(self.root, ox + px0, oy + py0, ox + px1, oy + py1,
                                0.0, height, self.wall_texture, self.wall_tile_m)
            if side == "n":
                back_face = min(back_face, oy + r.y0 - WALL_PANEL_INSET)

        for furn in self.interior.furniture:
            r = furn.rect
            art = self.furniture_art.get(furn.id)
            if art is not None:
                texture, height = art
                make_prop_card(
                    self.root,
                    Rect(ox + r.x0, oy + r.y0, ox + r.x1, oy + r.y1),
                    texture,
                    height,
                    name=f"furn_{furn.id}",
                    width=r.x1 - r.x0,
                    tile=True,
                    base_y=min(oy + r.y0, back_face - height * CARD_LEAN_SIN),
                )
            else:
                make_box(self.root, ox + r.x0, oy + r.y0, ox + r.x1, oy + r.y1, 0.0,
                         FURNITURE_HEIGHT, self.furniture_color)

    def _panel_edge(self, rect: Rect, side: str, w: float, h: float) -> tuple[float, float, float, float]:
        """墙面卡片的底边（房间本地坐标，往房里缩进一点避免与墙体共面闪烁）。"""
        inset = WALL_PANEL_INSET
        if side == "n":
            return (0.0, rect.y0 - inset, w, rect.y0 - inset)
        if side == "s":
            return (0.0, rect.y1 + inset, w, rect.y1 + inset)
        if side == "w":
            return (rect.x1 + inset, 0.0, rect.x1 + inset, h)
        return (rect.x0 - inset, 0.0, rect.x0 - inset, h)

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
