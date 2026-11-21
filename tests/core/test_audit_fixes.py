"""Regression tests for verified code, flow, audio, save, and systems audit fixes."""

from __future__ import annotations

import json
import math
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from game import config
from game.app import apply_prc
from game.core.asset_registry import AssetRegistry
from game.core.audio import AudioManager
from game.core.event_bus import TOPIC_DAY_STARTED, EventBus
from game.core.flow import GameFlow, resolve_services
from game.core.render_pipeline import LowResPipeline, snap_to_pixel_grid
from game.core.save_manager import SaveManager
from game.core.scene_manager import SceneManager
from game.core.state import GameState, new_state
from game.core.world_scene import EventSceneAdapter
from game.systems.activity_service import ActivityService
from game.systems.content_db import RULES_DIR, ContentDB, default_rules_dir, reset_cache


class _DummyScene:
    def __init__(self, scene_id: str, **kwargs) -> None:
        self.scene_id = scene_id
        self.kwargs = kwargs

    def on_enter(self, **_kwargs) -> None:
        pass

    def on_exit(self) -> None:
        pass


def _make_flow(tmp_path: Path, *, fade_seconds: float = 0.0) -> GameFlow:
    bus = EventBus()
    scenes = SceneManager(
        app=None,
        factory=lambda sid, kw: _DummyScene(sid, **kw),
        bus=bus,
        fade_seconds=fade_seconds,
    )
    saves = SaveManager(saves_root=tmp_path / "saves")
    return GameFlow(app=None, scenes=scenes, saves=saves, bus=bus, services=resolve_services())


def test_cli_windowed_explicit_flag_distinguishes_default_from_override(monkeypatch):
    opts_default = config.parse_args([])
    opts_explicit = config.parse_args(["--windowed", "1280", "720"])
    assert opts_default.windowed_explicit is False
    assert opts_explicit.windowed_explicit is True
    assert opts_explicit.windowed == (1280, 720)

    loaded_prc: list[str] = []
    monkeypatch.setattr("panda3d.core.loadPrcFileData", lambda _name, data: loaded_prc.append(data))

    settings = config.Settings(window_size=(1920, 1080))
    loaded_prc.clear()
    apply_prc(opts_default, settings)
    assert "win-size 1920 1080" in loaded_prc

    loaded_prc.clear()
    apply_prc(opts_explicit, settings)
    assert "win-size 1280 720" in loaded_prc


def test_scene_manager_blocks_input_while_transitioning():
    scenes = SceneManager(
        app=None,
        factory=lambda sid, kw: _DummyScene(sid, **kw),
        fade_seconds=0.25,
    )
    scenes.start("MainMenu")
    scenes.change("CampusScene")
    assert scenes.is_transitioning() is True
    assert scenes.blocks_input(scenes.base_scene) is True
    scenes.update(0.3)
    scenes.update(0.3)
    assert scenes.is_transitioning() is False
    assert scenes.blocks_input(scenes.base_scene) is False


def test_finish_day_defers_begin_next_day_until_summary_closes(tmp_path):
    flow = _make_flow(tmp_path)
    state = flow.new_game(seed=7, skip_intro=True)
    state.action_slot = 3
    state.world.x = 25.0
    state.world.y = 8.0

    started: list[int] = []
    flow.bus.subscribe(TOPIC_DAY_STARTED, lambda **data: started.append(data["day_index"]))

    result = flow.finish_day()
    assert result is not None and not result.semester_event_id and not result.graduated
    assert flow.scenes.top_overlay_id == "DaySummary"
    assert (state.world.x, state.world.y) == (25.0, 8.0)
    assert started == []

    flow.scenes.pop()
    flow.close_day_summary()
    assert (state.world.x, state.world.y) == (40.0, 5.0)
    assert started == [1]


def test_resume_graduation_preserves_highlights(tmp_path):
    flow = _make_flow(tmp_path)
    state = flow.new_game(seed=5, skip_intro=True)
    state.day_index = config.TOTAL_DAYS
    state.phase = "graduation"
    state.ending_id = "ending_mediocre"
    state.counters["library_count"] = 6
    state.event_log.append("sem_1_club_fair:fair_club")
    flow.saves.save(state, "slot_1")

    loaded = flow.load_game("slot_1")
    assert loaded.ending_id == "ending_mediocre"
    grad_scene = flow.scenes.base_scene
    ending = grad_scene.kwargs["ending"]
    assert "library_count×6" in ending.highlights
    assert "sem_1_club_fair:fair_club" in ending.highlights


def test_align_camera_uses_true_pixel_grid_while_keeping_default_helper():
    assert snap_to_pixel_grid(40.0 + (1.0 / 24.0) * 0.6) == pytest.approx(40.0 + 1.0 / 24.0)

    pipeline = LowResPipeline(app=None)
    sx, sy = pipeline.align_camera(12.345, 23.456)
    step_x = config.FILM_WIDTH_METERS / config.INTERNAL_WIDTH
    step_y = (config.FILM_HEIGHT_METERS / config.INTERNAL_HEIGHT) / abs(
        math.sin(math.radians(config.CAMERA_TILT_DEGREES))
    )
    assert sx == pytest.approx(round(12.345 / step_x) * step_x)
    assert sy == pytest.approx(round(23.456 / step_y) * step_y)


def test_load_music_uses_load_music_and_event_adapter_switches_bgm(tmp_path):
    class _FakeLoader:
        def __init__(self) -> None:
            self.sfx_calls: list[str] = []
            self.music_calls: list[str] = []

        def loadSfx(self, path):  # noqa: N802 - Panda3D name
            self.sfx_calls.append(str(path))
            return ("sfx", str(path))

        def loadMusic(self, path):  # noqa: N802 - Panda3D name
            self.music_calls.append(str(path))
            return ("music", str(path))

    loader = _FakeLoader()
    registry = AssetRegistry(loader=SimpleNamespace(loader=loader))
    music = registry.load_music("bgm_event")
    assert music is not None and music[0] == "music"
    assert len(loader.music_calls) == 1
    assert loader.sfx_calls == []

    # EventSceneAdapter switches to bgm_event and restores bgm_campus_day on finish.
    audio = AudioManager(registry, config.Settings(), enabled=False)
    audio.play_music("bgm_campus_day")

    class _FakeWidget:
        def __init__(self) -> None:
            self.on_choose = None
            self.on_finished = None
            self.dialogue = SimpleNamespace(show_page=lambda *_a, **_k: None)

        def on_space(self) -> None:
            pass

        def on_click(self) -> None:
            pass

        def on_move(self, _d: int) -> None:
            pass

        def on_digit(self, _d: int) -> None:
            pass

        def on_escape(self) -> None:
            pass

        def show(self) -> None:
            pass

        def hide(self) -> None:
            pass

        def destroy(self) -> None:
            pass

        def load_event(self, _view) -> None:
            pass

        def set_text_speed(self, _speed) -> None:
            pass

    scenes = SimpleNamespace(
        base_id="CampusScene",
        overlays=[],
        pop=lambda: None,
        is_transitioning=lambda: False,
    )
    flow = SimpleNamespace(
        require_state=lambda: new_state(seed=1),
        handle_event_result=lambda _res: None,
    )
    view = SimpleNamespace(choices=[], page_text_ids=["evt.sem_1_club_fair.body.1"])
    app = SimpleNamespace(
        audio=audio,
        scenes=scenes,
        flow=flow,
        settings=config.Settings(),
        services=SimpleNamespace(event=SimpleNamespace(get_view=lambda *_a: view)),
        text=SimpleNamespace(dialogues={"evt.sem_1_club_fair.body.1": {}}),
        input=SimpleNamespace(bind=lambda *_a: None, unbind=lambda *_a: None),
    )
    adapter = EventSceneAdapter(app)
    adapter._make_widget = _FakeWidget
    adapter.on_enter(event_id="sem_1_club_fair")
    assert audio.current_music == "bgm_event"

    adapter._pending_result = SimpleNamespace(next_event_id=None)
    adapter._finished("sem_1_club_fair")
    assert audio.current_music == "bgm_campus_day"


def test_save_manager_slot_status_distinguishes_empty_incompatible_corrupt(tmp_path):
    saves = SaveManager(saves_root=tmp_path / "saves")
    assert saves.slot_status("slot_1") == "empty"

    state = new_state(seed=1)
    saves.save(state, "slot_1")
    assert saves.slot_status("slot_1") == "ok"

    bad_ver = saves.path_for("slot_2")
    bad_ver.write_text(json.dumps({"save_version": 999, "state": {}}), encoding="utf-8")
    assert saves.slot_status("slot_2") == "incompatible"

    corrupt = saves.path_for("slot_3")
    corrupt.write_text("{broken json", encoding="utf-8")
    assert saves.slot_status("slot_3") == "corrupt"


def test_content_db_resolves_resource_root_and_activity_add_flags(tmp_path):
    content_dir = tmp_path / "content"
    rules_dir = content_dir / "rules"
    shutil.copytree(RULES_DIR, rules_dir)
    acts_path = rules_dir / "activities.json"
    acts = json.loads(acts_path.read_text(encoding="utf-8"))
    acts[0]["add_flags"] = ["custom_act_flag"]
    acts_path.write_text(json.dumps(acts, ensure_ascii=False, indent=2), encoding="utf-8")

    # Endings reference the custom activity flag; ContentDB must see it from loaded JSON.
    ends_path = rules_dir / "endings.json"
    ends = json.loads(ends_path.read_text(encoding="utf-8"))
    ends[0]["conditions"].append({"type": "flag", "key": "custom_act_flag"})
    ends_path.write_text(json.dumps(ends, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        config.set_resource_root(tmp_path)
        reset_cache()
        assert default_rules_dir() == rules_dir
        db = ContentDB()
        svc = ActivityService(db=db)
        state = new_state(seed=3)
        res = svc.start(state, acts[0]["id"])
        assert res.ok
        assert "custom_act_flag" in state.flags
        assert "custom_act_flag" in res.added_flags
    finally:
        config.set_resource_root(None)
        reset_cache()
