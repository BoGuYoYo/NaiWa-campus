"""任务 C1~C3 / C6 / C9 的 Panda3D 场景层烟测（离屏渲染）。

这些测试需要 Panda3D 图形上下文，默认被 `-m 'not gui'` 跳过；
它们验证 campus_scene / interior_scene / debug_draw / camera_controller /
player_controller 能真实构建并协同工作。
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.gui

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def base():
    pytest.importorskip("panda3d.core")
    from panda3d.core import loadPrcFileData

    loadPrcFileData("", "window-type offscreen")
    loadPrcFileData("", "audio-library-name null")
    loadPrcFileData("", "notify-level-display fatal")

    from direct.showbase.ShowBase import ShowBase

    app = ShowBase()
    try:
        yield app
    finally:
        app.destroy()


class FakePlayer:
    def __init__(self) -> None:
        self.teleports: list[tuple[float, float]] = []

    def teleport(self, x, y, facing=None):
        self.teleports.append((x, y))


# ------------------------------------------------------------------ C1~C3 场景


def test_campus_scene_builds(base, map_data):
    from game.world.campus_scene import CampusScene

    scene = CampusScene(map_data, base.render, dev=True)
    try:
        assert scene.scene_id == "CampusScene"
        assert scene.root.getName() == "CampusScene"
        assert scene.colliders == map_data.colliders_for("campus")
        assert scene.bounds == map_data.bounds
        assert not scene.root.isEmpty()
    finally:
        scene.destroy()


def test_campus_scene_is_flattened(base, map_data):
    from game.world.campus_scene import CampusScene

    scene = CampusScene(map_data, base.render)
    try:
        # flattenStrong 之后应合并为个位数的几何节点
        assert len(scene.root.getChildren()) < 10
    finally:
        scene.destroy()


def test_interior_scene_world_bounds_and_points(base, map_data):
    from game.world.collision import Rect
    from game.world.interior_scene import InteriorScene

    scene = InteriorScene(map_data, "loc_dorm", base.render)
    try:
        assert scene.scene_id == "InteriorScene"
        assert scene.bounds_world() == Rect(200.0, 0.0, 216.0, 10.0)
        assert scene.entry_world() == (208.0, 1.6, "n")
        assert scene.mat_world() == pytest.approx((208.0, 0.6, 0.8))
        assert scene.exit_world() == map_data.exit_point("loc_dorm") == (19.8, 17.0, "e")
    finally:
        scene.destroy()


def test_interior_scene_colliders_are_translated(base, map_data):
    from game.world.interior_scene import InteriorScene

    scene = InteriorScene(map_data, "loc_dorm", base.render)
    try:
        origin = map_data.interior("loc_dorm").origin
        local = scene.colliders_local()
        world = scene.colliders_world()
        assert len(local) == len(world)
        for loc, wld in zip(local, world):
            assert wld.x0 == pytest.approx(loc.x0 + origin[0])
            assert wld.y0 == pytest.approx(loc.y0 + origin[1])
    finally:
        scene.destroy()


INTERIOR_IDS = ("loc_dorm", "loc_classroom", "loc_library", "loc_clubroom", "loc_canteen")


@pytest.mark.parametrize("building_id", INTERIOR_IDS)
def test_every_interior_builds(base, map_data, building_id):
    """5 栋室内都必须能构造并完成 flatten。

    旧版用 GeomLinestrips 画地垫/NPC 圈，Panda3D 1.10.16 下
    library / canteen 会在 flattenStrong() 处踩断言直接崩。
    """
    from game.world.interior_scene import InteriorScene

    scene = InteriorScene(map_data, building_id, base.render)
    try:
        base.graphics_engine.render_frame()
        assert scene.root.get_num_children() > 0
        bounds = scene.bounds_world()
        assert bounds.x1 > bounds.x0 and bounds.y1 > bounds.y0
        assert scene.entry_world()[2] in ("n", "s", "e", "w")
    finally:
        scene.destroy()


def test_interior_entry_mat_triggers_once_with_cooldown(base, map_data):
    from game.world.interior_scene import EXIT_COOLDOWN, InteriorScene

    scene = InteriorScene(map_data, "loc_dorm", base.render)
    try:
        assert scene.update_mat(210.0, 5.0, 0.016) is False  # 远离地垫
        assert scene.update_mat(208.0, 0.6, 0.016) is True
        # 冷却期内不再触发
        assert scene.update_mat(208.0, 0.6, EXIT_COOLDOWN / 2.0) is False
        assert scene.update_mat(208.0, 0.6, EXIT_COOLDOWN / 2.0) is False
        # 冷却结束后再次触发
        assert scene.update_mat(208.0, 0.6, 0.016) is True
        scene.reset_cooldown()
        assert scene.update_mat(208.0, 0.6, 0.016) is True
    finally:
        scene.destroy()


# ------------------------------------------------------------------ C9 调试绘制


def test_debug_draw_toggles_collision_and_interactables(base, map_data):
    from game.world.debug_draw import DebugDraw

    dd = DebugDraw(map_data, base.render)
    try:
        assert dd.toggle_collision() is True
        assert len(dd.collision_root.getChildren()) == len(map_data.colliders_for("campus"))
        assert dd.toggle_collision() is False
        assert dd.collision_root.isHidden() is True

        assert dd.toggle_interactables() is True
        assert len(dd.interactable_root.getChildren()) == len(
            map_data.interactables_for("campus")
        )
    finally:
        dd.root.removeNode()


def test_debug_draw_rebuilds_on_scene_change(base, map_data):
    from game.world.debug_draw import DebugDraw

    dd = DebugDraw(map_data, base.render)
    try:
        dd.toggle_interactables()
        dd.set_scene("loc_dorm")
        assert len(dd.interactable_root.getChildren()) == 0
        dd.toggle_interactables()
        assert len(dd.interactable_root.getChildren()) == len(
            map_data.interactables_for("loc_dorm")
        )
    finally:
        dd.root.removeNode()


def test_debug_draw_teleport_cycles_all_interactables(base, map_data):
    from game.world.debug_draw import DebugDraw

    player = FakePlayer()
    dd = DebugDraw(map_data, base.render, player=player)
    try:
        total = len(map_data.interactables)
        seen = [dd.teleport_next_interactable() for _ in range(total)]
        assert seen == [ia.id for ia in map_data.interactables]
        # 再次调用回到起点
        assert dd.teleport_next_interactable() == map_data.interactables[0].id
        assert len(player.teleports) == total + 1
    finally:
        dd.root.removeNode()


def test_debug_draw_f6_sets_action_slot(base, map_data):
    from game.world.debug_draw import DebugDraw

    from fixtures.fake_state import FakeState

    state = FakeState(action_slot=0)
    dd = DebugDraw(map_data, base.render, state=state)
    try:
        dd.set_slot_three()
        assert state.action_slot == 3
        # 不触碰属性字段
        assert not hasattr(state, "academic")
    finally:
        dd.root.removeNode()


# ------------------------------------------------------------------ C6 相机


def test_camera_controller_sets_ortho_lens_and_fixed_hpr(base):
    from panda3d.core import Camera, OrthographicLens

    from game.world.camera_controller import (
        CAMERA_HPR,
        FILM_HEIGHT,
        FILM_WIDTH,
        CameraController,
    )

    cam_np = base.render.attachNewNode(Camera("test_cam"))
    try:
        ctrl = CameraController(cam_np)
        lens = cam_np.node().getLens()
        assert isinstance(lens, OrthographicLens)
        assert lens.getFilmSize().getX() == pytest.approx(FILM_WIDTH)
        assert lens.getFilmSize().getY() == pytest.approx(FILM_HEIGHT)

        hpr = cam_np.getHpr()
        assert (hpr.getX(), hpr.getY(), hpr.getZ()) == pytest.approx(CAMERA_HPR)

        for _ in range(120):
            ctrl.update((70.0, 50.0), 1.0 / 60.0)
        # 相机朝向始终不变
        hpr = cam_np.getHpr()
        assert (hpr.getX(), hpr.getY(), hpr.getZ()) == pytest.approx(CAMERA_HPR)
        assert cam_np.getX() * 24 == pytest.approx(round(cam_np.getX() * 24))
    finally:
        cam_np.removeNode()


# ------------------------------------------------------------------ C5 玩家


def test_player_controller_moves_real_node(base, map_data):
    from game.world.player_controller import PlayerController

    from fixtures.fake_state import FakeState

    state = FakeState()
    node = base.render.attachNewNode("player")
    try:
        ctrl = PlayerController(map_data, state, node, key_down=lambda k: k == "d")
        for _ in range(30):
            ctrl.update(1.0 / 60.0)
        assert node.getX() > 40.0
        assert node.getY() == pytest.approx(5.0)
        assert node.getH() == pytest.approx(0.0)  # 卡片不按朝向旋转
        assert state.world.x == pytest.approx(node.getX())
    finally:
        node.removeNode()
