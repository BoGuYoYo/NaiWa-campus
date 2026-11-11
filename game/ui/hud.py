"""HUD（D2）：日期框、精力/心情条、行动时段圆点、按键提示。

布局（逻辑像素，全部取自 theme.RECTS）：
- 日期框 4, 4, 156, 40：底板 + 第 1 行「大一 · 上学期 · 第 1 天」+
  第 2 行 3 个时段圆点（已用为实心）；
- 精力/心情 320, 4, 156, 40：底板 + 图标(ui_icon_energy/mood) + 100 像素条 + 数字；
- 两块底板的内容统一内缩 12 px（4 px 边框 + 8 px 内缘留白），文字不再压金边；
  精力条按当前上限（80 + 体力/5）计算，精力 < 20 时用警告色并闪烁；
- 按键提示 4, 252, 200, 16：仅前 3 天显示。
"""

from __future__ import annotations

import logging

from panda3d.core import CardMaker, TransparencyAttrib

from game.ui import theme
from game.ui.widgets import UILabel, StatBar, UIIcon, UIPanel, UITransform, UIWidget

_log = logging.getLogger("naiwa.ui.hud")

YEAR_IDS = {1: "ui.hud.year.1", 2: "ui.hud.year.2", 3: "ui.hud.year.3", 4: "ui.hud.year.4"}
SEM_IDS = {1: "ui.hud.semester.1", 2: "ui.hud.semester.2"}

LOW_ENERGY = 20
BLINK_INTERVAL = 0.5

#: HUD 底板边框（逻辑像素）：36 高的面板放不下 8×6 的标准边框
HUD_PANEL_BORDER_X = 4.0
HUD_PANEL_BORDER_Y = 3.0


class HUD(UIWidget):
    def __init__(self, parent, transform: UITransform, text_db, asset_registry=None) -> None:
        self.text_db = text_db
        self.transform = transform
        self.assets = asset_registry
        root = parent.attach_new_node("hud")

        # 日期框：内容统一从底板外缘内缩 12 px（4 px 边框 + 8 px 内缘留白）
        self.date_panel = self._make_panel(root, theme.RECTS["hud_date"])
        self.date_label = UILabel(root, transform, 16, 12, "", color=theme.COLOR_TEXT)

        self.slot_dots: list = []
        for i in range(3):
            cm = CardMaker("slot_dot")
            cm.set_frame(0, 1, -1, 0)
            dot = root.attach_new_node(cm.generate())
            dot.set_transparency(TransparencyAttrib.M_alpha)
            ax, ay = transform.to_aspect2d(16 + i * 12, 27)
            dot.set_pos(ax, 0, ay)
            dot.set_scale(transform.px(8), 1, transform.px(8))
            self.slot_dots.append(dot)

        # 精力 / 心情
        self.gauge_panel = self._make_panel(root, theme.RECTS["hud_gauges"])
        self.energy_icon = UIIcon(root, transform, 332, 14, theme.STAT_ICON_IDS["energy"],
                                  8.0, asset_registry)
        self.energy_bar = StatBar(root, transform, 344, 14, fill_color=theme.COLOR_GAIN,
                                  asset_registry=asset_registry)
        self.energy_label = UILabel(root, transform, 446, 13, "", color=theme.COLOR_TEXT)
        self.mood_icon = UIIcon(root, transform, 332, 26, theme.STAT_ICON_IDS["mood"],
                                8.0, asset_registry, fallback_color=theme.COLOR_WARN)
        self.mood_bar = StatBar(root, transform, 344, 26,
                                fill_color=theme.hex_to_rgba(theme.HEX["warn"]),
                                asset_registry=asset_registry)
        self.mood_label = UILabel(root, transform, 446, 25, "", color=theme.COLOR_TEXT)

        # 按键提示（前 3 天显示）
        self.key_hint = UILabel(
            root, transform, 4, 252, text_db.get("ui.hud.key_hint"),
            color=theme.COLOR_SECONDARY,
        )

        self._energy_value = 0
        self._max_energy = 1
        self._blink_on = False
        self._blink_accum = 0.0
        super().__init__(root)

    # ------------------------------------------------------------------
    def _make_panel(self, parent, rect):
        """HUD 的底板：跟其他界面共用 UIPanel 的真九宫格。

        HUD 面板只有 36 高，内容（日期行 / 两条数值槽）一直排到 y+34，
        所以边框收窄到 4×3：金饰仍然完整，中间 28 行留给内容。
        """
        panel = UIPanel(parent, self.transform, rect, self.assets,
                        border=(HUD_PANEL_BORDER_X, HUD_PANEL_BORDER_Y))
        return panel.root

    # ------------------------------------------------------------------
    def update(self, state) -> None:
        """state: game.core.state.GameState（鸭子类型，避免依赖 A）。"""
        text = self.text_db.get(
            "ui.hud.date_fmt",
            year_name=self.text_db.get_raw(YEAR_IDS.get(state.year, "ui.hud.year.1")),
            sem_name=self.text_db.get_raw(SEM_IDS.get(state.semester, "ui.hud.semester.1")),
            day=state.day,
        )
        self.date_label.set_text(text)

        for i, dot in enumerate(self.slot_dots):
            dot.set_color(*(theme.COLOR_WARN if i < state.action_slot else theme.COLOR_SECONDARY))

        self._max_energy = max(1, state.max_energy())
        self._energy_value = state.energy
        self.energy_bar.set_value(state.energy, self._max_energy)
        self.energy_label.set_text(str(state.energy))
        self.mood_bar.set_value(state.mood, 100.0)
        self.mood_label.set_text(str(state.mood))

        if state.day_index < theme.KEY_HINT_DAYS:
            self.key_hint.show()
        else:
            self.key_hint.hide()

    def refresh_text(self) -> None:
        """语言/设置变化后刷新静态文本。"""
        self.key_hint.set_text(self.text_db.get("ui.hud.key_hint"))

    def set_key_hint_visible(self, visible: bool) -> None:
        (self.key_hint.show if visible else self.key_hint.hide)()

    def tick(self, dt: float) -> None:
        """精力 < 20 时警告条闪烁（0.5 秒一次）；数值在 update() 里更新。"""
        if self._max_energy <= 0 or self._energy_value >= LOW_ENERGY:
            self._blink_on = False
            self._blink_accum = 0.0
            self.energy_bar.set_color(theme.COLOR_GAIN)
            return
        self._blink_accum += dt
        if self._blink_accum >= BLINK_INTERVAL:
            self._blink_accum = 0.0
            self._blink_on = not self._blink_on
        self.energy_bar.set_color(theme.COLOR_WARN if self._blink_on else theme.COLOR_LOSS)
