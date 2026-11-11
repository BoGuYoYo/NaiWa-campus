"""Run in Blender to export the Game_Building placement for the game cards.

This reads the user's arranged scene without changing or saving the blend.
The game uses the south elevation, matching its fixed north-facing camera.
"""

import json
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "content" / "world" / "building_visuals.json"
BUILDINGS = (
    "loc_dorm", "loc_classroom", "loc_library", "loc_clubroom", "loc_canteen",
)


def export_layout():
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    layouts = {}
    for building_id in BUILDINGS:
        name = f"Game_Building_{building_id}"
        root = bpy.data.objects.get(name)
        if root is None:
            raise RuntimeError(f"missing Blender building: {name}")
        points = []
        for obj in (root, *root.children_recursive):
            if obj.type != "MESH":
                continue
            evaluated = obj.evaluated_get(depsgraph)
            points.extend(evaluated.matrix_world @ Vector(p) for p in evaluated.bound_box)
        if not points:
            raise RuntimeError(f"no building geometry: {name}")
        lower = [min(p[i] for p in points) for i in range(3)]
        upper = [max(p[i] for p in points) for i in range(3)]
        layouts[building_id] = {
            "blender_object": name,
            "world_bounds": [[round(v, 6) for v in lower], [round(v, 6) for v in upper]],
            "position": [round((lower[0] + upper[0]) / 2, 6), round(lower[1], 6), round(lower[2], 6)],
            "width": round(upper[0] - lower[0], 6),
            "height": round(upper[2] - lower[2], 6),
        }
    payload = {
        "schema_version": 1,
        "source": Path(bpy.data.filepath).name,
        "view": "south",
        "buildings": layouts,
    }
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Exported {len(layouts)} building placements to {TARGET}")
    for name, layout in layouts.items():
        print(name, layout["position"], layout["width"], layout["height"])


if __name__ == "__main__":
    export_layout()
