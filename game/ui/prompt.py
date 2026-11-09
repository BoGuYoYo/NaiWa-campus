"""交互提示框（D2）：居中，y=218，宽 ≤220，高 30。

- 第 1 行「[E] 图书馆学习」；
- 第 2 行 preview 变化「精力 -20  学业 +5」；
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
        self.panel = UIPanel(root, transform, rect, asset_registry)
        self.title = UILabel(root, transform, rect[0] + 8, rect[1] + 2, "")
        self.detail = UILabel(root, transform, rect[0] + 8, rect[1] + 2 + theme.LINE_HEIGHT, "",
                              color=theme.COLOR_SECONDARY)
        self._id: str | None = None
        super().__init__(root)
        self.hide()

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
            self.detail.set_text(reason)
            self.detail.set_color(theme.COLOR_DISABLED)
        else:
            preview = getattr(prompt_view, "cost_preview", None) or {}
            name_of = {k: self.text_db.get_raw(t) for k, t in theme.STAT_NAME_IDS.items()}
            parts = [text for _k, _v, text in theme.format_deltas(preview, name_of)]
            self.detail.set_text("  ".join(parts))
            self.detail.set_color(theme.COLOR_SECONDARY)
        self.show()

    def current_id(self) -> str | None:
        return self._id

    def hide_prompt(self) -> None:
        self._id = None
        self.hide()
