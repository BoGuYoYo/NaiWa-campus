"""对话框（D2）：整体 4, 166, 472, 100。

- 头像 84×84 位于 (12,174)，在对话框内缘留 8px 边距；
- 名字条 (108,170)；
- 正文区 (108,188,362,72)，4 行；
- 打字机速度读 settings.text_speed（instant=0 → 立即整页）；
- Space / Enter / E：打字中 → 立即显示整页；整页已显示 → 下一页。
"""

from __future__ import annotations

import logging

from panda3d.core import CardMaker, TextNode, TransparencyAttrib

from game.ui import theme
from game.ui.widgets import (
    FONT_SIZE_BODY,
    UILabel,
    MultilineLabel,
    UIPanel,
    UITransform,
    UIWidget,
    default_font,
)

_log = logging.getLogger("naiwa.ui.dialogue_box")


def _resolve_portrait_id(page: dict) -> str:
    """Resolve explicit or speaker-based portrait fallback for a dialogue page."""
    portrait_id = page.get("portrait")
    if portrait_id:
        return str(portrait_id)
    speaker = page.get("speaker")
    if speaker and str(speaker).startswith("npc_"):
        return f"portrait_npc_{str(speaker).removeprefix('npc_')}_neutral"
    return "portrait_naiwan_neutral"


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
        self.page_label = UILabel(
            root, transform, rect[0] + rect[2] - 14, rect[1] + 4, "",
            color=theme.COLOR_SECONDARY, align=TextNode.A_right,
        )
        self.page_label.hide()
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

        #: 折行用的测量节点（与正文同字体同字号）；正文区宽度见 dialogue_body
        self._measure_node = TextNode("dialogue_measure")
        self._measure_node.set_align(TextNode.A_left)
        chosen_font = default_font()
        if chosen_font is not None:
            self._measure_node.set_font(chosen_font)

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

    def set_page_indicator(self, current: int, total: int) -> None:
        if total > 1:
            self.page_label.set_text(f"{current}/{total}")
            self.page_label.show()
        else:
            self.page_label.set_text("")
            self.page_label.hide()

    def _set_body_portrait_layout(self) -> None:
        x = theme.RECTS["dialogue_body"][0]
        self.body._x = x
        for index, label in enumerate(self.body.labels):
            y = self.body._y + index * self.body._line_height
            ax, ay = self.transform.to_aspect2d(x, y + label._size)
            label.text_node.set_pos(ax, 0, ay)

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

        portrait_id = _resolve_portrait_id(page)

        self._set_body_portrait_layout()
        tex = None
        if self.assets is not None:
            try:
                tex = self.assets.load_texture(portrait_id)
            except Exception:
                tex = None
        if tex is not None:
            self.portrait.set_texture(tex)
            self.portrait.set_color(1, 1, 1, 1)
            self.portrait.show()
        else:
            # Keep the placeholder visible only for an actual requested portrait
            # that failed to load; this remains a clear QA signal.
            _log.warning("asset.missing asset_id=%s", portrait_id)
            self.portrait.clear_texture()
            self.portrait.set_color(*theme.hex_to_rgba("#4A5578"))
            self.portrait.show()

        self._full_lines = self._wrap_lines(lines)
        self._total_chars = sum(len(line) for line in self._full_lines)
        self._revealed_chars = 0 if self._cps > 0 else self._total_chars
        self._apply_typewriter()
        self.continue_mark.hide()

    def _measure(self, text: str) -> float:
        self._measure_node.set_text(text)
        return self._measure_node.get_width() * FONT_SIZE_BODY

    def _wrap_lines(self, lines: list[str]) -> list[str]:
        """把过长的行按正文区宽度折开，最多 MAX_LINES_PER_PAGE 行。

        正式剧情页在 dialogues.json 里已经手工分好行，这里对它们是空操作；
        查看点（inspect）这类整段塞进来的文本才会真正折行——旧版会一路画出
        对话框、画到屏幕外面去。
        """
        if getattr(self, "_measure_node", None) is None:
            return list(lines)[: theme.MAX_LINES_PER_PAGE]
        limit = float(theme.RECTS["dialogue_body"][2])
        wrapped: list[str] = []
        for line in lines:
            wrapped.extend(theme.wrap_cjk(str(line), limit, self._measure))
            if len(wrapped) >= theme.MAX_LINES_PER_PAGE:
                break
        return wrapped[: theme.MAX_LINES_PER_PAGE]

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
