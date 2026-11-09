"""对话框（D2）：整体 4, 166, 472, 100。

- 头像 96×96 位于 (6,168)；
- 名字条 (108,170)；
- 正文区 (108,188,362,72)，4 行；
- 打字机速度读 settings.text_speed（instant=0 → 立即整页）；
- Space / Enter / E：打字中 → 立即显示整页；整页已显示 → 下一页。
"""

from __future__ import annotations

import logging

from panda3d.core import CardMaker, TransparencyAttrib

from game.ui import theme
from game.ui.widgets import UILabel, MultilineLabel, UIPanel, UITransform, UIWidget

_log = logging.getLogger("naiwa.ui.dialogue_box")


class DialogueBox(UIWidget):
    def __init__(self, parent, transform: UITransform, text_db, asset_registry=None) -> None:
        self.text_db = text_db
        self.transform = transform
        self.assets = asset_registry
        root = parent.attach_new_node("dialogue_box")
        rect = theme.RECTS["dialogue"]
        self.panel = UIPanel(root, transform, rect, asset_registry)

        self.portrait = self._make_portrait(root, theme.RECTS["dialogue_portrait"])
        name_rect = theme.RECTS["dialogue_name"]
        self.name_label = UILabel(
            root, transform, name_rect[0], name_rect[1], "", color=theme.COLOR_WARN
        )
        body_rect = theme.RECTS["dialogue_body"]
        self.body = MultilineLabel(
            root, transform, body_rect[0], body_rect[1], [],
            line_height=body_rect[3] / theme.MAX_LINES_PER_PAGE,
        )
        self.continue_mark = UILabel(
            root, transform, rect[0] + rect[2] - 24, rect[1] + rect[3] - 18,
            text_db.get("ui.dialogue.continue"), color=theme.COLOR_SECONDARY,
        )
        self.continue_mark.hide()

        self._full_lines: list[str] = []
        self._revealed_chars = 0
        self._total_chars = 0
        self._cps = theme.chars_per_second(theme.DEFAULT_TEXT_SPEED)
        self._typing_done_callback = None
        super().__init__(root)
        self.hide()

    def _make_portrait(self, parent, rect):
        x, y, w, h = rect
        cm = CardMaker("dialogue_portrait")
        cm.set_frame(0, 1, -1, 0)
        node = parent.attach_new_node(cm.generate())
        node.set_color(*theme.hex_to_rgba("#4A5578"))
        node.set_transparency(TransparencyAttrib.M_alpha)
        node.set_scale(self.transform.px(w), 1, self.transform.px(h))
        ax, ay = self.transform.to_aspect2d(x, y)
        node.set_pos(ax, 0, ay)
        return node

    # ------------------------------------------------------------------
    def set_text_speed(self, speed_name: str) -> None:
        self._cps = theme.chars_per_second(speed_name)

    def show_page(self, page: dict | None, fallback_lines: list[str] | None = None) -> None:
        """显示一个对话页。

        page 结构来自 dialogues.json：
        {"speaker": "npc_sumo" | None, "portrait": asset_id | None, "lines": [...]}
        """
        self.show()
        page = page or {}
        lines = page.get("lines") or fallback_lines or [""]

        speaker = page.get("speaker")
        if speaker:
            short = str(speaker).replace("npc_", "")
            self.name_label.set_text(self.text_db.get(f"npc.{short}.name"))
        else:
            self.name_label.set_text("")

        portrait_id = page.get("portrait")
        if portrait_id and self.assets is not None:
            tex = None
            try:
                tex = self.assets.load_texture(portrait_id)
            except Exception:
                tex = None
            if tex is not None:
                self.portrait.set_texture(tex)
                self.portrait.set_color(1, 1, 1, 1)
            else:
                _log.warning("asset.missing asset_id=%s", portrait_id)
                self.portrait.set_color(*theme.hex_to_rgba("#4A5578"))
        else:
            self.portrait.set_color(*theme.hex_to_rgba("#4A5578"))

        self._full_lines = list(lines)
        self._total_chars = sum(len(line) for line in self._full_lines)
        self._revealed_chars = 0 if self._cps > 0 else self._total_chars
        self._apply_typewriter()
        self.continue_mark.hide()

    def _apply_typewriter(self) -> None:
        """按已显示字符数渲染多行打字机文本。"""
        remaining = self._revealed_chars
        shown: list[str] = []
        for line in self._full_lines:
            take = max(0, min(len(line), remaining))
            shown.append(line[:take])
            remaining -= take
        self.body.set_lines(shown)
        if self._revealed_chars >= self._total_chars:
            self._typing_finished()

    def _typing_finished(self) -> None:
        self.continue_mark.show()
        if self._typing_done_callback:
            callback, self._typing_done_callback = self._typing_done_callback, None
            callback()

    def tick(self, dt: float) -> None:
        if not self.visible or self._cps <= 0 or self._revealed_chars >= self._total_chars:
            return
        self._revealed_chars = min(
            self._total_chars, self._revealed_chars + int(self._cps * dt + 0.999)
        )
        self._apply_typewriter()

    def advance(self) -> bool:
        """Space / Enter / E。返回 False 表示本页已完整显示。"""
        if self._revealed_chars < self._total_chars:
            self._revealed_chars = self._total_chars
            self._apply_typewriter()
            return True
        return False
