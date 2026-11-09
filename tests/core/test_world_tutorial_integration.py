"""无窗口覆盖世界场景与教程控制器的关键接线。"""

from __future__ import annotations

from types import SimpleNamespace

from game.core.state import GameState
from game.core.world_scene import ResultPanelSceneAdapter, WorldSceneBase
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
    popped = []
    closed = []
    scene = _HarnessScene.__new__(_HarnessScene)
    scene.app = SimpleNamespace(
        scenes=SimpleNamespace(
            input_locked=False,
            base_scene=scene,
            pop=lambda: popped.append(True),
        ),
        flow=SimpleNamespace(close_result_panel=lambda result: closed.append(result)),
        audio=SimpleNamespace(play_sfx=lambda _asset: None),
    )
    scene._state = state
    scene.player = _FakePlayer()
    scene.animator = _FakeAnimator()
    scene.hud = _FakeHud()
    scene.prompt = SimpleNamespace(hide_prompt=lambda: None)
    scene.tutorial = TutorialController(state, SimpleNamespace())
    scene.tutorial_overlay = _FakeOverlay(scene.tutorial)
    scene._last_player_position = (0.0, 0.0)
    scene.tracker = SimpleNamespace(active_id="blocked_interaction")
    scene.interaction = SimpleNamespace(
        interact=lambda _state, _id: SimpleNamespace(kind="blocked")
    )

    # The world scene entry path starts the movement step.
    scene.tutorial.notify("enter_campus")
    assert scene.tutorial.active_step == "tut.move"

    scene.on_update(0.1)
    assert scene.tutorial.active_step == "tut.move"
    scene.on_update(0.1)
    assert "tut.move" in state.tutorial_done
    assert scene.tutorial.active_step is None

    # Low energy is emitted by the real on_update path and can be completed.
    state.energy = 39
    scene.on_update(0.1)
    assert scene.tutorial.active_step == "tut.energy"
    scene._on_interact()  # real key_space site; blocked interaction is harmless
    assert "tut.energy" in state.tutorial_done

    # ResultPanel close uses the real adapter path and starts the slots step.
    result = object()
    panel = ResultPanelSceneAdapter.__new__(ResultPanelSceneAdapter)
    panel.app = scene.app
    panel.kwargs = {"result": result}
    panel._close()
    assert popped == [True]
    assert closed == [result]
    assert scene.tutorial.active_step == "tut.slots"
    assert scene.tutorial_overlay.refresh_count >= 1

    # Day end queues tab instead of dropping it; key_space completed slots first.
    scene._on_tutorial_day_ended()
    assert scene.tutorial.active_step == "tut.slots"
    scene._on_interact()
    assert scene.tutorial.active_step == "tut.tab"
    assert scene.tutorial_overlay.refresh_count >= 2
