"""主菜单（D2）：列表 180, 150, 120, 90。

新游戏 / 继续（无 autosave 时置灰）/ 读档 / 设置 / 退出。
"""

from __future__ import annotations

from typing import Callable

from game.ui import theme
from game.ui.widgets import UILabel, UIPanel, UITransform, UIWidget

ITEM_HEIGHT = 16

ITEMS = (
    ("ui.menu.new_game", "new_game"),
    ("ui.menu.continue", "continue"),
    ("ui.menu.load", "load"),
    ("ui.menu.settings", "settings"),
    ("ui.menu.quit", "quit"),
)


class MainMenu(UIWidget):
    def __init__(self, parent, transform: UITransform, text_db, asset_registry=None) -> None:
        self.text_db = text_db
        self.transform = transform
        root = parent.attach_new_node("main_menu")
        self.panel = UIPanel(root, transform, theme.RECTS["main_menu"], asset_registry)
        rect = theme.RECTS["main_menu"]
        x, y = rect[0], rect[1]

        self.title = UILabel(
            root, transform, 90, 40, text_db.get("ui.main_menu.title"),
            size=theme.TITLE_SIZE, color=theme.COLOR_TEXT,
        )
        self.subtitle = UILabel(
            root, transform, 90, 76, text_db.get("ui.main_menu.subtitle"),
            color=theme.COLOR_SECONDARY,
        )

        self.enabled = {key: True for _tid, key in ITEMS}
        self.labels: list[UILabel] = []
        for i, (text_id, _key) in enumerate(ITEMS):
            self.labels.append(UILabel(root, transform, x + 8, y + 4 + i * ITEM_HEIGHT, text_db.get_raw(text_id)))
        self.cursor = UILabel(root, transform, x - 2, y + 4, ">", color=theme.COLOR_CURSOR)

        self.save_manager = None
        self.handlers: dict[str, Callable[[], None]] = {}
        self.index = 0
        super().__init__(root)
        self.refresh()

    # ------------------------------------------------------------------
    def attach_save_manager(self, save_manager) -> None:
        self.save_manager = save_manager
        self.refresh()

    def _has_autosave(self) -> bool:
        if self.save_manager is None:
            return False
        try:
            return bool(self.save_manager.exists("autosave"))
        except Exception:
            return False

    def refresh(self) -> None:
        self.enabled["continue"] = self._has_autosave()
        for i, (text_id, key) in enumerate(ITEMS):
            enabled = self.enabled[key]
            self.labels[i].set_text(
                self.text_db.get_raw(text_id) if enabled
                else f"{self.text_db.get_raw(text_id)}（{self.text_db.get('ui.menu.reason.no_save_short')}）"
            )
            self.labels[i].set_color(theme.COLOR_TEXT if enabled else theme.COLOR_DISABLED)
        if not self.enabled[ITEMS[self.index][1]]:
            self.index = 0
        ax, ay = self.transform.to_aspect2d(
            theme.RECTS["main_menu"][0] - 2, theme.RECTS["main_menu"][1] + 4 + self.index * ITEM_HEIGHT + 12
        )
        self.cursor.root.set_pos(ax, 0, ay)

    def show(self) -> None:
        super().show()
        self.refresh()

    def move(self, direction: int) -> None:
        n = len(ITEMS)
        for _ in range(n):
            self.index = (self.index + direction) % n
            if self.enabled[ITEMS[self.index][1]]:
                break
        self.refresh()

    def confirm(self) -> str | None:
        text_id, key = ITEMS[self.index]
        if not self.enabled[key]:
            return None
        handler = self.handlers.get(key)
        if handler:
            handler()
        return key
