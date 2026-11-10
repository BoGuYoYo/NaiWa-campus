"""数据一致性守卫：室内 NPC 交互点坐标 == 室内 `npc_marks`。

背景（BUG-15 的数据侧）：
- `interactables.json` 里 `type=="npc"` 的点才是玩家真正能交互的位置；
- `map.json` 的 `npc_marks` 只是渲染用的地标；
- 实测两者**并不一致**：sumo 差 1.0 米、chenlang 差 1.0 米、xiaoyou 差 0.6 米，
  且 `npc_marks` 共 5 条而 NPC 只有 3 个（2 条幽灵标记）。

这条用例把"人肉拿尺子量"变成护栏：
- 现在数据不一致 → 用 `xfail(strict=True)` 标记，CI 保持绿但不隐身；
- 数据修好之后 → 会变成 **XPASS**，`strict=True` 直接报红，提醒把标记删掉，
  以免这条护栏在修复后被无声地留成"永远跳过"。
"""

from __future__ import annotations

import game.config as config
import pytest

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


@pytest.mark.xfail(
    strict=True,
    reason="BUG-15：室内 npc_marks 与 NPC 交互点不一致（1.0/1.0/0.6 米偏差 + 2 个幽灵标记）；"
           "数据统一后本条会 XPASS，请删掉 xfail 标记",
)
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
