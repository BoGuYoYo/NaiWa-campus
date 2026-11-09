"""新手教程（D7）：5 个步骤的触发、显示与完成条件。

步骤表（触发 → 显示 → 完成条件）：
    tut.move     开场结束进入校园        「用 WASD 移动」         累计移动 3 米
    tut.interact 第一次进入交互点范围    「按 E 互动」            完成第 1 次活动
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
        self._moved_meters = 0.0
        self._tab_timer = 0.0

    # ------------------------------------------------------------------
    def _start(self, step: str) -> None:
        if step in self.state.tutorial_done or self.active_step == step:
            return
        # 步骤不并行：同一时刻只显示一个教程横幅
        if self.active_step is not None:
            return
        self.active_step = step
        _log.info("tutorial start: %s", step)

    def _complete(self, step: str) -> None:
        if step in self.state.tutorial_done:
            return
        self.state.tutorial_done.add(step)
        if self.active_step == step:
            self.active_step = None
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

    BANNER_RECT = (120, 210, 240, 24)

    def __init__(self, parent, transform, text_db, asset_registry=None) -> None:
        from game.ui.widgets import UILabel, UIPanel

        self.transform = transform
        self.text_db = text_db
        self.root = parent.attach_new_node("tutorial_overlay")
        self.panel = UIPanel(self.root, transform, self.BANNER_RECT, asset_registry)
        self.label = UILabel(
            self.root, transform, self.BANNER_RECT[0] + 8, self.BANNER_RECT[1] + 6, "",
            color=theme.COLOR_WARN,
        )
        self.controller: TutorialController | None = None
        self.hide()

    def attach(self, controller: TutorialController) -> None:
        self.controller = controller

    def refresh(self) -> None:
        if not self.controller:
            return
        text = self.controller.banner_text()
        if text:
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
