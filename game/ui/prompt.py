"""交互提示框：底部居中，宽 220、高 64，支持活动预览最多三行。

- 第 1 行「[E] 图书馆学习」；
- 后续最多三行 preview 变化（按当前字体实际宽度折行）；
- 禁用时整体变灰并显示原因（err.* 文本，来自 error_code）。

文案 ID 由 C 的 InteractionService 产出：
activity → act.<id>.name，npc → npc.<id>.talk，door → ui.prompt.enter，
save → ui.prompt.save，inspect → insp.<id>.name。
"""

from __future__ import annotations

import logging

from game.ui import theme
from game.ui.widgets import UILabel, UIPanel, UITransform, UIWidget

_log = logging.getLogger("naiwa.ui.prompt")

ERROR_TEXT_IDS = {
    "E_NO_SLOT": "err.no_slot",
    "E_LOW_ENERGY": "err.low_energy",
    "E_DAILY_LIMIT": "err.daily_limit",
    "E_ALREADY_TALKED": "err.already_talked",
    "E_WRONG_PHASE": "err.wrong_phase",
    "E_UNKNOWN_ID": "err.unknown_id",
    "E_CHOICE_LOCKED": "err.choice_locked",
}


class InteractionPrompt(UIWidget):
    def __init__(self, parent, transform: UITransform, text_db, asset_registry=None) -> None:
        self.text_db = text_db
        self.transform = transform
        root = parent.attach_new_node("interaction_prompt")
        rect = theme.RECTS["prompt"]
        # show_prompt() 里折行要用面板内宽，把它留在实例上（局部 rect 已经出过 NameError）
        self._rect = rect
        self._assets = asset_registry
        self.panel = UIPanel(root, transform, rect, asset_registry)
        self.title = UILabel(root, transform, rect[0] + 8, rect[1] + 2, "")
        self.detail = UILabel(
            root, transform, rect[0] + 8, rect[1] + 17, "",
            color=theme.COLOR_SECONDARY,
        )
        self.detail_lines = [self.detail]
        for row in range(1, 3):
            label = UILabel(
                root, transform, rect[0] + 8, rect[1] + 17 + row * 13, "",
                color=theme.COLOR_SECONDARY,
            )
            label.hide()
            self.detail_lines.append(label)
        self._id: str | None = None
        self._panel_height = float(rect[3])
        super().__init__(root)
        self.hide()

    # ------------------------------------------------------------------
    def _layout(self, detail_lines: int) -> None:
        """按明细行数重排：面板底边固定贴住按键提示，向上收缩。

        尺寸必须把九宫格金边算进去：边框占掉上下各 border_y，文字若从
        panel_y+2 开始画，就会压在金边上（底下的提示框看起来"字比框还大"）。
        """
        detail_lines = max(1, min(3, int(detail_lines)))
        border_x, border_y = getattr(self.panel, "border", (4.0, 4.0))
        title_top = border_y + 1.0
        detail_top = title_top + 15.0
        content_bottom = detail_top + 13.0 * (detail_lines - 1) + 12.0
        height = content_bottom + border_y + 2.0
        x, y, w, _h = self._rect
        bottom = y + self._rect[3]
        new_rect = (x, bottom - height, w, height)
        if abs(height - self._panel_height) > 0.5:
            self.panel.destroy()
            self.panel = UIPanel(self.root, self.transform, new_rect, self._assets)
            self._panel_height = height
        self._rect = new_rect
        # UILabel 的坐标是「文字左上角」，内部按 y+字号 落基线，这里同理补一个字号
        size = self.title._size
        ax, ay = self.transform.to_aspect2d(
            new_rect[0] + border_x + 2.0, new_rect[1] + title_top + size
        )
        self.title.text_node.set_pos(ax, 0, ay)
        for index, label in enumerate(self.detail_lines):
            ax, ay = self.transform.to_aspect2d(
                new_rect[0] + border_x + 2.0, new_rect[1] + detail_top + index * 13 + size
            )
            label.text_node.set_pos(ax, 0, ay)

    # ------------------------------------------------------------------
    def show_prompt(self, prompt_view) -> None:
        """prompt_view: game.core.results.PromptView（鸭子类型）。"""
        self._id = getattr(prompt_view, "interactable_id", None)
        label = self.text_db.get_raw(prompt_view.label_text_id)
        enabled = bool(prompt_view.enabled)

        self.title.set_text(self.text_db.get("ui.prompt.hint", label=label))
        self.title.set_color(theme.COLOR_TEXT if enabled else theme.COLOR_DISABLED)

        if not enabled:
            reason_id = ERROR_TEXT_IDS.get(getattr(prompt_view, "reason_code", None) or "", "")
            if reason_id == "err.unknown_id":
                reason = self.text_db.get(
                    reason_id, id=getattr(prompt_view, "interactable_id", "")
                )
            else:
                reason = self.text_db.get(reason_id) if reason_id else self.text_db.get("ui.prompt.disabled")
            self._layout(1)
            self._set_detail_lines([reason], theme.COLOR_DISABLED)
        else:
            preview = getattr(prompt_view, "cost_preview", None) or {}
            name_of = {k: self.text_db.get_raw(t) for k, t in theme.STAT_NAME_IDS.items()}
            for key in preview:
                if theme._rel_sort_key(key)[0] == "":
                    npc_id = theme._rel_sort_key(key)[1]
                    short_id = npc_id.removeprefix("npc_")
                    npc_name = self.text_db.get_raw(f"npc.{short_id}.name")
                    name_of[key] = f"与{npc_name}的关系"
            parts = [text for _key, _value, text in theme.format_deltas(preview, name_of)]

            def measure_text(text: str) -> float:
                self.detail.node.set_text(text)
                # TextNode width is in font-height units; UILabel scales it to 12px.
                return self.detail.node.get_width() * self.detail._size

            lines = theme.wrap_prompt_details(parts, self._rect[2] - 16, measure_text)
            self._layout(len(lines))
            self._set_detail_lines(lines, theme.COLOR_SECONDARY)
        self.show()

    def _set_detail_lines(self, lines: list[str], color) -> None:
        for index, label in enumerate(self.detail_lines):
            text = lines[index] if index < len(lines) else ""
            label.set_text(text)
            label.set_color(color)
            (label.show if text else label.hide)()

    def current_id(self) -> str | None:
        return self._id

    def hide_prompt(self) -> None:
        self._id = None
        self.hide()
