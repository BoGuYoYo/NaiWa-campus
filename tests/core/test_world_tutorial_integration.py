"""无窗口覆盖世界场景与教程控制器的关键接线。"""

from __future__ import annotations

from types import SimpleNamespace

from game.core.state import GameState
from game.core.world_scene import WorldSceneBase
from game.ui.tutorial import TutorialController


class _FakePlayer:
    def __init__(self) -> None:
        self.motion = SimpleNamespace(x=0.0, y=0.0)

    def update(self, _dt, locked=False) -> None:
        if not locked:
            self.motion.x += 1.5


class _FakeHud:
    visible = True

    def hide(self):
        self.visible = False

    def show(self):
        self.visible = True

    def update(self, _state):
        pass

    def tick(self, _dt):
        pass


class _FakeAnimator:
    def tick(self, _dt):
        pass


class _FakeOverlay:
    def __init__(self, controller) -> None:
        self.controller = controller
        self.refresh_count = 0

    def refresh(self) -> None:
        self.refresh_count += 1


class _HarnessScene(WorldSceneBase):
    def _update_scene_camera(self, _dt, force=False) -> None:
        pass

    def _refresh_prompt(self, force=False) -> None:
        pass

    def _check_autostep(self) -> None:
        pass


def test_world_scene_wires_movement_result_and_day_tutorial_steps():
    state = GameState()
    state.day_index = 1
    scene = _HarnessScene.__new__(_HarnessScene)
    scene.app = SimpleNamespace(
        scenes=SimpleNamespace(input_locked=False),
    )
    scene._state = state
    scene.player = _FakePlayer()
    scene.animator = _FakeAnimator()
    scene.hud = _FakeHud()
    scene.prompt = SimpleNamespace(hide_prompt=lambda: None)
    scene.tutorial = TutorialController(state, SimpleNamespace())
    scene.tutorial_overlay = _FakeOverlay(scene.tutorial)
    scene._last_player_position = (0.0, 0.0)

    scene.tutorial.notify("enter_campus")
    assert scene.tutorial.active_step == "tut.move"

    scene.on_update(0.1)
    assert scene.tutorial.active_step == "tut.move"
    scene.on_update(0.1)
    assert "tut.move" in state.tutorial_done
    assert scene.tutorial.active_step is None

    # ResultPanel close starts slots; day end queues tab instead of dropping it.
    scene.tutorial.notify("result_closed")
    assert scene.tutorial.active_step == "tut.slots"
    scene._on_tutorial_day_ended()
    assert scene.tutorial.active_step == "tut.slots"
    scene.tutorial.notify("key_space")
    assert scene.tutorial.active_step == "tut.tab"
    assert scene.tutorial_overlay.refresh_count >= 2
