"""Exercise opening NPCs through the real Panda3D scene transitions."""

from collections import Counter

import pytest

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    pytest.importorskip("panda3d.core")
    from game import config
    from game.app import NaiwaApp, apply_prc

    config.set_user_dir(tmp_path_factory.mktemp("opening_npc_lifecycle"))
    options = config.parse_args(["--offscreen", "--frames", "999999", "--seed", "42"])
    apply_prc(options, config.Settings())
    instance = NaiwaApp(options)
    try:
        _finish_transition(instance)
        yield instance
    finally:
        instance.scenes.pop_all()
        if instance.scenes.base_scene is not None:
            instance.scenes._exit(instance.scenes.base_scene)
        instance.stop_audio()
        instance.destroy()
        config.set_user_dir(None)


def _finish_transition(app):
    for _ in range(3):
        if not app.scenes.is_transitioning():
            return
        app.scenes.update(0.3)
    assert not app.scenes.is_transitioning()


def _npc_counts(app):
    return Counter(node.get_name() for node in app.render.find_all_matches("**/npc_*"))


def _new_game(app, *, skip_intro=False):
    app.scenes.pop_all()
    state = app.flow.new_game(seed=42, skip_intro=skip_intro)
    _finish_transition(app)
    assert _npc_counts(app) == Counter({"npc_chenlang": 1, "npc_sumo": 1})
    if not skip_intro:
        assert app.scenes.top_overlay_id == "EventScene"
        opening = app.scenes.overlays[-1][1]
        opening._choose("story_opening", "begin")
        assert opening._pending_result is not None
        opening._finished("story_opening")
        assert app.scenes.top_overlay_id is None
    return state


def _enter_building(app, door_id):
    campus = app.scenes.base_scene
    old_root = campus.root
    door = app.map_data.interactable(door_id)
    campus.player.teleport(door.x, door.y)
    campus._refresh_prompt(force=True)
    assert campus.tracker.active_id == door_id
    campus._on_interact()
    _finish_transition(app)
    assert app.scenes.current_id == "InteriorScene"
    assert old_root.is_empty()
    return app.scenes.base_scene


def _leave_building(app):
    interior = app.scenes.base_scene
    old_root = interior.root
    x, y, _radius = interior.scene.mat_world()
    interior.player.teleport(x, y)
    interior._check_autostep(0.1)
    _finish_transition(app)
    assert app.scenes.current_id == "CampusScene"
    assert old_root.is_empty()


@pytest.mark.parametrize(
    "door_id,expected",
    [
        ("ia_door_dorm", {}),
        ("ia_door_classroom", {}),
        ("ia_door_library", {"npc_chenlang": 1}),
        ("ia_door_clubroom", {"npc_sumo": 1}),
        ("ia_door_canteen", {"npc_xiaoyou": 1}),
    ],
)
def test_opening_characters_leave_after_entering_any_building(app, door_id, expected):
    _new_game(app)
    _enter_building(app, door_id)
    assert _npc_counts(app) == Counter(expected)
    _leave_building(app)
    assert _npc_counts(app) == Counter()


def test_opening_characters_follow_save_state_and_reset_on_new_game(app):
    state = _new_game(app)
    app.saves.save(state, "slot_1")
    _enter_building(app, "ia_door_library")
    app.saves.save(state, "slot_2")

    app.flow.load_game("slot_2")
    _finish_transition(app)
    assert _npc_counts(app) == Counter()

    app.flow.load_game("slot_1")
    _finish_transition(app)
    assert _npc_counts(app) == Counter({"npc_chenlang": 1, "npc_sumo": 1})

    legacy = app.flow.state.copy()
    legacy.flags.discard("opening_npcs_active")
    app.saves.save(legacy, "slot_3")
    app.flow.load_game("slot_3")
    _finish_transition(app)
    assert _npc_counts(app) == Counter()

    _new_game(app)
    _new_game(app, skip_intro=True)
