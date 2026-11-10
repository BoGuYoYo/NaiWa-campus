"""守卫：模态覆盖层打开时，教程横幅隐藏；解锁后横幅仍真实可见。

BUG-23 修复路径：教程横幅通过场景锁定谓词自我隐藏，并由 on_update 统一刷新，
防止开场剧情或日结算时出现横幅闪帧、遮挡对话内容。

**为什么这里断言"可见性状态"而不是"调用次数"**：只数 `refresh()` 被调过几次，挡不住
"先 refresh 再无条件 hide"这种把教程变成哑巴的实现——调用发生了，画面却是空的。
所以假 overlay 维护 `visible` 状态，断言最终可见性。

**矩形闸只覆盖解锁态同时可见的对**：对话框/选项面板是**模态**面板（只在 locked 出现），
与横幅永不同屏，那类关系由可见性闸负责；对它们做矩形断言等于要求改布局，是过严的。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from game.core.state import GameState
from game.core.world_scene import WorldSceneBase
from game.ui import theme
from game.ui.tutorial import TutorialOverlay


class _RecOverlay:
    """按真实 refresh→show / hide 的语义维护可见状态。"""

    def __init__(self) -> None:
        self.refresh_count = 0
        self.visible = False

    def refresh(self) -> None:
        self.refresh_count += 1
        self.visible = True

    def show(self) -> None:
        self.visible = True

    def hide(self) -> None:
        self.visible = False


class _FakeNode:
    def __init__(self) -> None:
        self.hidden = False

    def hide(self) -> None:
        self.hidden = True

    def show(self) -> None:
        self.hidden = False


class _FakeLabel:
    def __init__(self) -> None:
        self.text = ""

    def set_text(self, text: str) -> None:
        self.text = text


class _RecTutorial:
    def notify(self, event, **data):
        return None


class _FakePlayer:
    motion = SimpleNamespace(x=0.0, y=0.0)

    def update(self, dt, locked=False):
        return None


class _Scene(WorldSceneBase):
    """绕过真实 on_enter，只驱动 on_update 的可见性分支。"""

    def __init__(self, state, locked):
        self.app = SimpleNamespace(scenes=SimpleNamespace(input_locked=locked))
        self._state = state
        self.player = _FakePlayer()
        self.animator = SimpleNamespace(tick=lambda dt: None)
        self.hud = SimpleNamespace(
            visible=True,
            hide=lambda: None,
            show=lambda: None,
            update=lambda s: None,
            tick=lambda dt: None,
        )
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


def test_tutorial_overlay_refresh_obeys_injected_lock_predicate() -> None:
    overlay = TutorialOverlay.__new__(TutorialOverlay)
    overlay.is_locked = lambda: True
    overlay.controller = SimpleNamespace(banner_text=lambda: "tutorial")
    overlay.root = _FakeNode()
    overlay.label = _FakeLabel()

    overlay.refresh()

    assert overlay.root.hidden is True
    assert overlay.label.text == ""


def test_tutorial_overlay_hidden_while_overlay_open() -> None:
    state = GameState()
    scene = _Scene(state, locked=True)

    scene.on_update(0.1)

    assert scene.tutorial_overlay.visible is False, (
        "覆盖层（对话框/结果面板/菜单）打开时教程横幅仍然可见 → 会压在对话框上"
    )


def test_tutorial_overlay_actually_visible_when_unlocked() -> None:
    """反向用例：没有覆盖层时横幅必须**真的可见**。

    断言 `visible is True` 而不是 `refresh_count >= 1`——后者挡不住"先 refresh 再
    无条件 hide"这种把教程变哑巴的实现。
    """
    state = GameState()
    scene = _Scene(state, locked=False)

    scene.on_update(0.1)

    assert scene.tutorial_overlay.refresh_count >= 1
    assert scene.tutorial_overlay.visible is True, "解锁态横幅被藏起来了：教程会变成哑巴"


def test_banner_does_not_overlap_unlocked_co_visible_panels() -> None:
    """矩形闸：横幅不得压住**解锁态同时可见**的界面元素。

    **不含** `dialogue` / `event_choices` 等模态面板——它们只在 locked 时出现，
    与横幅永不同屏；那类关系由上面的可见性闸负责。
    """
    banner = TutorialOverlay.BANNER_RECT
    for name in ("hud_date", "hud_gauges", "hud_key_hint", "prompt"):
        assert not theme.rect_overlaps(banner, theme.RECTS[name]), (
            f"教程横幅与 {name} 在解锁态会同时可见且矩形重叠："
            f"banner={banner} {name}={theme.RECTS[name]}"
        )

    # 横幅 label 行高 12 逻辑像素，不能压到提示框标题
    assert banner[1] + 6 + 12 <= theme.RECTS["prompt"][1] + 2
