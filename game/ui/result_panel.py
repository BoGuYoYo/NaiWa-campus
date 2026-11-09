"""活动结果面板（D2）：主体 100, 40, 280, 190。

- 标题：活动名（act.<activity_id>.name）；
- 活动插图 160×90（asset_id = cg_naiwan_<activity_id>，由 A 的 AssetRegistry 提供）；
- 结果文本最多 2 行（result.text_ids 按顺序显示）；
- 数值变化列表：只显示 B 的 deltas，不自行计算，逐条出现，间隔 0.12 秒；
- 底部「[Space] 继续」/「有事情发生了……」。
"""

from __future__ import annotations

import logging

from panda3d.core import CardMaker, TransparencyAttrib

from game.ui import theme
from game.ui.widgets import UILabel, MultilineLabel, UIPanel, UITransform, UIWidget

_log = logging.getLogger("naiwa.ui.result_panel")

REVEAL_INTERVAL = 0.12  # 数值逐条出现间隔

#: 交谈不是"活动"，没有 cg_naiwan_<id>；标题和正文改读 NPC 的文本键
NPC_TALK_PREFIX = "talk."


def _talk_npc_short(activity_id: str) -> str | None:
    """`talk.npc_sumo` -> `sumo`；不是交谈返回 None。"""
    if not activity_id.startswith(NPC_TALK_PREFIX):
        return None
    return activity_id.split(".", 1)[1].removeprefix("npc_")


class ResultPanel(UIWidget):
    def __init__(self, parent, transform: UITransform, text_db, asset_registry=None) -> None:
        self.text_db = text_db
        self.transform = transform
        self.assets = asset_registry
        root = parent.attach_new_node("result_panel")
        rect = theme.RECTS["result"]
        self.panel = UIPanel(root, transform, rect, asset_registry)
        x, y, w, _h = rect

        self.title = UILabel(root, transform, x + 8, y + 6, "", size=theme.TITLE_SIZE / 2)
        self.illustration = self._make_illustration(root, theme.RECTS["result_illustration"])
        self.result_text = MultilineLabel(root, transform, x + 8, y + 110, [])
        self.delta_labels: list[UILabel] = []
        self.continue_hint = UILabel(
            root, transform, x + w - 96, y + 172,
            text_db.get("ui.result.continue"), color=theme.COLOR_SECONDARY,
        )
        self._deltas: list[tuple[str, int, str]] = []
        self._reveal_count = 0
        self._accum = 0.0
        self.on_close = None
        super().__init__(root)
        self.hide()

    def _make_illustration(self, parent, rect):
        x, y, w, h = rect
        cm = CardMaker("result_illustration")
        cm.set_frame(0, 1, -1, 0)
        node = parent.attach_new_node(cm.generate())
        node.set_color(*theme.hex_to_rgba("#3A4358"))
        node.set_transparency(TransparencyAttrib.M_alpha)
        node.set_scale(self.transform.px(w), 1, self.transform.px(h))
        ax, ay = self.transform.to_aspect2d(x, y)
        node.set_pos(ax, 0, ay)
        return node

    # ------------------------------------------------------------------
    def _apply_illustration(self, activity_id: str) -> None:
        """按 cg_naiwan_<activity_id> 取活动插图；缺失时保留占位色块。"""
        if self.assets is None or not activity_id:
            return
        asset_id = f"cg_naiwan_{activity_id}"
        try:
            tex = self.assets.load_texture(asset_id)
        except Exception:
            tex = None
        if tex is None:
            _log.warning("asset.missing asset_id=%s（结果面板使用占位色块）", asset_id)
            self.illustration.set_color(*theme.hex_to_rgba("#3A4358"))
            return
        self.illustration.set_texture(tex)
        self.illustration.set_color(1, 1, 1, 1)

    # ------------------------------------------------------------------
    def show_result(self, activity_result) -> None:
        """activity_result: game.core.results.ActivityResult。"""
        self.show()
        self._accum = 0.0
        self._reveal_count = 0

        activity_id = getattr(activity_result, "activity_id", "") or ""
        talk_short = _talk_npc_short(activity_id)
        if talk_short:
            # 交谈复用 NPC 的文本键与占位色块（B 会给 talk.<npc>.result.1，
            # 与 npc.<short>.talk 语义重复，只显示 D 的那句）
            self.title.set_text(self.text_db.get(f"npc.{talk_short}.name"))
            self.illustration.clear_texture()
            self.illustration.set_color(*theme.hex_to_rgba("#3A4358"))
            text_ids = [f"npc.{talk_short}.talk"]
        else:
            self.title.set_text(self.text_db.get(f"act.{activity_id}.name"))
            self._apply_illustration(activity_id)
            text_ids = list(getattr(activity_result, "text_ids", None) or [])

        # 结果文本：text_ids 顺序显示，最多 2 行
        lines: list[str] = []
        for text_id in text_ids[:2]:
            lines.extend(self.text_db.get(text_id).splitlines() or [""])
        self.result_text.set_lines(lines[:2])

        # 数值变化：deltas 全部非零项
        name_of = {k: self.text_db.get_raw(t) for k, t in theme.STAT_NAME_IDS.items()}
        self._deltas = theme.format_deltas(getattr(activity_result, "deltas", None) or {}, name_of)

        for label in self.delta_labels:
            label.destroy()
        self.delta_labels = []
        x, y, _w, _h = theme.RECTS["result"]
        for i, (_key, value, text) in enumerate(self._deltas):
            label = UILabel(
                self.root, self.transform, x + 168, y + 118 + i * theme.LINE_HEIGHT,
                text, color=theme.delta_color(value),
            )
            label.hide()
            self.delta_labels.append(label)
        if not self._deltas:
            _log.debug("结果面板收到空 deltas: %s", activity_id)

        # 日常事件是立即结算的，后面没有场景可跟进，提示语保持"继续"
        from game.core.flow import is_immediate_event

        if getattr(activity_result, "triggered_event_id", None) and not is_immediate_event(
            activity_result.triggered_event_id
        ):
            self.continue_hint.set_text(self.text_db.get("ui.result.event_follow"))
        else:
            self.continue_hint.set_text(self.text_db.get("ui.result.continue"))

    def tick(self, dt: float) -> None:
        if not self.visible or self._reveal_count >= len(self._deltas):
            return
        self._accum += dt
        while self._accum >= REVEAL_INTERVAL and self._reveal_count < len(self._deltas):
            self._accum -= REVEAL_INTERVAL
            self.delta_labels[self._reveal_count].show()
            self._reveal_count += 1

    def confirm(self) -> None:
        """Space：数值未完全展示时先补齐，再关闭。"""
        if self._reveal_count < len(self._deltas):
            for label in self.delta_labels:
                label.show()
            self._reveal_count = len(self._deltas)
            return
        self.hide()
        if self.on_close:
            self.on_close()
