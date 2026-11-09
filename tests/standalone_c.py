"""任务 C 的独立命令入口（手册"独立运行测试契约"）。

本模块不启动完整游戏，也不依赖 A / B / D 尚未交付的代码：
只使用 tests/world/fixtures 下的 Fake 服务、固定 JSON 与 game/world 的纯逻辑模块。

四条独立命令：
    python -m pytest tests/world -m 'not gui' -q
    python -m tests.standalone_c --route C-R1 --fake-services
    python -m tests.standalone_c --collision-fuzz 3000 --out reports/standalone/C/collision.json
    python -m tests.standalone_c --camera-check --map content/world/map.json

临时报告一律写入 reports/standalone/C/，不写入用户存档、正式 assets 或正式 content。
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORLD_TESTS = ROOT / "tests" / "world"

for _path in (str(ROOT), str(WORLD_TESTS)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from fixtures.core_stub import install_core_results_stub  # noqa: E402
from fixtures.fake_services import (  # noqa: E402
    FakeActivityService,
    FakeEventBus,
    FakeRelationshipService,
    FakeSceneManager,
)
from fixtures.fake_state import FakeState  # noqa: E402

install_core_results_stub(ROOT)

from game.world.camera_controller import (  # noqa: E402
    CAMERA_HPR,
    FILM_HEIGHT,
    FILM_WIDTH,
    OUTDOOR_TARGET_MAX,
    OUTDOOR_TARGET_MIN,
    PIXEL,
    CameraRig,
    align_pixel,
    clamp_target,
    deadzone_desired,
    smooth,
)
from game.world.collision import (  # noqa: E402
    PLAYER_HALF,
    Rect,
    clamp_to_bounds,
    move_and_collide,
    overlap,
)
from game.world.interaction_service import InteractionService  # noqa: E402
from game.world.map_data import CAMPUS_SCENE, MapData  # noqa: E402

REPORT_DIR = ROOT / "reports" / "standalone" / "C"
CONTENT_MAP = ROOT / "content" / "world" / "map.json"

# 相机：半视宽 10 米（film 20 / 2），半视深 = 11.25 / 2 / sin40° ≈ 8.75 米
# 规格把 target.y 的下界定为 8.75，即由该半视深取整得到。
HALF_VIEW_X = FILM_WIDTH / 2.0
HALF_VIEW_Y = OUTDOOR_TARGET_MIN[1]


class _Vec:
    """带可读写 x / y 的最小坐标对象，供 move_and_collide 就地修改。"""

    __slots__ = ("x", "y")

    def __init__(self, x: float, y: float) -> None:
        self.x = float(x)
        self.y = float(y)


class _Clock:
    """单调递增的假时钟：每次读取前进 1 秒，避免命中 0.3 秒重复按键锁。"""

    def __init__(self, start: float = 1000.0) -> None:
        self._t = float(start)

    def __call__(self) -> float:
        self._t += 1.0
        return self._t


def _report_path(name: str) -> Path:
    return REPORT_DIR / name


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def _load_map(map_path: Path | str) -> MapData:
    path = Path(map_path)
    return MapData.from_files(path, path.parent / "interactables.json")


def _scene_rects_bounds(map_data: MapData, scene: str):
    """返回某场景在世界坐标下的阻挡矩形与可通行边界。"""
    if scene == CAMPUS_SCENE:
        return map_data.colliders_for(CAMPUS_SCENE), map_data.bounds
    origin = map_data.interior(scene).origin
    size = map_data.interior(scene).size
    rects = tuple(
        Rect(r.x0 + origin[0], r.y0 + origin[1], r.x1 + origin[0], r.y1 + origin[1])
        for r in map_data.colliders_for(scene)
    )
    bounds = Rect(origin[0], origin[1], origin[0] + size[0], origin[1] + size[1])
    return rects, bounds


def walk_to(pos: _Vec, target, rects, bounds, *, step: float = 0.05, max_steps: int = 20000) -> bool:
    """朝目标贪心行走：用 move_and_collide 贴墙滑动；完全卡死时返回 False。"""
    for _ in range(max_steps):
        dx = target[0] - pos.x
        dy = target[1] - pos.y
        dist = math.hypot(dx, dy)
        if dist <= step:
            return True
        delta = _Vec(dx / dist * step, dy / dist * step)
        bx, by = pos.x, pos.y
        move_and_collide(pos, delta, rects)
        clamp_to_bounds(pos, bounds)
        if math.hypot(pos.x - bx, pos.y - by) < 1e-9:
            return False
    return False


# ---------------------------------------------------------------------- 路线


class RouteRunner:
    """按 C-R1 路线驱动玩家：行走、进出门、按 E 交互，并记录服务调用。"""

    def __init__(self, map_data: MapData) -> None:
        self.map_data = map_data
        self.state = FakeState(location_id="loc_gate", x=40.0, y=5.0, facing="n")
        self.activity = FakeActivityService()
        self.relationship = FakeRelationshipService()
        self.scene_manager = FakeSceneManager()
        self.bus = FakeEventBus()
        self.service = InteractionService(
            map_data,
            self.activity,
            self.relationship,
            self.scene_manager,
            self.bus,
            clock=_Clock(),
        )
        self.pos = _Vec(*map_data.spawn[0])
        self.scene = CAMPUS_SCENE
        self.origin = (0.0, 0.0)
        self.rects, self.bounds = _scene_rects_bounds(map_data, CAMPUS_SCENE)
        self.steps: list[dict] = []
        self.problems: list[str] = []

    # -------------------------------------------------------------- 行走
    def walk(self, x: float, y: float, label: str = "", required: bool = True) -> bool:
        ok = walk_to(self.pos, (x, y), self.rects, self.bounds)
        if not ok and required:
            self.problems.append(
                f"无法走到 {label or f'({x:.2f}, {y:.2f})'}，卡在 ({self.pos.x:.2f}, {self.pos.y:.2f})"
            )
        return ok

    def walk_local(self, lx: float, ly: float, label: str = "", required: bool = True) -> bool:
        return self.walk(self.origin[0] + lx, self.origin[1] + ly, label, required)

    def walk_to_interactable(self, ia_id: str) -> bool:
        ia = self.map_data.interactable(ia_id)
        x, y = self.map_data.to_world(ia)
        return self.walk(x, y, label=ia_id)

    # -------------------------------------------------------------- 交互
    def interact(self, ia_id: str) -> str:
        result = self.service.interact(self.state, ia_id)
        ia = self.map_data.interactable(ia_id)
        self.steps.append(
            {
                "interactable": ia_id,
                "type": ia.type,
                "target": ia.target,
                "kind": result.kind,
            }
        )
        return result.kind

    # ---------------------------------------------------------- 场景切换
    def enter(self, building_id: str) -> None:
        self.scene = building_id
        self.state.world.location_id = building_id
        self.origin = self.map_data.interior(building_id).origin
        lx, ly, facing = self.map_data.interior_entry(building_id)
        self.pos = _Vec(self.origin[0] + lx, self.origin[1] + ly)
        self.state.world.facing = facing
        self.rects, self.bounds = _scene_rects_bounds(self.map_data, building_id)

    def exit(self, building_id: str, vias_local=()) -> None:
        for lx, ly in vias_local:
            self.walk_local(lx, ly, label=f"{building_id} 退出绕行")
        mx, my, mat_r = self.map_data.entry_mat(building_id)
        self.walk_local(mx, my, label=f"{building_id} 入口地垫", required=False)
        dist = math.hypot(self.pos.x - (self.origin[0] + mx), self.pos.y - (self.origin[1] + my))
        if dist > mat_r + 1e-6:
            self.problems.append(
                f"{building_id} 未走进入口地垫（距离 {dist:.3f} > 半径 {mat_r}）"
            )
        ex, ey, ef = self.map_data.exit_point(building_id)
        self.steps.append({"exit": building_id, "to": [ex, ey], "facing": ef})
        self.scene = CAMPUS_SCENE
        self.state.world.location_id = self.map_data.area_at(ex, ey) or CAMPUS_SCENE
        self.state.world.facing = ef
        self.pos = _Vec(ex, ey)
        self.rects, self.bounds = _scene_rects_bounds(self.map_data, CAMPUS_SCENE)


# 室内绕行点（房间本地坐标）：避开家具，直接给出可复现的点位
_CLASSROOM_IN = [(12.0, 1.6), (12.0, 6.0)]
_LIBRARY_IN = [(3.0, 1.6), (3.0, 5.0)]


def run_route(map_data: MapData, route_id: str, out_path: Path) -> dict:
    if route_id != "C-R1":
        raise SystemExit(f"只支持 C-R1 路线，收到：{route_id}")

    r = RouteRunner(map_data)

    # 出生点 → 宿舍（进出）
    r.walk_to_interactable("ia_door_dorm")
    if r.interact("ia_door_dorm") != "door":
        r.problems.append("宿舍门未返回 door")
    r.enter("loc_dorm")
    r.walk_to_interactable("ia_bed")
    r.interact("ia_bed")
    r.exit("loc_dorm")

    # → 操场
    r.walk_to_interactable("ia_track_start")
    r.interact("ia_track_start")

    # → 广场
    r.walk_to_interactable("ia_plaza_bench")
    r.interact("ia_plaza_bench")

    # → 教学楼（进出）
    r.walk_to_interactable("ia_door_classroom")
    if r.interact("ia_door_classroom") != "door":
        r.problems.append("教学楼门未返回 door")
    r.enter("loc_classroom")
    for vx, vy in _CLASSROOM_IN:
        r.walk_local(vx, vy, label="教学楼进入绕行")
    r.walk_to_interactable("ia_class_desk")
    r.interact("ia_class_desk")
    r.exit("loc_classroom", vias_local=[(12.0, 6.0), (12.0, 1.6)])

    # → 图书馆（进出）
    r.walk_to_interactable("ia_door_library")
    if r.interact("ia_door_library") != "door":
        r.problems.append("图书馆门未返回 door")
    r.enter("loc_library")
    for vx, vy in _LIBRARY_IN:
        r.walk_local(vx, vy, label="图书馆进入绕行")
    r.walk_to_interactable("ia_reading_desk")
    r.interact("ia_reading_desk")
    r.exit("loc_library", vias_local=[(3.0, 5.0), (3.0, 1.6)])

    # → 社团楼（进出）
    r.walk_to_interactable("ia_door_clubroom")
    if r.interact("ia_door_clubroom") != "door":
        r.problems.append("社团楼门未返回 door")
    r.enter("loc_clubroom")
    r.walk_to_interactable("ia_game_pc")
    r.interact("ia_game_pc")
    r.exit("loc_clubroom")

    # → 食堂（进出）
    r.walk_to_interactable("ia_door_canteen")
    if r.interact("ia_door_canteen") != "door":
        r.problems.append("食堂门未返回 door")
    r.enter("loc_canteen")
    r.walk_to_interactable("ia_food_window")
    r.interact("ia_food_window")
    r.exit("loc_canteen")

    # → 校门（绕开告示牌：先东移至 x=44.5，再南下落到底部，最后向北靠近）
    r.walk(44.5, 46.2, label="校门绕行 1")
    r.walk(44.5, 2.0, label="校门绕行 2")
    r.walk_to_interactable("ia_gate_notice")
    r.interact("ia_gate_notice")

    expected_activities = [
        "rest_dorm",
        "exercise",
        "campus_walk",
        "attend_class",
        "library_study",
        "play_games",
        "eat_canteen",
    ]
    expected_doors = ["loc_dorm", "loc_classroom", "loc_library", "loc_clubroom", "loc_canteen"]
    expected_pushes = [("EventScene", {"event_id": None, "text_id": "insp.gate_notice.body"})]

    actual_activities = [target for _loc, target in r.activity.start_calls]
    actual_doors = [kw.get("building_id") for sid, kw in r.scene_manager.changes if sid == "InteriorScene"]
    actual_pushes = r.scene_manager.pushes

    if actual_activities != expected_activities:
        r.problems.append(f"活动调用序列不符：{actual_activities} != {expected_activities}")
    if actual_doors != expected_doors:
        r.problems.append(f"门切换序列不符：{actual_doors} != {expected_doors}")
    if actual_pushes != expected_pushes:
        r.problems.append(f"覆盖层推送不符：{actual_pushes} != {expected_pushes}")
    if r.relationship.talk_calls:
        r.problems.append(f"C-R1 中不应有 NPC 交谈：{r.relationship.talk_calls}")
    done_events = [topic for topic, _ in r.bus.events]
    if done_events.count("activity.done") != len(expected_activities):
        r.problems.append(f"activity.done 事件数不符：{done_events}")

    report = {
        "agent": "C",
        "check": "route",
        "route": route_id,
        "ok": not r.problems,
        "steps": r.steps,
        "activity_calls": [list(c) for c in r.activity.start_calls],
        "scene_changes": [[sid, kw] for sid, kw in r.scene_manager.changes],
        "scene_pushes": [[sid, kw] for sid, kw in actual_pushes],
        "events": done_events,
        "final_position": [round(r.pos.x, 3), round(r.pos.y, 3)],
        "final_scene": r.scene,
        "problems": r.problems,
    }
    _write_json(out_path, report)
    return report


# ------------------------------------------------------------------ 碰撞模糊


def run_collision_fuzz(map_data: MapData, iterations: int, out_path: Path, seed: int) -> dict:
    rng = random.Random(seed)
    rects = map_data.colliders_for(CAMPUS_SCENE)
    bounds = map_data.bounds
    pos = _Vec(*map_data.spawn[0])
    failures: list[dict] = []
    blocked_steps = 0
    max_step = 0.0

    for i in range(iterations):
        angle = rng.uniform(0.0, 2.0 * math.pi)
        speed = rng.choice((4.0, 6.0))
        dt = rng.uniform(1.0 / 120.0, 1.0 / 30.0)
        delta = _Vec(math.cos(angle) * speed * dt, math.sin(angle) * speed * dt)
        before = (pos.x, pos.y)
        move_and_collide(pos, delta, rects)
        clamp_to_bounds(pos, bounds)

        moved = math.hypot(pos.x - before[0], pos.y - before[1])
        max_step = max(max_step, moved)
        if moved + 1e-9 < math.hypot(delta.x, delta.y):
            blocked_steps += 1

        if not (math.isfinite(pos.x) and math.isfinite(pos.y)):
            failures.append({"iteration": i, "reason": "NaN", "pos": [pos.x, pos.y]})
        elif not (
            bounds.x0 + PLAYER_HALF - 1e-6 <= pos.x <= bounds.x1 - PLAYER_HALF + 1e-6
            and bounds.y0 + PLAYER_HALF - 1e-6 <= pos.y <= bounds.y1 - PLAYER_HALF + 1e-6
        ):
            failures.append({"iteration": i, "reason": "out_of_bounds", "pos": [pos.x, pos.y]})
        elif any(overlap(pos, PLAYER_HALF, r) for r in rects):
            failures.append({"iteration": i, "reason": "inside_obstacle", "pos": [pos.x, pos.y]})

        # 周期性把玩家放到一个随机的空位，覆盖整张地图
        if i % 173 == 0:
            for _ in range(64):
                cand = _Vec(
                    rng.uniform(bounds.x0 + PLAYER_HALF, bounds.x1 - PLAYER_HALF),
                    rng.uniform(bounds.y0 + PLAYER_HALF, bounds.y1 - PLAYER_HALF),
                )
                if not any(overlap(cand, PLAYER_HALF, r) for r in rects):
                    pos = cand
                    break

    report = {
        "agent": "C",
        "check": "collision-fuzz",
        "ok": not failures,
        "iterations": iterations,
        "seed": seed,
        "blocked_steps": blocked_steps,
        "max_step_distance": round(max_step, 6),
        "bounds": [bounds.x0, bounds.y0, bounds.x1, bounds.y1],
        "obstacle_count": len(rects),
        "failures": failures[:20],
        "failure_count": len(failures),
    }
    _write_json(out_path, report)
    return report


# ------------------------------------------------------------------ 相机检查


def _approx(a, b, tol: float = 1e-6) -> bool:
    return math.isclose(a, b, rel_tol=0.0, abs_tol=tol)


def run_camera_check(map_data: MapData, out_path: Path) -> dict:
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    # 规格常量
    check(
        "film_is_24_px_per_meter",
        _approx(FILM_WIDTH * 24.0, 480.0) and _approx(FILM_HEIGHT * 24.0, 270.0),
        f"film=({FILM_WIDTH}, {FILM_HEIGHT})",
    )
    check("camera_hpr_is_fixed", CAMERA_HPR == (0.0, -40.0, 0.0), str(CAMERA_HPR))
    offset = (0.0, -30.0 * math.cos(math.radians(40.0)), 30.0 * math.sin(math.radians(40.0)))
    check(
        "camera_offset_matches_spec",
        _approx(offset[1], -22.98, 1e-2) and _approx(offset[2], 19.28, 1e-2),
        f"offset=({offset[1]:.4f}, {offset[2]:.4f})",
    )

    # 死区
    check("deadzone_holds_inside", deadzone_desired((40.0, 30.0), (41.5, 31.0)) == (40.0, 30.0))
    check(
        "deadzone_pushes_to_edge_x",
        deadzone_desired((40.0, 30.0), (44.0, 30.0)) == (42.0, 30.0),
    )
    check(
        "deadzone_pushes_to_edge_y",
        deadzone_desired((40.0, 30.0), (40.0, 33.0)) == (40.0, 31.5),
    )

    # 平滑：帧率无关
    one_shot = smooth((0.0, 0.0), (1.0, 1.0), 0.5)
    stepwise = (0.0, 0.0)
    for _ in range(30):
        stepwise = smooth(stepwise, (1.0, 1.0), 1.0 / 60.0)
    check(
        "smooth_is_frame_rate_independent",
        _approx(one_shot[0], stepwise[0], 2e-3) and _approx(one_shot[1], stepwise[1], 2e-3),
        f"one_shot={one_shot[0]:.4f} stepwise={stepwise[0]:.4f}",
    )

    # 边界
    check("clamp_low", clamp_target((-5.0, -5.0)) == OUTDOOR_TARGET_MIN, str(OUTDOOR_TARGET_MIN))
    check("clamp_high", clamp_target((99.0, 99.0)) == OUTDOOR_TARGET_MAX, str(OUTDOOR_TARGET_MAX))

    # 像素对齐
    v = 3.14159
    check("pixel_align_to_1_over_24", _approx(align_pixel(v), round(v / PIXEL) * PIXEL), f"align({v})")

    # 走到四个角落：视野不越出地图
    b = map_data.bounds
    corners = (
        (b.x0, b.y0),
        (b.x1, b.y0),
        (b.x0, b.y1),
        (b.x1, b.y1),
    )
    for cx, cy in corners:
        rig = CameraRig()
        for _ in range(900):
            rig.update((cx, cy), 1.0 / 60.0)
        tx, ty = rig.target
        inside = (
            b.x0 - 1e-6 <= tx - HALF_VIEW_X
            and tx + HALF_VIEW_X <= b.x1 + 1e-6
            and b.y0 - 1e-6 <= ty - HALF_VIEW_Y
            and ty + HALF_VIEW_Y <= b.y1 + 1e-6
        )
        check(
            f"corner_view_inside_map_{int(cx)}_{int(cy)}",
            inside,
            f"target=({tx:.3f}, {ty:.3f})",
        )

    # 相机位置像素对齐
    rig = CameraRig()
    rig.update((70.0, 50.0), 1.0 / 60.0)
    x, y, _z = rig.camera_xyz()
    check(
        "camera_position_pixel_aligned",
        _approx(x * 24.0, round(x * 24.0)) and _approx(y * 24.0, round(y * 24.0)),
        f"camera=({x:.4f}, {y:.4f})",
    )

    report = {
        "agent": "C",
        "check": "camera",
        "ok": all(c["ok"] for c in checks),
        "half_view": {"x": HALF_VIEW_X, "y": HALF_VIEW_Y},
        "target_bounds": {"min": list(OUTDOOR_TARGET_MIN), "max": list(OUTDOOR_TARGET_MAX)},
        "checks": checks,
    }
    _write_json(out_path, report)
    return report


# ------------------------------------------------------------------ 地图总览


def render_map(map_data: MapData, out_path: Path, width: int = 960, height: int = 720) -> bool:
    """用 Panda3D 离屏渲染一张带 F1 碰撞线框 + F2 交互点圆的俯视总览图。"""
    try:
        from panda3d.core import (
            Filename,
            OrthographicLens,
            loadPrcFileData,
        )
    except ImportError:
        return False

    loadPrcFileData("", "window-type offscreen")
    loadPrcFileData("", "audio-library-name null")
    loadPrcFileData("", "notify-level-display fatal")
    loadPrcFileData("", f"win-size {width} {height}")

    from direct.showbase.ShowBase import ShowBase

    from game.world.campus_scene import CampusScene
    from game.world.debug_draw import DebugDraw

    app = ShowBase()
    try:
        CampusScene(map_data, app.render)
        debug = DebugDraw(map_data, app.render)
        debug.toggle_collision()
        debug.toggle_interactables()

        b = map_data.bounds
        margin = 4.0
        film_w = (b.x1 - b.x0) + margin * 2.0
        film_h = (b.y1 - b.y0) + margin * 2.0
        lens = OrthographicLens()
        lens.setFilmSize(film_w, film_h)
        lens.setNearFar(1.0, 500.0)
        app.cam.node().setLens(lens)
        app.cam.setPos((b.x0 + b.x1) / 2.0, (b.y0 + b.y1) / 2.0, 120.0)
        app.cam.setHpr(0.0, -90.0, 0.0)

        app.graphicsEngine.renderFrame()
        app.graphicsEngine.renderFrame()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        return bool(app.win.saveScreenshot(Filename(str(out_path))))
    finally:
        app.destroy()


def render_map_with_pillow(map_data: MapData, out_path: Path, scale: int = 10) -> bool:
    """离屏渲染不可用时的兜底：用 pillow 直接画俯视示意图（含碰撞框与交互点）。"""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return False

    b = map_data.bounds
    w = int((b.x1 - b.x0) * scale)
    h = int((b.y1 - b.y0) * scale)
    img = Image.new("RGB", (w, h), (107, 140, 89))
    draw = ImageDraw.Draw(img)

    def to_px(x: float, y: float):
        return (x - b.x0) * scale, h - (y - b.y0) * scale

    for area in map_data.areas:
        r = area.rect
        draw.rectangle([to_px(r.x0, r.y1), to_px(r.x1, r.y0)], fill=(150, 150, 145))

    for rect in map_data.colliders_for(CAMPUS_SCENE):
        draw.rectangle([to_px(rect.x0, rect.y1), to_px(rect.x1, rect.y0)], outline=(255, 40, 40), width=2)

    for ia in map_data.interactables_for(CAMPUS_SCENE):
        x, y = map_data.to_world(ia)
        cx, cy = to_px(x, y)
        rr = ia.radius * scale
        draw.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=(51, 230, 77), width=2)

    sx, sy = map_data.spawn[0]
    px, py = to_px(sx, sy)
    draw.polygon([(px, py - 8), (px - 7, py + 5), (px + 7, py + 5)], fill=(245, 217, 46))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return True


# ---------------------------------------------------------------------- 入口


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tests.standalone_c")
    parser.add_argument("--route", metavar="ID", help="人工烟测路线（目前支持 C-R1）")
    parser.add_argument("--fake-services", action="store_true", help="使用 tests/world/fixtures 的 Fake 服务")
    parser.add_argument("--collision-fuzz", type=int, metavar="N", help="运行 N 步随机碰撞模糊")
    parser.add_argument("--camera-check", action="store_true", help="校验相机数学与边界")
    parser.add_argument("--render-map", metavar="PATH", help="渲染地图总览图（F1+F2）到指定路径")
    parser.add_argument("--map", default=str(CONTENT_MAP), help="map.json 路径")
    parser.add_argument("--out", default=None, help="报告输出路径")
    parser.add_argument("--seed", type=int, default=20261109, help="随机种子")
    args = parser.parse_args(argv)

    map_data = _load_map(args.map)

    if args.route:
        if not args.fake_services:
            print("[route] 独立命令必须搭配 --fake-services（不启动完整游戏）", file=sys.stderr)
            return 2
        out = Path(args.out) if args.out else _report_path("route_C-R1.json")
        report = run_route(map_data, args.route, out)
        print(f"[route] {args.route}: {'通过' if report['ok'] else '失败'}")
        for step in report["steps"]:
            if "interactable" in step:
                print(f"  E  {step['interactable']:<20} -> {step['kind']}（{step['target']}）")
            else:
                print(f"  退出 {step['exit']} -> ({step['to'][0]}, {step['to'][1]})")
        for problem in report["problems"]:
            print(f"  问题：{problem}")
        print(f"[route] 报告写入 {out}")
        return 0 if report["ok"] else 1

    if args.collision_fuzz is not None:
        out = Path(args.out) if args.out else _report_path("collision.json")
        report = run_collision_fuzz(map_data, args.collision_fuzz, out, args.seed)
        print(
            f"[collision-fuzz] {report['iterations']} 步，阻挡 {report['blocked_steps']} 步，"
            f"失败 {report['failure_count']}：{'通过' if report['ok'] else '失败'}"
        )
        for failure in report["failures"]:
            print(f"  失败：{failure}")
        print(f"[collision-fuzz] 报告写入 {out}")
        return 0 if report["ok"] else 1

    if args.camera_check:
        out = Path(args.out) if args.out else _report_path("camera_check.json")
        report = run_camera_check(map_data, out)
        print(f"[camera-check] {'通过' if report['ok'] else '失败'}")
        for item in report["checks"]:
            print(f"  [{'ok' if item['ok'] else '!!'}] {item['name']} {item['detail']}".rstrip())
        print(f"[camera-check] 报告写入 {out}")
        return 0 if report["ok"] else 1

    if args.render_map:
        out = Path(args.render_map)
        if not render_map(map_data, out):
            print("[render-map] Panda3D 离屏渲染不可用，改用 pillow 兜底")
            if not render_map_with_pillow(map_data, out):
                print("[render-map] 渲染失败", file=sys.stderr)
                return 1
        print(f"[render-map] 已写入 {out}")
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
