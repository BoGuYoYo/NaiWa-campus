"""Settings must replace the visible contents of its parent menu while open."""

from __future__ import annotations

import pytest

from game.core.world_scene import SettingsMenuSceneAdapter


class FakeWidget:
    def __init__(self, visible=True):
        self.visible = visible
        self.on_back = None

    def show(self):
        self.visible = True

    def hide(self):
        self.visible = False

    def destroy(self):
        self.visible = False

    def move(self, _direction):
        pass

    def adjust(self, _direction):
        pass

    def confirm(self):
        pass

    def cancel(self):
        pass


class FakeInput:
    def bind(self, _owner, _event, _handler):
        pass

    def unbind(self, _owner):
        pass


class FakeScenes:
    def __init__(self, base_scene, overlays):
        self.base_scene = base_scene
        self.overlays = overlays


class FakeScene:
    def __init__(self, widget):
        self.widget = widget


@pytest.mark.parametrize("entry", ["main_menu", "pause_menu"])
def test_settings_hides_and_restores_parent_menu(entry):
    main_menu = FakeScene(FakeWidget())
    pause_menu = FakeScene(FakeWidget(visible=entry != "pause_menu"))
    base_scene = main_menu
    overlays = []
    if entry == "pause_menu":
        overlays.append(("PauseMenu", pause_menu))

    app = type("FakeApp", (), {})()
    app.scenes = FakeScenes(base_scene, overlays)
    app.input = FakeInput()
    adapter = SettingsMenuSceneAdapter(app)
    settings_widget = FakeWidget(visible=False)
    adapter._make_widget = lambda: settings_widget
    app.scenes.overlays.append(("SettingsMenu", adapter))

    adapter.on_enter()
    parent_widget = pause_menu.widget if entry == "pause_menu" else main_menu.widget
    assert not parent_widget.visible
    assert settings_widget.visible

    # SceneManager removes an overlay from the stack before calling on_exit.
    app.scenes.overlays.pop()
    adapter.on_exit()
    assert parent_widget.visible
    assert not settings_widget.visible
