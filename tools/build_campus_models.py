"""A 的工具：按用户提供的等距参考图生成低多边形校园模型（.bam，无贴图、顶点色）。

参考图：`素材/建筑/{宿舍楼,教学楼,图书馆,社团,饭堂,12 个道具,草地1}.jfif`
输出：`assets/campus/*.bam`（5 栋建筑 + 5 个室内 + 地面 + 12 个道具）

规格（A7）：
* 命名 `mesh_*`；原点在建筑占地西南角；Z 向上；1 单位 = 1 米；
* 单栋建筑 ≤ 800 三角面，整张室外场景 ≤ 30,000；
* 不使用贴图（纯顶点色/材质色），碰撞体不放进模型（由 C 的 map.json 提供）。

用法：python tools/build_campus_models.py [--out assets/campus]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 取自参考图的配色（对应 docs/art 的 32 色板）
C_WALL_LIGHT = (0.79, 0.81, 0.84)      # 宿舍冷灰
C_WALL_CREAM = (0.95, 0.89, 0.74)      # 教学/图书馆奶油
C_WALL_CREAM2 = (0.89, 0.81, 0.62)     # 奶油暗带
C_WALL_GREEN = (0.43, 0.61, 0.48)      # 社团灰绿
C_WALL_GREEN2 = (0.36, 0.54, 0.39)     # 社团暗部
C_WALL_OCHRE = (0.89, 0.81, 0.62)      # 饭堂赭黄
C_ROOF_RED = (0.75, 0.28, 0.25)        # 砖红屋顶/女儿墙
C_ROOF_RED2 = (0.66, 0.23, 0.21)       # 屋顶暗面
C_GLASS = (0.12, 0.16, 0.26)           # 深蓝不透明玻璃
C_GLASS2 = (0.16, 0.21, 0.33)
C_FRAME = (0.91, 0.93, 0.95)           # 窗框白
C_TRIM = (0.74, 0.63, 0.37)            # 金/木饰条
C_DOOR = (0.54, 0.41, 0.28)            # 棕木门
C_STONE = (0.72, 0.72, 0.70)           # 石材台阶
C_METAL = (0.72, 0.75, 0.78)           # 金属水箱/管道
C_GRASS = (0.32, 0.51, 0.31)
C_GRASS2 = (0.26, 0.43, 0.26)
C_PATH = (0.62, 0.60, 0.56)
C_LEAF = (0.30, 0.47, 0.29)
C_LEAF2 = (0.38, 0.55, 0.33)


# --------------------------------------------------------------------------- #
# 低层几何助手
# --------------------------------------------------------------------------- #
def _mesh(name, verts, tris, color):
    from panda3d.core import (Geom, GeomNode, GeomTriangles, GeomVertexData,
                              GeomVertexFormat, GeomVertexWriter, NodePath, Vec4)

    data = GeomVertexData(name, GeomVertexFormat.getV3(), Geom.UHStatic)
    writer = GeomVertexWriter(data, "vertex")
    for vertex in verts:
        writer.addData3(*vertex)
    prim = GeomTriangles(Geom.UHStatic)
    for a, b, c in tris:
        prim.addVertices(a, b, c)
    geom = Geom(data)
    geom.addPrimitive(prim)
    node = GeomNode("mesh_" + name)
    node.addGeom(geom)
    path = NodePath(node)
    path.setColor(Vec4(color[0], color[1], color[2], 1.0))
    return path


def box(root, name, x, y, z, w, d, h, color):
    """轴对齐盒子：原点在最小角。"""
    verts = [
        (x, y, z), (x + w, y, z), (x + w, y + d, z), (x, y + d, z),
        (x, y, z + h), (x + w, y, z + h), (x + w, y + d, z + h), (x, y + d, z + h),
    ]
    tris = [
        (0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),
        (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5),
        (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7),
    ]
    root.attachNewNode(_mesh(name, verts, tris, color).node())
    return root


def quad(root, name, p0, p1, p2, p3, color):
    verts = [p0, p1, p2, p3]
    tris = [(0, 1, 2), (0, 2, 3)]
    root.attachNewNode(_mesh(name, verts, tris, color).node())
    return root


def gable_roof(root, name, x, y, z, w, d, rise, color, color_side=None):
    """双坡屋顶：沿 x 方向起脊，底面不封（省面）。"""
    color_side = color_side or color
    ridge_y = y + d / 2.0
    a = (x, y, z)
    b = (x + w, y, z)
    c = (x + w, y + d, z)
    d0 = (x, y + d, z)
    r0 = (x, ridge_y, z + rise)
    r1 = (x + w, ridge_y, z + rise)
    quad(root, name + "_south", a, b, r1, r0, color)          # 南坡
    quad(root, name + "_north", d0, c, r1, r0, color_side)    # 北坡
    root.attachNewNode(_mesh(name + "_gable_w", [a, d0, r0], [(0, 1, 2)], color_side).node())
    root.attachNewNode(_mesh(name + "_gable_e", [b, c, r1], [(0, 2, 1)], color_side).node())
    return root


def hipped_roof(root, name, x, y, z, w, d, rise, inset, color, color_side):
    """四坡屋顶：4 个三角形坡面（8 个三角面以内）。"""
    a = (x, y, z)
    b = (x + w, y, z)
    c = (x + w, y + d, z)
    e = (x, y + d, z)
    r0 = (x + inset, y + d / 2.0, z + rise)
    r1 = (x + w - inset, y + d / 2.0, z + rise)
    root.attachNewNode(_mesh(name + "_s", [a, b, r1], [(0, 1, 2)], color).node())
    root.attachNewNode(_mesh(name + "_s2", [a, r1, r0], [(0, 1, 2)], color).node())
    root.attachNewNode(_mesh(name + "_n", [c, e, r0], [(0, 1, 2)], color_side).node())
    root.attachNewNode(_mesh(name + "_n2", [c, r0, r1], [(0, 1, 2)], color_side).node())
    root.attachNewNode(_mesh(name + "_w", [e, a, r0], [(0, 1, 2)], color_side).node())
    root.attachNewNode(_mesh(name + "_e", [b, c, r1], [(0, 1, 2)], color).node())
    return root


def panel(root, name, x, y, z, w, h, color, face="s"):
    """墙面上的平板（窗玻璃、招牌面），沿 z 立起，向 -y 或 +y 偏移一点点。"""
    eps = 0.02
    if face == "s":
        quad(root, name, (x, y - eps, z), (x + w, y - eps, z),
             (x + w, y - eps, z + h), (x, y - eps, z + h), color)
    elif face == "n":
        quad(root, name, (x + w, y + eps, z), (x, y + eps, z),
             (x, y + eps, z + h), (x + w, y + eps, z + h), color)
    elif face == "w":
        quad(root, name, (x - eps, y + 0, z), (x - eps, y + w, z),
             (x - eps, y + w, z + h), (x - eps, y, z + h), color)
    else:  # e
        quad(root, name, (x + eps, y + w, z), (x + eps, y, z),
             (x + eps, y, z + h), (x + eps, y + w, z + h), color)
    return root


def window_row(root, name, x, y, z, count, win_w, win_h, gap, color=C_GLASS, face="s",
               frame=True, mullions=1, frame_color=C_FRAME):
    """A row of glazed windows with separate perimeter frames and mullions."""
    for index in range(count):
        wx = x + index * (win_w + gap)
        panel(root, f"{name}_{index}", wx, y, z, win_w, win_h, color, face=face)
        if frame:
            edge = 0.055
            if face in ("s", "n"):
                panel(root, f"{name}_{index}_left", wx - edge, y, z - edge,
                      edge, win_h + edge * 2, frame_color, face=face)
                panel(root, f"{name}_{index}_right", wx + win_w, y, z - edge,
                      edge, win_h + edge * 2, frame_color, face=face)
                panel(root, f"{name}_{index}_bottom", wx - edge, y, z - edge,
                      win_w + edge * 2, edge, frame_color, face=face)
                panel(root, f"{name}_{index}_top", wx - edge, y, z + win_h,
                      win_w + edge * 2, edge, frame_color, face=face)
                for mullion in range(1, mullions + 1):
                    mx = wx + win_w * mullion / (mullions + 1)
                    panel(root, f"{name}_{index}_mullion{mullion}", mx - edge / 2, y, z,
                          edge, win_h, frame_color, face=face)
            else:
                panel(root, f"{name}_{index}_left", x, y - edge, z - edge,
                      edge, win_h + edge * 2, frame_color, face=face)
                panel(root, f"{name}_{index}_right", x, y + win_w, z - edge,
                      edge, win_h + edge * 2, frame_color, face=face)
                panel(root, f"{name}_{index}_bottom", x, y - edge, z - edge,
                      win_w + edge * 2, edge, frame_color, face=face)
                panel(root, f"{name}_{index}_top", x, y - edge, z + win_h,
                      win_w + edge * 2, edge, frame_color, face=face)
                for mullion in range(1, mullions + 1):
                    my = y + win_w * mullion / (mullions + 1)
                    panel(root, f"{name}_{index}_mullion{mullion}", x, my - edge / 2, z,
                          edge, win_h, frame_color, face=face)
    return root


def cylinder(root, name, cx, cy, z, radius, height, sides, color):
    import math

    verts = []
    for index in range(sides):
        angle = 2 * math.pi * index / sides
        verts.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle), z))
    for index in range(sides):
        angle = 2 * math.pi * index / sides
        verts.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle), z + height))
    tris = []
    for index in range(sides):
        nxt = (index + 1) % sides
        tris.append((index, nxt, sides + nxt))
        tris.append((index, sides + nxt, sides + index))
    center_top = len(verts)
    verts.append((cx, cy, z + height))
    center_bottom = len(verts)
    verts.append((cx, cy, z))
    for index in range(sides):
        nxt = (index + 1) % sides
        tris.append((sides + index, center_top, sides + nxt))
        tris.append((index, center_bottom, nxt))
    root.attachNewNode(_mesh(name, verts, tris, color).node())
    return root


def rod(root, name, p0, p1, radius, color, sides=6):
    """Low-poly round beam between two points."""
    import math

    direction = tuple(p1[i] - p0[i] for i in range(3))
    length = math.sqrt(sum(value * value for value in direction))
    if length <= 1e-6:
        return root
    axis = tuple(value / length for value in direction)
    reference = (0.0, 0.0, 1.0) if abs(axis[2]) < 0.92 else (0.0, 1.0, 0.0)
    side = (axis[1] * reference[2] - axis[2] * reference[1],
            axis[2] * reference[0] - axis[0] * reference[2],
            axis[0] * reference[1] - axis[1] * reference[0])
    side_len = math.sqrt(sum(value * value for value in side))
    side = tuple(value / side_len for value in side)
    up = (axis[1] * side[2] - axis[2] * side[1],
          axis[2] * side[0] - axis[0] * side[2],
          axis[0] * side[1] - axis[1] * side[0])
    verts = []
    for point in (p0, p1):
        for index in range(sides):
            angle = 2 * math.pi * index / sides
            verts.append(tuple(point[k] + radius * (
                math.cos(angle) * side[k] + math.sin(angle) * up[k]) for k in range(3)))
    tris = []
    for index in range(sides):
        nxt = (index + 1) % sides
        tris.extend(((index, nxt, sides + nxt), (index, sides + nxt, sides + index),
                     (2 * sides, index, nxt), (2 * sides + 1, sides + nxt, sides + index)))
    verts.extend((p0, p1))
    root.attachNewNode(_mesh(name, verts, tris, color).node())
    return root


def ellipsoid(root, name, cx, cy, cz, rx, ry, rz, color, sides=8):
    """A compact faceted ellipsoid for foliage and soft low-poly forms."""
    import math

    profiles = ((-0.82, 0.54), (-0.25, 0.92), (0.36, 0.78), (0.82, 0.48))
    verts = [(cx, cy, cz - rz)]
    for ring, (height, radius) in enumerate(profiles):
        phase = ring * 0.17
        for index in range(sides):
            angle = 2 * math.pi * index / sides + phase
            verts.append((cx + rx * radius * math.cos(angle),
                          cy + ry * radius * math.sin(angle), cz + rz * height))
    top = len(verts)
    verts.append((cx, cy, cz + rz))
    tris = []
    for index in range(sides):
        nxt = (index + 1) % sides
        tris.append((0, 1 + nxt, 1 + index))
    for ring in range(len(profiles) - 1):
        start_a = 1 + ring * sides
        start_b = start_a + sides
        for index in range(sides):
            nxt = (index + 1) % sides
            a, b = start_a + index, start_a + nxt
            c, d0 = start_b + nxt, start_b + index
            tris.extend(((a, b, c), (a, c, d0)))
    last = 1 + (len(profiles) - 1) * sides
    for index in range(sides):
        nxt = (index + 1) % sides
        tris.append((last + index, last + nxt, top))
    root.attachNewNode(_mesh(name, verts, tris, color).node())
    return root


def circle_panel(root, name, cx, y, cz, radius, color, sides=16):
    """Filled circular detail on a south-facing vertical facade."""
    import math

    verts = [(cx, y, cz)]
    for index in range(sides):
        angle = 2 * math.pi * index / sides
        verts.append((cx + radius * math.cos(angle), y, cz + radius * math.sin(angle)))
    tris = [(0, 1 + index, 1 + (index + 1) % sides) for index in range(sides)]
    root.attachNewNode(_mesh(name, verts, tris, color).node())
    return root


def grass_blade(root, name, x, y, z, width, height, color, lean=0.0):
    """One triangular grass blade used in the ground reference sheet."""
    verts = [(x - width / 2, y, z), (x + width / 2, y, z),
             (x + lean, y, z + height)]
    root.attachNewNode(_mesh(name, verts, [(0, 1, 2)], color).node())
    return root


# --------------------------------------------------------------------------- #
# 五栋建筑（尺寸 = 占地 w×d，高 h，单位米；原点在西南角）
# --------------------------------------------------------------------------- #
def build_dorm() -> "object":
    from panda3d.core import NodePath

    root = NodePath("model_dorm")
    w, d, floors, fh = 16.0, 12.0, 4, 2.7
    h = floors * fh
    box(root, "dorm_body", 0, 0, 0, w, d, h, C_WALL_LIGHT)
    box(root, "dorm_plinth", -0.15, -0.15, 0, w + 0.3, d + 0.3, 0.35, C_STONE)
    # Wide floor bands and a slightly darker ground strip match the reference's cool facade.
    box(root, "dorm_ground_band", -0.12, -0.12, 0.55, w + 0.24, d + 0.24, 0.18, C_FRAME)
    for floor in range(1, floors):
        box(root, f"dorm_band{floor}", -0.06, -0.06, floor * fh - 0.09,
            w + 0.12, d + 0.12, 0.18, C_FRAME)
    # South facade: paired windows, projecting balconies and simple drying rails.
    for floor in range(floors):
        base_z = floor * fh + 0.75
        window_row(root, f"dorm_win{floor}", 1.25, 0.0, base_z, 5, 1.55, 1.3, 1.0,
                   frame=False, mullions=0)
        for balcony, bx in enumerate((2.55, 9.55)):
            box(root, f"dorm_bal{floor}_{balcony}", bx, -0.75, base_z - 0.22,
                2.45, 0.82, 0.12, C_FRAME)
            quad(root, f"dorm_rail{floor}_{balcony}", (bx, -0.76, base_z - 0.1),
                 (bx + 2.45, -0.76, base_z - 0.1), (bx + 2.45, -0.76, base_z + 0.45),
                 (bx, -0.76, base_z + 0.45), C_FRAME)
            rod(root, f"dorm_clothesline{floor}_{balcony}", (bx + 0.2, -0.84, base_z + 0.48),
                (bx + 2.2, -0.84, base_z + 0.48), 0.025, C_METAL, sides=4)
    # Both side walls carry the narrow stacked windows seen in the source render.
    for floor in range(floors):
        base_z = floor * fh + 0.78
        window_row(root, f"dorm_ewin{floor}", w, 1.2, base_z, 2, 1.25, 1.2, 2.5,
                   face="e", frame=False, mullions=0)
        window_row(root, f"dorm_wwin{floor}", 0.0, 1.2, base_z, 2, 1.25, 1.2, 2.5,
                   face="w", frame=False, mullions=0)
    # Entrance canopy, framed door and shallow steps.
    box(root, "dorm_steps", 6.4, -1.5, 0, 3.2, 1.5, 0.3, C_STONE)
    box(root, "dorm_steps2", 6.6, -0.9, 0, 2.8, 0.9, 0.6, C_STONE)
    panel(root, "dorm_door", 7.0, 0.0, 0.6, 2.0, 2.1, C_DOOR)
    box(root, "dorm_door_l", 6.88, -0.08, 0.52, 0.1, 0.12, 2.28, C_TRIM)
    box(root, "dorm_door_r", 9.02, -0.08, 0.52, 0.1, 0.12, 2.28, C_TRIM)
    quad(root, "dorm_awning", (6.5, -1.3, 2.85), (9.5, -1.3, 2.85),
         (9.5, 0.0, 3.25), (6.5, 0.0, 3.25), C_TRIM)
    # Red gable roof with three front dormers.
    gable_roof(root, "dorm_roof", -0.3, -0.3, h, w + 0.6, d + 0.6, 3.2, C_ROOF_RED, C_ROOF_RED2)
    for index, dx in enumerate((3.0, 7.4, 11.8)):
        box(root, f"dorm_dormer{index}", dx, -0.55, h + 0.35, 1.9, 1.1, 1.25, C_WALL_LIGHT)
        quad(root, f"dorm_dormer_roof{index}", (dx - 0.1, -0.7, h + 1.6),
             (dx + 2.0, -0.7, h + 1.6), (dx + 1.4, 0.6, h + 2.35),
             (dx + 0.5, 0.6, h + 2.35), C_ROOF_RED)
        panel(root, f"dorm_dormer_win{index}", dx + 0.55, -0.58, h + 0.65, 0.8, 0.75, C_GLASS)
    # Rooftop water tank on four legs, with a small antenna and chimney cluster.
    tank_x, tank_y = 11.1, 8.9
    for leg_x in (tank_x - 0.62, tank_x + 0.62):
        for leg_y in (tank_y - 0.62, tank_y + 0.62):
            box(root, f"dorm_tank_leg_{leg_x}_{leg_y}", leg_x, leg_y, h + 0.25,
                0.16, 0.16, 1.45, C_METAL)
    box(root, "dorm_tank_crossbar", tank_x - 0.75, tank_y - 0.08, h + 0.65,
        1.5, 0.16, 0.12, C_METAL)
    cylinder(root, "dorm_tank", tank_x, tank_y, h + 1.7, 0.85, 1.45, 8, C_METAL)
    cylinder(root, "dorm_tank_cap", tank_x, tank_y, h + 3.15, 0.92, 0.14, 8, C_FRAME)
    box(root, "dorm_antenna", 8.9, 9.35, h + 0.15, 0.08, 0.08, 3.0, C_METAL)
    for index in range(3):
        rod(root, f"dorm_antenna_bar{index}", (8.45, 9.35, h + 2.1 + index * 0.32),
            (9.4, 9.35, h + 2.1 + index * 0.32), 0.035, C_METAL, sides=5)
    box(root, "dorm_chimney", 12.4, 7.4, h + 0.6, 1.1, 1.1, 1.0, C_WALL_LIGHT)
    box(root, "dorm_chimney_cap", 12.3, 7.3, h + 1.6, 1.3, 1.3, 0.16, C_ROOF_RED)
    return root


def build_teaching() -> "object":
    from panda3d.core import NodePath

    root = NodePath("model_teaching")
    w, d, floors, fh = 20.0, 14.0, 4, 2.85
    h = floors * fh
    # U 形：两翼 + 后侧连接体
    box(root, "teach_left", 0, 0, 0, 6.6, d, h, C_WALL_CREAM)
    box(root, "teach_right", w - 6.6, 0, 0, 6.6, d, h, C_WALL_CREAM)
    box(root, "teach_back", 6.6, d - 5.0, 0, w - 13.2, 5.0, h, C_WALL_CREAM)
    # Each wing has three deep blue window bays with cream separators.
    for floor in range(floors):
        base_z = floor * fh + 0.8
        window_row(root, f"teach_winL{floor}", 0.45, 0.0, base_z, 3, 1.52, 1.5, 0.28,
                   frame=False, mullions=0)
        window_row(root, f"teach_winR{floor}", w - 5.0, 0.0, base_z, 3, 1.52, 1.5, 0.28,
                   frame=False, mullions=0)
        window_row(root, f"teach_winLw{floor}", 0.0, 1.2, base_z, 3, 1.25, 1.5, 0.55,
                   color=C_GLASS2, face="w", frame=False, mullions=0)
        window_row(root, f"teach_winRw{floor}", w, 1.2, base_z, 3, 1.25, 1.5, 0.55,
                   color=C_GLASS2, face="e", frame=False, mullions=0)
        box(root, f"teach_band{floor}", -0.07, -0.07, floor * fh + 2.45,
            w + 0.14, d + 0.14, 0.2, C_WALL_CREAM2)
    # Central clock tower: tall glazed slit, clock face and a projecting entrance.
    tower_w = 5.2
    tx = (w - tower_w) / 2
    box(root, "teach_tower", tx, -1.2, 0, tower_w, 5.2, h + 2.6, C_WALL_CREAM)
    panel(root, "teach_tower_win", tx + 1.5, -1.2, 1.0, 2.2, h + 0.6, C_GLASS)
    for mullion in (tx + 2.15, tx + 3.05):
        box(root, f"teach_tower_mullion{mullion}", mullion, -1.28, 1.0, 0.08, 0.1, h + 0.6, C_FRAME)
    circle_panel(root, "teach_clock_outer", tx + tower_w / 2, -1.29, h + 1.92, 0.88, C_FRAME)
    circle_panel(root, "teach_clock_face", tx + tower_w / 2, -1.33, h + 1.92, 0.72, C_GLASS2)
    box(root, "teach_clock_hand_h", tx + tower_w / 2 - 0.38, -1.38, h + 1.88,
        0.76, 0.05, 0.08, C_FRAME)
    box(root, "teach_clock_hand_v", tx + tower_w / 2 - 0.04, -1.38, h + 1.88,
        0.08, 0.05, 0.48, C_FRAME)
    # 女儿墙（红）
    for name, (bx, by, bw, bd) in {
        "p_left": (0, 0, 6.6, d), "p_right": (w - 6.6, 0, 6.6, d),
        "p_back": (6.6, d - 5.0, w - 13.2, 5.0),
    }.items():
        box(root, f"teach_{name}n", bx, by + bd - 0.25, h, bw, 0.25, 0.45, C_ROOF_RED)
        box(root, f"teach_{name}s", bx, by, h, bw, 0.25, 0.45, C_ROOF_RED)
        box(root, f"teach_{name}w", bx, by, h, 0.25, bd, 0.45, C_ROOF_RED)
        box(root, f"teach_{name}e", bx + bw - 0.25, by, h, 0.25, bd, 0.45, C_ROOF_RED)
    box(root, "teach_tower_cap", tx - 0.2, -1.4, h + 2.6, tower_w + 0.4, 5.6, 0.4, C_ROOF_RED)
    # 入口 + 台阶 + 雨棚
    box(root, "teach_steps", tx + 0.6, -2.4, 0, 4.0, 1.2, 0.3, C_STONE)
    box(root, "teach_steps2", tx + 0.95, -1.65, 0, 3.3, 0.75, 0.5, C_STONE)
    panel(root, "teach_door", tx + 1.4, -1.2, 0.3, 2.4, 2.0, C_DOOR)
    box(root, "teach_door_l", tx + 1.26, -1.3, 0.22, 0.1, 0.12, 2.18, C_TRIM)
    box(root, "teach_door_r", tx + 3.84, -1.3, 0.22, 0.1, 0.12, 2.18, C_TRIM)
    quad(root, "teach_canopy", (tx + 0.4, -2.1, 2.7), (tx + 4.8, -2.1, 2.7),
         (tx + 4.8, -1.2, 2.95), (tx + 0.4, -1.2, 2.95), C_FRAME)
    # Flag, roof vents and a few small service boxes keep the roof silhouette busy.
    box(root, "teach_flagpole", 1.6, 1.2, h, 0.1, 0.1, 5.2, C_METAL)
    quad(root, "teach_flag", (1.7, 1.25, h + 4.9), (1.7, 2.55, h + 4.9),
         (1.7, 2.55, h + 3.9), (1.7, 1.25, h + 3.9), C_ROOF_RED)
    for index, (ax, ay) in enumerate(((2.2, d - 3.2), (12.4, d - 3.4), (16.2, 2.0))):
        box(root, f"teach_ac{index}", ax, ay, h, 1.1, 0.8, 0.55, C_METAL)
        box(root, f"teach_ac_cap{index}", ax - 0.08, ay - 0.08, h + 0.55, 1.26, 0.96, 0.08, C_FRAME)
    return root


def build_library() -> "object":
    from panda3d.core import NodePath

    root = NodePath("model_library")
    w, d, floors, fh = 18.0, 16.0, 3, 3.1
    h = floors * fh
    box(root, "lib_body", 0, 0, 0, w, d, h, C_WALL_CREAM)
    box(root, "lib_plinth", -0.2, -0.2, 0, w + 0.4, d + 0.4, 0.4, C_STONE)
    for floor in range(1, floors):
        box(root, f"lib_band{floor}", -0.08, -0.08, floor * fh - 0.08,
            w + 0.16, d + 0.16, 0.16, C_WALL_CREAM2)
    # Corner quoins give the library the chunky yellow trim visible in the reference.
    for name, (qx, qy) in {"q1": (0.0, 0.0), "q2": (w - 1.0, 0.0),
                           "q3": (0.0, d - 1.0), "q4": (w - 1.0, d - 1.0)}.items():
        for floor in range(floors):
            box(root, f"lib_{name}_{floor}", qx, qy, floor * fh + 0.2, 1.0, 1.0, 0.46,
                C_WALL_CREAM2)
    # Central full-height glazed bay and a four-column portico.
    panel(root, "lib_tall_win", w / 2 - 1.6, 0.0, 1.2, 3.2, h - 2.6, C_GLASS)
    for index in range(3):
        box(root, f"lib_tall_mullion{index}", w / 2 - 1.55 + index * 1.05, -0.08, 1.2,
            0.08, 0.1, h - 2.6, C_FRAME)
    for index in range(4):
        px = 3.0 + index * 3.1
        box(root, f"lib_col{index}", px, -1.9, 0, 0.65, 0.65, h * 0.62, C_WALL_CREAM)
    box(root, "lib_portico", 2.6, -2.2, h * 0.62, 10.6, 2.4, 0.45, C_WALL_CREAM2)
    box(root, "lib_steps", 1.6, -3.6, 0, 12.6, 1.5, 0.28, C_STONE)
    box(root, "lib_steps2", 2.4, -2.6, 0, 11.0, 1.0, 0.5, C_STONE)
    panel(root, "lib_door", w / 2 - 1.1, -1.9, 0.5, 2.2, 2.1, C_TRIM)
    # Repeated windows on the front and side walls.
    for floor in range(floors):
        window_row(root, f"lib_win{floor}", 1.2, 0.0, floor * fh + 1.0, 4, 1.12, 1.28, 2.0,
                   mullions=1)
        window_row(root, f"lib_ewin{floor}", w, 2.0, floor * fh + 1.0, 3, 1.25, 1.28, 2.0,
                   color=C_GLASS, face="e", mullions=1)
        window_row(root, f"lib_wwin{floor}", 0.0, 2.0, floor * fh + 1.0, 3, 1.25, 1.28, 2.0,
                   color=C_GLASS, face="w", mullions=1)
    # Four-sided red roof and raised skylight ridge.
    hipped_roof(root, "lib_roof", -0.4, -0.4, h, w + 0.8, d + 0.8, 4.2, 3.2,
                C_ROOF_RED, C_ROOF_RED2)
    quad(root, "lib_skylight", (w / 2 - 2.0, d / 2 - 2.4, h + 3.0),
         (w / 2 + 2.0, d / 2 - 2.4, h + 3.0), (w / 2 + 2.0, d / 2 + 2.4, h + 3.9),
         (w / 2 - 2.0, d / 2 + 2.4, h + 3.9), C_GLASS2)
    for index in range(3):
        box(root, f"lib_skylight_bar{index}", w / 2 - 2.0, d / 2 - 2.4 + index * 2.0,
            h + 3.0, 4.0, 0.1, 0.95, C_FRAME)
    return root


def build_club() -> "object":
    from panda3d.core import NodePath

    root = NodePath("model_club")
    w, d, floors, fh = 14.0, 12.0, 2, 3.6
    h = floors * fh
    box(root, "club_body", 0, 0, 0, w, d, h, C_WALL_GREEN)
    box(root, "club_band", -0.08, -0.08, fh - 0.12, w + 0.16, d + 0.16, 0.24, C_WALL_GREEN2)
    box(root, "club_plinth", -0.15, -0.15, 0, w + 0.3, d + 0.3, 0.28, C_WALL_GREEN2)
    # Ground-floor shopfront glazing and a framed side entrance.
    for index in range(3):
        window_row(root, f"club_shopwin{index}", 1.05 + index * 3.0, 0.0, 0.75, 1, 2.45, 2.4, 0,
                   mullions=2)
    panel(root, "club_door", 10.6, 0.0, 0.5, 1.8, 2.2, C_DOOR)
    box(root, "club_door_l", 10.48, -0.08, 0.42, 0.1, 0.12, 2.38, C_TRIM)
    box(root, "club_door_r", 12.42, -0.08, 0.42, 0.1, 0.12, 2.38, C_TRIM)
    box(root, "club_step", 10.5, -0.9, 0, 2.0, 0.9, 0.22, C_STONE)
    # Bright striped awning from the supplied club reference.
    colors = ((0.80, 0.30, 0.35), (0.90, 0.72, 0.30), (0.35, 0.55, 0.75))
    for index, color in enumerate(colors * 2):
        quad(root, f"club_awning{index}", (10.4 + index * 0.62, -1.15, 3.05),
             (11.02 + index * 0.62, -1.15, 3.05), (11.02 + index * 0.62, 0.0, 3.35),
             (10.4 + index * 0.62, 0.0, 3.35), color)
    # Upper windows repeat the same narrow framed language.
    for index in range(3):
        window_row(root, f"club_win2_{index}", 1.5 + index * 3.7, 0.0, fh + 0.9, 1, 1.7, 1.5,
                   0, mullions=1)
        window_row(root, f"club_ewin2_{index}", w, 1.4 + index * 3.2, fh + 0.9, 1, 1.35, 1.4,
                   0, color=C_GLASS, face="e", mullions=1)
    # Roof parapet, green deck, rooftop sign and a tiny service box.
    for name, (bx, by, bw, bd) in {"s": (0, 0, w, 0.3), "n": (0, d - 0.3, w, 0.3),
                                   "w": (0, 0, 0.3, d), "e": (w - 0.3, 0, 0.3, d)}.items():
        box(root, f"club_parapet_{name}", bx, by, h, bw, bd, 0.5, C_ROOF_RED)
    box(root, "club_roofdeck", 0.3, 0.3, h, w - 0.6, d - 0.6, 0.12, C_WALL_GREEN2)
    box(root, "club_sign_postL", 6.2, 7.2, h + 0.12, 0.16, 0.16, 2.0, C_METAL)
    box(root, "club_sign_postR", 10.4, 7.2, h + 0.12, 0.16, 0.16, 2.0, C_METAL)
    box(root, "club_sign_board", 5.9, 7.05, h + 2.0, 5.0, 0.18, 1.3, C_FRAME)
    box(root, "club_sign_strip", 5.9, 6.96, h + 2.88, 5.0, 0.1, 0.16, C_ROOF_RED)
    box(root, "club_roofbox", 1.4, 2.0, h + 0.12, 1.2, 0.9, 0.5, C_METAL)
    return root


def build_canteen() -> "object":
    from panda3d.core import NodePath

    root = NodePath("model_canteen")
    w, d, h = 16.0, 12.0, 5.2
    box(root, "canteen_body", 0, 0, 0, w, d, h, C_WALL_OCHRE)
    box(root, "canteen_plinth", -0.15, -0.15, 0, w + 0.3, d + 0.3, 0.3, C_STONE)
    box(root, "canteen_band", -0.07, -0.07, h - 0.5, w + 0.14, d + 0.14, 0.22, C_WALL_CREAM)
    # Front glass wall with strong mullions and a warm service counter.
    for index in range(4):
        window_row(root, f"canteen_glass{index}", 1.15 + index * 2.65, 0.0, 0.85, 1, 2.1, 3.0,
                   0, mullions=1)
    # Side windows are smaller and sit above the counter line.
    for index in range(3):
        window_row(root, f"canteen_ewin{index}", w, 1.8 + index * 3.1, 2.35, 1, 1.85, 1.2, 0,
                   color=C_GLASS2, face="e", mullions=1)
    # Deep red canopy, four slim posts and a framed side door.
    quad(root, "canteen_canopy", (0.6, -2.6, 3.3), (9.4, -2.6, 3.3),
         (9.4, 0.0, 3.7), (0.6, 0.0, 3.7), C_ROOF_RED)
    for index in range(4):
        box(root, f"canteen_post{index}", 0.9 + index * 2.8, -2.4, 0, 0.18, 0.18, 3.3, C_TRIM)
        box(root, f"canteen_post_cap{index}", 0.82 + index * 2.8, -2.48, 3.25,
            0.34, 0.34, 0.12, C_ROOF_RED2)
    panel(root, "canteen_door", 10.6, 0.0, 0.4, 2.2, 2.4, C_DOOR)
    box(root, "canteen_door_l", 10.46, -0.08, 0.32, 0.1, 0.12, 2.62, C_TRIM)
    box(root, "canteen_door_r", 12.94, -0.08, 0.32, 0.1, 0.12, 2.62, C_TRIM)
    box(root, "canteen_step", 10.5, -1.0, 0, 2.4, 1.0, 0.22, C_STONE)
    # Low asymmetric gable roof, exhaust pipes and rooftop AC boxes.
    gable_roof(root, "canteen_roof", -0.5, -0.5, h, w + 1.0, d + 1.0, 2.6,
               C_ROOF_RED, C_ROOF_RED2)
    box(root, "canteen_roof_ridge", 2.0, 4.6, h + 2.55, 10.0, 0.28, 0.22, C_ROOF_RED2)
    box(root, "canteen_chimney_base", 12.4, 8.6, h + 0.6, 2.0, 1.4, 0.9, C_METAL)
    for index, (cx, height) in enumerate(((12.7, 2.4), (13.3, 2.0), (13.9, 2.7))):
        cylinder(root, f"canteen_pipe{index}", cx, 9.3, h + 1.5, 0.16, height, 6, C_METAL)
    for index in range(2):
        box(root, f"canteen_ac{index}", 3.0 + index * 2.4, 9.4, h + 0.4, 1.2, 0.8, 0.55, C_METAL)
    # 外侧售餐台
    box(root, "canteen_counter", 1.0, -2.9, 0.0, 5.0, 0.7, 0.95, C_WALL_CREAM2)
    box(root, "canteen_counter_top", 0.85, -3.0, 0.95, 5.3, 0.9, 0.14, C_TRIM)
    return root


# --------------------------------------------------------------------------- #
# 室内（16×10 房间 + 家具，家具随建筑性格不同）
# --------------------------------------------------------------------------- #
def build_interior(kind: str) -> "object":
    from panda3d.core import NodePath

    root = NodePath(f"model_interior_{kind}")
    w, d, h = 16.0, 10.0, 3.2
    box(root, "room_floor", 0, 0, 0, w, d, 0.2, (0.62, 0.55, 0.46))
    for name, (bx, by, bw, bd) in {"n": (0, d - 0.3, w, 0.3), "w": (0, 0, 0.3, d),
                                   "e": (w - 0.3, 0, 0.3, d)}.items():
        box(root, f"room_wall_{name}", bx, by, 0.2, bw, bd, h, (0.84, 0.82, 0.78))
    box(root, "room_board", 1.2, d - 0.34, 1.0, 4.0, 0.06, 1.6, (0.20, 0.26, 0.22))
    if kind == "dorm":
        box(root, "dorm_bed", 1.0, 1.2, 0.2, 2.2, 4.0, 0.55, (0.55, 0.68, 0.78))
        box(root, "dorm_pillow", 1.2, 1.4, 0.75, 1.8, 0.9, 0.25, (0.92, 0.90, 0.84))
        box(root, "dorm_desk", 3.8, 1.2, 0.2, 2.6, 1.2, 0.75, (0.56, 0.42, 0.30))
        box(root, "dorm_locker", 0.4, 6.6, 0.2, 1.8, 0.8, 2.2, (0.70, 0.66, 0.60))
    elif kind == "teaching":
        for index in range(4):
            box(root, f"teach_deskS{index}", 1.4 + index * 3.2, 2.2, 0.2,
                2.0, 0.8, 0.72, (0.56, 0.42, 0.30))
            box(root, f"teach_deskN{index}", 1.4 + index * 3.2, 4.4, 0.2,
                2.0, 0.8, 0.72, (0.56, 0.42, 0.30))
        box(root, "teach_podium", 11.6, 5.4, 0.2, 2.0, 1.0, 1.05, (0.50, 0.38, 0.27))
    elif kind == "library":
        for index in range(3):
            box(root, f"lib_shelf{index}", 1.0 + index * 2.2, 6.6, 0.2,
                1.8, 0.7, 2.1, (0.48, 0.36, 0.26))
        box(root, "lib_table", 6.0, 2.4, 0.2, 3.2, 2.4, 0.75, (0.52, 0.38, 0.26))
        for index in range(4):
            box(root, f"lib_chair{index}", 6.2 + (index % 2) * 1.8,
                1.6 + (index // 2) * 4.2, 0.2, 0.7, 0.7, 0.9, (0.42, 0.34, 0.26))
    elif kind == "club":
        box(root, "club_table", 3.0, 3.4, 0.2, 3.6, 1.6, 0.75, (0.56, 0.42, 0.30))
        for index in range(3):
            box(root, f"club_sofa{index}", 1.0 + index * 4.0, 1.4, 0.2,
                2.4, 1.0, 0.85, (0.62, 0.48, 0.52))
        box(root, "club_counter", 9.0, 6.6, 0.2, 5.0, 0.8, 1.05, (0.50, 0.38, 0.27))
    else:  # canteen
        for index in range(3):
            box(root, f"canteen_tray{index}", 1.2 + index * 4.6, 2.0, 0.2,
                3.4, 1.2, 0.78, (0.82, 0.82, 0.80))
            box(root, f"canteen_stool{index}", 2.2 + index * 4.6, 1.2, 0.2,
                0.5, 0.5, 0.55, (0.55, 0.42, 0.30))
        box(root, "canteen_service", 1.0, 7.6, 0.2, 10.0, 0.9, 1.1, (0.72, 0.72, 0.70))
    return root


# --------------------------------------------------------------------------- #
# 道具（单件，原点在西南角，Z 向上）
# --------------------------------------------------------------------------- #
def build_ground() -> "object":
    from panda3d.core import NodePath

    root = NodePath("model_ground")
    w, d = 80.0, 45.0
    # Local origin is the south-west corner; the layered soil slab follows the grass tile reference.
    box(root, "ground_soil_deep", 0, 0, -1.0, w, d, 0.45, (0.18, 0.17, 0.15))
    box(root, "ground_soil_mid", 0, 0, -0.55, w, d, 0.35, (0.27, 0.24, 0.20))
    box(root, "ground_lawn", 0, 0, -0.2, w, d, 0.2, C_GRASS)
    box(root, "ground_road_n", 58.0, 0, -0.18, 6.0, d, 0.2, C_PATH)
    box(root, "ground_road_w", 0, 21.0, -0.18, w, 5.0, 0.2, C_PATH)
    # Irregular darker patches and small tufts break up the otherwise flat top surface.
    for index, (px, py, sx, sy) in enumerate(((24, 35, 6.0, 3.5), (42, 17, 5.0, 3.0),
                                              (70, 33, 6.0, 3.5), (32, 4, 5.0, 3.0),
                                              (12, 12, 3.0, 2.0), (68, 7, 3.0, 2.0))):
        ellipsoid(root, f"ground_patch{index}", px, py, 0.025, sx, sy, 0.035, C_GRASS2, sides=8)
    for index, (px, py, scale) in enumerate(((18, 37, 1.0), (24, 35, 1.25), (43, 18, 0.9),
                                              (70, 33, 1.25), (31, 5, 0.85), (67, 8, 0.75))):
        for blade in range(4):
            grass_blade(root, f"ground_grass_{index}_{blade}", px + blade * 0.18 - 0.25,
                        py + (blade % 2) * 0.12, 0.03, 0.16 * scale, 0.65 * scale,
                        C_LEAF if blade % 2 else C_LEAF2, lean=(blade - 1.5) * 0.06)
    return root


def build_prop_tree():
    from panda3d.core import NodePath

    root = NodePath("model_prop_tree")
    box(root, "tree_trunk", -0.35, -0.35, 0, 0.7, 0.7, 2.6, (0.42, 0.32, 0.22))
    box(root, "tree_trunk_cap", -0.48, -0.48, 2.35, 0.96, 0.96, 0.35, (0.36, 0.27, 0.19))
    ellipsoid(root, "tree_canopy_left", -0.72, -0.1, 3.25, 1.2, 1.0, 1.0, C_LEAF)
    ellipsoid(root, "tree_canopy_right", 0.62, 0.1, 3.35, 1.15, 1.0, 1.0, C_LEAF2)
    ellipsoid(root, "tree_canopy_top", -0.05, 0.0, 4.2, 1.05, 0.95, 0.95, C_LEAF)
    return root


def build_prop_lamp():
    from panda3d.core import NodePath

    root = NodePath("model_prop_lamp")
    box(root, "lamp_base", -0.25, -0.25, 0, 0.5, 0.5, 0.2, C_METAL)
    box(root, "lamp_pole", -0.09, -0.09, 0.2, 0.18, 0.18, 4.0, C_METAL)
    box(root, "lamp_arm", -0.09, -0.09, 4.0, 0.18, 0.18, 0.28, C_METAL)
    box(root, "lamp_head", -0.34, -0.34, 4.1, 0.68, 0.68, 0.6, C_METAL)
    box(root, "lamp_glass", -0.25, -0.25, 4.2, 0.5, 0.5, 0.34, (0.95, 0.88, 0.62))
    box(root, "lamp_cap", -0.38, -0.38, 4.7, 0.76, 0.76, 0.12, C_METAL)
    return root


def build_prop_bench():
    from panda3d.core import NodePath

    root = NodePath("model_prop_bench")
    wood = (0.58, 0.44, 0.30)
    for index, x in enumerate((-0.1, 0.55, 1.2)):
        box(root, f"bench_seat_slats{index}", x, -0.4, 0.45, 0.58, 0.8, 0.14, wood)
        box(root, f"bench_back_slats{index}", x, 0.3, 0.72, 0.58, 0.14, 0.42, (0.52, 0.39, 0.27))
    for index, x in enumerate((0.05, 1.75)):
        rod(root, f"bench_leg_front{index}", (x, -0.32, 0.0), (x, -0.32, 0.48), 0.07, C_METAL, sides=5)
        rod(root, f"bench_leg_back{index}", (x, 0.32, 0.0), (x, 0.32, 0.48), 0.07, C_METAL, sides=5)
        rod(root, f"bench_leg_cross{index}", (x - 0.08, -0.32, 0.05), (x + 0.08, 0.32, 0.48),
            0.055, C_METAL, sides=5)
    return root


def build_prop_fence():
    from panda3d.core import NodePath

    root = NodePath("model_prop_fence")
    for index in (0, 1):
        box(root, f"fence_post{index}", index * 1.85, -0.1, 0, 0.16, 0.16, 1.1, C_STONE)
        box(root, f"fence_cap{index}", index * 1.85 - 0.04, -0.14, 1.1, 0.24, 0.24, 0.12, C_STONE)
    box(root, "fence_rail_top", 0, -0.07, 0.9, 2.0, 0.1, 0.12, C_STONE)
    box(root, "fence_rail_mid", 0, -0.07, 0.55, 2.0, 0.1, 0.12, C_STONE)
    return root


def build_prop_sign():
    from panda3d.core import NodePath

    root = NodePath("model_prop_sign")
    box(root, "sign_post", -0.08, -0.08, 0, 0.16, 0.16, 1.9, C_METAL)
    box(root, "sign_board", -0.8, -0.09, 1.1, 1.7, 0.12, 1.0, C_FRAME)
    box(root, "sign_board_inner", -0.67, -0.16, 1.22, 1.44, 0.06, 0.66, C_GLASS2)
    box(root, "sign_strip", -0.8, -0.11, 1.95, 1.7, 0.1, 0.16, C_ROOF_RED)
    return root


def build_prop_planter():
    from panda3d.core import NodePath

    root = NodePath("model_prop_planter")
    box(root, "planter_box", -0.7, -0.7, 0, 1.4, 1.4, 0.55, C_STONE)
    box(root, "planter_rim", -0.78, -0.78, 0.55, 1.56, 1.56, 0.16, C_FRAME)
    ellipsoid(root, "planter_shrub", 0, 0, 0.92, 0.62, 0.62, 0.55, C_LEAF2)
    ellipsoid(root, "planter_shrub_top", 0.12, -0.08, 1.18, 0.38, 0.38, 0.32, C_LEAF)
    return root


def build_prop_bin():
    from panda3d.core import NodePath

    root = NodePath("model_prop_bin")
    cylinder(root, "bin_body", 0, 0, 0, 0.34, 0.85, 8, (0.28, 0.42, 0.32))
    cylinder(root, "bin_lid", 0, 0, 0.85, 0.38, 0.12, 8, (0.22, 0.34, 0.26))
    return root


def build_prop_bike_rack():
    from panda3d.core import NodePath

    root = NodePath("model_prop_bike_rack")
    box(root, "rack_foot_l", -0.1, -0.4, 0, 1.2, 0.12, 0.1, C_METAL)
    box(root, "rack_foot_r", 1.0, -0.4, 0, 1.2, 0.12, 0.1, C_METAL)
    rod(root, "rack_bar", (0.2, -0.1, 0.1), (0.2, -0.1, 0.8), 0.07, C_METAL, sides=6)
    rod(root, "rack_bar_top", (0.2, -0.1, 0.8), (1.6, -0.1, 0.8), 0.07, C_METAL, sides=6)
    rod(root, "rack_up_l", (1.6, -0.1, 0.8), (1.6, -0.1, 0.1), 0.07, C_METAL, sides=6)
    rod(root, "rack_back", (0.2, 0.25, 0.1), (1.6, 0.25, 0.1), 0.06, C_METAL, sides=6)
    return root


def build_prop_flag_pole():
    from panda3d.core import NodePath

    root = NodePath("model_prop_flag_pole")
    box(root, "flag_base", -0.3, -0.3, 0, 0.6, 0.6, 0.25, C_STONE)
    cylinder(root, "flag_pole", 0, 0, 0.25, 0.08, 6.0, 6, C_FRAME)
    cylinder(root, "flag_finial", 0, 0, 6.2, 0.14, 0.25, 6, C_TRIM)
    quad(root, "flag_cloth", (0.1, -0.7, 5.6), (0.1, 0.0, 5.6),
         (0.1, 0.0, 4.7), (0.1, -0.7, 4.7), C_ROOF_RED)
    quad(root, "flag_cloth_blue", (0.1, -0.7, 5.55), (0.1, -0.34, 5.55),
         (0.1, -0.34, 4.75), (0.1, -0.7, 4.75), C_GLASS2)
    return root


def build_prop_rock():
    from panda3d.core import NodePath

    root = NodePath("model_prop_rock")
    import math

    sides = 6
    verts = []
    radius = 0.8
    for ring, (rr, zz) in enumerate(((radius, 0.0), (radius * 0.92, 0.45), (radius * 0.4, 0.85))):
        for index in range(sides):
            angle = 2 * math.pi * index / sides + ring * 0.35
            verts.append((rr * math.cos(angle), rr * math.sin(angle) * 0.8, zz))
    tris = []
    for ring in range(2):
        for index in range(sides):
            nxt = (index + 1) % sides
            a = ring * sides + index
            b = ring * sides + nxt
            c = (ring + 1) * sides + nxt
            d0 = (ring + 1) * sides + index
            tris += [(a, b, c), (a, c, d0)]
    top = len(verts)
    verts.append((0, 0, 1.1))
    for index in range(sides):
        nxt = (index + 1) % sides
        tris.append((2 * sides + index, 2 * sides + nxt, top))
    root.attachNewNode(_mesh("rock_body", verts, tris, (0.52, 0.52, 0.50)).node())
    return root


def build_prop_flower_bed():
    from panda3d.core import NodePath

    root = NodePath("model_prop_flower_bed")
    box(root, "bed_ground", -1.2, -0.6, 0, 2.4, 1.2, 0.18, (0.42, 0.32, 0.24))
    box(root, "bed_edge", -1.25, -0.65, 0.18, 2.5, 0.15, 0.28, C_ROOF_RED)
    box(root, "bed_edge_n", -1.25, 0.5, 0.18, 2.5, 0.15, 0.28, C_ROOF_RED)
    box(root, "bed_edge_w", -1.25, -0.65, 0.18, 0.15, 1.3, 0.28, C_ROOF_RED)
    box(root, "bed_edge_e", 1.1, -0.65, 0.18, 0.15, 1.3, 0.28, C_ROOF_RED)
    for index in range(6):
        color = (0.88, 0.57, 0.69) if index % 2 else (0.90, 0.85, 0.45)
        ellipsoid(root, f"flower{index}", -0.95 + index * 0.38, -0.1 + (index % 2) * 0.28,
                  0.5, 0.16, 0.16, 0.2, color, sides=6)
    return root


def build_prop_road():
    from panda3d.core import NodePath

    root = NodePath("model_prop_road")
    box(root, "road_slab", 0, 0, 0, 6.0, 6.0, 0.12, (0.62, 0.60, 0.56))
    box(root, "road_border_s", 0, -0.02, 0.12, 6.0, 0.12, 0.06, C_STONE)
    box(root, "road_border_n", 0, 5.9, 0.12, 6.0, 0.12, 0.06, C_STONE)
    box(root, "road_border_w", -0.02, 0, 0.12, 0.12, 6.0, 0.06, C_STONE)
    box(root, "road_border_e", 5.9, 0, 0.12, 0.12, 6.0, 0.06, C_STONE)
    for row in range(4):
        for col in range(4):
            box(root, f"road_tile_{row}_{col}", 0.35 + col * 1.35, 0.35 + row * 1.35, 0.12,
                1.1, 1.1, 0.02, (0.70, 0.68, 0.64) if (row + col) % 2 else (0.66, 0.64, 0.60))
    return root


PROPS = {
    "road": build_prop_road,
    "tree": build_prop_tree,
    "lamp": build_prop_lamp,
    "bench": build_prop_bench,
    "fence": build_prop_fence,
    "sign": build_prop_sign,
    "planter": build_prop_planter,
    "bin": build_prop_bin,
    "bike_rack": build_prop_bike_rack,
    "flag_pole": build_prop_flag_pole,
    "rock": build_prop_rock,
    "flower_bed": build_prop_flower_bed,
}

BUILDINGS = {
    "dorm": build_dorm,
    "teaching": build_teaching,
    "library": build_library,
    "club": build_club,
    "canteen": build_canteen,
}


def tri_count(root) -> int:
    """统计真实三角面数（GeomTriangles 的图元数），不是 mesh 个数。"""
    from panda3d.core import GeomNode

    total = 0
    for node in root.findAllMatches("**/+GeomNode"):
        geom_node = node.node()
        for index in range(geom_node.getNumGeoms()):
            geom = geom_node.getGeom(index)
            for prim_index in range(geom.getNumPrimitives()):
                primitive = geom.getPrimitive(prim_index)
                total += primitive.getNumPrimitives()
    return total


def save(root, path: Path) -> int:
    from panda3d.core import Filename

    tris = tri_count(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    ok = root.writeBamFile(Filename.fromOsSpecific(str(path)))
    if not ok:
        raise SystemExit(f"写入失败: {path}")
    print(f"  {path.name:<24} tri={tris:>5}  {path.stat().st_size // 1024} KB")
    return tris


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成低多边形校园模型")
    parser.add_argument("--out", default=str(ROOT / "assets" / "campus"))
    args = parser.parse_args(argv)
    out = Path(args.out)

    from panda3d.core import loadPrcFileData

    loadPrcFileData("", "window-type offscreen")
    loadPrcFileData("", "audio-library-name null")

    print("建筑：")
    total = 0
    for name, builder in BUILDINGS.items():
        total += save(builder(), out / f"{name}.bam")
        total += save(build_interior(name), out / f"interior_{name}.bam")
    total += save(build_ground(), out / "ground.bam")
    print("道具：")
    for name, builder in PROPS.items():
        total += save(builder(), out / "props" / f"{name}.bam")
    print(f"合计三角面 {total}（室外预算 30,000）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
