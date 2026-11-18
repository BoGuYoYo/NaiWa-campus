"""数据一致性守卫：室内 NPC 交互点坐标 == 室内 `npc_marks`。

`interactables.json` 里的 NPC 交互位置必须和 `map.json` 中的立绘站位一致。
"""

from __future__ import annotations

import game.config as config
from game.world.map_data import MapData


def _md() -> MapData:
    return MapData.from_content_root(config.resource_root() / "content")


def _npc_points(md: MapData, scene: str) -> set[tuple[float, float]]:
    return {
        tuple(round(v, 3) for v in md.to_world(ia))
        for ia in md.interactables_for(scene)
        if ia.type == "npc"
    }


def _mark_points(md: MapData, building_id: str) -> set[tuple[float, float]]:
    it = md.interior(building_id)
    ox, oy = it.origin
    return {(round(ox + m.x, 3), round(oy + m.y, 3)) for m in it.npc_marks}


def test_interior_npc_marks_match_interactables() -> None:
    md = _md()
    mismatches: dict[str, dict[str, set]] = {}

    for it in md.interiors:
        npc_pts = _npc_points(md, it.id)
        mark_pts = _mark_points(md, it.id)
        if npc_pts != mark_pts:
            mismatches[it.id] = {
                "只有交互点": npc_pts - mark_pts,
                "只有标记": mark_pts - npc_pts,
            }

    assert mismatches == {}, f"室内 npc_marks 与 NPC 交互点不一致：{mismatches}"


def test_npc_interactables_have_renderable_asset_ids() -> None:
    """NPC 卡要用的资源必须真的在 manifest 里（`char_npc_<short>_idle`）。"""
    import json

    md = _md()
    manifest = json.loads((config.resource_root() / "assets/manifest.json").read_text(encoding="utf-8"))
    raw = manifest.get("assets", manifest)
    asset_ids = {a["id"] for a in raw}

    npc_ids = [ia.target for ia in md.interactables if ia.type == "npc"]
    assert npc_ids, "没有任何 NPC 交互点"

    missing = []
    for npc_id in npc_ids:
        short = npc_id.removeprefix("npc_")
        asset_id = f"char_npc_{short}_idle"
        if asset_id not in asset_ids:
            missing.append(asset_id)

    assert missing == [], f"NPC 缺少可渲染的 idle 资源：{missing}"


# --------------------------------------------------- 第 17 轮：室外 NPC 不参与靠近互动

def test_outdoor_npcs_are_decoration_only(map_data):
    """开局争论的两个 NPC 只是布景，不能有交互点。

    用户要求：争论只在开局自动播一次；走近他们时不应触发任何互动
    （否则会白扣一个行动时段、并弹出一段与剧情无关的对话）。
    """
    outdoor_npc = [ia for ia in map_data.interactables
                   if ia.scene == "campus" and ia.type == "npc"]
    assert outdoor_npc == [], (
        "室外不该有 NPC 交互点：" + ", ".join(ia.id for ia in outdoor_npc)
    )


def test_outdoor_npc_marks_exist_for_the_opening_argument(map_data):
    """路口确有李振兴与符闹吃的立牌（纯展示）。"""
    names = {mark.name for mark in map_data.outdoor_npc_marks}
    assert {"李振兴", "符闹吃"} <= names, names
