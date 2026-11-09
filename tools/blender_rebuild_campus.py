import math
from mathutils import Vector

import bpy


ROOT = r"C:\Users\huang\Desktop\奶娃\naiwa_campus"
BLEND_OUT = ROOT + r"\blender_reconstructed_campus.blend"
RENDER_OUT = ROOT + r"\reports\blender_campus_render.png"


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    # Keep named materials alive because the palette is created at module load time.
    for datablocks in (bpy.data.meshes, bpy.data.curves, bpy.data.cameras, bpy.data.lights):
        for block in list(datablocks):
            if block.users == 0:
                datablocks.remove(block)


def material(name, color, metallic=0.0, roughness=0.8):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1.0)
    mat.use_nodes = True
    bsdf = next((node for node in mat.node_tree.nodes if node.type == "BSDF_PRINCIPLED"), None)
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
    return mat


WALL_CREAM = material("Wall_Cream", (0.95, 0.72, 0.39))
WALL_CREAM_LIGHT = material("Wall_Cream_Light", (1.0, 0.84, 0.52))
WALL_COOL = material("Wall_Cool", (0.73, 0.77, 0.80))
WALL_GREEN = material("Wall_Green", (0.33, 0.55, 0.39))
WALL_GREEN_DARK = material("Wall_Green_Dark", (0.23, 0.40, 0.29))
ROOF_RED = material("Roof_Red", (0.72, 0.16, 0.11))
ROOF_RED_DARK = material("Roof_Red_Dark", (0.50, 0.08, 0.06))
GLASS = material("Glass_Blue", (0.035, 0.09, 0.19), roughness=0.28)
GLASS_LIGHT = material("Glass_Blue_Light", (0.07, 0.18, 0.30), roughness=0.28)
FRAME = material("Frame_Cream", (0.92, 0.84, 0.64))
STONE = material("Stone", (0.63, 0.64, 0.62))
METAL = material("Metal", (0.42, 0.46, 0.50), metallic=0.65, roughness=0.35)
WOOD = material("Wood", (0.49, 0.28, 0.12))
WOOD_LIGHT = material("Wood_Light", (0.68, 0.42, 0.20))
DOOR = material("Door", (0.30, 0.15, 0.08))
GRASS = material("Grass", (0.20, 0.43, 0.22))
GRASS_DARK = material("Grass_Dark", (0.12, 0.29, 0.15))
PATH = material("Path", (0.48, 0.47, 0.43))
LEAF = material("Leaf", (0.13, 0.39, 0.16))
LEAF_LIGHT = material("Leaf_Light", (0.24, 0.53, 0.21))
FLOWER_PINK = material("Flower_Pink", (0.87, 0.28, 0.42))
FLOWER_YELLOW = material("Flower_Yellow", (0.98, 0.72, 0.20))
LIGHT_GLOW = material("Lamp_Glow", (1.0, 0.74, 0.24), roughness=0.3)


def collection(name):
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(coll)
    return coll


def link(obj, coll, parent=None):
    coll.objects.link(obj)
    if parent is not None:
        obj.parent = parent
    return obj


def root(name, location):
    obj = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    return obj


def box(name, x, y, z, w, d, h, mat, coll, parent=None, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(location=(x + w / 2, y + d / 2, z + h / 2))
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = (w, d, h)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if mat:
        obj.data.materials.append(mat)
    if bevel:
        mod = obj.modifiers.new("Soft_Edges", "BEVEL")
        mod.width = bevel
        mod.segments = 2
    link(obj, coll, parent)
    return obj


def cylinder(name, x, y, z, radius, depth, mat, coll, parent=None, vertices=8, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth,
                                        location=(x, y, z + depth / 2), rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    if mat:
        obj.data.materials.append(mat)
    link(obj, coll, parent)
    return obj


def sphere(name, x, y, z, scale, mat, coll, parent=None, segments=12, rings=6):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, location=(x, y, z))
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if mat:
        obj.data.materials.append(mat)
    link(obj, coll, parent)
    return obj


def mesh_object(name, verts, faces, mat, coll, parent=None):
    mesh = bpy.data.meshes.new(name + "_Mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    link(obj, coll, parent)
    if mat:
        obj.data.materials.append(mat)
    return obj


def panel(name, x, y, z, w, h, mat, coll, parent=None, face="south", frame=False, mullions=0):
    if face == "south":
        box(name, x, y - 0.035, z, w, 0.07, h, mat, coll, parent)
        if frame:
            edge = 0.055
            for suffix, xx, zz, ww, hh in (
                ("L", x - edge, z - edge, edge, h + edge * 2),
                ("R", x + w, z - edge, edge, h + edge * 2),
                ("B", x - edge, z - edge, w + edge * 2, edge),
                ("T", x - edge, z + h, w + edge * 2, edge),
            ):
                box(name + "_" + suffix, xx, y - 0.07, zz, ww, 0.11, hh, FRAME, coll, parent)
            for i in range(1, mullions + 1):
                mx = x + w * i / (mullions + 1)
                box(name + f"_M{i}", mx - edge / 2, y - 0.07, z, edge, 0.11, h, FRAME, coll, parent)
    elif face == "east":
        box(name, x - 0.035, y, z, 0.07, w, h, mat, coll, parent)
        if frame:
            edge = 0.055
            for suffix, yy, zz, ww, hh in (
                ("L", y - edge, z - edge, edge, h + edge * 2),
                ("R", y + w, z - edge, edge, h + edge * 2),
                ("B", y - edge, z - edge, w + edge * 2, edge),
                ("T", y - edge, z + h, w + edge * 2, edge),
            ):
                box(name + "_" + suffix, x - 0.07, yy, zz, 0.11, ww, hh, FRAME, coll, parent)
            for i in range(1, mullions + 1):
                my = y + w * i / (mullions + 1)
                box(name + f"_M{i}", x - 0.07, my - edge / 2, z, 0.11, edge, h, FRAME, coll, parent)


def gable_roof(name, x, y, z, w, d, rise, mat, coll, parent=None):
    verts = [(x, y, z), (x + w, y, z), (x + w, y + d, z), (x, y + d, z),
             (x, y + d / 2, z + rise), (x + w, y + d / 2, z + rise)]
    faces = [(0, 1, 5, 4), (3, 4, 5, 2), (0, 4, 3), (1, 2, 5), (0, 3, 2, 1)]
    return mesh_object(name, verts, faces, mat, coll, parent)


def hipped_roof(name, x, y, z, w, d, rise, mat, coll, parent=None):
    cx, cy = x + w / 2, y + d / 2
    verts = [(x, y, z), (x + w, y, z), (x + w, y + d, z), (x, y + d, z),
             (cx, cy, z + rise)]
    faces = [(0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4), (0, 3, 2, 1)]
    return mesh_object(name, verts, faces, mat, coll, parent)


def rod(name, p0, p1, radius, mat, coll, parent=None, vertices=6):
    p0, p1 = Vector(p0), Vector(p1)
    delta = p1 - p0
    mid = (p0 + p1) / 2
    obj = cylinder(name, mid.x, mid.y, mid.z - delta.length / 2, radius, delta.length,
                   mat, coll, parent, vertices=vertices)
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(delta.normalized())
    return obj


def clock(root_obj, coll):
    cylinder("Clock_Rim", 0, -2.67, 13.6, 1.0, 0.14, FRAME, coll, root_obj, vertices=20,
             rotation=(math.pi / 2, 0, 0))
    cylinder("Clock_Face", 0, -2.75, 13.6, 0.82, 0.05, GLASS_LIGHT, coll, root_obj, vertices=20,
             rotation=(math.pi / 2, 0, 0))
    box("Clock_Hand_H", -0.38, -2.83, 13.57, 0.76, 0.05, 0.08, FRAME, coll, root_obj)
    box("Clock_Hand_V", -0.04, -2.83, 13.57, 0.08, 0.05, 0.46, FRAME, coll, root_obj)


def add_windows_front(root_obj, coll, x0, width, floors, floor_h, count, win_w, gap, y=0.0, z0=0.75,
                      mat=GLASS, framed=False):
    for floor in range(floors):
        z = z0 + floor * floor_h
        for i in range(count):
            panel(f"Window_{floor}_{i}", x0 + i * (win_w + gap), y, z, win_w, 1.35, mat, coll,
                  root_obj, frame=framed, mullions=1 if framed else 0)


def build_teaching(location):
    coll = collection("Building_Teaching")
    r = root("Building_Teaching", location)
    w, d, h = 20.0, 14.0, 11.4
    box("LeftWing", 0, 0, 0, 6.6, d, h, WALL_CREAM, coll, r)
    box("RightWing", w - 6.6, 0, 0, 6.6, d, h, WALL_CREAM, coll, r)
    box("BackWing", 6.6, d - 5.0, 0, w - 13.2, 5.0, h, WALL_CREAM, coll, r)
    for floor in range(4):
        z = 0.8 + floor * 2.85
        for i in range(3):
            panel(f"LeftWindow_{floor}_{i}", 0.45 + i * 1.8, 0, z, 1.52, 1.5, GLASS, coll, r)
            panel(f"RightWindow_{floor}_{i}", w - 5.0 + i * 1.8, 0, z, 1.52, 1.5, GLASS, coll, r)
        box(f"FloorBand_{floor}", -0.07, -0.07, floor * 2.85 + 2.45, w + 0.14, d + 0.14,
            0.2, WALL_CREAM_LIGHT, coll, r)
    tower_w = 5.2
    tx = (w - tower_w) / 2
    box("ClockTower", tx, -1.2, 0, tower_w, 5.2, 14.0, WALL_CREAM_LIGHT, coll, r)
    panel("TowerGlass", tx + 1.5, -1.2, 1.0, 2.2, 11.0, GLASS, coll, r)
    clock(r, coll)
    for bx, by, bw, bd in ((0, 0, 6.6, d), (w - 6.6, 0, 6.6, d), (6.6, d - 5.0, w - 13.2, 5.0)):
        box("Parapet_S", bx, by, h, bw, 0.25, 0.45, ROOF_RED, coll, r)
        box("Parapet_N", bx, by + bd - 0.25, h, bw, 0.25, 0.45, ROOF_RED, coll, r)
        box("Parapet_W", bx, by, h, 0.25, bd, 0.45, ROOF_RED, coll, r)
        box("Parapet_E", bx + bw - 0.25, by, h, 0.25, bd, 0.45, ROOF_RED, coll, r)
    box("EntrySteps", tx + 0.6, -2.4, 0, 4.0, 1.2, 0.3, STONE, coll, r)
    box("EntryStepsTop", tx + 0.95, -1.65, 0, 3.3, 0.75, 0.5, STONE, coll, r)
    panel("EntryDoor", tx + 1.4, -1.2, 0.3, 2.4, 2.0, DOOR, coll, r)
    box("Canopy", tx + 0.4, -2.1, 2.7, 4.4, 0.95, 0.24, FRAME, coll, r)
    box("FlagPole", 1.6, 1.2, h, 0.1, 0.1, 5.2, METAL, coll, r)
    box("Flag", 1.7, 1.25, h + 3.9, 1.3, 0.05, 1.0, ROOF_RED, coll, r)
    for i, (ax, ay) in enumerate(((2.2, 10.8), (12.4, 10.6), (16.2, 2.0))):
        box(f"RoofAC_{i}", ax, ay, h, 1.1, 0.8, 0.55, METAL, coll, r)
    return r


def build_dorm(location):
    coll = collection("Building_Dorm")
    r = root("Building_Dorm", location)
    w, d, floors, floor_h = 16.0, 12.0, 4, 2.7
    h = floors * floor_h
    box("Body", 0, 0, 0, w, d, h, WALL_COOL, coll, r)
    box("Plinth", -0.15, -0.15, 0, w + 0.3, d + 0.3, 0.35, STONE, coll, r)
    for floor in range(1, floors):
        box(f"Band_{floor}", -0.06, -0.06, floor * floor_h - 0.09, w + 0.12, d + 0.12, 0.18,
            FRAME, coll, r)
    for floor in range(floors):
        z = floor * floor_h + 0.75
        for i in range(5):
            panel(f"FrontWindow_{floor}_{i}", 1.25 + i * 2.55, 0, z, 1.55, 1.3, GLASS, coll, r)
        for bx in (2.55, 9.55):
            box("Balcony", bx, -0.75, z - 0.22, 2.45, 0.82, 0.12, FRAME, coll, r)
            box("BalconyRail", bx, -0.78, z - 0.1, 2.45, 0.06, 0.55, FRAME, coll, r)
            rod("ClothesLine", (bx + 0.2, -0.84, z + 0.48), (bx + 2.2, -0.84, z + 0.48), 0.025,
                METAL, coll, r, vertices=5)
        for i in range(2):
            panel(f"SideWindow_{floor}_{i}", w, 1.2 + i * 3.75, z, 1.25, 1.2, GLASS, coll, r,
                  face="east")
    box("Steps", 6.4, -1.5, 0, 3.2, 1.5, 0.3, STONE, coll, r)
    box("StepsTop", 6.6, -0.9, 0, 2.8, 0.9, 0.6, STONE, coll, r)
    panel("Door", 7.0, 0, 0.6, 2.0, 2.1, DOOR, coll, r)
    box("Awning", 6.5, -1.3, 2.85, 3.0, 1.3, 0.22, FRAME, coll, r)
    gable_roof("Roof", -0.3, -0.3, h, w + 0.6, d + 0.6, 3.2, ROOF_RED, coll, r)
    for i, dx in enumerate((3.0, 7.4, 11.8)):
        box(f"Dormer_{i}", dx, -0.55, h + 0.35, 1.9, 1.1, 1.25, WALL_COOL, coll, r)
        panel(f"DormerGlass_{i}", dx + 0.55, -0.58, h + 0.65, 0.8, 0.75, GLASS, coll, r)
    tank_x, tank_y = 11.1, 8.9
    for lx in (tank_x - 0.62, tank_x + 0.62):
        for ly in (tank_y - 0.62, tank_y + 0.62):
            box("TankLeg", lx, ly, h + 0.25, 0.16, 0.16, 1.45, METAL, coll, r)
    cylinder("Tank", tank_x, tank_y, h + 1.7, 0.85, 1.45, METAL, coll, r, vertices=12)
    cylinder("TankCap", tank_x, tank_y, h + 3.15, 0.92, 0.14, FRAME, coll, r, vertices=12)
    box("Antenna", 8.9, 9.35, h + 0.15, 0.08, 0.08, 3.0, METAL, coll, r)
    for i in range(3):
        rod("AntennaBar", (8.45, 9.35, h + 2.1 + i * 0.32), (9.4, 9.35, h + 2.1 + i * 0.32),
            0.035, METAL, coll, r, vertices=5)
    return r


def build_library(location):
    coll = collection("Building_Library")
    r = root("Building_Library", location)
    w, d, floors, floor_h = 18.0, 16.0, 3, 3.1
    h = floors * floor_h
    box("Body", 0, 0, 0, w, d, h, WALL_CREAM_LIGHT, coll, r)
    box("Plinth", -0.2, -0.2, 0, w + 0.4, d + 0.4, 0.4, STONE, coll, r)
    for floor in range(1, floors):
        box("Band", -0.08, -0.08, floor * floor_h - 0.08, w + 0.16, d + 0.16, 0.16, WALL_CREAM, coll, r)
    for floor in range(floors):
        z = floor * floor_h + 1.0
        for i in range(4):
            panel(f"FrontWindow_{floor}_{i}", 1.2 + i * 3.05, 0, z, 1.12, 1.28, GLASS, coll, r,
                  frame=True, mullions=1)
        for i in range(3):
            panel(f"SideWindow_{floor}_{i}", w, 2.0 + i * 3.0, z, 1.25, 1.28, GLASS, coll, r,
                  face="east", frame=True, mullions=1)
    panel("TallGlass", w / 2 - 1.6, -0.02, 1.2, 3.2, h - 2.6, GLASS, coll, r)
    for i in range(4):
        box("PorticoColumn", 3.0 + i * 3.1, -1.9, 0, 0.65, 0.65, h * 0.62, WALL_CREAM_LIGHT, coll, r)
    box("Portico", 2.6, -2.2, h * 0.62, 10.6, 2.4, 0.45, WALL_CREAM, coll, r)
    box("Steps", 1.6, -3.6, 0, 12.6, 1.5, 0.28, STONE, coll, r)
    panel("Door", w / 2 - 1.1, -1.9, 0.5, 2.2, 2.1, DOOR, coll, r)
    hipped_roof("Roof", -0.4, -0.4, h, w + 0.8, d + 0.8, 4.2, ROOF_RED, coll, r)
    box("Skylight", w / 2 - 2.0, d / 2 - 2.4, h + 2.9, 4.0, 4.8, 0.12, GLASS_LIGHT, coll, r)
    for i in range(3):
        box("SkylightBar", w / 2 - 2.05, d / 2 - 2.4 + i * 2.0, h + 3.0, 4.1, 0.1, 0.95, FRAME, coll, r)
    return r


def build_club(location):
    coll = collection("Building_Club")
    r = root("Building_Club", location)
    w, d, floors, floor_h = 14.0, 12.0, 2, 3.6
    h = floors * floor_h
    box("Body", 0, 0, 0, w, d, h, WALL_GREEN, coll, r)
    box("Plinth", -0.15, -0.15, 0, w + 0.3, d + 0.3, 0.28, WALL_GREEN_DARK, coll, r)
    box("Band", -0.08, -0.08, floor_h - 0.12, w + 0.16, d + 0.16, 0.24, WALL_GREEN_DARK, coll, r)
    for i in range(3):
        panel(f"Shopfront_{i}", 1.05 + i * 3.0, 0, 0.75, 2.45, 2.4, GLASS, coll, r, frame=True, mullions=2)
    panel("Door", 10.6, 0, 0.5, 1.8, 2.2, DOOR, coll, r)
    box("Step", 10.5, -0.9, 0, 2.0, 0.9, 0.22, STONE, coll, r)
    awning_mats = [ROOF_RED, FLOWER_YELLOW, GLASS_LIGHT, LEAF_LIGHT, ROOF_RED, FLOWER_YELLOW]
    for i, mat in enumerate(awning_mats):
        box(f"Awning_{i}", 10.4 + i * 0.62, -1.15, 3.05, 0.62, 1.15, 0.3, mat, coll, r)
    for i in range(3):
        panel(f"UpperWindow_{i}", 1.5 + i * 3.7, 0, floor_h + 0.9, 1.7, 1.5, GLASS, coll, r,
              frame=True, mullions=1)
    for side in ("south", "north", "west", "east"):
        if side == "south": box("Parapet", 0, 0, h, w, 0.3, 0.5, ROOF_RED, coll, r)
        if side == "north": box("Parapet", 0, d - 0.3, h, w, 0.3, 0.5, ROOF_RED, coll, r)
        if side == "west": box("Parapet", 0, 0, h, 0.3, d, 0.5, ROOF_RED, coll, r)
        if side == "east": box("Parapet", w - 0.3, 0, h, 0.3, d, 0.5, ROOF_RED, coll, r)
    box("RoofDeck", 0.3, 0.3, h, w - 0.6, d - 0.6, 0.12, WALL_GREEN_DARK, coll, r)
    box("SignBoard", 5.9, 7.05, h + 2.0, 5.0, 0.18, 1.3, FRAME, coll, r)
    box("RoofBox", 1.4, 2.0, h + 0.12, 1.2, 0.9, 0.5, METAL, coll, r)
    return r


def build_canteen(location):
    coll = collection("Building_Canteen")
    r = root("Building_Canteen", location)
    w, d, h = 16.0, 12.0, 5.2
    box("Body", 0, 0, 0, w, d, h, WALL_CREAM, coll, r)
    box("Plinth", -0.15, -0.15, 0, w + 0.3, d + 0.3, 0.3, STONE, coll, r)
    for i in range(4):
        panel(f"Glass_{i}", 1.15 + i * 2.65, 0, 0.85, 2.1, 3.0, GLASS, coll, r, frame=True, mullions=1)
    for i in range(3):
        panel(f"SideGlass_{i}", w, 1.8 + i * 3.1, 2.35, 1.85, 1.2, GLASS_LIGHT, coll, r,
              face="east", frame=True, mullions=1)
    box("Canopy", 0.6, -2.6, 3.3, 8.8, 2.6, 0.3, ROOF_RED, coll, r)
    for i in range(4):
        box("CanopyPost", 0.9 + i * 2.8, -2.4, 0, 0.18, 0.18, 3.3, FRAME, coll, r)
    panel("Door", 10.6, 0, 0.4, 2.2, 2.4, DOOR, coll, r)
    box("Step", 10.5, -1.0, 0, 2.4, 1.0, 0.22, STONE, coll, r)
    gable_roof("Roof", -0.5, -0.5, h, w + 1.0, d + 1.0, 2.6, ROOF_RED, coll, r)
    box("Counter", 1.0, -2.9, 0, 5.0, 0.7, 0.95, WALL_CREAM_LIGHT, coll, r)
    for i, (x, height) in enumerate(((12.7, 2.4), (13.3, 2.0), (13.9, 2.7))):
        cylinder(f"Exhaust_{i}", x, 9.3, h + 1.5, 0.16, height, METAL, coll, r, vertices=8)
    return r


def add_tree(x, y):
    coll = collection("Props")
    r = root("Prop_Tree", (x, y, 0))
    cylinder("Trunk", 0, 0, 0, 0.35, 2.6, WOOD, coll, r, vertices=8)
    sphere("Canopy_L", -0.72, -0.1, 3.25, (1.2, 1.0, 1.0), LEAF, coll, r)
    sphere("Canopy_R", 0.62, 0.1, 3.35, (1.15, 1.0, 1.0), LEAF_LIGHT, coll, r)
    sphere("Canopy_T", -0.05, 0.0, 4.2, (1.05, 0.95, 0.95), LEAF, coll, r)


def add_lamp(x, y, heading=0):
    coll = collection("Props")
    r = root("Prop_Lamp", (x, y, 0))
    box("Base", -0.25, -0.25, 0, 0.5, 0.5, 0.2, METAL, coll, r)
    box("Pole", -0.09, -0.09, 0.2, 0.18, 0.18, 4.0, METAL, coll, r)
    box("Head", -0.34, -0.34, 4.1, 0.68, 0.68, 0.6, METAL, coll, r)
    box("Glow", -0.25, -0.25, 4.2, 0.5, 0.5, 0.34, LIGHT_GLOW, coll, r)
    r.rotation_euler[2] = math.radians(heading)


def add_bench(x, y, heading=0):
    coll = collection("Props")
    r = root("Prop_Bench", (x, y, 0))
    for i in range(3):
        box("SeatSlat", -0.1 + i * 0.65, -0.4, 0.45, 0.58, 0.8, 0.14, WOOD_LIGHT, coll, r)
        box("BackSlat", -0.1 + i * 0.65, 0.3, 0.72, 0.58, 0.14, 0.42, WOOD, coll, r)
    for x0 in (0.05, 1.75):
        rod("LegFront", (x0, -0.32, 0), (x0, -0.32, 0.48), 0.07, METAL, coll, r)
        rod("LegBack", (x0, 0.32, 0), (x0, 0.32, 0.48), 0.07, METAL, coll, r)
    r.rotation_euler[2] = math.radians(heading)


def add_planter(x, y):
    coll = collection("Props")
    r = root("Prop_Planter", (x, y, 0))
    box("Planter", -0.7, -0.7, 0, 1.4, 1.4, 0.55, STONE, coll, r)
    box("Rim", -0.78, -0.78, 0.55, 1.56, 1.56, 0.16, FRAME, coll, r)
    sphere("Shrub", 0, 0, 0.92, (0.62, 0.62, 0.55), LEAF_LIGHT, coll, r)


def add_bin(x, y):
    coll = collection("Props")
    r = root("Prop_Bin", (x, y, 0))
    cylinder("Body", 0, 0, 0, 0.34, 0.85, WALL_GREEN_DARK, coll, r, vertices=10)
    cylinder("Lid", 0, 0, 0.85, 0.38, 0.12, LEAF, coll, r, vertices=10)


def add_flag(x, y):
    coll = collection("Props")
    r = root("Prop_Flag", (x, y, 0))
    cylinder("Pole", 0, 0, 0.25, 0.08, 6.0, FRAME, coll, r, vertices=8)
    sphere("Finial", 0, 0, 6.35, (0.14, 0.14, 0.14), FLOWER_YELLOW, coll, r, segments=8, rings=4)
    box("Cloth", 0.1, -0.7, 4.7, 0.06, 0.7, 0.9, ROOF_RED, coll, r)


def add_sign(x, y):
    coll = collection("Props")
    r = root("Prop_Sign", (x, y, 0))
    box("Post", -0.08, -0.08, 0, 0.16, 0.16, 1.9, METAL, coll, r)
    box("Board", -0.8, -0.09, 1.1, 1.7, 0.12, 1.0, FRAME, coll, r)
    box("Inner", -0.67, -0.16, 1.22, 1.44, 0.06, 0.66, GLASS_LIGHT, coll, r)
    box("Strip", -0.8, -0.11, 1.95, 1.7, 0.1, 0.16, ROOF_RED, coll, r)


def add_bike_rack(x, y):
    coll = collection("Props")
    r = root("Prop_BikeRack", (x, y, 0))
    box("FootL", -0.1, -0.4, 0, 1.2, 0.12, 0.1, METAL, coll, r)
    box("FootR", 1.0, -0.4, 0, 1.2, 0.12, 0.1, METAL, coll, r)
    rod("RackTop", (0.2, -0.1, 0.1), (0.2, -0.1, 0.8), 0.07, METAL, coll, r)
    rod("RackBar", (0.2, -0.1, 0.8), (1.6, -0.1, 0.8), 0.07, METAL, coll, r)
    rod("RackDown", (1.6, -0.1, 0.8), (1.6, -0.1, 0.1), 0.07, METAL, coll, r)


def add_flower_bed(x, y):
    coll = collection("Props")
    r = root("Prop_FlowerBed", (x, y, 0))
    box("Soil", -1.2, -0.6, 0, 2.4, 1.2, 0.18, WOOD, coll, r)
    for xx, mat in zip((-0.95, -0.57, -0.19, 0.19, 0.57, 0.95),
                       (FLOWER_PINK, FLOWER_YELLOW, FLOWER_PINK, FLOWER_YELLOW, FLOWER_PINK, FLOWER_YELLOW)):
        sphere("Flower", xx, 0, 0.5, (0.16, 0.16, 0.2), mat, coll, r, segments=8, rings=4)


def add_ground():
    coll = collection("Ground")
    box("Ground", -40, -27.5, -0.5, 80, 55, 0.5, GRASS, coll)
    box("SoilLayer", -40, -27.5, -0.95, 80, 55, 0.45, GRASS_DARK, coll)
    box("Road_NS", -3, -27.5, 0, 6, 55, 0.06, PATH, coll)
    box("Road_EW", -40, 0, 0.01, 80, 5, 0.06, PATH, coll)
    for i, (x, y, w, d) in enumerate(((20, 18, 12, 7), (-20, -14, 10, 6), (25, -20, 12, 6), (-30, 20, 8, 5))):
        box(f"GrassPatch_{i}", x, y, 0.08, w, d, 0.025, GRASS_DARK, coll)


def add_lighting():
    world = bpy.context.scene.world
    world.color = (0.12, 0.15, 0.20)
    world.use_nodes = True
    bg = next((node for node in world.node_tree.nodes if node.type == "BACKGROUND"), None)
    if bg:
        bg.inputs["Color"].default_value = (0.12, 0.15, 0.20, 1.0)
        bg.inputs["Strength"].default_value = 0.35
    bpy.ops.object.light_add(type="AREA", location=(12, -16, 35))
    key = bpy.context.object
    key.name = "Key_Light"
    key.data.energy = 1800
    key.data.shape = "DISK"
    key.data.size = 25
    key.rotation_euler = (math.radians(25), 0, math.radians(25))
    bpy.ops.object.light_add(type="SUN", location=(-20, 10, 30))
    sun = bpy.context.object
    sun.name = "Sun"
    sun.data.energy = 2.0
    sun.rotation_euler = (math.radians(28), math.radians(-25), math.radians(-35))


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def add_camera():
    # Keep the same isometric angle while widening the campus framing.
    bpy.ops.object.camera_add(location=(65, -75, 58.5))
    cam = bpy.context.object
    cam.name = "Camera"
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 90
    look_at(cam, (0, 0, 6))
    bpy.context.scene.camera = cam


def setup_scene():
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = RENDER_OUT
    scene.render.film_transparent = False
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass


def build():
    clear_scene()
    setup_scene()
    add_ground()
    # Spread building centers around the central road junction by about 1.2x.
    build_teaching((-28, 12.8, 0))
    build_dorm((11.2, 15, 0))
    build_library((-27, -15.8, 0))
    build_club((13.4, -11.4, 0))
    build_canteen((31.6, -22.2, 0))
    for x, y in ((-10, 2), (18, 2), (-10, 11), (18, 11), (-34, 4), (34, 7)):
        add_tree(x, y)
    for x, y, h in ((-4, 2, 0), (4, 2, 180), (-4, 11, 180), (4, 11, 0)):
        add_lamp(x, y, h)
    add_bench(-5.5, 1.3, 90)
    add_bench(5.2, 1.0, 90)
    add_planter(-3.8, 1.5)
    add_bin(-8.2, 0.8)
    add_flag(7, 16)
    add_sign(4.6, 11.5)
    add_bike_rack(5.2, 3.0)
    add_flower_bed(16, 1.2)
    add_lighting()
    add_camera()
    bpy.ops.wm.save_as_mainfile(filepath=BLEND_OUT)
    bpy.ops.render.render(write_still=True)
    return {
        "blend": BLEND_OUT,
        "render": RENDER_OUT,
        "objects": len(bpy.context.scene.objects),
        "collections": [c.name for c in bpy.data.collections],
    }


print(build())
