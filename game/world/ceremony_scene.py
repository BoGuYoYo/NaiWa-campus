"""开学典礼独立礼堂场景（纯代码占位几何 + 碰撞 + 角色站位 + 出口地垫）。

坐标放在独立区间 (400, 0)，完全避开主校园与 5 栋室内房间（x=200..296）。
本模块只处理空间与白模几何，不读写任何游戏属性字段。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from game import config
from game.world.campus_scene import make_box, make_circle_lines, make_ground, make_wall_panel
from game.world.collision import Rect
from game.world.map_data import Interactable
from game.world.trigger_zone import Candidate

CEREMONY_SCENE_ID = "OpeningCeremonyScene"
CEREMONY_LOCATION_ID = "loc_auditorium"

# 礼堂放在独立坐标区，避免与室外地图和 5 栋室内房间重叠
ORIGIN: tuple[float, float] = (400.0, 0.0)
SIZE: tuple[float, float] = (18.0, 12.0)
WALL_THICKNESS = 0.5

# 配色（第一版占位符几何：清晰区分地板、红毯、舞台、演讲台、校长与出口）
FLOOR_COLOR = (0.60, 0.53, 0.44, 1.0)
CARPET_COLOR = (0.64, 0.16, 0.18, 1.0)
CARPET_TRIM_COLOR = (0.86, 0.72, 0.34, 1.0)
WALL_COLOR = (0.34, 0.36, 0.43, 1.0)
CURTAIN_COLOR = (0.50, 0.12, 0.16, 1.0)
BANNER_COLOR = (0.88, 0.72, 0.30, 1.0)
STAGE_COLOR = (0.42, 0.25, 0.18, 1.0)
STAGE_TRIM_COLOR = (0.76, 0.62, 0.32, 1.0)
BENCH_COLOR = (0.46, 0.33, 0.24, 1.0)
PODIUM_WOOD_COLOR = (0.33, 0.19, 0.12, 1.0)
PODIUM_TOP_COLOR = (0.48, 0.30, 0.20, 1.0)
MIC_COLOR = (0.16, 0.18, 0.22, 1.0)
PRINCIPAL_SUIT_COLOR = (0.18, 0.24, 0.38, 1.0)
PRINCIPAL_SHIRT_COLOR = (0.92, 0.92, 0.94, 1.0)
PRINCIPAL_TIE_COLOR = (0.76, 0.18, 0.20, 1.0)
PRINCIPAL_SKIN_COLOR = (0.93, 0.78, 0.66, 1.0)
PRINCIPAL_HAIR_COLOR = (0.68, 0.70, 0.74, 1.0)
EXIT_MAT_FILL = (0.78, 0.30, 0.24, 1.0)
EXIT_MAT_RING = (0.94, 0.36, 0.28, 1.0)
NPC_RING_COLOR = (0.28, 0.62, 0.92, 1.0)

WALL_HEIGHT_SIDE = 2.6
WALL_HEIGHT_NORTH = 2.4
WALL_HEIGHT_SOUTH = 0.35
STAGE_HEIGHT = 0.55
STEP_HEIGHT = 0.28
EXIT_COOLDOWN = 0.6

# 出口地垫（本地坐标 + 半径）：底边落在 y = 0.50 处，不压出南侧门框
EXIT_MAT_LOCAL: tuple[float, float, float] = (9.0, 1.25, 0.75)
# 玩家站位（本地坐标 + 初始朝向：面朝北侧演讲台）
PLAYER_SPAWN_LOCAL: tuple[float, float, str] = (7.9, 5.4, "n")
# 校长站位（演讲台后方，站在舞台上）
PRINCIPAL_LOCAL: tuple[float, float, float] = (9.0, 9.25, STAGE_HEIGHT)
#: 校长立牌资产：有这张图就用立牌，缺图才退回代码几何占位
PRINCIPAL_ART = "char_npc_principal_idle"

#: 礼堂可替换贴图（缺哪个就用纯色块顶上，不影响流程）
CEREMONY_ART: dict[str, str] = {
    "carpet": "ceremony_carpet",
    "curtain": "ceremony_curtain",
    "podium": "ceremony_podium",
}
#: 演讲台立牌贴图 41×43 px ÷ 24 = 1.708 m × 1.792 m
PODIUM_CARD_WIDTH = 41 / 24.0
PODIUM_CARD_HEIGHT = 43 / 24.0


@dataclass(frozen=True)
class CeremonyNpcSpec:
    npc_id: str
    short_id: str
    name: str
    local_x: float
    local_y: float
    facing: str = "s"
    interact_radius: float = 1.85


# 台下除玩家外的 3 位同学（与玩家共 4 人，整齐站在舞台前方）
CEREMONY_NPCS: tuple[CeremonyNpcSpec, ...] = (
    CeremonyNpcSpec("npc_sumo", "sumo", "符闹吃", 5.6, 5.6),
    CeremonyNpcSpec("npc_chenlang", "chenlang", "李振兴", 10.1, 5.4),
    CeremonyNpcSpec("npc_xiaoyou", "xiaoyou", "奈珑", 12.4, 5.6),
)

# 观众席占位长椅（左右各 2 排；四周及行间净宽 >= 1.0 m，确保玩家 0.70 m 碰撞体顺畅通行）
BENCH_RECTS_LOCAL: tuple[Rect, ...] = (
    Rect(1.5, 1.9, 4.5, 2.65),
    Rect(1.5, 3.7, 4.5, 4.45),
    Rect(13.5, 1.9, 16.5, 2.65),
    Rect(13.5, 3.7, 16.5, 4.45),
)

# 角色卡片按 CAMERA_TILT_DEGREES 向北倾倒，北墙碰撞体需要留出同款倾斜净空避免贴墙穿模
CARD_LEAN_SIN = abs(math.sin(math.radians(config.CAMERA_TILT_DEGREES)))
NORTH_WALL_CLEARANCE = config.CHARACTER_CARD_SIZE_METERS[1] * CARD_LEAN_SIN

# 舞台主体与中央台阶分拆碰撞：避免在台阶左右两侧平地上生成 0.6 m 隐形空气墙，
# 同时向南留出 0.25 m 倾斜余量，确保角色深度与小腿完全落在舞台前沿（z=0.57 金边）之前
STAGE_RECT_LOCAL = Rect(2.6, 7.55, 15.4, 11.5)
STAGE_STEP_RECT_LOCAL = Rect(7.6, 7.2, 10.4, 7.8)
NPC_COLLIDER_HALF = 0.30


def build_local_colliders() -> tuple[Rect, ...]:
    """返回礼堂的纯逻辑本地碰撞矩形（便于无图形单元测试验证）。"""
    w, h = SIZE
    t = WALL_THICKNESS
    rects: list[Rect] = [
        Rect(0.0, h - t - NORTH_WALL_CLEARANCE, w, h),  # 北墙（含 2.5D 倾斜净空）
        Rect(0.0, 0.0, t, h),                           # 西墙
        Rect(w - t, 0.0, w, h),                         # 东墙
        Rect(0.0, 0.0, 7.5, t),                         # 南墙左侧（中央 7.5..10.5 为出口豁口）
        Rect(10.5, 0.0, w, t),                          # 南墙右侧
        Rect(7.35, 0.0, 7.65, t + 0.1),                 # 左侧门柱
        Rect(10.35, 0.0, 10.65, t + 0.1),               # 右侧门柱
        Rect(7.5, -0.3, 10.5, 0.2),                     # 出口南缘兜底，防止走出礼堂边界
        STAGE_RECT_LOCAL,                               # 主席台主体
        STAGE_STEP_RECT_LOCAL,                          # 中央台阶
    ]
    rects.extend(BENCH_RECTS_LOCAL)
    for spec in CEREMONY_NPCS:
        rects.append(Rect(
            spec.local_x - NPC_COLLIDER_HALF,
            spec.local_y - NPC_COLLIDER_HALF,
            spec.local_x + NPC_COLLIDER_HALF,
            spec.local_y + NPC_COLLIDER_HALF,
        ))
    return tuple(rects)


def build_world_colliders(origin: tuple[float, float] = ORIGIN) -> tuple[Rect, ...]:
    ox, oy = origin
    return tuple(
        Rect(r.x0 + ox, r.y0 + oy, r.x1 + ox, r.y1 + oy) for r in build_local_colliders()
    )


def make_ceremony_candidates(origin: tuple[float, float] = ORIGIN) -> tuple[Candidate, ...]:
    """为礼堂台下 3 位同学构造标准交互候选点，复用 PromptTracker。"""
    ox, oy = origin
    candidates: list[Candidate] = []
    for spec in CEREMONY_NPCS:
        wx, wy = ox + spec.local_x, oy + spec.local_y
        ia = Interactable(
            id=f"ceremony_{spec.npc_id}",
            name=spec.name,
            scene=CEREMONY_SCENE_ID,
            location_id=CEREMONY_LOCATION_ID,
            x=spec.local_x,
            y=spec.local_y,
            radius=spec.interact_radius,
            type="npc",
            target=spec.npc_id,
        )
        candidates.append(Candidate(interactable=ia, x=wx, y=wy))
    return tuple(candidates)


class CeremonyScene:
    """开学典礼礼堂的 2.5D 占位几何场景。"""

    scene_id = CEREMONY_SCENE_ID

    def __init__(self, parent, *, origin: tuple[float, float] = ORIGIN,
                 draw_principal_placeholder: bool = True,
                 textures: dict[str, object] | None = None) -> None:
        self.origin = (float(origin[0]), float(origin[1]))
        self.size = SIZE
        self.draw_principal_placeholder = bool(draw_principal_placeholder)
        #: 可替换贴图：carpet / curtain / podium（缺哪个就用纯色块顶上）
        self.textures = dict(textures or {})
        self.root = parent.attachNewNode("CeremonyScene")
        self._exit_cooldown = 0.0
        self._build()

    # ------------------------------------------------------------------ 构建
    def _build(self) -> None:
        ox, oy = self.origin
        w, h = self.size
        t = WALL_THICKNESS

        # 1) 地板 + 中央红毯（有贴图就整块铺满：UV 0..1，图里自带金色滚边）
        make_ground(self.root, ox, oy, ox + w, oy + h, 0.0, FLOOR_COLOR)
        carpet = self.textures.get("carpet")
        if carpet is not None:
            from panda3d.core import Texture

            make_ground(self.root, ox + 7.2, oy + 0.5, ox + 10.8, oy + 7.3, 0.015,
                        CARPET_COLOR, texture=carpet)
            carpet.set_wrap_u(Texture.WM_clamp)
            carpet.set_wrap_v(Texture.WM_clamp)
        else:
            make_ground(self.root, ox + 7.2, oy + 0.5, ox + 10.8, oy + 7.3, 0.015, CARPET_COLOR)
            make_ground(self.root, ox + 7.05, oy + 0.5, ox + 7.2, oy + 7.3, 0.016, CARPET_TRIM_COLOR)
            make_ground(self.root, ox + 10.8, oy + 0.5, ox + 10.95, oy + 7.3, 0.016, CARPET_TRIM_COLOR)

        # 2) 四周墙体（南墙中央留出口豁口，配一对门柱）
        make_box(self.root, ox, oy + h - t, ox + w, oy + h, 0.0, WALL_HEIGHT_NORTH, WALL_COLOR)
        make_box(self.root, ox, oy, ox + t, oy + h, 0.0, WALL_HEIGHT_SIDE, WALL_COLOR)
        make_box(self.root, ox + w - t, oy, ox + w, oy + h, 0.0, WALL_HEIGHT_SIDE, WALL_COLOR)
        make_box(self.root, ox, oy, ox + 7.5, oy + t, 0.0, WALL_HEIGHT_SOUTH, WALL_COLOR)
        make_box(self.root, ox + 10.5, oy, ox + w, oy + t, 0.0, WALL_HEIGHT_SOUTH, WALL_COLOR)
        make_box(self.root, ox + 7.35, oy, ox + 7.65, oy + t + 0.1, 0.0, 0.85, STAGE_TRIM_COLOR)
        make_box(self.root, ox + 10.35, oy, ox + 10.65, oy + t + 0.1, 0.0, 0.85, STAGE_TRIM_COLOR)

        # 3) 北墙幕布（贴图里已经画了金穗与褶皱，不再叠金色横幅块）
        curtain = self.textures.get("curtain")
        if curtain is not None:
            from panda3d.core import Texture

            make_wall_panel(self.root, ox + 3.0, oy + h - t - 0.06,
                            ox + 15.0, oy + h - t - 0.06,
                            STAGE_HEIGHT, 2.35, curtain, tile_m=12.0, name="ceremony_curtain")
            curtain.set_wrap_u(Texture.WM_clamp)
            curtain.set_wrap_v(Texture.WM_clamp)
        else:
            make_box(self.root, ox + 3.0, oy + h - t - 0.06, ox + 15.0, oy + h - t,
                     STAGE_HEIGHT, 2.35, CURTAIN_COLOR)
            make_box(self.root, ox + 4.4, oy + h - t - 0.10, ox + 13.6, oy + h - t - 0.05,
                     1.75, 2.20, BANNER_COLOR)

        # 4) 抬高主席台 + 前沿金边 + 中央台阶
        make_box(self.root, ox + 2.6, oy + 7.8, ox + 15.4, oy + 11.5, 0.0, STAGE_HEIGHT, STAGE_COLOR)
        make_box(self.root, ox + 2.6, oy + 7.76, ox + 15.4, oy + 7.86,
                 STAGE_HEIGHT - 0.08, STAGE_HEIGHT + 0.02, STAGE_TRIM_COLOR)
        make_box(self.root, ox + 7.6, oy + 7.2, ox + 10.4, oy + 7.8, 0.0, STEP_HEIGHT, STAGE_COLOR)

        # 5) 演讲台占位模型（台座 + 台身 + 顶板 + 话筒）
        self._build_podium(ox, oy)

        # 6) 台上校长：有 `char_npc_principal_idle` 立牌时由适配层摆卡片，
        #    这里只在缺图时画代码几何占位。
        if self.draw_principal_placeholder:
            self._build_principal_placeholder(ox, oy)

        # 7) 观众席占位长椅（座板 + 靠背）
        for rect in BENCH_RECTS_LOCAL:
            make_box(self.root, ox + rect.x0, oy + rect.y0, ox + rect.x1, oy + rect.y1,
                     0.0, 0.45, BENCH_COLOR)
            make_box(self.root, ox + rect.x0, oy + rect.y0, ox + rect.x1, oy + rect.y0 + 0.14,
                     0.45, 0.88, STAGE_COLOR)

        # 8) 台下 NPC 站位圆环 + 出口地垫标识
        for spec in CEREMONY_NPCS:
            make_circle_lines(self.root, ox + spec.local_x, oy + spec.local_y, 0.42, 0.04,
                              NPC_RING_COLOR, segments=20, thickness=2.0)

        mx, my, mr = self.exit_mat_world()
        make_ground(self.root, mx - 1.05, my - 0.50, mx + 1.05, my + 0.50, 0.025, EXIT_MAT_FILL)
        make_circle_lines(self.root, mx, my, mr, 0.045, EXIT_MAT_RING, segments=24, thickness=3.0)

        self.root.flattenStrong()

    def _build_podium(self, ox: float, oy: float) -> None:
        z0 = STAGE_HEIGHT
        podium = self.textures.get("podium")
        if podium is not None:
            # 41×43 立牌贴图（1.71 m 宽 × 1.79 m 高），按 CAMERA_TILT_DEGREES 倾斜朝向镜头
            from panda3d.core import CardMaker, Texture, TransparencyAttrib

            podium.set_wrap_u(Texture.WM_clamp)
            podium.set_wrap_v(Texture.WM_clamp)
            cm = CardMaker("ceremony_podium")
            cm.set_frame(-PODIUM_CARD_WIDTH / 2.0, PODIUM_CARD_WIDTH / 2.0, 0.0, PODIUM_CARD_HEIGHT)
            card = self.root.attach_new_node(cm.generate())
            card.set_texture(podium)
            card.set_transparency(TransparencyAttrib.M_binary)
            card.set_light_off()
            card.set_p(config.CAMERA_TILT_DEGREES)
            card.set_pos(ox + 9.0, oy + 8.08, z0)
            return
        # 底座
        make_box(self.root, ox + 8.15, oy + 8.10, ox + 9.85, oy + 8.92, z0, z0 + 0.12, PODIUM_WOOD_COLOR)
        # 主体立柜
        make_box(self.root, ox + 8.32, oy + 8.18, ox + 9.68, oy + 8.85, z0 + 0.12, z0 + 1.02, PODIUM_WOOD_COLOR)
        # 前饰金色徽标条
        make_box(self.root, ox + 8.65, oy + 8.14, ox + 9.35, oy + 8.19, z0 + 0.56, z0 + 0.80, STAGE_TRIM_COLOR)
        # 台顶读稿板
        make_box(self.root, ox + 8.18, oy + 8.08, ox + 9.82, oy + 8.95, z0 + 1.02, z0 + 1.14, PODIUM_TOP_COLOR)
        # 话筒杆与麦克风头
        make_box(self.root, ox + 9.26, oy + 8.46, ox + 9.33, oy + 8.53, z0 + 1.14, z0 + 1.42, MIC_COLOR)
        make_box(self.root, ox + 9.20, oy + 8.44, ox + 9.36, oy + 8.58, z0 + 1.40, z0 + 1.50, MIC_COLOR)

    def _build_principal_placeholder(self, ox: float, oy: float) -> None:
        px, py, pz = PRINCIPAL_LOCAL
        wx, wy = ox + px, oy + py
        # 双腿/下半身
        make_box(self.root, wx - 0.24, wy - 0.18, wx + 0.24, wy + 0.18, pz, pz + 0.72, PRINCIPAL_SUIT_COLOR)
        # 西装上身
        make_box(self.root, wx - 0.34, wy - 0.22, wx + 0.34, wy + 0.22, pz + 0.72, pz + 1.40, PRINCIPAL_SUIT_COLOR)
        # 衬衫领口与红领带（面朝 -Y 镜头）
        make_box(self.root, wx - 0.11, wy - 0.24, wx + 0.11, wy - 0.20, pz + 1.08, pz + 1.38, PRINCIPAL_SHIRT_COLOR)
        make_box(self.root, wx - 0.04, wy - 0.26, wx + 0.04, wy - 0.22, pz + 0.96, pz + 1.34, PRINCIPAL_TIE_COLOR)
        # 头部与银灰短发
        make_box(self.root, wx - 0.22, wy - 0.20, wx + 0.22, wy + 0.20, pz + 1.42, pz + 1.82, PRINCIPAL_SKIN_COLOR)
        make_box(self.root, wx - 0.23, wy - 0.18, wx + 0.23, wy + 0.22, pz + 1.72, pz + 1.90, PRINCIPAL_HAIR_COLOR)

    # ------------------------------------------------------------------ 查询
    def center_world(self) -> tuple[float, float]:
        return (self.origin[0] + self.size[0] / 2.0, self.origin[1] + self.size[1] / 2.0)

    def bounds_world(self) -> Rect:
        ox, oy = self.origin
        return Rect(ox, oy, ox + self.size[0], oy + self.size[1])

    def colliders_world(self) -> tuple[Rect, ...]:
        return build_world_colliders(self.origin)

    def player_spawn_world(self) -> tuple[float, float, str]:
        lx, ly, facing = PLAYER_SPAWN_LOCAL
        return (self.origin[0] + lx, self.origin[1] + ly, facing)

    def principal_world(self) -> tuple[float, float, float]:
        px, py, pz = PRINCIPAL_LOCAL
        return (self.origin[0] + px, self.origin[1] + py, pz)

    def npc_spots_world(self) -> tuple[tuple[CeremonyNpcSpec, float, float], ...]:
        ox, oy = self.origin
        return tuple((spec, ox + spec.local_x, oy + spec.local_y) for spec in CEREMONY_NPCS)

    def exit_mat_world(self) -> tuple[float, float, float]:
        mx, my, mr = EXIT_MAT_LOCAL
        return (self.origin[0] + mx, self.origin[1] + my, mr)

    def candidates_world(self) -> tuple[Candidate, ...]:
        return make_ceremony_candidates(self.origin)

    # ------------------------------------------------------------------ 出口地垫
    def update_exit_mat(self, x: float, y: float, dt: float) -> bool:
        """玩家脚点走入南侧出口地垫时返回 True。"""
        if self._exit_cooldown > 0.0:
            self._exit_cooldown = max(0.0, self._exit_cooldown - max(dt, 0.0))
            return False
        mx, my, mr = self.exit_mat_world()
        if (x - mx) ** 2 + (y - my) ** 2 <= mr * mr:
            self._exit_cooldown = EXIT_COOLDOWN
            return True
        return False

    def destroy(self) -> None:
        if self.root is not None and not self.root.isEmpty():
            self.root.removeNode()
