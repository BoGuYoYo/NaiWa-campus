"""事件场景（D2/D3）：分页、打字机、选项、锁定原因。

数据来源：B 的 EventService.get_view(state, event_id) -> EventView；
独立夹具使用 tests/ui/fixtures/events.json 的 FakeEventView。

键盘规则（D3）：
- W/S、↑/↓：选项间循环移动光标；
- Space / Enter / E：打字中 → 整页；整页 → 下一页 / 确认选项；
- 1/2/3：直接选择（锁定项无效）；
- Esc 无效（事件不可中途退出）。

流程：page 推进 → 最后一页后显示选项 → confirm → on_choose
（由集成层调 B 的 EventService.choose）。
"""

from __future__ import annotations

import logging

from game.ui import theme
from game.ui.dialogue_box import DialogueBox
from game.ui.widgets import UILabel, UIPanel, UITransform, UIWidget

_log = logging.getLogger("naiwa.ui.event_scene")

LOCK_HINT_SECONDS = 2.0


class EventScene(UIWidget):
    """事件展示与选择。不计算数值，只显示 B 的结构化结果。"""

    def __init__(self, parent, transform: UITransform, text_db, asset_registry=None) -> None:
        self.text_db = text_db
        self.transform = transform
        self.assets = asset_registry
        root = parent.attach_new_node("event_scene")
        self.dialogue = DialogueBox(root, transform, text_db, asset_registry)

        rect = theme.RECTS["event_choices"]
        self.panel = UIPanel(root, transform, rect, asset_registry)
        self.choice_labels: list[UILabel] = []
        self.lock_hint = UILabel(
            root, transform, rect[0] + 8, rect[1] + rect[3] - 18,
            "", color=theme.COLOR_WARN,
        )
        self.page_hint = UILabel(
            root, transform, rect[0], rect[1] - 18,
            text_db.get("ui.event.page_hint"), color=theme.COLOR_SECONDARY,
        )
        self._lock_hint_timer = 0.0

        self.on_choose = None      # fn(event_id, choice_id) -> None
        self.on_finished = None    # fn(event_id) -> None（无选项事件读完触发）

        self._event_id: str | None = None
        self._pages: list[dict] = []
        self._page_index = 0
        self._cursor = None
        self._showing_result = False
        super().__init__(root)
        self.hide()

    # ------------------------------------------------------------------
    # 数据
    # ------------------------------------------------------------------
    def load_event(self, event_view) -> None:
        """event_view: EventView 或等价 dict。

        EventView: event_id / kind / speaker / page_text_ids / choices
        choices: [ChoiceView(choice_id, text_id, enabled, lock_reason_id)]
        """
        self.show()
        self._showing_result = False
        if isinstance(event_view, dict):
            self._event_id = event_view.get("event_id")
            page_ids = event_view.get("page_text_ids") or []
            choices = event_view.get("choices") or []
        else:
            self._event_id = getattr(event_view, "event_id", None)
            page_ids = getattr(event_view, "page_text_ids", None) or []
            choices = getattr(event_view, "choices", None) or []

        self._pages = [
            self.text_db.get_dialogue(pid) or {"lines": [self.text_db.get("err.unknown_id", id=pid)]}
            for pid in page_ids
        ]
        self._page_index = 0
        self._choice_text_ids = {}
        items = []
        for c in choices:
            if isinstance(c, dict):
                choice_id = c.get("choice_id")
                enabled = bool(c.get("enabled", True))
                lock = c.get("lock_reason_id")
                text_id = c.get("text_id")
            else:
                choice_id = getattr(c, "choice_id", None)
                enabled = bool(getattr(c, "enabled", True))
                lock = getattr(c, "lock_reason_id", None)
                text_id = getattr(c, "text_id", None)
            items.append((choice_id, enabled, lock))
            if text_id:
                self._choice_text_ids[choice_id] = text_id
        self._cursor = theme.MenuCursor(items) if items else None

        self._build_choice_labels()
        if self._pages:
            self._show_current_page()
        else:
            # 无分页（例如查看点的一段描述）：直接铺到对话框，不显示选项面板
            self.panel.hide()
            self.page_hint.hide()
            self.dialogue.show_page({"lines": [self.text_db.get("ui.event.page_hint")]})

    def _build_choice_labels(self) -> None:
        for label in self.choice_labels:
            label.destroy()
        self.choice_labels = []
        rect = theme.RECTS["event_choices"]
        if not self._cursor:
            self.lock_hint.set_text("")
            return
        for i, (choice_id, enabled, _reason) in enumerate(self._cursor.items):
            # 优先用 B 给的 text_id（ChoiceView.text_id），没有才按命名约定拼
            text_id = self._choice_text_ids.get(choice_id) or f"evt.{self._event_id}.choice.{choice_id}"
            label = UILabel(
                self.panel.root, self.transform,
                rect[0] + 12, rect[1] + 4 + i * 20,
                self.text_db.get(text_id),
                color=theme.COLOR_TEXT if enabled else theme.COLOR_DISABLED,
            )
            self.choice_labels.append(label)
        self._refresh_cursor()
        self.lock_hint.set_text("")

    def _refresh_cursor(self) -> None:
        if not self._cursor:
            return
        for i, label in enumerate(self.choice_labels):
            enabled = self._cursor.items[i][1]
            if not enabled:
                label.set_color(theme.COLOR_DISABLED)
            elif i == self._cursor.index:
                label.set_color(theme.COLOR_CURSOR)
            else:
                label.set_color(theme.COLOR_TEXT)
        reason = self._cursor.lock_reason
        if reason:
            self._show_lock_hint(self._resolve_lock_text(reason))
        else:
            self.lock_hint.set_text("")

    def _resolve_lock_text(self, reason: str) -> str:
        """锁定原因：B 可以直接给完整 text_id（含点号），否则按 evt.<id>.lock.<reason> 拼。"""
        if "." in reason and self.text_db.has(reason):
            return self.text_db.get_raw(reason)
        specific = f"evt.{self._event_id}.lock.{reason}"
        if self.text_db.has(specific):
            return self.text_db.get_raw(specific)
        return self.text_db.get("ui.event.choice_locked_hint")

    def _show_lock_hint(self, text: str) -> None:
        self.lock_hint.set_text(text)
        self._lock_hint_timer = LOCK_HINT_SECONDS

    # ------------------------------------------------------------------
    # 翻页与选择
    # ------------------------------------------------------------------
    def _show_current_page(self) -> None:
        page = self._pages[self._page_index]
        self.dialogue.show_page(page)
        if self._cursor and self._page_index >= len(self._pages) - 1:
            self.panel.show()
            for label in self.choice_labels:
                label.show()
            self.page_hint.hide()
        else:
            self.panel.hide()
            for label in self.choice_labels:
                label.hide()
            self.page_hint.show() if self._cursor else self.page_hint.hide()

    def _next_page(self) -> bool:
        if self._page_index < len(self._pages) - 1:
            self._page_index += 1
            self._show_current_page()
            return True
        return False

    # ------------------------------------------------------------------
    # 输入（D3）
    # ------------------------------------------------------------------
    def on_space(self) -> None:
        if self._showing_result:
            self._finish()
            return
        if self.dialogue.advance():
            return
        if self._cursor is None or not self.panel.is_shown():
            if not self._next_page() and self._cursor is None:
                self._finish()
            return
        self._confirm_choice()

    def on_move(self, direction: int) -> None:
        if self._cursor and self.panel.is_shown():
            self._cursor.move(direction)
            self._refresh_cursor()

    def on_digit(self, digit: int) -> None:
        if not self._cursor or not self.panel.is_shown():
            return
        result = self._cursor.select_digit(digit)
        if result is None:
            return
        choice_id, reason = result
        if reason:
            self._show_lock_hint(self._resolve_lock_text(reason))
            return
        self._emit_choice(choice_id)

    def _confirm_choice(self) -> None:
        result = self._cursor.confirm()
        if result is None:
            return
        choice_id, reason = result
        if reason:
            self._show_lock_hint(self._resolve_lock_text(reason))
            return
        self._emit_choice(choice_id)

    def _emit_choice(self, choice_id: str) -> None:
        self.panel.hide()
        for label in self.choice_labels:
            label.hide()
        if self.on_choose:
            self.on_choose(self._event_id, choice_id)

    # ------------------------------------------------------------------
    # 结果与结束
    # ------------------------------------------------------------------
    def show_event_result(self, event_result) -> None:
        """显示 EventResult.result_text_ids（B 返回，D 不计算）。"""
        self._showing_result = True
        lines = [self.text_db.get(tid) for tid in (getattr(event_result, "result_text_ids", None) or [])]
        self.dialogue.show_page({"speaker": None, "portrait": None, "lines": lines})

    def show_simple_pages(self, event_id: str, body_text_ids: list[str]) -> None:
        """无选项事件（关系事件 / 开场 / 日常事件）的展示。"""
        self.load_event({"event_id": event_id, "page_text_ids": body_text_ids, "choices": []})

    def tick(self, dt: float) -> None:
        self.dialogue.tick(dt)
        if self._lock_hint_timer > 0:
            self._lock_hint_timer -= dt
            if self._lock_hint_timer <= 0:
                self.lock_hint.set_text("")

    def _finish(self) -> None:
        self.hide()
        if self.on_finished and self._event_id:
            self.on_finished(self._event_id)
