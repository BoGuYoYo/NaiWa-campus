"""暂停菜单（D3/D2）：Esc 呼出。

继续 / 设置 / 存档 / 读档 / 回主菜单；Esc 再按返回校园。
"""

from __future__ import annotations

from typing import Callable

from game.ui import theme
from game.ui.widgets import UILabel, UIPanel, UITransform, UIWidget

RECT = (150, 60, 180, 150)
ITEM_HEIGHT = 20


class PauseMenu(UIWidget):
    def __init__(self, parent, transform: UITransform, text_db, asset_registry=None) -> None:
        self.text_db = text_db
        self.transform = transform
        root = parent.attach_new_node("pause_menu")
        rect = RECT
        self.panel = UIPanel(root, transform, rect, asset_registry)
        x, y = rect[0], rect[1]

        # 标题曾经借用 ui.tab.title，暂停菜单顶上写着「状态面板」
        self.title = UILabel(root, transform, x + 8, y + 6, text_db.get("ui.menu.pause_title"),
                             color=theme.COLOR_SECONDARY)

        self.item_keys = [
            "ui.menu.resume",
            "ui.menu.settings",
            "ui.menu.save",
            "ui.menu.load",
            "ui.menu.main_menu",
        ]
        self.labels: list[UILabel] = []
        for i, key in enumerate(self.item_keys):
            self.labels.append(
                UILabel(root, transform, x + 22, y + 26 + i * ITEM_HEIGHT,
                        text_db.get_raw(key))
            )
        self.cursor = UILabel(root, transform, x + 12, y + 26, ">", color=theme.COLOR_CURSOR)
        self.hint = UILabel(
            root, transform, x + 10, y + rect[3] - 24,
            text_db.get("ui.menu.hint.pause"), color=theme.COLOR_SECONDARY,
        )

        self.on_resume: Callable[[], None] | None = None
        self.on_settings: Callable[[], None] | None = None
        self.on_save: Callable[[], None] | None = None
        self.on_load: Callable[[], None] | None = None
        self.on_main_menu: Callable[[], None] | None = None
        self.index = 0
        super().__init__(root)
        self.hide()

    # ------------------------------------------------------------------
    def _move_cursor(self) -> None:
        ax, ay = self.transform.to_aspect2d(RECT[0] + 12, RECT[1] + 26 + self.index * ITEM_HEIGHT + 12)
        self.cursor.root.set_pos(ax, 0, ay)

    def move(self, direction: int) -> None:
        self.index = (self.index + direction) % len(self.item_keys)
        self._move_cursor()

    def confirm(self) -> str | None:
        """返回动作键名（ui.menu.*），由集成层分发。"""
        key = self.item_keys[self.index]
        self.hide()
        return key

    def cancel(self) -> None:
        self.hide()
        if self.on_resume:
            self.on_resume()
