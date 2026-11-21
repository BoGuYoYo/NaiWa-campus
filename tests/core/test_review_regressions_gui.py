"""上轮审查问题的真实场景、输入与渲染回归。"""

from __future__ import annotations

import pytest

from game import config
from game.app import NaiwaApp, apply_prc
from game.core.results import EndingResult
from game.sim.simulator import run
from game.ui.graduation_scene import GraduationScene

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    config.set_user_dir(tmp_path_factory.mktemp("review_regressions"))
    options = config.Options(offscreen=True, windowed=(1280, 600))
    apply_prc(options, config.Settings())
    instance = NaiwaApp(options)
    _settle(instance)
    try:
        yield instance
    finally:
        instance.scenes.pop_all()
        if instance.scenes.base_scene is not None:
            instance.scenes._exit(instance.scenes.base_scene)
        instance.stop_audio()
        instance.destroy()
        config.set_user_dir(None)


def _settle(app):
    for _ in range(4):
        if not app.scenes.is_transitioning():
            return
        app.scenes.update(0.3)
    raise AssertionError("场景切换没有结束")


def _new_game(app):
    app.scenes.pop_all()
    state = app.flow.new_game(seed=42, skip_intro=True)
    _settle(app)
    return state


def _close_result(app):
    for _ in range(4):
        if app.scenes.top_overlay_id != "ResultPanel":
            return
        app.input.dispatch("space")
    raise AssertionError("结果面板没有关闭")


def test_loaded_actions_summary_and_no_stale_interaction(app):
    state = _new_game(app)
    campus = app.scenes.base_scene
    campus.player.teleport(40.0, 31.5)
    campus._refresh_prompt(force=True)
    assert campus.tracker.active_id == "ia_plaza_bench"
    now = [0.0]
    campus.interaction._clock = lambda: now[0]
    events = []
    handler = app.bus.subscribe("activity.done", lambda **data: events.append(data["result"]))
    try:
        for _ in range(2):
            now[0] += 1.0
            app.input.dispatch("e")
            assert app.scenes.top_overlay_id == "ResultPanel"
            _close_result(app)
        assert state.action_slot == 2
        assert len(events) == 2  # 每次交互只广播一次
        app.saves.save(state, "slot_1")

        state = app.flow.load_game("slot_1")
        _settle(app)
        campus = app.scenes.base_scene
        campus._refresh_prompt(force=True)
        now[0] += 1.0
        campus.interaction._clock = lambda: now[0]
        app.input.dispatch("e")
        _close_result(app)
        assert len(events) == 3
        assert app.scenes.top_overlay_id == "DaySummary"
        rows = app.scenes.overlays[-1][1].widget.action_lines
        assert [line.get_text() for line in rows if line.visible] == [
            "1. 校园闲逛", "2. 校园闲逛", "3. 校园闲逛",
        ]
        now[0] += 1.0
        app.input.dispatch("space")
        assert (state.world.x, state.world.y) == (40.0, 5.0)
        app.input.dispatch("e")  # 同一帧关面板并交互，不能使用广场的旧目标
        assert app.scenes.top_overlay_id is None
        assert state.action_slot == 0
    finally:
        app.bus.unsubscribe("activity.done", handler)


def test_ui_viewport_and_fade_cover_existing_window_after_resize(app):
    from types import SimpleNamespace

    from panda3d.core import PNMImage, Point3
    from game.ui.widgets import UITransform

    _new_game(app)

    def assert_aligned():
        transform = app.ui_transform
        for x, y, cx, cz in ((0, 0, -1, 1), (480, 270, 1, -1)):
            ax, az = transform.to_aspect2d(x, y)
            ui = app.render2d.get_relative_point(app.ui_root, Point3(ax, 0, az))
            world = app.render2d.get_relative_point(app.pipeline.card, Point3(cx, 0, cz))
            assert (ui.x, ui.z) == pytest.approx((world.x, world.z), abs=1e-5)

    assert_aligned()
    original_transform = app.ui_transform

    class ResizedWindow:
        def __init__(self, width, height):
            self.width, self.height = width, height

        def getXSize(self):
            return self.width

        def getYSize(self):
            return self.height

        get_x_size = getXSize
        get_y_size = getYSize

    try:
        # 离屏 GraphicsBuffer 不支持调整尺寸；模拟系统尺寸事件并更新引擎纵横比。
        for width, height in ((1010, 720), (600, 1000)):
            window = ResizedWindow(width, height)
            app.adjustWindowAspectRatio(width / height)
            app._on_window_event(window)
            assert app.ui_transform is original_transform
            assert_aligned()
            direct = UITransform.from_base(SimpleNamespace(win=window))
            ax, az = direct.to_aspect2d(0, 0)
            ui = app.render2d.get_relative_point(app.aspect2d, Point3(ax, 0, az))
            world = app.render2d.get_relative_point(app.pipeline.card, Point3(-1, 0, 1))
            assert (ui.x, ui.z) == pytest.approx((world.x, world.z), abs=1e-5)

        app.scenes.fade_alpha = 1.0
        app._update_fade()
        for _ in range(3):
            app.graphics_engine.render_frame()
        image = PNMImage()
        assert app.win.get_screenshot(image)
        for x, y in ((5, 5), (1274, 5), (5, 594), (1274, 594), (640, 300)):
            assert max(image.get_xel(x, y)) < 0.01
    finally:
        app.scenes.fade_alpha = 0.0
        app._update_fade()
        app.adjustWindowAspectRatio(1280 / 600)
        app._on_window_event(app.win)


@pytest.mark.parametrize("ending_id", [
    "ending_mediocre",
    "ending_tech_master",
    "ending_delayed",
    "ending_kaoyan",
    "ending_romance_nailong",
])
def test_graduation_shows_the_matching_ending_cg(app, ending_id):
    widget = GraduationScene(app.ui_root, app.ui_transform, app.text, app.registry)
    try:
        widget.open(EndingResult(ending_id=ending_id))
        widget.on_space()
        widget.on_space()

        asset_id = f"cg_{ending_id}"
        assert app.registry.has_texture(asset_id)
        assert not widget.ending_cg.is_hidden()
        assert not widget.ending_cg_scrim.is_hidden()
        assert widget.panel.is_shown() is False
        assert widget.ending_title.get_text() == app.text.get(f"ending.{ending_id}.title")
    finally:
        widget.destroy()


def test_graduation_falls_back_to_text_when_ending_cg_is_unavailable(app):
    widget = GraduationScene(app.ui_root, app.ui_transform, app.text)
    try:
        widget.open(EndingResult(ending_id="ending_mediocre"))
        widget.on_space()
        widget.on_space()

        assert widget.ending_cg.is_hidden()
        assert widget.ending_cg_scrim.is_hidden()
        assert widget.panel.is_shown()
        assert widget.page_title.is_shown()
        assert widget.ending_title.get_text() == app.text.get("ending.ending_mediocre.title")
    finally:
        widget.destroy()


def test_graduation_review_keeps_all_eight_semester_choices(app):
    report = run("kaoyan", seed=42)
    ending = EndingResult(ending_id=report["ending_id"], highlights=report["highlights"])
    widget = GraduationScene(app.ui_root, app.ui_transform, app.text, app.registry)
    try:
        widget.open(ending, report["final"])
        widget.on_space()
        lines = [label.get_text() for label in widget.content.labels if label.visible]
        assert len(lines) == 11
        assert lines[-1] == "完成毕业答辩"
        assert widget.content.labels[-1].text_node.get_z() > widget.page_hint.text_node.get_z()
    finally:
        widget.destroy()


def test_npc_prompt_matches_rendered_position_and_board_is_reachable(app):
    from types import SimpleNamespace

    from game.world.collision import PLAYER_HALF, overlap

    state = _new_game(app)
    for building_id, npc_name in (("loc_library", "李振兴"),
                                  ("loc_clubroom", "符闹吃"),
                                  ("loc_canteen", "奈珑")):
        app.scenes.change("InteriorScene", building_id=building_id, state=state)
        _settle(app)
        room = app.scenes.base_scene
        mark = next(mark for mark in room.npc_marks() if mark.name == npc_name)
        candidate = next(c for c in room.candidates if c.type == "npc")
        ox, oy = room.scene.origin
        assert (candidate.x, candidate.y) == pytest.approx((ox + mark.x, oy + mark.y))
        for dy in (-0.75, 0.75):
            point = SimpleNamespace(x=ox + mark.x, y=oy + mark.y + dy)
            assert not any(overlap(point, PLAYER_HALF, rect) for rect in room.player._rects)
            room.player.teleport(point.x, point.y)
            room.tracker.reset()
            room._refresh_prompt(force=True)
            assert room.tracker.active_id == candidate.id

    app.scenes.change("InteriorScene", building_id="loc_classroom", state=state)
    _settle(app)
    room = app.scenes.base_scene
    ox, oy = room.scene.origin
    room.player._key_down = lambda key: key == "w"
    for dx in (-1.0, 0.0, 1.0):
        room.player.teleport(ox + 3.0 + dx, oy + 6.0)
        room.tracker.reset()
        for _ in range(120):
            room.on_update(1 / 60)
        assert room.tracker.active_id == "ia_course_board"
