"""室内建筑材质（地板 / 墙面）的接线守卫。

用户提供的 `素材/建筑材质/` 由 `tools/import_interior_art.py` 落成
`assets/campus/textures/interior/<建筑>_{floor,wall}.png` 并登记进 manifest
（带 `tile_m` 与 `average_rgb`）。这里钉住三件事：

1. 五栋建筑的地板/墙面材质都在 manifest 里、文件真的存在、`tile_m` 合理；
2. 墙面卡片的朝向分类与缩进方向不会跑到房间外面（否则墙面会贴在墙外或穿墙）；
3. 家具取色规则：地面太深时改用墙面材质，避免家具与地面糊成一片。
"""

from __future__ import annotations

import json

import pytest

from game import config
from game.core.world_scene import InteriorSceneAdapter
from game.world.interior_scene import (
    SOUTH_WALL_HEIGHT,
    WALL_HEIGHT,
    InteriorScene,
    wall_side,
)
from game.world.map_data import MapData

BUILDINGS = ("dorm", "teaching", "library", "club", "canteen")


def _manifest() -> dict[str, dict]:
    data = json.loads((config.resource_root() / "assets" / "manifest.json").read_text("utf-8"))
    entries = data["assets"] if isinstance(data, dict) else data
    return {entry["id"]: entry for entry in entries}


@pytest.fixture(scope="module")
def map_data() -> MapData:
    return MapData.from_content_root(config.resource_root() / "content")


def test_every_building_has_floor_and_wall_material():
    entries = _manifest()
    missing_entries, missing_files = [], []
    for building in BUILDINGS:
        for kind in ("floor", "wall"):
            asset_id = f"interior_{kind}_{building}"
            entry = entries.get(asset_id)
            if entry is None:
                missing_entries.append(asset_id)
                continue
            path = config.resource_root() / "assets" / entry["path"]
            if not path.is_file():
                missing_files.append(f"{asset_id} -> {entry['path']}")
            assert entry.get("tile_m", 0) > 0, f"{asset_id} 缺少 tile_m（UV 无法计算）"
            assert len(entry.get("average_rgb") or []) == 3, f"{asset_id} 缺少 average_rgb"
            assert (entry.get("license_id") or "").startswith("LIC-"), (
                f"{asset_id} 没有登记 license_id"
            )
    assert missing_entries == [], f"manifest 缺少室内材质：{missing_entries}"
    assert missing_files == [], f"室内材质文件不存在：{missing_files}"


def test_material_textures_match_pixel_density():
    """地板 96px/4m、墙面 72px/3m = 24px/m，与游戏像素密度一致。"""
    from PIL import Image

    entries = _manifest()
    px_per_m = config.PIXELS_PER_METER
    for building in BUILDINGS:
        floor = entries[f"interior_floor_{building}"]
        image = Image.open(config.resource_root() / "assets" / floor["path"])
        density = image.width / float(floor["tile_m"])
        assert abs(density - px_per_m) <= 1.0, f"{building} 地板密度 {density:.1f}px/m ≠ {px_per_m}"
        wall = entries[f"interior_wall_{building}"]
        image = Image.open(config.resource_root() / "assets" / wall["path"])
        assert image.height == 3 * px_per_m, f"{building} 墙面高度不是 3 米"


def test_wall_side_covers_all_four_sides(map_data):
    thickness = map_data.interior_wall_thickness
    for interior in map_data.interiors:
        sides = {wall_side(rect, interior.size, thickness)
                 for rect in map_data.interior_walls(interior.id)}
        assert sides == {"n", "s", "e", "w"}, f"{interior.id} 墙体分类异常：{sides}"


def test_wall_panel_edges_point_into_the_room(map_data):
    """墙面卡片必须朝房间里缩进：跑出去就会贴在墙外/穿墙。"""
    thickness = map_data.interior_wall_thickness
    for interior in map_data.interiors:
        w, h = interior.size
        for rect in map_data.interior_walls(interior.id):
            side = wall_side(rect, (w, h), thickness)
            x0, y0, x1, y1 = InteriorScene._panel_edge(None, rect, side, w, h)
            assert 0.0 <= x0 <= w and 0.0 <= x1 <= w, f"{interior.id}/{side} u 越界"
            assert 0.0 <= y0 <= h and 0.0 <= y1 <= h, f"{interior.id}/{side} v 越界"
            if side == "n":
                assert y0 < rect.y0, "北墙卡片应在墙内侧（更靠南）"
            if side == "w":
                assert x0 > rect.x1, "西墙卡片应在墙内侧（更靠东）"
            if side == "e":
                assert x0 < rect.x0, "东墙卡片应在墙内侧（更靠西）"


def test_south_wall_is_a_cutaway_curb():
    """南墙（正对镜头）必须矮：3 米高会把门口地垫整块挡住。"""
    assert 0.0 < SOUTH_WALL_HEIGHT <= 0.5
    assert WALL_HEIGHT >= 2.5


def test_furniture_color_follows_floor_when_it_is_bright():
    color = InteriorSceneAdapter._furniture_color([0.8, 0.8, 0.8], [0.5, 0.5, 0.5])
    assert color is not None
    assert color[:3] == pytest.approx((0.496, 0.496, 0.496), abs=0.01)


def test_furniture_color_falls_back_to_wall_when_floor_is_dark():
    color = InteriorSceneAdapter._furniture_color([0.17, 0.08, 0.06], [0.66, 0.62, 0.53])
    assert color is not None
    assert color[0] > 0.3, f"深色地板时家具仍太暗：{color}"
    assert color[:3] == pytest.approx((0.409, 0.384, 0.329), abs=0.01)


def test_furniture_color_without_materials_is_none():
    assert InteriorSceneAdapter._furniture_color(None, None) is None
