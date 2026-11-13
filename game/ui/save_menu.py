"""存读档界面（D2/D3）：3 个手动存档位 + 自动存档展示。

与 A 的 SaveManager 对齐：
- 槽位 ID 固定为 slot_1 / slot_2 / slot_3 / autosave（config.SLOT_IDS）；
- list_slots() 返回 list[SaveSummary]，其中 summary["day_index"] 是存档天；
- save(state, slot) 需要当前 GameState，由集成层通过 state_provider 提供；
- 自动存档只可读，不可覆盖。
"""

from __future__ import annotations

import logging

from game.ui import theme
from game.ui.widgets import UILabel, UIPanel, UITransform, UIWidget

_log = logging.getLogger("naiwa.ui.save_menu")

MANUAL_SLOTS = ("slot_1", "slot_2", "slot_3")
AUTOSAVE = "autosave"
RECT = (140, 50, 200, 170)
ROW_HEIGHT = 20


class SaveMenu(UIWidget):
    def __init__(self, parent, transform: UITransform, text_db, asset_registry=None) -> None:
        self.text_db = text_db
        self.transform = transform
        root = parent.attach_new_node("save_menu")
        rect = RECT
        self.panel = UIPanel(root, transform, rect, asset_registry)
        x, y = rect[0], rect[1]

        self.title = UILabel(root, transform, x + 8, y + 6, "", size=theme.TITLE_SIZE / 2)
        self.row_labels: list[UILabel] = []
        self.rows = MANUAL_SLOTS + (AUTOSAVE,)
        for i in range(len(self.rows)):
            self.row_labels.append(
                UILabel(root, transform, x + 18, y + 6 + 2 * theme.LINE_HEIGHT + i * ROW_HEIGHT, "")
            )
        self.cursor = UILabel(root, transform, x + 8,
                              y + 6 + 2 * theme.LINE_HEIGHT, ">", color=theme.COLOR_CURSOR)
        self.hint = UILabel(root, transform, x + 10, y + rect[3] - 26,
                            text_db.get("ui.save.hint"), color=theme.COLOR_SECONDARY)
        #: 操作结果/错误提示（空槽、写盘失败、已保存）。以前这些情况只写日志，
        #: 玩家按了 Space 看不到任何变化，观感就是"界面卡死"。
        self.status = UILabel(root, transform, x + 8, y + rect[3] - 42, "",
                              color=theme.COLOR_WARN)
        self.status.hide()

        self.mode = "save"
        self.index = 0
        self.save_manager = None
        self.state_provider = None   # fn() -> GameState
        self.on_done = None          # fn(success: bool) -> None
        self.on_loaded = None        # fn(state) -> None
        super().__init__(root)
        self.hide()

    def _show_status(self, text: str) -> None:
        self.status.set_text(text)
        self.status.show()

    # ------------------------------------------------------------------
    def open(self, mode: str, save_manager, state_provider=None) -> None:
        self.mode = mode
        self.save_manager = save_manager
        self.state_provider = state_provider
        self.index = 0
        self.status.set_text("")
        self.status.hide()
        self.title.set_text(
            self.text_db.get("ui.save.title" if mode == "save" else "ui.save.load_title")
        )
        self.show()
        self.refresh()

    def _slots(self) -> dict[str, dict]:
        if not self.save_manager:
            return {}
        try:
            summaries = self.save_manager.list_slots() or []
        except Exception as exc:  # pragma: no cover - 依赖 A 的实现
            _log.warning("list_slots 失败: %s", exc)
            return {}
        out: dict[str, dict] = {}
        for summary in summaries:
            slot = getattr(summary, "slot", None)
            if slot is None and isinstance(summary, dict):
                slot = summary.get("slot")
            if slot is None:
                continue
            meta = getattr(summary, "summary", None)
            if meta is None and isinstance(summary, dict):
                meta = summary.get("summary", summary)
            out[str(slot)] = dict(meta or {})
        return out

    def refresh(self) -> None:
        slots = self._slots()
        for i, slot in enumerate(self.rows):
            if slot == AUTOSAVE:
                name = self.text_db.get("ui.save.slot_autosave")
            else:
                name = self.text_db.get("ui.save.slot", n=i + 1)
            meta = slots.get(slot)
            if meta is None:
                text = f"{name}  {self.text_db.get('ui.save.empty')}"
            else:
                day = int(meta.get("day_index", 0)) + 1
                text = f"{name}  第 {day} 天"
            self.row_labels[i].set_text(text)
        ax, ay = self.transform.to_aspect2d(
            RECT[0] + 8, RECT[1] + 6 + 2 * theme.LINE_HEIGHT + self.index * ROW_HEIGHT + 12
        )
        self.cursor.root.set_pos(ax, 0, ay)

    # ------------------------------------------------------------------
    def _selectable(self) -> list[int]:
        if self.mode == "save":
            return list(range(len(MANUAL_SLOTS)))   # autosave 不可覆盖
        return list(range(len(self.rows)))           # 读档可读自动存档

    def move(self, direction: int) -> None:
        options = self._selectable()
        if not options:
            return
        if self.index not in options:
            self.index = options[0]
            self.refresh()
            return
        pos = (options.index(self.index) + direction) % len(options)
        self.index = options[pos]
        self.refresh()

    def confirm(self) -> None:
        if not self.save_manager:
            return
        slot = self.rows[self.index]
        if self.mode == "save":
            state = self.state_provider() if self.state_provider else None
            if state is None:
                _log.error("没有可保存的 GameState，忽略本次存档")
                self._show_status(self.text_db.get("ui.save.failed"))
                return
            try:
                self.save_manager.save(state, slot)
            except Exception as exc:
                _log.error("存档失败 slot=%s: %s", slot, exc)
                self._show_status(self.text_db.get("ui.save.failed"))
                return
            self.refresh()
            self._show_status(self.text_db.get("ui.save.saved"))
            if self.on_done:
                self.on_done(True)
            return
        try:
            state = self.save_manager.load(slot)
        except Exception as exc:
            _log.warning("读档失败 slot=%s: %s", slot, exc)
            # 空槽/损坏存档必须给反馈：以前只写日志，玩家按 Space 后
            # 面板毫无变化，看起来就是"死了"。
            self._show_status(self.text_db.get("ui.save.empty_slot"))
            return
        if state is None:
            self._show_status(self.text_db.get("ui.save.empty_slot"))
            return
        self.refresh()
        self._show_status(self.text_db.get("ui.save.loaded"))
        self.hide()
        if self.on_loaded:
            self.on_loaded(state)
        elif self.on_done:
            self.on_done(True)

    def cancel(self) -> None:
        self.hide()
        if self.on_done:
            self.on_done(False)
