"""毕业界面（D2）：全屏 0, 0, 480, 270，共 4 页。

1. 总评属性（5 属性 + 关系）；
2. 四年回顾（EndingResult.highlights，text_id 列表逐条显示）；
3. 结局标题与正文（ending.<id>.title / body.1~3）；
4. 制作人员与返回。
"""

from __future__ import annotations

import logging

from game.ui import theme
from game.ui.widgets import UILabel, MultilineLabel, UIPanel, UITransform, UIWidget

_log = logging.getLogger("naiwa.ui.graduation")

PAGES = ("stats", "review", "ending", "credits")


class GraduationScene(UIWidget):
    def __init__(self, parent, transform: UITransform, text_db, asset_registry=None) -> None:
        self.text_db = text_db
        self.transform = transform
        root = parent.attach_new_node("graduation_scene")
        rect = theme.RECTS["graduation"]
        self.panel = UIPanel(root, transform, rect, asset_registry)

        self.page_title = UILabel(root, transform, 60, 26, "", size=theme.TITLE_SIZE)
        self.content = MultilineLabel(root, transform, 60, 62, [])
        self.ending_title = UILabel(root, transform, 60, 62, "",
                                    size=theme.TITLE_SIZE / 2, color=theme.COLOR_WARN)
        self.ending_body = MultilineLabel(root, transform, 60, 92, [])
        self.credits = MultilineLabel(root, transform, 60, 96, [])
        #: 折行测量节点（与正文同字体同字号）。结局正文是整段中文、不带换行，
        #: 以前直接 set_lines 原样输出：实测最宽 456px，从 x=60 起会冲出 480
        #: 画布右缘，末尾几个字被裁掉。这里按可用宽度重新折。
        from panda3d.core import TextNode

        from game.ui.widgets import default_font

        self._measure_node = TextNode("graduation_measure")
        self._measure_node.set_align(TextNode.A_left)
        chosen_font = default_font()
        if chosen_font is not None:
            self._measure_node.set_font(chosen_font)
        self.page_hint = UILabel(
            root, transform, 60, 244,
            text_db.get("ui.graduation.page_hint"), color=theme.COLOR_SECONDARY,
        )
        self.return_hint = UILabel(
            root, transform, 60, 244,
            text_db.get("ui.graduation.return"), color=theme.COLOR_CURSOR,
        )

        self._page = 0
        self._state_snapshot: dict = {}
        self._ending = None
        self._closed = False
        self.on_back_to_menu = None
        super().__init__(root)
        self.hide()

    # ------------------------------------------------------------------
    def open(self, ending_result, state_snapshot: dict | None = None) -> None:
        """ending_result: EndingResult；state_snapshot: 毕业时的总评数据。"""
        self._ending = ending_result
        self._state_snapshot = state_snapshot or {}
        self._page = 0
        self._closed = False
        self.show()
        self._render()

    def _highlight_line(self, entry) -> str:
        """把 EndingResult.highlights 的一行还原成玩家看得懂的文案。

        highlights 由 B 产出，是「计数器×次数」或「事件:选项」两种内部键，
        并不是 text_id；直接交给 get_raw() 会印成 `#class_count×3`。
        这里逐种解析，解析不出来就返回空串——宁可不显示，也不把内部 ID 印给玩家。
        """
        text = str(entry or "").strip()
        if not text:
            return ""
        if self.text_db.has(text):
            return self.text_db.get_raw(text)
        if "×" in text:
            key, _, count = text.rpartition("×")
            count = count.strip()
            text_id = f"ending.counter.{key.strip()}"
            if self.text_db.has(text_id):
                return self.text_db.get(text_id, n=count, count=count)
            return ""
        if ":" in text:
            event_id, _, choice_id = text.partition(":")
            for text_id in (f"evt.{event_id}.choice.{choice_id}.review",
                            f"evt.{event_id}.choice.{choice_id}"):
                if self.text_db.has(text_id):
                    return self.text_db.get_raw(text_id)
            title_id = f"evt.{event_id}.title"
            if self.text_db.has(title_id):
                return self.text_db.get_raw(title_id)
            return ""
        return ""

    def _wrap_body(self, lines: list[str]) -> list[str]:
        """按画布可用宽度折行；折出来的行数超过版面容量时压一下行距。

        正文从 x=60 起，右缘留 20px 边距，可用 480-60-20=400 逻辑像素。
        三行正文按 12px 字号、22px 行距排得下 3~5 行；更多行说明文案过长，
        继续缩行距会糊在一起，所以只在 92..240 的高度里平均分配。
        """
        limit = 480.0 - 60.0 - 20.0
        wrapped: list[str] = []
        for line in lines:
            wrapped.extend(theme.wrap_cjk(str(line), limit, self._measure))
        if len(wrapped) > 5:
            _log.warning("结局正文 %d 行，超过版面容量（5 行），按 5 行显示", len(wrapped))
            wrapped = wrapped[:5]
        line_height = 22.0
        if len(wrapped) > 3:
            # 92 起、到返回提示 244 之前：最多 152px 可用
            line_height = min(line_height, 150.0 / max(1, len(wrapped) - 1))
        self.ending_body._line_height = line_height
        self.ending_body.set_lines(wrapped)
        return wrapped

    def _measure(self, text: str) -> float:
        self._measure_node.set_text(text)
        return self._measure_node.get_width() * 12.0

    def _render(self) -> None:
        for widget in (self.content, self.ending_title, self.ending_body, self.credits):
            widget.hide()
        self.page_hint.hide()
        self.return_hint.hide()

        page = PAGES[self._page]
        self.page_title.show()
        if page == "stats":
            self.page_title.set_text(self.text_db.get("ui.graduation.page1_title"))
            stats = self._state_snapshot.get("stats", {})
            mood = self._state_snapshot.get("mood", 0)
            lines = []
            for key in theme.PANEL_STAT_KEYS:
                value = mood if key == "mood" else stats.get(key, 0)
                lines.append(f"{self.text_db.get_raw(theme.STAT_NAME_IDS[key])}  {value}")
            relationships = self._state_snapshot.get("relationships") or {}
            if relationships:
                lines.append("")
                for npc_id, value in relationships.items():
                    short = str(npc_id).removeprefix("npc_")
                    name = self.text_db.get_raw(f"npc.{short}.name")
                    lines.append(f"{name}  {int(value)}")
            self.content.set_lines(lines)
            self.content.show()
            self.page_hint.show()
        elif page == "review":
            self.page_title.set_text(self.text_db.get("ui.graduation.page2_title"))
            highlights: list[str] = []
            for entry in getattr(self._ending, "highlights", None) or []:
                line = self._highlight_line(entry)
                if line and line not in highlights:
                    highlights.append(line)
                if len(highlights) >= 10:
                    break
            if not highlights:
                highlights = [self.text_db.get("ui.graduation.no_highlight")]
            self.content.set_lines(highlights)
            self.content.show()
            self.page_hint.show()
        elif page == "ending":
            ending_id = getattr(self._ending, "ending_id", None) or "ending_mediocre"
            self.page_title.set_text(self.text_db.get("ui.graduation.page3_title"))
            self.ending_title.set_text(self.text_db.get(f"ending.{ending_id}.title"))
            self.ending_title.show()
            body = [self.text_db.get(f"ending.{ending_id}.body.{i}") for i in (1, 2, 3)]
            self.ending_body.set_lines(self._wrap_body(body))
            self.ending_body.show()
            self.page_hint.show()
        else:
            self.page_title.set_text(self.text_db.get("ui.graduation.page4_title"))
            self.credits.set_lines([
                self.text_db.get("ui.graduation.credits"),
                self.text_db.get("ui.graduation.credits_team"),
            ])
            self.credits.show()
            self.return_hint.show()

    # ------------------------------------------------------------------
    def on_space(self) -> None:
        if self._closed:
            # 最后一页连按两下：第一次已经隐藏并回主菜单（0.25 秒黑场期间
            # 本场景还在台上），第二次再调 on_back_to_menu 会把已经没有 state
            # 的流程推一遍 —— RuntimeError 崩溃。
            return
        if self._page < len(PAGES) - 1:
            self._page += 1
            self._render()
        else:
            self._closed = True
            self.hide()
            if self.on_back_to_menu:
                self.on_back_to_menu()

    def confirm(self) -> None:
        self.on_space()
