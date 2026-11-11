"""Align the building footprints and doors with the supplied side elevations.

The game draws each building as a south-facing billboard taken from the user's
PNG.  For the door mat, the door interactable and the exit point to line up
with the entrance that is *drawn* on that billboard:

* the footprint comes from the Blender world bounds (``building_visuals.json``),
  so the art stands exactly on the front edge of its own collision rectangle;
* ``door_anchor_u`` is the horizontal centre of the drawn entrance on the card
  (0 = left edge, 1 = right edge), so the door sits under the picture's entrance
  instead of at an arbitrary point of the wall.

Run without arguments to rewrite ``content/world/map.json`` and
``content/world/interactables.json``; pass ``--check`` to verify they agree.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content" / "world"
TRIGGER_OFFSET = 0.8   # 门触发点离墙面 0.8 米


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _dump(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def plan() -> list[dict]:
    visuals = _load(CONTENT / "building_visuals.json")["buildings"]
    raw_map = _load(CONTENT / "map.json")
    out = []
    for building in raw_map["buildings"]:
        bid = building["id"]
        visual = visuals.get(bid)
        if visual is None:
            continue
        (x0, y0, _z0), (x1, _y1, _z1) = visual["world_bounds"]
        u = visual.get("door_anchor_u")
        door_x = (x0 + x1) / 2.0 if u is None else x0 + float(u) * (x1 - x0)
        door_x = round(min(max(door_x, x0 + 0.6), x1 - 0.6), 3)
        door_y = round(y0, 3)
        out.append({
            "id": bid,
            "rect": [round(x0, 3), round(y0, 3), round(x1, 3), round(_y1, 3)],
            "door": [door_x, door_y],
            "trigger": [door_x, round(door_y - TRIGGER_OFFSET, 3)],
        })
    return out


def apply(changes: list[dict]) -> None:
    by_id = {c["id"]: c for c in changes}
    map_path = CONTENT / "map.json"
    raw_map = _load(map_path)
    for building in raw_map["buildings"]:
        change = by_id.get(building["id"])
        if change is None:
            continue
        building["rect"] = change["rect"]
        building["door"] = {"x": change["door"][0], "y": change["door"][1], "facing": "s"}
        building["outside_trigger"] = change["trigger"]
    _dump(map_path, raw_map)

    ia_path = CONTENT / "interactables.json"
    raw_ia = _load(ia_path)
    for item in raw_ia["interactables"]:
        if item.get("type") != "door":
            continue
        change = by_id.get(item.get("target"))
        if change is None:
            continue
        item["x"], item["y"] = change["trigger"]
    _dump(ia_path, raw_ia)


def check(changes: list[dict]) -> int:
    map_raw = _load(CONTENT / "map.json")
    ia_raw = _load(CONTENT / "interactables.json")
    doors = {i["target"]: i for i in ia_raw["interactables"] if i.get("type") == "door"}
    bad = 0
    for change in changes:
        building = next(b for b in map_raw["buildings"] if b["id"] == change["id"])
        door = doors.get(change["id"], {})
        pairs = (
            ("rect", building["rect"], change["rect"]),
            ("door", [building["door"]["x"], building["door"]["y"]], change["door"]),
            ("facing", building["door"]["facing"], "s"),
            ("trigger", building["outside_trigger"], change["trigger"]),
            ("interactable", [door.get("x"), door.get("y")], change["trigger"]),
        )
        for label, got, want in pairs:
            if got != want:
                print(f"[DIFF] {change['id']} {label}: {got!r} != {want!r}")
                bad += 1
    print(f"checked {len(changes)} buildings, {bad} mismatch(es)")
    return 1 if bad else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    changes = plan()
    for change in changes:
        print(f"{change['id']}: rect={change['rect']} door={change['door']} trigger={change['trigger']}")
    if args.check:
        return check(changes)
    apply(changes)
    print("updated content/world/map.json and content/world/interactables.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
