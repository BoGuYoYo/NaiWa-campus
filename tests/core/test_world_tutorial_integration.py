"""无窗口覆盖世界场景与教程控制器的关键接线。"""

from __future__ import annotations

import logging
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
        self.visible = False

    def refresh(self) -> None:
        self.refresh_count += 1
        self.visible = True

    def hide(self) -> None:
        self.visible = False


class _HarnessScene(WorldSceneBase):
    def _update_scene_camera(self, _dt, force=False) -> None:
        pass

    def _refresh_prompt(self, force=False) -> None:
        pass

    def _check_autostep(self, dt: float = 0.0) -> None:
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
    # 这个夹具绕过了 __init__（直接 __new__），要补齐 _on_interact 用到的 log
    scene.log = logging.getLogger("test.world_tutorial")
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
    refresh_before_close = scene.tutorial_overlay.refresh_count
    panel._close()
    assert popped == [True]
    assert closed == [result]
    assert scene.tutorial.active_step == "tut.slots"
    assert scene.tutorial_overlay.refresh_count == refresh_before_close
    state.energy = 60
    scene.on_update(0.1)  # the only render refresh runs on the next unlocked frame
    state.energy = 39
    assert scene.tutorial_overlay.visible is True

    # Day end queues tab instead of dropping it; a modal DaySummary hides the banner.
    scene.app.scenes.input_locked = True
    scene._on_tutorial_day_ended()
    assert scene.tutorial.active_step == "tut.slots"
    scene.on_update(0.1)
    assert scene.tutorial_overlay.visible is False
    scene.tutorial.notify("key_space")
    assert scene.tutorial.active_step == "tut.tab"
    scene.app.scenes.input_locked = False
    scene.on_update(0.1)
    assert scene.tutorial_overlay.visible is True


def test_npc_interaction_shows_result_and_finishes_interact_tutorial():
    """NPC 交谈也必须走结果面板，并结束「按 E 互动」教程横幅。"""
    state = GameState()
    scene = _HarnessScene.__new__(_HarnessScene)
    pushed = []
    handled = []
    hidden = []
    scene.app = SimpleNamespace(
        scenes=SimpleNamespace(
            input_locked=False,
            push=lambda *args, **kwargs: pushed.append((args, kwargs)),
        ),
        flow=SimpleNamespace(handle_activity_result=lambda result: handled.append(result)),
        audio=SimpleNamespace(play_sfx=lambda _asset: None),
    )
    scene._state = state
    scene.log = logging.getLogger("test.world_tutorial")
    scene.prompt = SimpleNamespace(hide_prompt=lambda: hidden.append(True))
    scene.tutorial = TutorialController(state, SimpleNamespace())
    scene.tracker = SimpleNamespace(active_id="ia_npc_sumo")

    payload = SimpleNamespace(
        ok=True,
        activity_id="talk.npc_sumo",
        error_code=None,
        deltas={"energy": -5, "mood": 2},
        triggered_event_id=None,
        day_finished=False,
    )
    scene.interaction = SimpleNamespace(
        interact=lambda _state, _id: SimpleNamespace(kind="npc", payload=payload)
    )

    scene.tutorial.notify("enter_campus")
    scene.tutorial.notify("near_interactable")
    assert scene.tutorial.active_step == "tut.move"

    scene._on_interact()

    assert handled == [payload]
    assert pushed == [(("ResultPanel",), {"result": payload})]
    assert hidden == [True]
    assert "tut.move" in state.tutorial_done
    assert "tut.interact" in state.tutorial_done
    assert scene.tutorial.active_step is None
