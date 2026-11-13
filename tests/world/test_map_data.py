"""任务 C1~C4 独立测试：地图数据、建筑/区域/室内、交互点表与数据校验。"""

from __future__ import annotations

import copy
import json
import pathlib

import pytest

from game.world.collision import PLAYER_HALF, overlap
from game.world.map_data import (
    CAMPUS_SCENE,
    Building,
    Interactable,
    Interior,
    MapData,
    MapDataError,
)

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"


def _raw_map() -> dict:
    return json.loads((FIXTURES / "test_map.json").read_text(encoding="utf-8"))


def _raw_ia() -> dict:
    return json.loads((FIXTURES / "test_interactables.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------- 表 11 建筑

# 2026-11-11 起：占地取 Blender 世界包围盒，门取立面图上画出来的入口
# （content/world/building_visuals.json 的 door_anchor_u），统一开在南侧；
# 由 tools/align_building_doors.py 生成，改图后重跑该脚本并同步本表。
DOC_BUILDINGS = {
    "loc_dorm": ((3.915, 9.723, 18.055, 23.939), (16.924, 9.723), "s", (16.924, 8.923)),
    "loc_classroom": ((4.676, 31.673, 20.669, 47.726), (18.35, 31.673), "s", (18.35, 30.873)),
    "loc_library": ((59.602, 31.817, 75.778, 48.008), (64.568, 31.817), "s", (64.568, 31.017)),
    "loc_clubroom": ((61.56, 12.923, 76.107, 27.429), (64.033, 12.923), "s", (64.033, 12.123)),
    "loc_canteen": ((30.0, 48.0, 50.0, 58.0), (40.0, 48.0), "s", (40.0, 47.2)),
}

# --------------------------------------------------------------- 表 12 区域

DOC_AREAS = {
    "loc_gate": (34.0, 0.0, 46.0, 8.0),
    "loc_playground": (22.0, 10.0, 34.0, 24.0),
    "loc_plaza": (30.0, 26.0, 50.0, 42.0),
    "road_main": (37.0, 0.0, 43.0, 48.0),
    "road_east_west": (18.0, 15.0, 62.0, 19.0),
    "road_north": (20.0, 38.0, 60.0, 42.0),
}

# ----------------------------------------------------------- 表 13 室内原点

DOC_INTERIOR_ORIGINS = {
    "loc_dorm": (200.0, 0.0),
    "loc_classroom": (220.0, 0.0),
    "loc_library": (240.0, 0.0),
    "loc_clubroom": (260.0, 0.0),
    "loc_canteen": (280.0, 0.0),
}

# --------------------------------------------------------- 表 14 交互点坐标

DOC_INTERACTABLES = {
    "ia_gate_notice": ("campus", 43.0, 4.0, 1.5, "inspect", "inspect.gate_notice"),
    "ia_track_start": ("campus", 28.0, 17.0, 2.0, "activity", "exercise"),
    "ia_plaza_bench": ("campus", 40.0, 33.0, 1.5, "activity", "campus_walk"),
    "ia_class_desk": ("loc_classroom", 8.0, 6.0, 1.2, "activity", "attend_class"),
    "ia_course_board": ("loc_classroom", 3.0, 9.0, 1.2, "inspect", "inspect.course_board"),
    "ia_reading_desk": ("loc_library", 6.0, 5.0, 1.2, "activity", "library_study"),
    "ia_bookshelf": ("loc_library", 2.0, 8.0, 1.2, "inspect", "inspect.bookshelf"),
    "ia_npc_sumo": ("loc_library", 11.0, 6.0, 1.3, "npc", "npc_sumo"),
    "ia_librarian": ("loc_library", 13.0, 2.0, 1.3, "inspect", "inspect.librarian"),
    "ia_bed": ("loc_dorm", 3.0, 7.0, 1.2, "activity", "rest_dorm"),
    "ia_dorm_desk": ("loc_dorm", 12.0, 7.0, 1.2, "save", "save_point"),
    "ia_game_pc": ("loc_clubroom", 3.0, 7.0, 1.2, "activity", "play_games"),
    "ia_easel": ("loc_clubroom", 8.0, 8.0, 1.2, "activity", "create_work"),
    "ia_club_board": ("loc_clubroom", 13.0, 8.0, 1.2, "activity", "join_club"),
    "ia_npc_chenlang": ("loc_clubroom", 12.0, 5.0, 1.3, "npc", "npc_chenlang"),
    "ia_food_window": ("loc_canteen", 8.0, 8.5, 1.5, "activity", "eat_canteen"),
    "ia_npc_xiaoyou": ("loc_canteen", 13.0, 4.0, 1.3, "npc", "npc_xiaoyou"),
    "ia_canteen_aunt": ("loc_canteen", 5.0, 8.5, 1.3, "inspect", "inspect.canteen_aunt"),
    "ia_door_dorm": ("campus", 16.924, 8.923, 1.2, "door", "loc_dorm"),
    "ia_door_classroom": ("campus", 18.35, 30.873, 1.2, "door", "loc_classroom"),
    "ia_door_library": ("campus", 64.568, 31.017, 1.2, "door", "loc_library"),
    "ia_door_clubroom": ("campus", 64.033, 12.123, 1.2, "door", "loc_clubroom"),
    "ia_door_canteen": ("campus", 40.0, 47.2, 1.2, "door", "loc_canteen"),
}


def test_buildings_match_spec_table(map_data):
    assert len(map_data.buildings) == 5
    for b in map_data.buildings:
        rect, door, facing, trigger = DOC_BUILDINGS[b.id]
        assert isinstance(b, Building)
        assert (b.rect.x0, b.rect.y0, b.rect.x1, b.rect.y1) == rect
        assert b.door == door
        assert b.door_facing == facing
        assert b.outside_trigger == trigger


def test_areas_match_spec_table(map_data):
    assert len(map_data.areas) == 6
    for a in map_data.areas:
        rect = DOC_AREAS[a.id]
        assert (a.rect.x0, a.rect.y0, a.rect.x1, a.rect.y1) == rect


def test_interior_origins_and_size(map_data):
    assert len(map_data.interiors) == 5
    for interior in map_data.interiors:
        assert isinstance(interior, Interior)
        assert interior.origin == DOC_INTERIOR_ORIGINS[interior.id]
        assert interior.size == (16.0, 10.0)


def test_interior_entry_mat_and_spawn(map_data):
    for interior in map_data.interiors:
        assert interior.entry_mat == (8.0, 0.6)
        assert interior.entry_radius == 0.8
        assert interior.spawn == (8.0, 1.6)
        assert interior.spawn_facing == "n"


def test_buildings_and_interiors_are_one_to_one(map_data):
    assert [b.id for b in map_data.buildings] == [i.id for i in map_data.interiors]


def test_spawn_point(map_data):
    pos, facing, location_id = map_data.spawn
    assert pos == (40.0, 5.0)
    assert facing == "n"
    assert location_id == "loc_gate"


def test_interactables_match_spec_table(map_data):
    assert len(map_data.interactables) == 23
    by_id = {ia.id: ia for ia in map_data.interactables}
    assert set(by_id) == set(DOC_INTERACTABLES)
    for ia_id, (scene, x, y, radius, kind, target) in DOC_INTERACTABLES.items():
        ia = by_id[ia_id]
        assert isinstance(ia, Interactable)
        assert (ia.scene, ia.x, ia.y, ia.radius, ia.type, ia.target) == (scene, x, y, radius, kind, target)


def test_interactable_type_counts(map_data):
    counts: dict[str, int] = {}
    for ia in map_data.interactables:
        counts[ia.type] = counts.get(ia.type, 0) + 1
    assert counts == {"activity": 9, "npc": 3, "inspect": 5, "save": 1, "door": 5}


def test_interactables_for_scene(map_data):
    campus = map_data.interactables_for(CAMPUS_SCENE)
    assert len(campus) == 8  # 3 室外 + 5 扇门
    assert len(map_data.interactables_for("loc_library")) == 4  # 阅览桌 + 书架 + 苏墨 + 图书管理员
    assert len(map_data.interactables_for("loc_dorm")) == 2


def test_to_world_offsets_interior_coordinates(map_data):
    desk = map_data.interactable("ia_reading_desk")
    assert map_data.to_world(desk) == (246.0, 5.0)
    gate = map_data.interactable("ia_gate_notice")
    assert map_data.to_world(gate) == (43.0, 4.0)
    assert map_data.world_to_local("loc_library", 246.0, 5.0) == (6.0, 5.0)


def test_area_at_returns_first_matching_area(map_data):
    assert map_data.area_at(40.0, 5.0) == "loc_gate"  # 与 road_main 重叠时取先声明者
    assert map_data.area_at(28.0, 17.0) == "loc_playground"
    assert map_data.area_at(40.0, 30.0) == "loc_plaza"
    assert map_data.area_at(50.0, 50.0) is None


def test_nearest_area_falls_back_for_points_outside_every_area(map_data):
    assert map_data.area_at(16.924, 7.923) is None      # 宿舍楼门前的草地不在任何区域内
    assert map_data.nearest_area(16.924, 7.923) == "loc_playground"
    assert map_data.outdoor_location_at(16.924, 7.923) == "loc_playground"
    # 区域内仍以 area_at 为准
    assert map_data.outdoor_location_at(40.0, 5.0) == "loc_gate"


def test_exit_points_always_land_outside(map_data):
    """回归：出口地点不能停在建筑 id 上。

    BUG-25：宿舍楼门挪到南侧后，出口 (16.924, 7.923) 不落在任何登记区域里，
    location_id 于是保留成 loc_dorm，scene_of() 一直判成室内，
    户外交互点全部变成「内容缺失」。
    """
    for building in map_data.buildings:
        ex, ey, _facing = map_data.exit_point(building.id)
        location = map_data.outdoor_location_at(ex, ey)
        assert not map_data.has_interior(location), f"{building.id} 出口地点仍是室内：{location}"


def test_exit_point_is_outside_the_door_trigger_radius(map_data):
    """出门落点必须离开门的交互半径。

    BUG：旧版落点只离门 1.0 米，而门的交互半径是 1.2 米 —— 刚出室内就站在
    「进入」提示里，连按 E 会立刻被送回室内。现在落点固定 1.8 米。
    """
    assert map_data.exit_point("loc_dorm") == (16.924, 7.123, "s")
    assert map_data.exit_point("loc_library") == (64.568, 29.217, "s")
    assert map_data.exit_point("loc_canteen")[:2] == pytest.approx((40.0, 45.4))
    doors = {ia.id: ia for ia in map_data.interactables if ia.id.startswith("ia_door_")}
    for building in map_data.buildings:
        ex, ey, _facing = map_data.exit_point(building.id)
        door = doors[f"ia_door_{building.id.removeprefix('loc_')}"]
        distance = ((ex - door.x) ** 2 + (ey - door.y) ** 2) ** 0.5
        assert distance > door.radius, f"{building.id} 出门落点仍在门半径内：{distance:.2f}"
        assert not map_data.is_blocked("campus", ex, ey), f"{building.id} 出门落点落在阻挡体里"


def test_interior_entry_is_spawn(map_data):
    assert map_data.interior_entry("loc_library") == (8.0, 1.6, "n")


def test_interior_center(map_data):
    assert map_data.interior_center("loc_dorm") == (8.0, 5.0)


def test_campus_colliders_include_walls_buildings_and_props(map_data):
    rects = map_data.colliders_for(CAMPUS_SCENE)
    # 4 面外墙 + 全部建筑 + 全部登记的道具（数量随 map.json 变化，不写死）
    assert len(rects) == 4 + len(map_data.buildings) + len(map_data.props)
    assert len(map_data.outdoor_walls()) == 4
    assert len(map_data.props) >= 2  # 至少保留长椅与告示牌
    ids = [prop.id for prop in map_data.props]
    assert len(ids) == len(set(ids)), "道具 id 不能重复"


def test_interior_colliders_are_local(map_data):
    rects = map_data.colliders_for("loc_library")
    # 南墙被门口切成两段 → 5 段墙 + 4 件家具
    assert len(rects) == 5 + 4
    assert max(r.x1 for r in rects) <= 16.0
    assert max(r.y1 for r in rects) <= 10.0


def test_interior_south_wall_leaves_a_doorway(map_data):
    """南墙必须给入口地垫留门洞，否则玩家只能贴着墙横着蹭才出得去。

    （实机反馈：交互完"出不去，像有一道空气墙"。）
    """
    for building_id in ("loc_dorm", "loc_classroom", "loc_library",
                        "loc_clubroom", "loc_canteen"):
        interior = map_data.interior(building_id)
        door_x = interior.entry_mat[0]
        for r in map_data.colliders_for(building_id):
            assert not (r.x0 <= door_x <= r.x1 and r.y0 <= interior.entry_mat[1] <= r.y1), (
                f"{building_id} 的门口 ({door_x}, {interior.entry_mat[1]}) 被 {r} 堵住"
            )


def test_every_interactable_has_a_free_standing_spot(map_data):
    """每个交互点的“玩家站立点”都必须能站得下（不与任何碰撞矩形重叠）。"""
    for ia in map_data.interactables:
        if ia.type == "door":
            continue  # 门触发点在建筑外侧，站立点由门口空位决定，单独在下方校验
        rects = map_data.colliders_for(ia.scene)
        for r in rects:
            assert not overlap(ia, PLAYER_HALF, r), f"{ia.id} 与碰撞矩形 {r} 重叠"


def test_door_trigger_points_are_standable(map_data):
    for ia in map_data.interactables:
        if ia.type != "door":
            continue
        rects = map_data.colliders_for(CAMPUS_SCENE)
        for r in rects:
            assert not overlap(ia, PLAYER_HALF, r), f"{ia.id} 与碰撞矩形 {r} 重叠"


def test_route_waypoints_are_free(map_data):
    """C-R1 路线的关键落点必须可站立。"""
    waypoints = [
        (40.0, 5.0),
        (16.924, 8.923),
        (28.0, 17.0),
        (40.0, 33.0),
        (18.35, 30.873),
        (60.896, 31.017),
        (58.0, 30.0),
        (64.033, 12.123),
        (40.0, 47.2),
    ]
    rects = map_data.colliders_for(CAMPUS_SCENE)
    for x, y in waypoints:
        node = type("P", (), {"x": x, "y": y})()
        for r in rects:
            assert not overlap(node, PLAYER_HALF, r), f"路线落点 ({x}, {y}) 与 {r} 重叠"


# --------------------------------------------------------------- 数据校验


def test_rejects_id_that_violates_naming_rule():
    raw = _raw_map()
    raw["buildings"][0]["id"] = "Loc_Hall"
    with pytest.raises(MapDataError, match="id 不合法"):
        MapData(raw, _raw_ia())


def test_rejects_duplicate_interactable_id():
    raw_ia = _raw_ia()
    raw_ia["interactables"].append(copy.deepcopy(raw_ia["interactables"][0]))
    with pytest.raises(MapDataError, match="重复"):
        MapData(_raw_map(), raw_ia)


def test_rejects_building_without_interior():
    raw = _raw_map()
    raw["interiors"][0]["id"] = "loc_orphan"  # 建筑 loc_hall 失去对应的室内房间
    with pytest.raises(MapDataError, match="室内"):
        MapData(raw, _raw_ia())


def test_rejects_interactable_outside_outdoor_bounds():
    raw_ia = _raw_ia()
    raw_ia["interactables"][0]["x"] = 999.0
    with pytest.raises(MapDataError, match="室外地图之外"):
        MapData(_raw_map(), raw_ia)


def test_rejects_interior_interactable_outside_room():
    raw_ia = _raw_ia()
    raw_ia["interactables"][-1]["y"] = 99.0
    with pytest.raises(MapDataError, match="房间之外"):
        MapData(_raw_map(), raw_ia)


def test_rejects_unknown_scene():
    raw_ia = _raw_ia()
    raw_ia["interactables"][0]["scene"] = "loc_nowhere"
    with pytest.raises(MapDataError, match="不是已知建筑"):
        MapData(_raw_map(), raw_ia)


def test_rejects_door_with_non_building_target():
    raw_ia = _raw_ia()
    for ia in raw_ia["interactables"]:
        if ia["type"] == "door":
            ia["target"] = "npc_sumo"
    with pytest.raises(MapDataError, match="门目标"):
        MapData(_raw_map(), raw_ia)


def test_rejects_furniture_outside_room():
    raw = _raw_map()
    raw["interiors"][0]["furniture"][0]["rect"] = [1.0, 7.0, 99.0, 9.0]
    with pytest.raises(MapDataError, match="家具越界"):
        MapData(raw, _raw_ia())


def test_rejects_spawn_inside_entry_mat():
    raw = _raw_map()
    raw["interiors"][0]["spawn"] = {"x": 8.0, "y": 0.7, "facing": "n"}
    with pytest.raises(MapDataError, match="入口地垫"):
        MapData(raw, _raw_ia())


def test_rejects_non_positive_interactable_radius():
    raw_ia = _raw_ia()
    raw_ia["interactables"][0]["radius"] = 0.0
    with pytest.raises(MapDataError, match="radius 必须为正数"):
        MapData(_raw_map(), raw_ia)


def test_rejects_unknown_interactable_type():
    raw_ia = _raw_ia()
    raw_ia["interactables"][0]["type"] = "portal"
    with pytest.raises(MapDataError, match="type 不合法"):
        MapData(_raw_map(), raw_ia)
