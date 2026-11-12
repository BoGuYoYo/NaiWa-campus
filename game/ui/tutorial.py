"""新手教程（D7）：5 个步骤的触发、显示与完成条件。

步骤表（触发 → 显示 → 完成条件）：
    tut.move     开场结束进入校园        「用 WASD 移动」         累计移动 3 米
    tut.interact 第一次进入交互点范围    「按 E 互动」            完成第 1 次互动（活动或交谈）
    tut.slots    第 1 次结果面板关闭      高亮时段圆点             按 Space
    tut.energy   首次精力 < 40           高亮精力条               按 Space
    tut.tab      第 1 天日结算后         「按 Tab 查看属性」      打开 Tab 或 30 秒

完成的步骤写入 GameState.tutorial_done（D 写入），读档后不再重复。
TutorialController 是纯逻辑类（可独立测试）；TutorialOverlay 负责渲染，
**不继承 UIWidget**，这样本模块可以在没有 panda3d 的环境里被导入
（旧版在模块级继承 UIWidget，导致 tests/ui 收集阶段 NameError）。
"""

from __future__ import annotations

import logging
from typing import Callable

from game.ui import theme

_log = logging.getLogger("naiwa.ui.tutorial")

#: 步骤 ID 顺序（展示顺序）
TUTORIAL_STEPS = ("tut.move", "tut.interact", "tut.slots", "tut.energy", "tut.tab")


class TutorialController:
    """纯逻辑教程状态机。

    用法：集成层把输入/流程事件喂给 notify()，控制器返回当前应
    显示的步骤（或 None）；渲染层据此显示横幅与高亮。
    """

    def __init__(self, state, text_db) -> None:
        self.state = state          # GameState（tutorial_done 由 D 写入）
        self.text_db = text_db
        self.active_step: str | None = None
        self._pending_steps: list[str] = []
        self._moved_meters = 0.0
        self._tab_timer = 0.0

    # ------------------------------------------------------------------
    def _start(self, step: str) -> None:
        if step in self.state.tutorial_done or self.active_step == step:
            return
        # 步骤不并行：当前横幅显示期间先排队，不能静默丢失触发。
        if self.active_step is not None:
            if step not in self._pending_steps:
                self._pending_steps.append(step)
            return
        self.active_step = step
        if step == "tut.tab":
            self._tab_timer = 0.0
        _log.info("tutorial start: %s", step)

    def _activate_next(self) -> None:
        while self.active_step is None and self._pending_steps:
            step = self._pending_steps.pop(0)
            if step in self.state.tutorial_done:
                continue
            self._start(step)

    def _complete(self, step: str) -> None:
        if step in self.state.tutorial_done:
            return
        self.state.tutorial_done.add(step)
        if step in self._pending_steps:
            self._pending_steps.remove(step)
        if self.active_step == step:
            self.active_step = None
            self._activate_next()
        elif self.active_step is None:
            self._activate_next()
        _log.info("tutorial done: %s", step)

    # ------------------------------------------------------------------
    # 事件入口（集成层调用）
    # ------------------------------------------------------------------
    def notify(self, event: str, **data) -> str | None:
        """处理流程事件，返回当前应显示的步骤 ID 或 None。

        事件：enter_campus / near_interactable / activity_done /
        result_closed / low_energy / day_ended / tab_opened / key_space
        以及 player_moved(distance_m=float) / tick(dt=float)
        """
        if event == "enter_campus":
            self._start("tut.move")
        elif event == "player_moved":
            self._moved_meters += float(data.get("distance_m", 0.0))
            if self._moved_meters >= 3.0:
                self._complete("tut.move")
        elif event == "near_interactable":
            self._start("tut.interact")
        elif event == "activity_done":
            self._complete("tut.move")
            self._complete("tut.interact")
        elif event == "result_closed":
            self._start("tut.slots")
        elif event == "low_energy":
            self._start("tut.energy")
        elif event == "day_ended":
            if self.state.day_index >= 1:
                self._start("tut.tab")
        elif event == "tab_opened":
            self._complete("tut.tab")
        elif event == "key_space":
            if self.active_step in ("tut.slots", "tut.energy"):
                self._complete(self.active_step)
        elif event == "tick":
            self._tick(float(data.get("dt", 0.0)))
        return self.active_step

    def _tick(self, dt: float) -> None:
        if self.active_step == "tut.tab":
            self._tab_timer += dt
            if self._tab_timer >= theme.TUTORIAL_TAB_TIMEOUT_SECONDS:
                self._complete("tut.tab")

    # ------------------------------------------------------------------
    def banner_text(self) -> str | None:
        """当前横幅文本（来自 tut.* 文本）。"""
        if not self.active_step:
            return None
        return self.text_db.get(f"{self.active_step}.body")

    def is_finished(self) -> bool:
        return all(step in self.state.tutorial_done for step in TUTORIAL_STEPS)


class TutorialOverlay:
    """教程横幅渲染层。仅集成环境使用（依赖 widgets / panda3d）。"""

    BANNER_RECT = (120, 48, 240, 24)
    BANNER_Y = 48
    #: 24 高的横幅被九宫格金边吃掉上下各 6 px，12 px 正文会压在金边上 → 抬到 30
    BANNER_HEIGHT = 30
    BANNER_MIN_WIDTH = 120
    BANNER_MAX_WIDTH = 320

    def __init__(
        self, parent, transform, text_db, asset_registry=None,
        is_locked: Callable[[], bool] | None = None,
    ) -> None:
        from panda3d.core import TextNode

        from game.ui.widgets import UILabel, UIPanel, default_font

        self.transform = transform
        self.text_db = text_db
        self.assets = asset_registry
        self.is_locked = is_locked
        self.root = parent.attach_new_node("tutorial_overlay")
        self._measure = TextNode("tutorial_measure")
        font = default_font()
        if font is not None:
            self._measure.set_font(font)
        # 面板按文案宽度重建（宽度变了才重建），避免「用 WASD 移动」占 240 宽只写 1/3
        self._panel = None
        self._panel_width = 0.0
        self._panel_x = self.BANNER_RECT[0]
        self._ensure_banner(self.BANNER_MIN_WIDTH)
        self.label = UILabel(
            self.root, transform, self.BANNER_RECT[0] + 8, self.BANNER_Y + 6, "",
            color=theme.COLOR_WARN,
        )
        self.controller: TutorialController | None = None
        self.hide()

    @property
    def panel(self):
        return self._panel

    def _text_width(self, text: str) -> float:
        from game.ui.widgets import FONT_SIZE_BODY

        self._measure.set_text(text)
        return self._measure.get_width() * FONT_SIZE_BODY

    def _ensure_banner(self, width: float) -> None:
        from game.ui.widgets import UIPanel

        width = max(self.BANNER_MIN_WIDTH, min(self.BANNER_MAX_WIDTH, width))
        if self._panel is not None and abs(width - self._panel_width) < 0.5:
            return
        if self._panel is not None:
            self._panel.destroy()
        x = (theme.CANVAS_W - width) / 2.0
        self._panel = UIPanel(
            self.root, self.transform, (x, self.BANNER_Y, width, self.BANNER_HEIGHT),
            self.assets,
        )
        self._panel_width = width
        self._panel_x = x
        self._place_label()

    def _place_label(self) -> None:
        if getattr(self, "label", None) is None or self._panel is None:
            return
        border_x, border_y = getattr(self._panel, "border", (4.0, 4.0))
        # 文字从金边内侧开始；同 UILabel 的锚点规则，落点再下移一个字号
        ax, ay = self.transform.to_aspect2d(
            self._panel_x + border_x + 2.0, self.BANNER_Y + border_y + 1.0 + 12
        )
        self.label.text_node.set_pos(ax, 0, ay)

    def attach(self, controller: TutorialController) -> None:
        self.controller = controller

    def refresh(self) -> None:
        if (self.is_locked and self.is_locked()) or not self.controller:
            self.hide()
            return
        text = self.controller.banner_text()
        if text:
            self._ensure_banner(self._text_width(text) + 32.0)
            self._place_label()
            self.label.set_text(text)
            self.show()
        else:
            self.hide()

    def show(self) -> None:
        if self.root is not None:
            self.root.show()

    def hide(self) -> None:
        if self.root is not None:
            self.root.hide()

    def destroy(self) -> None:
        if self.root is not None:
            self.root.remove_node()
            self.root = None
