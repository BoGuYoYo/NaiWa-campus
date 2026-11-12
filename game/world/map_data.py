"""任务 C1~C4：地图、区域、建筑、室内房间与交互点数据的唯一入口。

本模块只处理空间数据（坐标、矩形、半径、场景归属），
禁止读写任何属性字段（academic / stamina / social / interest / mood / energy）。
所有坐标来自 content/world/map.json 与 content/world/interactables.json，代码中不得硬编码。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from game.world.collision import PLAYER_HALF, Rect, make_rect, overlap

CAMPUS_SCENE = "campus"
FACINGS = ("s", "se", "e", "ne", "n", "nw", "w", "sw")
INTERACTABLE_TYPES = ("activity", "npc", "inspect", "door", "save")


class _Point:
    """overlap() 只需要 .x / .y；这里避免为一次判断建完整 WorldPos。"""

    __slots__ = ("x", "y")

    def __init__(self, x: float, y: float) -> None:
        self.x = float(x)
        self.y = float(y)


_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")

_DIRECTION = {
    "e": (1.0, 0.0),
    "ne": (0.7071067811865476, 0.7071067811865476),
    "n": (0.0, 1.0),
    "nw": (-0.7071067811865476, 0.7071067811865476),
    "w": (-1.0, 0.0),
    "sw": (-0.7071067811865476, -0.7071067811865476),
    "s": (0.0, -1.0),
    "se": (0.7071067811865476, -0.7071067811865476),
}


class MapDataError(Exception):
    """地图或交互点数据缺失、越界或格式错误。"""


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    return (dx * dx + dy * dy) ** 0.5


@dataclass(frozen=True)
class Building:
    id: str
    name: str
    rect: Rect
    door: tuple[float, float]
    door_facing: str
    outside_trigger: tuple[float, float]


@dataclass(frozen=True)
class Area:
    id: str
    name: str
    rect: Rect


@dataclass(frozen=True)
class Furniture:
    id: str
    name: str
    rect: Rect


@dataclass(frozen=True)
class NpcMark:
    name: str
    x: float
    y: float


@dataclass(frozen=True)
class Interior:
    id: str
    origin: tuple[float, float]
    size: tuple[float, float]
    entry_mat: tuple[float, float]
    entry_radius: float
    spawn: tuple[float, float]
    spawn_facing: str
    furniture: tuple[Furniture, ...]
    npc_marks: tuple[NpcMark, ...]

    @property
    def center(self) -> tuple[float, float]:
        return (self.size[0] / 2.0, self.size[1] / 2.0)


@dataclass(frozen=True)
class Interactable:
    id: str
    name: str
    scene: str
    location_id: str
    x: float
    y: float
    radius: float
    type: str
    target: str


def _read_json(path: Path) -> Any:
    if not path.is_file():
        raise MapDataError(f"缺少数据文件：{path}")
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        raise MapDataError(f"{path} 不是合法 JSON：{exc}") from exc


def _check_id(value: Any, where: str) -> str:
    if not isinstance(value, str) or not _ID_RE.match(value):
        raise MapDataError(f"{where} 的 id 不合法（要求 ^[a-z][a-z0-9_]*$）：{value!r}")
    return value


def _check_rect(value: Any, where: str) -> Rect:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise MapDataError(f"{where} 的 rect 必须是 [x0, y0, x1, y1]：{value!r}")
    try:
        nums = [float(v) for v in value]
    except (TypeError, ValueError) as exc:
        raise MapDataError(f"{where} 的 rect 含非数值：{value!r}") from exc
    r = make_rect(*nums)
    if r.x1 - r.x0 <= 0.0 or r.y1 - r.y0 <= 0.0:
        raise MapDataError(f"{where} 的 rect 面积为 0：{value!r}")
    return r


def _check_point(value: Any, where: str) -> tuple[float, float]:
    if isinstance(value, dict):
        value = [value.get("x"), value.get("y")]
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise MapDataError(f"{where} 必须是 (x, y)：{value!r}")
    try:
        return (float(value[0]), float(value[1]))
    except (TypeError, ValueError) as exc:
        raise MapDataError(f"{where} 含非数值：{value!r}") from exc


def _check_facing(value: Any, where: str) -> str:
    if value not in FACINGS:
        raise MapDataError(f"{where} 的朝向必须是 {FACINGS} 之一：{value!r}")
    return value


class MapData:
    """加载并校验 content/world 下的两份数据文件，并提供查询接口。"""

    def __init__(self, raw_map: dict, raw_ia: dict):
        self._bounds = _check_rect(raw_map.get("outdoor", {}).get("bounds"), "outdoor.bounds")
        wall = raw_map.get("outdoor", {}).get("wall_thickness")
        if wall is None or float(wall) <= 0.0:
            raise MapDataError("outdoor.wall_thickness 必须为正数")
        self._outdoor_wall = float(wall)
        inner_wall = raw_map.get("interior_wall_thickness")
        if inner_wall is None or float(inner_wall) <= 0.0:
            raise MapDataError("interior_wall_thickness 必须为正数")
        self._interior_wall = float(inner_wall)

        spawn = raw_map.get("outdoor", {}).get("spawn", {})
        self._spawn = (
            _check_point(spawn, "outdoor.spawn"),
            _check_facing(spawn.get("facing"), "outdoor.spawn"),
            str(spawn.get("location_id", CAMPUS_SCENE)),
        )

        self._buildings = self._load_buildings(raw_map.get("buildings"))
        self._areas = self._load_areas(raw_map.get("areas"))
        self._props = self._load_props(raw_map.get("props", []))
        self._interiors = self._load_interiors(raw_map.get("interiors"))
        self._interactables = self._load_interactables(raw_ia.get("interactables"))
        self._validate_relations()

        self._collider_cache: dict[str, tuple[Rect, ...]] = {}

    # ---------------------------------------------------------------- 加载

    @classmethod
    def from_files(cls, map_path: Path | str, interactables_path: Path | str) -> "MapData":
        return cls(_read_json(Path(map_path)), _read_json(Path(interactables_path)))

    @classmethod
    def from_content_root(cls, content_root: Path | str) -> "MapData":
        root = Path(content_root)
        return cls.from_files(root / "world" / "map.json", root / "world" / "interactables.json")

    def _load_buildings(self, raw: Any) -> tuple[Building, ...]:
        if not isinstance(raw, list) or not raw:
            raise MapDataError("buildings 必须是非空数组")
        out: list[Building] = []
        seen: set[str] = set()
        for item in raw:
            bid = _check_id(item.get("id"), "buildings[]")
            if bid in seen:
                raise MapDataError(f"building id 重复：{bid}")
            seen.add(bid)
            rect = _check_rect(item.get("rect"), f"buildings[{bid}].rect")
            door = item.get("door")
            if not isinstance(door, dict):
                raise MapDataError(f"buildings[{bid}].door 缺失")
            outside = _check_point(item.get("outside_trigger"), f"buildings[{bid}].outside_trigger")
            if not self._inside(self._bounds, outside):
                raise MapDataError(f"buildings[{bid}].outside_trigger 在室外地图之外：{outside}")
            out.append(
                Building(
                    id=bid,
                    name=str(item.get("name", bid)),
                    rect=rect,
                    door=_check_point(door, f"buildings[{bid}].door"),
                    door_facing=_check_facing(door.get("facing"), f"buildings[{bid}].door"),
                    outside_trigger=outside,
                )
            )
        return tuple(out)

    def _load_areas(self, raw: Any) -> tuple[Area, ...]:
        if not isinstance(raw, list) or not raw:
            raise MapDataError("areas 必须是非空数组")
        out: list[Area] = []
        seen: set[str] = set()
        for item in raw:
            aid = _check_id(item.get("id"), "areas[]")
            if aid in seen:
                raise MapDataError(f"area id 重复：{aid}")
            seen.add(aid)
            out.append(
                Area(
                    id=aid,
                    name=str(item.get("name", aid)),
                    rect=_check_rect(item.get("rect"), f"areas[{aid}].rect"),
                )
            )
        return tuple(out)

    def _load_props(self, raw: Any) -> tuple[Furniture, ...]:
        if not isinstance(raw, list):
            raise MapDataError("props 必须是数组")
        return tuple(
            Furniture(
                id=_check_id(item.get("id"), "props[]"),
                name=str(item.get("name", item.get("id"))),
                rect=_check_rect(item.get("rect"), f"props[{item.get('id')}].rect"),
            )
            for item in raw
        )

    def _load_interiors(self, raw: Any) -> tuple[Interior, ...]:
        if not isinstance(raw, list) or not raw:
            raise MapDataError("interiors 必须是非空数组")
        out: list[Interior] = []
        seen: set[str] = set()
        for item in raw:
            iid = _check_id(item.get("id"), "interiors[]")
            if iid in seen:
                raise MapDataError(f"interior id 重复：{iid}")
            seen.add(iid)
            size = _check_point(item.get("size"), f"interiors[{iid}].size")
            if size[0] <= 0.0 or size[1] <= 0.0:
                raise MapDataError(f"interiors[{iid}].size 必须为正数：{size}")
            origin = _check_point(item.get("origin"), f"interiors[{iid}].origin")
            mat = item.get("entry_mat")
            if not isinstance(mat, dict):
                raise MapDataError(f"interiors[{iid}].entry_mat 缺失")
            mat_pos = _check_point(mat, f"interiors[{iid}].entry_mat")
            mat_radius = float(mat.get("radius", 0.0))
            if mat_radius <= 0.0:
                raise MapDataError(f"interiors[{iid}].entry_mat.radius 必须为正数")
            spawn = item.get("spawn")
            if not isinstance(spawn, dict):
                raise MapDataError(f"interiors[{iid}].spawn 缺失")
            spawn_pos = _check_point(spawn, f"interiors[{iid}].spawn")
            furniture = tuple(
                Furniture(
                    id=_check_id(f.get("id"), f"interiors[{iid}].furniture[]"),
                    name=str(f.get("name", f.get("id"))),
                    rect=_check_rect(f.get("rect"), f"interiors[{iid}].furniture[{f.get('id')}].rect"),
                )
                for f in item.get("furniture", [])
            )
            for furn in furniture:
                if not self._rect_inside(size, furn.rect):
                    raise MapDataError(f"interiors[{iid}] 家具越界：{furn.id}")
            marks = tuple(
                NpcMark(
                    name=str(m.get("name", "")),
                    x=float(m.get("x", 0.0)),
                    y=float(m.get("y", 0.0)),
                )
                for m in item.get("npc_marks", [])
            )
            for pos, label in ((mat_pos, "entry_mat"), (spawn_pos, "spawn")):
                if not self._inside(size, pos):
                    raise MapDataError(f"interiors[{iid}].{label} 在房间之外：{pos}")
            if _dist(spawn_pos, mat_pos) <= mat_radius:
                raise MapDataError(
                    f"interiors[{iid}] 的出生点落在入口地垫半径内，进入后会立刻被送回室外"
                )
            out.append(
                Interior(
                    id=iid,
                    origin=origin,
                    size=size,
                    entry_mat=mat_pos,
                    entry_radius=mat_radius,
                    spawn=spawn_pos,
                    spawn_facing=_check_facing(spawn.get("facing"), f"interiors[{iid}].spawn"),
                    furniture=furniture,
                    npc_marks=marks,
                )
            )
        return tuple(out)

    def _load_interactables(self, raw: Any) -> tuple[Interactable, ...]:
        if not isinstance(raw, list) or not raw:
            raise MapDataError("interactables 必须是非空数组")
        out: list[Interactable] = []
        seen: set[str] = set()
        for item in raw:
            iid = _check_id(item.get("id"), "interactables[]")
            if iid in seen:
                raise MapDataError(f"interactable id 重复：{iid}")
            seen.add(iid)
            kind = item.get("type")
            if kind not in INTERACTABLE_TYPES:
                raise MapDataError(f"interactables[{iid}].type 不合法：{kind!r}")
            target = item.get("target")
            if not isinstance(target, str) or not target:
                raise MapDataError(f"interactables[{iid}].target 必须是非空字符串")
            radius = float(item.get("radius", 0.0))
            if radius <= 0.0:
                raise MapDataError(f"interactables[{iid}].radius 必须为正数")
            out.append(
                Interactable(
                    id=iid,
                    name=str(item.get("name", iid)),
                    scene=str(item.get("scene", CAMPUS_SCENE)),
                    location_id=str(item.get("location_id", "")),
                    x=float(item.get("x", 0.0)),
                    y=float(item.get("y", 0.0)),
                    radius=radius,
                    type=str(kind),
                    target=target,
                )
            )
        return tuple(out)

    def _validate_relations(self) -> None:
        building_ids = {b.id for b in self._buildings}
        interior_ids = {i.id for i in self._interiors}
        if building_ids != interior_ids:
            raise MapDataError(
                f"每栋建筑必须恰好有一个室内房间：建筑 {sorted(building_ids)} / 室内 {sorted(interior_ids)}"
            )
        for ia in self._interactables:
            if ia.scene == CAMPUS_SCENE:
                if not self._inside(self._bounds, (ia.x, ia.y)):
                    raise MapDataError(f"interactables[{ia.id}] 在室外地图之外：({ia.x}, {ia.y})")
            else:
                if ia.scene not in interior_ids:
                    raise MapDataError(f"interactables[{ia.id}].scene 不是已知建筑：{ia.scene}")
                interior = self.interior(ia.scene)
                if not self._inside(interior.size, (ia.x, ia.y)):
                    raise MapDataError(f"interactables[{ia.id}] 在房间之外：({ia.x}, {ia.y})")
            if ia.type == "door" and ia.target not in building_ids:
                raise MapDataError(f"interactables[{ia.id}] 的门目标不是建筑：{ia.target}")

    # ------------------------------------------------------------ 基础查询

    @property
    def bounds(self) -> Rect:
        return self._bounds

    @property
    def outdoor_wall_thickness(self) -> float:
        return self._outdoor_wall

    @property
    def interior_wall_thickness(self) -> float:
        return self._interior_wall

    @property
    def spawn(self) -> tuple[tuple[float, float], str, str]:
        return self._spawn

    @property
    def buildings(self) -> tuple[Building, ...]:
        return self._buildings

    @property
    def areas(self) -> tuple[Area, ...]:
        return self._areas

    @property
    def props(self) -> tuple[Furniture, ...]:
        return self._props

    @property
    def interiors(self) -> tuple[Interior, ...]:
        return self._interiors

    @property
    def interactables(self) -> tuple[Interactable, ...]:
        return self._interactables

    def building(self, building_id: str) -> Building:
        for b in self._buildings:
            if b.id == building_id:
                return b
        raise MapDataError(f"未知建筑：{building_id}")

    def interior(self, building_id: str) -> Interior:
        for i in self._interiors:
            if i.id == building_id:
                return i
        raise MapDataError(f"未知室内房间：{building_id}")

    def has_interior(self, location_id: str) -> bool:
        return any(i.id == location_id for i in self._interiors)

    def area(self, area_id: str) -> Area:
        for a in self._areas:
            if a.id == area_id:
                return a
        raise MapDataError(f"未知区域：{area_id}")

    def area_at(self, x: float, y: float) -> str | None:
        """返回包含该点的区域 id；多个区域重叠时按 map.json 中的先后顺序取第一个。"""
        for a in self._areas:
            if self._inside(a.rect, (x, y)):
                return a.id
        return None

    def nearest_area(self, x: float, y: float) -> str | None:
        """离该点最近的区域 id（点在区域外时用）。

        建筑门口、绿地这些没有登记区域的位置也要有个室外归属：否则
        ``WorldPos.location_id`` 会停在建筑 id 上，``scene_of()`` 一直判成室内，
        户外交互点全部查不到（提示框显示「内容缺失」）。
        """
        best_id: str | None = None
        best_dist: float | None = None
        for a in self._areas:
            dx = max(a.rect.x0 - x, 0.0, x - a.rect.x1)
            dy = max(a.rect.y0 - y, 0.0, y - a.rect.y1)
            dist = (dx * dx + dy * dy) ** 0.5
            if best_dist is None or dist < best_dist:
                best_id, best_dist = a.id, dist
        return best_id

    def outdoor_location_at(self, x: float, y: float, fallback: str = "loc_gate") -> str:
        """室外坐标 → 地点 id：先找所在区域，再找最近区域，最后用 fallback。"""
        return self.area_at(x, y) or self.nearest_area(x, y) or fallback

    def interactable(self, ia_id: str) -> Interactable:
        for ia in self._interactables:
            if ia.id == ia_id:
                return ia
        raise MapDataError(f"未知交互点：{ia_id}")

    def interactables_for(self, scene: str) -> tuple[Interactable, ...]:
        return tuple(ia for ia in self._interactables if ia.scene == scene)

    def to_world(self, ia: Interactable) -> tuple[float, float]:
        """把交互点坐标统一换算到世界坐标（室内为 房间原点 + 本地坐标）。"""
        if ia.scene == CAMPUS_SCENE:
            return (ia.x, ia.y)
        origin = self.interior(ia.scene).origin
        return (origin[0] + ia.x, origin[1] + ia.y)

    def world_to_local(self, building_id: str, x: float, y: float) -> tuple[float, float]:
        origin = self.interior(building_id).origin
        return (x - origin[0], y - origin[1])

    # -------------------------------------------------------------- 出入口

    #: 出门落点离门触发点的距离。必须大于门的交互半径（1.2 米），否则刚出门
    #: 就地站在「进入」提示里，连按 E 会立刻被送回室内。
    EXIT_DISTANCE = 1.8

    def exit_point(self, building_id: str) -> tuple[float, float, str]:
        """从室外门触发点再向外（EXIT_DISTANCE 米），朝向背离建筑。"""
        b = self.building(building_id)
        nx, ny = _DIRECTION[b.door_facing]
        return (b.outside_trigger[0] + nx * self.EXIT_DISTANCE,
                b.outside_trigger[1] + ny * self.EXIT_DISTANCE,
                b.door_facing)

    def interior_entry(self, building_id: str) -> tuple[float, float, str]:
        """进入室内后的出生位置（房间本地坐标）。"""
        i = self.interior(building_id)
        return (i.spawn[0], i.spawn[1], i.spawn_facing)

    def interior_center(self, building_id: str) -> tuple[float, float]:
        return self.interior(building_id).center

    def entry_mat(self, building_id: str) -> tuple[float, float, float]:
        i = self.interior(building_id)
        return (i.entry_mat[0], i.entry_mat[1], i.entry_radius)

    # ------------------------------------------------------------ 位置校验

    def is_blocked(self, location_id: str, x: float, y: float,
                   half: float = PLAYER_HALF) -> bool:
        """世界坐标 (x, y) 是否落在阻挡体内或地图之外。

        读档位置校验用：存档里的坐标可能来自旧地图、或存于"人卡在墙里"的状态，
        直接拿来建场景会让玩家走不动。室内按房间原点平移到世界坐标后判断。
        """
        if self.has_interior(location_id):
            i = self.interior(location_id)
            ox, oy = i.origin
            rects = tuple(
                Rect(r.x0 + ox, r.y0 + oy, r.x1 + ox, r.y1 + oy)
                for r in self.colliders_for(location_id)
            )
            bounds = make_rect(ox, oy, ox + i.size[0], oy + i.size[1])
        else:
            rects = self.colliders_for(CAMPUS_SCENE)
            bounds = self._bounds
        if not (bounds.x0 + half <= x <= bounds.x1 - half
                and bounds.y0 + half <= y <= bounds.y1 - half):
            return True
        pos = _Point(x, y)
        return any(overlap(pos, half, r) for r in rects)

    def safe_position(self, location_id: str) -> tuple[float, float, str]:
        """该地点的安全落点（世界坐标 + 朝向）：室内取房间出生点，室外取广场出生点。"""
        if self.has_interior(location_id):
            i = self.interior(location_id)
            ox, oy = i.origin
            return (ox + i.spawn[0], oy + i.spawn[1], i.spawn_facing)
        (sx, sy), facing, _loc = self.spawn
        return (sx, sy, facing)

    # ---------------------------------------------------------------- 碰撞

    def outdoor_walls(self) -> tuple[Rect, ...]:
        t = self._outdoor_wall
        b = self._bounds
        return (
            make_rect(b.x0, b.y0, b.x1, b.y0 + t),
            make_rect(b.x0, b.y1 - t, b.x1, b.y1),
            make_rect(b.x0, b.y0, b.x0 + t, b.y1),
            make_rect(b.x1 - t, b.y0, b.x1, b.y1),
        )

    def interior_walls(self, building_id: str) -> tuple[Rect, ...]:
        """房间四面墙；**南墙在门口留一个洞**。

        旧版四面全封：玩家撞到南墙就停住，看不到门在哪，入口地垫只能靠贴着墙
        横着蹭到 x=8 才踩得到，实机上就是"交互完出不去、像有空气墙"。
        这里把南墙按地垫 x 切成两段，缺口本身也是出口的视觉提示。
        """
        i = self.interior(building_id)
        t = self._interior_wall
        w, h = i.size
        door_x = float(i.entry_mat[0])
        gap = 1.2
        left = max(0.0, door_x - gap)
        right = min(w, door_x + gap)
        walls = [
            make_rect(0.0, h - t, w, h),      # 北墙
            make_rect(0.0, 0.0, t, h),        # 西墙
            make_rect(w - t, 0.0, w, h),      # 东墙
        ]
        if left > 0.0:
            walls.append(make_rect(0.0, 0.0, left, t))     # 南墙·门西
        if right < w:
            walls.append(make_rect(right, 0.0, w, t))      # 南墙·门东
        return tuple(walls)

    def colliders_for(self, scene: str) -> tuple[Rect, ...]:
        """返回该场景的阻挡矩形。campus 为世界坐标，室内为房间本地坐标。"""
        cached = self._collider_cache.get(scene)
        if cached is not None:
            return cached
        if scene == CAMPUS_SCENE:
            rects = list(self.outdoor_walls())
            rects.extend(b.rect for b in self._buildings)
            rects.extend(p.rect for p in self._props)
        elif self.has_interior(scene):
            rects = list(self.interior_walls(scene))
            rects.extend(f.rect for f in self.interior(scene).furniture)
        else:
            raise MapDataError(f"未知场景：{scene}")
        result = tuple(rects)
        self._collider_cache[scene] = result
        return result

    # ---------------------------------------------------------------- 工具

    @staticmethod
    def _inside(rect: Rect | tuple[float, float], point: tuple[float, float]) -> bool:
        if isinstance(rect, Rect):
            x0, y0, x1, y1 = rect
        else:
            x0, y0 = 0.0, 0.0
            x1, y1 = rect
        x, y = point
        return x0 <= x <= x1 and y0 <= y <= y1

    @staticmethod
    def _rect_inside(size: tuple[float, float], rect: Rect) -> bool:
        return 0.0 <= rect.x0 and rect.x1 <= size[0] and 0.0 <= rect.y0 and rect.y1 <= size[1]
