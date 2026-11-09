import bpy
from pathlib import Path


OUT = Path(r"C:\Users\huang\Desktop\奶娃\naiwa_campus\build\blender_exports")

BUILDINGS = {
    "teaching": "Building_Teaching",
    "dorm": "Building_Dorm",
    "library": "Building_Library",
    "club": "Building_Club",
    "canteen": "Building_Canteen",
}

PROPS = {
    "tree": "Prop_Tree",
    "lamp": "Prop_Lamp",
    "bench": "Prop_Bench",
    "planter": "Prop_Planter",
    "bin": "Prop_Bin",
    "flag_pole": "Prop_Flag",
    "sign": "Prop_Sign",
    "bike_rack": "Prop_BikeRack",
    "flower_bed": "Prop_FlowerBed",
}


def descendants(root):
    result = [root]
    result.extend(child for child in bpy.context.scene.objects if child.parent == root)
    return result


def export_one(name, root_name):
    root = bpy.data.objects.get(root_name)
    if root is None:
        raise RuntimeError(f"missing Blender root: {root_name}")
    objects = descendants(root)
    old_location = root.location.copy()
    old_rotation = root.rotation_euler.copy()
    old_scale = root.scale.copy()
    try:
        # Each game asset is placed by game/app.py, so export geometry in local asset space.
        root.location = (0.0, 0.0, 0.0)
        root.rotation_euler = (0.0, 0.0, 0.0)
        root.scale = (1.0, 1.0, 1.0)
        bpy.ops.object.select_all(action="DESELECT")
        for obj in objects:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = root
        target = OUT / f"{name}.glb"
        target.parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.export_scene.gltf(
            filepath=str(target),
            export_format="GLB",
            use_selection=True,
            export_apply=True,
            export_materials="EXPORT",
            export_cameras=False,
            export_lights=False,
            export_animations=False,
        )
        print(f"EXPORTED {name} {target}")
    finally:
        root.location = old_location
        root.rotation_euler = old_rotation
        root.scale = old_scale
        bpy.ops.object.select_all(action="DESELECT")


for name, root_name in {**BUILDINGS, **PROPS}.items():
    export_one(name, root_name)

print("DONE", len(BUILDINGS) + len(PROPS))
