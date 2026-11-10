"""守卫：覆盖层（对话框/结果面板/菜单）打开时，教程横幅必须跟着隐藏。

背景（BUG-23，BUG-13 修复引出的回归）：
`TutorialOverlay.BANNER_RECT = (120, 180, 240, 24)`（y 180..204）**整个落在**
`theme.RECTS["dialogue"] = (4, 166, 472, 100)`（y 166..266）里面；
而 `WorldSceneBase.on_update()` 里 `tutorial_overlay.refresh()` 在 `if locked` **之前**执行，
`locked` 分支又只隐藏 `hud` 与 `prompt`、**不隐藏 tutorial_overlay** ——
于是开局剧情（`enter_campus` 触发 `tut.move` 后立刻 push 开场 EventScene）会出现
"横幅压在对话框/头像/正文上"的第一屏。

修法二选一：把 refresh 挪到 `if locked` 之后，或在 `locked` 分支补
`self.tutorial_overlay.hide()`。修好后本条会 XPASS，请删掉 xfail 标记。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from game.core.state import GameState
from game.core.world_scene import WorldSceneBase


class _RecOverlay:
    def __init__(self) -> None:
        self.refresh_count = 0
        self.hidden = 0

    def refresh(self) -> None:
        self.refresh_count += 1

    def hide(self) -> None:
        self.hidden += 1


class _RecTutorial:
    def notify(self, event, **data):
        return None


class _FakePlayer:
    motion = SimpleNamespace(x=0.0, y=0.0)

    def update(self, dt, locked=False):
        return None


class _Scene(WorldSceneBase):
    def __init__(self, state, locked):  # 绕过真实 on_enter，只测 on_update 的可见性分支
        self.app = SimpleNamespace(scenes=SimpleNamespace(input_locked=locked))
        self._state = state
        self.player = _FakePlayer()
        self.animator = SimpleNamespace(tick=lambda dt: None)
        self.hud = SimpleNamespace(visible=True, hide=lambda: None, show=lambda: None,
                                   update=lambda s: None, tick=lambda dt: None)
        self.prompt = SimpleNamespace(hide_prompt=lambda: None, show_prompt=lambda v: None)
        self.tutorial = _RecTutorial()
        self.tutorial_overlay = _RecOverlay()
        self._last_player_position = (0.0, 0.0)
        self.tracker = None
        self.scene = None
        self.debug = None

    def _update_scene_camera(self, dt, force=False):
        return None

    def _refresh_prompt(self, force=False):
        return None

    def _update_scene_camera(self, dt, force=False):  # noqa: F811
        return None


@pytest.mark.xfail(
    strict=True,
    reason="BUG-23：覆盖层打开时 tutorial_overlay 未被隐藏（横幅压对话框）；"
           "修复后本条会 XPASS，请删掉 xfail 标记",
)
def test_tutorial_overlay_hidden_while_overlay_open() -> None:
    state = GameState()
    scene = _Scene(state, locked=True)

    scene.on_update(0.1)

    assert scene.tutorial_overlay.hidden >= 1, (
        "覆盖层（对话框/结果面板/菜单）打开时没有隐藏教程横幅："
        f"refresh={scene.tutorial_overlay.refresh_count}, hidden={scene.tutorial_overlay.hidden}"
    )


def test_tutorial_overlay_visible_when_unlocked() -> None:
    """反例：没有覆盖层时横幅照常刷新（不能被"一律隐藏"改成哑巴）。"""
    state = GameState()
    scene = _Scene(state, locked=False)

    scene.on_update(0.1)

    assert scene.tutorial_overlay.refresh_count >= 1
