"""Offscreen acceptance: real game textures, WASD movement and occlusion."""

import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from game import config
from game.app import NaiwaApp, apply_prc

OUT = ROOT / "reports" / "standalone" / "A" / "building_textures"
OUT.mkdir(parents=True, exist_ok=True)
options = config.Options(dev=True, scene="CampusScene", skip_intro=True, offscreen=True, seed=42)
config.setup_logging(options, ROOT / "build" / "texture_import" / "verify.log")
apply_prc(options, config.Settings.load())
app = NaiwaApp(options)
app.taskMgr.remove("offscreen_capture")


def capture(name):
    for _ in range(3):
        app.graphicsEngine.renderFrame()
    target = OUT / f"{name}.png"
    assert app.pipeline.save_buffer_screenshot(str(target))
    return np.asarray(Image.open(target).convert("RGB"))


try:
    app.scenes.update(1.0)
    app._update_fade()
    scene = app.scenes.base_scene
    assert app.scenes.current_id == "CampusScene"
    assert len(scene.root.findAllMatches("**/*_front_texture")) == 5
    ground = scene.root.find("**/model_ground")
    print("ground bounds", ground.getTightBounds(scene.root))
    report = {"buildings": {}, "movement": {}}

    class Keys:
        pressed = set()

        def isButtonDown(self, button):
            return button in self.pressed

    watcher = app.mouseWatcherNode
    keys = Keys()
    app.mouseWatcherNode = keys
    for key, (dx, dy) in {"w": (0, 1), "s": (0, -1), "a": (-1, 0), "d": (1, 0)}.items():
        before = tuple(scene.pos)
        keys.pressed = {scene.keys[key]}
        scene.on_update(0.25)
        delta = (scene.pos[0] - before[0], scene.pos[1] - before[1])
        assert abs(delta[0] - dx) < 1e-6 and abs(delta[1] - dy) < 1e-6, (key, delta)
        report["movement"][key] = delta
    before = tuple(scene.pos)
    keys.pressed = {scene.keys["w"], scene.keys["d"]}
    scene.on_update(0.25)
    assert abs(math.dist(before, scene.pos) - 1.0) < 1e-6
    report["movement"]["diagonal_distance"] = math.dist(before, scene.pos)
    app.mouseWatcherNode = watcher

    pitch = math.sin(math.radians(abs(config.CAMERA_TILT_DEGREES)))
    shots = []
    for name, cx, cy, width, depth in scene.BUILDINGS:
        node = scene.root.find(f"**/{name}_front_texture")
        assert not node.isEmpty()
        texture = node.getTexture()
        height = width * texture.getYSize() / texture.getXSize()
        base_y = cy - depth / 2
        app.pipeline.align_camera(cx, base_y + height / (2 * pitch))
        scene.facing = "s"
        scene.anim_time = 0
        scene._apply_frame(idle=True)
        scene.card.hide()
        background = capture(f"{name}_facade")
        shots.append((name, Image.fromarray(background)))

        scene.card.setPos(cx, base_y - 0.5, 0)
        scene.card.show()
        front = capture(f"{name}_player_front")
        front_pixels = int(np.any(background != front, axis=2).sum())
        assert front_pixels > 100, (name, "front player invisible", front_pixels)
        scene.card.setY(base_y + 0.5)
        behind = capture(f"{name}_player_behind")
        behind_pixels = int(np.any(background != behind, axis=2).sum())
        assert behind_pixels == 0, (name, "behind player shows through facade", behind_pixels)

        if name == "teaching":
            scene.card.setPos(cx - width * 0.46, base_y + height * 0.8 / pitch, 0)
            outside = capture("transparent_corner")
            corner_pixels = int(np.any(background != outside, axis=2).sum())
            assert corner_pixels > 100, ("transparent corner hides player", corner_pixels)
            report["transparent_corner_visible_pixels"] = corner_pixels

        report["buildings"][name] = {"texture_size": [texture.getXSize(), texture.getYSize()],
            "player_front_visible_pixels": front_pixels, "player_behind_visible_pixels": behind_pixels}

    scene.card.setPos(40, 5, 0)
    scene.card.show()
    app.pipeline.align_camera(40, 5)
    capture("spawn")
    app.pipeline.camera.getLens().setFilmSize(83, 83 * 9 / 16)
    app.pipeline.align_camera(38, 2.5)
    capture("campus_overview")
    assert not app.registry.missing, app.registry.missing
    report["missing_assets"] = dict(app.registry.missing)

    contact = Image.new("RGB", (1440, 930), (29, 34, 31))
    draw = ImageDraw.Draw(contact)
    for i, (name, shot) in enumerate(shots):
        x, y = (i % 2) * 720, (i // 2) * 310
        contact.paste(shot, (x + 120, y + 6))
        draw.text((x + 126, y + 282), name, fill="white", font_size=20)
    contact.save(OUT / "facade_contact.png")
    (OUT / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
finally:
    app.destroy()
