"""设置菜单（D3）：文本速度 + 三个音量滑块。

- W/S 移动光标；A/D 调整（音量每次 ±10，文本速度在 4 档间循环）；
- 音量写 A 的 Settings 字段：master_volume / bgm_volume / sfx_volume（0..100）；
- 文本速度写 settings.text_speed，取值与 game/config.py 的 TEXT_SPEED_TABLE 一致：
  slow 20 / normal 40 / fast 80 / instant；
- 关闭时调用 settings.save()，A 负责落盘。
"""

from __future__ import annotations

from typing import Callable

from game.ui import theme
from game.ui.widgets import UILabel, UIPanel, UITransform, UIWidget

RECT = (120, 40, 240, 190)
ROW_HEIGHT = 20
VOLUME_KEYS = ("master_volume", "bgm_volume", "sfx_volume")
VOLUME_TEXT_IDS = {
    "master_volume": "ui.settings.volume.master",
    "bgm_volume": "ui.settings.volume.music",
    "sfx_volume": "ui.settings.volume.sfx",
}
SPEED_TEXT_IDS = {
    "slow": "ui.settings.speed.slow",
    "normal": "ui.settings.speed.normal",
    "fast": "ui.settings.speed.fast",
    "instant": "ui.settings.speed.instant",
}


class SettingsMenu(UIWidget):
    """settings 是 A 的 config.Settings（支持属性读写与 save()）。"""

    def __init__(self, parent, transform: UITransform, text_db, settings, asset_registry=None) -> None:
        self.text_db = text_db
        self.settings = settings
        self.transform = transform
        root = parent.attach_new_node("settings_menu")
        rect = RECT
        self.panel = UIPanel(root, transform, rect, asset_registry)
        x, y = rect[0], rect[1]

        self.title = UILabel(root, transform, x + 8, y + 6,
                             text_db.get("ui.settings.title"), size=theme.TITLE_SIZE / 2)

        self.row_labels: list[UILabel] = []
        self.value_labels: list[UILabel] = []
        row_defs = [("ui.settings.text_speed", "text_speed")] + [
            (VOLUME_TEXT_IDS[k], k) for k in VOLUME_KEYS
        ]
        for i, (text_id, _key) in enumerate(row_defs):
            row_y = y + 6 + 2 * theme.LINE_HEIGHT + i * ROW_HEIGHT
            self.row_labels.append(UILabel(root, transform, x + 18, row_y, text_db.get_raw(text_id)))
            self.value_labels.append(
                UILabel(root, transform, x + 140, row_y, "", color=theme.COLOR_SECONDARY)
            )

        self.hint = UILabel(root, transform, x + 10, y + rect[3] - 26,
                            text_db.get("ui.settings.hint"), color=theme.COLOR_SECONDARY)
        self.cursor = UILabel(root, transform, x + 8,
                              y + 6 + 2 * theme.LINE_HEIGHT, ">", color=theme.COLOR_CURSOR)

        self.on_back: Callable[[], None] | None = None
        self.index = 0
        self._refresh_values()
        super().__init__(root)
        self.hide()

    # ------------------------------------------------------------------
    def _speed(self) -> str:
        speed = getattr(self.settings, "text_speed", theme.DEFAULT_TEXT_SPEED)
        return speed if speed in theme.TEXT_SPEED_ORDER else theme.DEFAULT_TEXT_SPEED

    def _refresh_values(self) -> None:
        self.value_labels[0].set_text(self.text_db.get_raw(SPEED_TEXT_IDS[self._speed()]))
        for i, key in enumerate(VOLUME_KEYS, start=1):
            self.value_labels[i].set_text(str(int(getattr(self.settings, key, 80))))

    def _move_cursor(self) -> None:
        ax, ay = self.transform.to_aspect2d(
            RECT[0] + 8, RECT[1] + 6 + 2 * theme.LINE_HEIGHT + self.index * ROW_HEIGHT + 12
        )
        self.cursor.root.set_pos(ax, 0, ay)

    # ------------------------------------------------------------------
    def move(self, direction: int) -> None:
        self.index = (self.index + direction) % 4
        self._move_cursor()

    def adjust(self, direction: int) -> None:
        """A/D 调整：音量 ±10；文本速度在 4 档间循环。"""
        if self.index == 0:
            i = theme.TEXT_SPEED_ORDER.index(self._speed())
            self.settings.text_speed = theme.TEXT_SPEED_ORDER[
                (i + direction) % len(theme.TEXT_SPEED_ORDER)
            ]
        else:
            key = VOLUME_KEYS[self.index - 1]
            value = int(getattr(self.settings, key, 80)) + direction * 10
            setattr(self.settings, key, max(0, min(100, value)))
        self._refresh_values()

    def _persist(self) -> None:
        save = getattr(self.settings, "save", None)
        if callable(save):
            try:
                save()
            except Exception:  # pragma: no cover - 落盘失败不应影响返回
                self.text_db  # noqa: B018 - 保持引用，异常由 A 的日志记录
                raise

    def confirm(self) -> None:
        self._persist()
        self.hide()
        if self.on_back:
            self.on_back()

    def cancel(self) -> None:
        self._persist()
        self.hide()
        if self.on_back:
            self.on_back()
