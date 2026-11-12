"""日结算面板（D2）：主体 120, 60, 240, 150。

- 「第 N 天结束」；
- 当天 3 次行动摘要（由 GameFlow 传入行动名列表）；
- 精力恢复值（DayEndResult.deltas["energy"]）；
- 学期事件预告（semester_event_id 非空时）；
- 「[Space] 继续」。
"""

from __future__ import annotations

from game.ui import theme
from game.ui.widgets import UILabel, UIPanel, UITransform, UIWidget


class DaySummary(UIWidget):
    def __init__(self, parent, transform: UITransform, text_db, asset_registry=None) -> None:
        self.text_db = text_db
        self.transform = transform
        root = parent.attach_new_node("day_summary")
        rect = theme.RECTS["day_summary"]
        self.panel = UIPanel(root, transform, rect, asset_registry)
        x, y, w, h = rect

        self.title = UILabel(root, transform, x + 8, y + 6, "", size=theme.TITLE_SIZE / 2)
        self.actions_title = UILabel(
            root, transform, x + 8, y + 6 + 2 * theme.LINE_HEIGHT, "",
            color=theme.COLOR_SECONDARY,
        )
        self.action_lines = [
            UILabel(root, transform, x + 8, y + 6 + 3 * theme.LINE_HEIGHT + i * theme.LINE_HEIGHT, "")
            for i in range(3)
        ]
        self.energy_line = UILabel(root, transform, x + 8, y + 6 + 6 * theme.LINE_HEIGHT, "")
        self.event_tease = UILabel(
            root, transform, x + 8, y + 6 + 7 * theme.LINE_HEIGHT, "",
            color=theme.COLOR_WARN,
        )
        self.continue_hint = UILabel(
            root, transform, x + w - 96, y + h - 26,
            text_db.get("ui.day_summary.continue"), color=theme.COLOR_SECONDARY,
        )
        self.on_close = None
        super().__init__(root)
        self.hide()

    def show_summary(self, day_end_result, day: int, action_names: list[str]) -> None:
        """day_end_result: DayEndResult；action_names: 当天 3 次行动名。"""
        self.show()
        self.title.set_text(self.text_db.get("ui.day_summary.title", day=day))
        self.actions_title.set_text(self.text_db.get("ui.day_summary.actions_title"))
        for i, label in enumerate(self.action_lines):
            if i < len(action_names):
                label.set_text(f"{i + 1}. {action_names[i]}")
                label.show()
            else:
                label.hide()
        deltas = getattr(day_end_result, "deltas", None) or {}
        energy_delta = int(deltas.get("energy", 0))
        self.energy_line.set_text(
            self.text_db.get("ui.day_summary.energy_recovered", amount=max(0, energy_delta))
        )
        if getattr(day_end_result, "semester_event_id", None):
            self.event_tease.set_text(self.text_db.get("ui.day_summary.semester_event"))
            self.event_tease.show()
        else:
            self.event_tease.hide()

    def confirm(self) -> None:
        self.hide()
        if self.on_close:
            self.on_close()
