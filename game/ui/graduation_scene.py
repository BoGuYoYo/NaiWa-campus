"""毕业界面（D2）：全屏 0, 0, 480, 270，共 4 页。

1. 总评属性（5 属性 + 关系）；
2. 四年回顾（EndingResult.highlights，text_id 列表逐条显示）；
3. 结局标题与正文（ending.<id>.title / body.1~3）；
4. 制作人员与返回。
"""

from __future__ import annotations

from game.ui import theme
from game.ui.widgets import UILabel, MultilineLabel, UIPanel, UITransform, UIWidget

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
        self.on_back_to_menu = None
        super().__init__(root)
        self.hide()

    # ------------------------------------------------------------------
    def open(self, ending_result, state_snapshot: dict | None = None) -> None:
        """ending_result: EndingResult；state_snapshot: 毕业时的总评数据。"""
        self._ending = ending_result
        self._state_snapshot = state_snapshot or {}
        self._page = 0
        self.show()
        self._render()

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
            self.content.set_lines(lines)
            self.content.show()
            self.page_hint.show()
        elif page == "review":
            self.page_title.set_text(self.text_db.get("ui.graduation.page2_title"))
            highlights = [
                self.text_db.get_raw(tid) for tid in (getattr(self._ending, "highlights", None) or [])[:10]
            ]
            if not highlights:
                highlights = [self.text_db.get("ui.graduation.credits")]
            self.content.set_lines(highlights)
            self.content.show()
            self.page_hint.show()
        elif page == "ending":
            ending_id = getattr(self._ending, "ending_id", None) or "ending_balanced"
            self.page_title.set_text(self.text_db.get("ui.graduation.page3_title"))
            self.ending_title.set_text(self.text_db.get(f"ending.{ending_id}.title"))
            self.ending_title.show()
            body = [self.text_db.get(f"ending.{ending_id}.body.{i}") for i in (1, 2, 3)]
            self.ending_body.set_lines(body)
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
        if self._page < len(PAGES) - 1:
            self._page += 1
            self._render()
        else:
            self.hide()
            if self.on_back_to_menu:
                self.on_back_to_menu()

    def confirm(self) -> None:
        self.on_space()
