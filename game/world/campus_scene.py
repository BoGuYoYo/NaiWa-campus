"""任务 C1~C3：室外校园场景（白模）。

按 content/world/map.json 生成地面、区域、5 栋建筑、室外物件、门与出生点标记；
所有坐标都来自 map_data，代码中不硬编码。加载完成后 flattenStrong()。

本模块同时提供供 interior_scene.py / debug_draw.py 复用的几何辅助函数。
"""

from __future__ import annotations

import math

from panda3d.core import (
    Geom,
    GeomLines,
    GeomNode,
    GeomTriangles,
    GeomVertexData,
    GeomVertexFormat,
    GeomVertexWriter,
    NodePath,
)

from game.world.collision import Rect

CAMPUS_SCENE = "campus"

GROUND_COLOR = (0.42, 0.55, 0.35, 1.0)  # 草地
AREA_COLORS = {
    "loc_gate": (0.72, 0.70, 0.62, 1.0),
    "loc_playground": (0.62, 0.50, 0.36, 1.0),
    "loc_plaza": (0.70, 0.70, 0.66, 1.0),
    "road_main": (0.55, 0.55, 0.52, 1.0),
    "road_east_west": (0.55, 0.55, 0.52, 1.0),
    "road_north": (0.55, 0.55, 0.52, 1.0),
}
BUILDING_COLOR = (0.82, 0.82, 0.84, 1.0)
BUILDING_HEIGHT = 6.0
PROP_COLOR = (0.55, 0.40, 0.24, 1.0)
PROP_HEIGHT = 0.9
DOOR_COLOR = (0.85, 0.24, 0.20, 1.0)
DOOR_HEIGHT = 2.2
SPAWN_COLOR = (0.96, 0.85, 0.18, 1.0)

Z_GROUND = 0.0
#: 区域分层：同一高度的两块面片重叠会 z-fighting（道路上叠广场时会闪条纹）。
#: 三条道路彼此相交，因此各给一个高度；区域（广场/操场/校门）高于道路。
AREA_Z = {
    "road_main": 0.010,
    "road_east_west": 0.012,
    "road_north": 0.014,
    "loc_gate": 0.020,
    "loc_playground": 0.022,
    "loc_plaza": 0.024,
}
Z_AREA = 0.020  # 未登记区域的兜底高度


# --------------------------------------------------------------- 几何辅助


def make_box(parent: NodePath, x0: float, y0: float, x1: float, y1: float, z0: float, z1: float, color) -> NodePath:
    """在 parent 下生成一个长方体（缺少底面，双面渲染，关闭光照）。"""
    fmt = GeomVertexFormat.getV3n3c4()
    vdata = GeomVertexData("box", fmt, Geom.UHStatic)
    vdata.setNumRows(20)
    vw = GeomVertexWriter(vdata, "vertex")
    nw = GeomVertexWriter(vdata, "normal")
    cw = GeomVertexWriter(vdata, "color")
    tris = GeomTriangles(Geom.UHStatic)

    faces = (
        ((0, 0, 1), [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]),  # 顶
        ((0, -1, 0), [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)]),  # 南
        ((0, 1, 0), [(x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1)]),  # 北
        ((-1, 0, 0), [(x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1)]),  # 西
        ((1, 0, 0), [(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)]),  # 东
    )
    r, g, b, a = color
    i = 0
    for normal, corners in faces:
        for vx, vy, vz in corners:
            vw.addData3(vx, vy, vz)
            nw.addData3(*normal)
            cw.addData4(r, g, b, a)
        tris.addVertices(i, i + 1, i + 2)
        tris.addVertices(i, i + 2, i + 3)
        i += 4

    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode("box")
    node.addGeom(geom)
    np = parent.attachNewNode(node)
    np.setTwoSided(True)
    np.setLightOff()
    return np


def make_ground(parent: NodePath, x0: float, y0: float, x1: float, y1: float, z: float, color) -> NodePath:
    """一块水平面片（朝上）。"""
    fmt = GeomVertexFormat.getV3n3c4()
    vdata = GeomVertexData("quad", fmt, Geom.UHStatic)
    vdata.setNumRows(4)
    vw = GeomVertexWriter(vdata, "vertex")
    nw = GeomVertexWriter(vdata, "normal")
    cw = GeomVertexWriter(vdata, "color")
    r, g, b, a = color
    for vx, vy in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        vw.addData3(vx, vy, z)
        nw.addData3(0, 0, 1)
        cw.addData4(r, g, b, a)
    tris = GeomTriangles(Geom.UHStatic)
    tris.addVertices(0, 1, 2)
    tris.addVertices(0, 2, 3)
    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode("ground")
    node.addGeom(geom)
    np = parent.attachNewNode(node)
    np.setTwoSided(True)
    np.setLightOff()
    return np


def _make_lines(parent: NodePath, points, z: float, color, thickness: float, name: str) -> NodePath:
    """用 GeomLines 画一组线段（points 为 [(x, y), ...]，两两成段）。

    注意：Panda3D 1.10.16 的 GeomLinestrips 既不渲染，又会让 flattenStrong()
    踩内存断言（图书馆/食堂室内构造即崩），所以这里一律用 GeomLines。
    """
    fmt = GeomVertexFormat.getV3c4()
    vdata = GeomVertexData(name, fmt, Geom.UHStatic)
    vw = GeomVertexWriter(vdata, "vertex")
    cw = GeomVertexWriter(vdata, "color")
    r, g, b, a = color
    for vx, vy in points:
        vw.addData3(vx, vy, z)
        cw.addData4(r, g, b, a)
    lines = GeomLines(Geom.UHStatic)
    for i in range(0, len(points) - 1, 2):
        lines.addVertices(i, i + 1)
    geom = Geom(vdata)
    geom.addPrimitive(lines)
    node = GeomNode(name)
    node.addGeom(geom)
    np = parent.attachNewNode(node)
    np.setLightOff()
    np.setRenderModeThickness(thickness)
    return np


def make_rect_lines(parent: NodePath, x0: float, y0: float, x1: float, y1: float, z: float, color, thickness: float = 2.0) -> NodePath:
    """矩形的线框（F1 碰撞调试用）。"""
    corners = [(x0, y0), (x1, y0), (x1, y0), (x1, y1), (x1, y1), (x0, y1), (x0, y1), (x0, y0)]
    return _make_lines(parent, corners, z, color, thickness, "rect_lines")


def make_circle_lines(parent: NodePath, cx: float, cy: float, radius: float, z: float, color, segments: int = 32, thickness: float = 2.0) -> NodePath:
    """水平圆环（F2 交互点 / 入口地垫 / NPC 站位用）。"""
    points = []
    for i in range(segments):
        a0 = 2.0 * math.pi * i / segments
        a1 = 2.0 * math.pi * (i + 1) / segments
        points.append((cx + radius * math.cos(a0), cy + radius * math.sin(a0)))
        points.append((cx + radius * math.cos(a1), cy + radius * math.sin(a1)))
    return _make_lines(parent, points, z, color, thickness, "circle_lines")


def make_triangle_marker(parent: NodePath, x: float, y: float, z: float, size: float, color) -> NodePath:
    """出生点的黄色三角标记（朝北）。"""
    fmt = GeomVertexFormat.getV3n3c4()
    vdata = GeomVertexData("tri", fmt, Geom.UHStatic)
    vdata.setNumRows(3)
    vw = GeomVertexWriter(vdata, "vertex")
    nw = GeomVertexWriter(vdata, "normal")
    cw = GeomVertexWriter(vdata, "color")
    r, g, b, a = color
    for vx, vy in ((x, y + size), (x - size * 0.87, y - size * 0.5), (x + size * 0.87, y - size * 0.5)):
        vw.addData3(vx, vy, z)
        nw.addData3(0, 0, 1)
        cw.addData4(r, g, b, a)
    tris = GeomTriangles(Geom.UHStatic)
    tris.addVertices(0, 1, 2)
    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode("tri")
    node.addGeom(geom)
    np = parent.attachNewNode(node)
    np.setTwoSided(True)
    np.setLightOff()
    return np


def rect_tuple(r: Rect) -> tuple[float, float, float, float]:
    return (r.x0, r.y0, r.x1, r.y1)


# --------------------------------------------------------------- 场景本体


class CampusScene:
    """室外场景：静态几何 + 碰撞 + 出生点。scene_id = "CampusScene"。"""

    scene_id = "CampusScene"

    def __init__(self, map_data, parent: NodePath, *, dev: bool = False):
        self.map_data = map_data
        self.root = parent.attachNewNode("CampusScene")
        self.dev = dev
        self.colliders = map_data.colliders_for(CAMPUS_SCENE)
        self.bounds = map_data.bounds
        self._build()

    def _build(self) -> None:
        b = self.bounds
        make_ground(self.root, b.x0, b.y0, b.x1, b.y1, Z_GROUND, GROUND_COLOR)

        for area in self.map_data.areas:
            color = AREA_COLORS.get(area.id, (0.6, 0.6, 0.6, 1.0))
            z = AREA_Z.get(area.id, Z_AREA)
            make_ground(self.root, area.rect.x0, area.rect.y0, area.rect.x1, area.rect.y1, z, color)

        for building in self.map_data.buildings:
            r = building.rect
            make_box(self.root, r.x0, r.y0, r.x1, r.y1, 0.0, BUILDING_HEIGHT, BUILDING_COLOR)
            dx, dy = building.door
            make_box(self.root, dx - 1.2, dy - 0.15, dx + 1.2, dy + 0.15, 0.0, DOOR_HEIGHT, DOOR_COLOR)

        for prop in self.map_data.props:
            r = prop.rect
            make_box(self.root, r.x0, r.y0, r.x1, r.y1, 0.0, PROP_HEIGHT, PROP_COLOR)

        spawn_pos, _facing, _loc = self.map_data.spawn
        make_triangle_marker(self.root, spawn_pos[0], spawn_pos[1], 0.3, 1.2, SPAWN_COLOR)

        self.root.flattenStrong()

    def destroy(self) -> None:
        self.root.removeNode()
