"""Offscreen Panda3D GUI regression tests for verified audit fixes."""

from __future__ import annotations

import json
import math

import pytest

from game import config
from game.app import NaiwaApp, apply_prc
from game.core.results import EndingResult
from game.core.world_scene import CampusSceneAdapter, SettingsMenuSceneAdapter
from game.ui import theme
from game.ui.graduation_scene import GraduationScene
from game.ui.main_menu import MainMenu
from game.ui.save_menu import SaveMenu
from game.ui.settings_menu import SettingsMenu
from game.ui.widgets import StatBar
from game.world.campus_scene import CampusScene, make_wall_panel
from game.world.collision import Rect
from game.world.debug_draw import DebugDraw

pytestmark = pytest.mark.gui


def _settle(app: NaiwaApp) -> None:
    for _ in range(8):
        if not app.scenes.is_transitioning():
            return
        app.scenes.update(0.25)


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    config.set_user_dir(tmp_path_factory.mktemp("audit_fixes_gui"))
    options = config.Options(offscreen=True, dev=True)
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


def test_fade_card_renders_above_gui_popup_bin(app):
    assert app._fade_card.getBinName() == "gui-popup"
    assert app._fade_card.getBinDrawOrder() >= 100


def test_statbar_crops_transparent_margin_and_stays_aligned(app):
    bar = StatBar(app.ui_root, app.ui_transform, 50.0, 50.0, asset_registry=app.registry, width=80.0)
    try:
        bar.set_value(10.0, 100.0)
        assert bar.fill.get_x() == pytest.approx(bar.back.get_x(), abs=1e-5)
        assert bar.fill.get_sx() == pytest.approx(bar.back.get_sx() * 0.1, rel=1e-3)
    finally:
        bar.destroy()


def test_main_menu_padding_keeps_cursor_and_items_inside_panel(app):
    menu = MainMenu(app.ui_root, app.ui_transform, app.text, app.registry)
    try:
        rect_x = theme.RECTS["main_menu"][0]
        ax_min = app.ui_transform.to_aspect2d(rect_x + 4, 0)[0]
        assert menu.cursor.root.get_x() >= ax_min - 1e-5
        assert menu.labels[0].root.get_x() > menu.cursor.root.get_x()
    finally:
        menu.destroy()


def test_graduation_cg_page_hint_sits_on_title_row_above_body(app):
    grad = GraduationScene(app.ui_root, app.ui_transform, app.text, app.registry)
    try:
        grad.open(EndingResult(ending_id="ending_kaoyan", highlights=[]), {"stats": {}, "relationships": {}})
        grad.on_space()
        grad.on_space()
        # Title sits at y=190 while body starts at y=210 -> higher aspect2d z means higher on screen.
        assert grad.page_hint.root.get_z() > grad.ending_body.labels[0].root.get_z()
    finally:
        grad.destroy()


def test_settings_menu_cancel_restores_snapshot_without_saving(app, tmp_path):
    settings = config.Settings(text_speed="normal", master_volume=70, bgm_volume=60, sfx_volume=50)
    calls: list[str] = []
    settings.save = lambda: calls.append("saved")  # type: ignore[method-assign]
    widget = SettingsMenu(app.ui_root, app.ui_transform, app.text, settings, app.registry)
    try:
        widget.show()
        widget.adjust(1)  # text_speed -> fast
        widget.move(1)
        widget.adjust(1)  # master_volume -> 80
        widget.cancel()
        assert settings.text_speed == "normal"
        assert settings.master_volume == 70
        assert calls == []

        widget.show()
        widget.adjust(1)
        widget.confirm()
        assert settings.text_speed == "fast"
        assert calls == ["saved"]
    finally:
        widget.destroy()

    # SettingsMenuSceneAdapter reapplies audio volume on cancel exit too.
    app.settings.master_volume = 50
    app.audio.current_music = "bgm_title"
    app.flow.new_game(seed=1, skip_intro=True)
    _settle(app)
    app.scenes.push("SettingsMenu")
    adapter = app.scenes.overlays[-1][1]
    assert isinstance(adapter, SettingsMenuSceneAdapter)
    adapter.widget.move(1)
    adapter._adjust(1)
    assert app.settings.master_volume == 60
    adapter.widget.cancel()
    assert app.settings.master_volume == 50


def test_save_menu_routes_via_request_save_shows_saved_and_slot_statuses(app):
    state = app.flow.new_game(seed=9, skip_intro=True)
    _settle(app)

    bad_ver = app.saves.path_for("slot_2")
    bad_ver.write_text(json.dumps({"save_version": 999, "state": {}}), encoding="utf-8")
    corrupt = app.saves.path_for("slot_3")
    corrupt.write_text("{corrupt", encoding="utf-8")

    app.scenes.push("SaveMenu", mode="save")
    menu: SaveMenu = app.scenes.overlays[-1][1].widget
    try:
        assert "旧版存档" in menu.row_labels[1].get_text()
        assert "存档已损坏" in menu.row_labels[2].get_text()
        assert tuple(menu.row_labels[3].text_node.node().getTextColor()) == pytest.approx(theme.COLOR_DISABLED)

        menu.confirm()
        # Menu remains open showing saved feedback and updated day summary instead of popping.
        assert app.scenes.top_overlay_id == "SaveMenu"
        assert menu.status.visible is True
        assert menu.status.get_text() == app.text.get("ui.save.saved")
        assert "第 1 天" in menu.row_labels[0].get_text()

        # Verify request_save phase rejection surfaces failure notice.
        state.phase = "event"
        menu.move(1)
        menu.confirm()
        assert menu.status.get_text() == app.text.get("ui.save.failed")
    finally:
        app.scenes.pop_all()


def test_campus_clubroom_does_not_occlude_library_and_north_wall_uv_scales(app):
    state = app.flow.new_game(seed=1, skip_intro=True)
    _settle(app)
    campus_adapter = app.scenes.base_scene
    assert isinstance(campus_adapter, CampusSceneAdapter)

    stele_tex, stele_h = campus_adapter._prop_art("prop_stele")
    assert stele_tex is not None and stele_h == pytest.approx(2.58)

    campus: CampusScene = campus_adapter.scene
    club_card = campus.root.find("**/side_loc_clubroom")
    assert not club_card.isEmpty()
    b0, b1 = club_card.getTightBounds()
    height = float(b1.getZ() - b0.getZ()) / math.cos(math.radians(abs(config.CAMERA_TILT_DEGREES)))
    club = next(b for b in app.map_data.buildings if b.id == "loc_clubroom")
    lib = next(b for b in app.map_data.buildings if b.id == "loc_library")
    cot = 1.0 / math.tan(math.radians(abs(config.CAMERA_TILT_DEGREES)))
    top_reach_y = club.rect.y0 + height * cot
    assert top_reach_y <= lib.outside_trigger[1] - 2.0

    # Cutaway north wall scales v by tile_v_m=3.0 so 1.6m wall gets max v = 1.6 / 3.0.
    tex = app.registry.load_texture("interior_dorm_wall")
    np_wall = make_wall_panel(app.render, 0, 0, 4, 0, 0, 1.6, tex, 2.0, tile_v_m=3.0)
    try:
        vdata = np_wall.node().getGeom(0).getVertexData()
        from panda3d.core import GeomVertexReader

        reader = GeomVertexReader(vdata, "texcoord")
        vs = [reader.getData2().y for _ in range(4)]
        assert max(vs) == pytest.approx(1.6 / 3.0, rel=1e-4)
    finally:
        np_wall.removeNode()


def test_debug_draw_cleans_status_uses_expanded_colliders_and_keeps_f5_index(app):
    app.flow.new_game(seed=1, skip_intro=True)
    _settle(app)

    debug: DebugDraw = app.scenes.base_scene.debug
    debug.toggle_status()
    assert debug._text is not None
    first = debug.teleport_next_interactable()
    assert app._debug_ia_index == 1

    # Switch to interior: previous F3 status text must be destroyed and F5 index persists.
    app.scenes.change("InteriorScene", building_id="loc_dorm", state=app.flow.state)
    _settle(app)
    assert debug._text is None
    dorm_debug: DebugDraw = app.scenes.base_scene.debug
    assert dorm_debug._ia_index == 1
    assert dorm_debug.teleport_next_interactable() != first

    # F1 inside InteriorScene uses colliders_world (expanded colliders count & bounds match player._rects).
    dorm_debug.toggle_collision()
    assert dorm_debug.collision_root.getNumChildren() == len(app.scenes.base_scene.player._rects)
    b0, _b1 = dorm_debug.collision_root.getChild(0).getTightBounds()
    assert float(b0.getY()) == pytest.approx(app.scenes.base_scene.player._rects[0].y0, abs=1e-4)
