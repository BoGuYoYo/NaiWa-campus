"""毕业界面（D2）：全屏 0, 0, 480, 270，共 4 页。

1. 总评属性（5 属性 + 关系）；
2. 四年回顾（EndingResult.highlights，text_id 列表逐条显示）；
3. 结局标题与正文（ending.<id>.title / body.1~3）；
4. 制作人员与返回。
"""

from __future__ import annotations

import logging

from panda3d.core import CardMaker, TransparencyAttrib

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
        self.assets = asset_registry

        # 结局 CG 是 480×270 的整页背景。它只在第 3 页且资源存在时显示；
        # 资源缺失时继续使用原来的纯文字结局页，避免缺图把毕业流程卡死。
        self.ending_cg = self._make_card(root, transform, "graduation_ending_cg", 0, 0,
                                         theme.CANVAS_W, theme.CANVAS_H, bin_index=30)
        self.ending_cg_scrim = self._make_card(
            root, transform, "graduation_ending_cg_scrim", 0, 184,
            theme.CANVAS_W, 86, color=theme.hex_to_rgba(theme.HEX["panel"], 0.92),
            bin_index=31,
        )

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
        self.ending_cg.hide()
        self.ending_cg_scrim.hide()
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

    def _wrap_body(self, lines: list[str], limit: float | None = None,
                   max_lines: int = 5, line_height: float | None = None) -> list[str]:
        """按画布可用宽度折行；折出来的行数超过版面容量时压一下行距。

        正文从 x=60 起，右缘留 20px 边距，可用 480-60-20=400 逻辑像素。
        三行正文按 12px 字号、22px 行距排得下 3~5 行；更多行说明文案过长，
        继续缩行距会糊在一起，所以只在 92..240 的高度里平均分配。
        """
        width_limit = 480.0 - 60.0 - 20.0 if limit is None else float(limit)
        wrapped: list[str] = []
        for line in lines:
            wrapped.extend(theme.wrap_cjk(str(line), width_limit, self._measure))
        if len(wrapped) > max_lines:
            _log.warning("结局正文 %d 行，超过版面容量（%d 行），按 %d 行显示",
                         len(wrapped), max_lines, max_lines)
            wrapped = wrapped[:max_lines]
        resolved_line_height = 22.0 if line_height is None else float(line_height)
        if line_height is None and len(wrapped) > 3:
            # 92 起、到返回提示 244 之前：最多 152px 可用
            resolved_line_height = min(resolved_line_height, 150.0 / max(1, len(wrapped) - 1))
        self.ending_body._line_height = resolved_line_height
        self.ending_body.set_lines(wrapped)
        return wrapped

    @staticmethod
    def _ending_cg_asset_id(ending_id: str | None) -> str | None:
        """把结局规则 ID 映射为资源 ID。"""
        if not ending_id:
            return None
        short_id = str(ending_id).removeprefix("ending_")
        return f"cg_ending_{short_id}"

    def _make_card(
        self,
        parent,
        transform: UITransform,
        name: str,
        x: float,
        y: float,
        w: float,
        h: float,
        color=(1.0, 1.0, 1.0, 1.0),
        bin_index: int = 30,
    ):
        """创建一个按逻辑像素定位的整页/矩形卡片。"""
        maker = CardMaker(name)
        maker.set_frame(0, 1, -1, 0)
        node = parent.attach_new_node(maker.generate())
        node.set_color(*color)
        node.set_transparency(TransparencyAttrib.M_alpha)
        node.set_bin("fixed", bin_index)
        node.set_depth_test(False)
        node.set_depth_write(False)
        node.set_scale(transform.px(max(w, 0.001)), 1, transform.px(max(h, 0.001)))
        ax, ay = transform.to_aspect2d(x, y)
        node.set_pos(ax, 0, ay)
        return node

    def _move_label(self, label: UILabel, x: float, y: float) -> None:
        """移动单行标签的左上角（UILabel 的公共 API 只负责改字）。"""
        ax, ay = self.transform.to_aspect2d(x, y + label._size)
        label.text_node.set_pos(ax, 0, ay)

    def _set_body_layout(self, x: float, y: float, line_height: float) -> None:
        """更新结局正文的起点与行距，并同步已有行的节点位置。"""
        self.ending_body._x = float(x)
        self.ending_body._y = float(y)
        self.ending_body._line_height = float(line_height)
        for index, label in enumerate(self.ending_body.labels):
            ax, ay = self.transform.to_aspect2d(
                self.ending_body._x,
                self.ending_body._y + index * self.ending_body._line_height + label._size,
            )
            label.text_node.set_pos(ax, 0, ay)

    def _show_ending_cg(self, ending_id: str) -> bool:
        """加载并显示对应结局 CG；返回是否真的找到了资源。"""
        asset_id = self._ending_cg_asset_id(ending_id)
        if not asset_id or self.assets is None:
            return False

        # AssetRegistry.load_texture() 缺图时会返回品红占位图；先问 has_texture，
        # 这样结局页可以按设计回退纯文字，而不会把占位图当作正式 CG。
        checker = getattr(self.assets, "has_texture", None)
        if callable(checker):
            try:
                if not checker(asset_id):
                    return False
            except Exception:
                return False
        try:
            texture = self.assets.load_texture(asset_id)
        except Exception as exc:  # pragma: no cover - 引擎/文件损坏时的兜底
            _log.warning("结局 CG 加载失败 asset_id=%s: %s", asset_id, exc)
            return False
        if texture is None:
            return False

        self.ending_cg.set_texture(texture)
        self.ending_cg.set_color(1, 1, 1, 1)
        self.ending_cg.show()
        self.ending_cg_scrim.show()
        return True

    def _measure(self, text: str) -> float:
        self._measure_node.set_text(text)
        return self._measure_node.get_width() * 12.0

    def _render(self) -> None:
        for widget in (self.content, self.ending_title, self.ending_body, self.credits):
            widget.hide()
        self.page_hint.hide()
        self.return_hint.hide()
        self.ending_cg.hide()
        self.ending_cg_scrim.hide()
        self.panel.show()
        # 第 3 页可能会把标题/正文移入 CG 暗带；每次重绘先恢复默认
        # 位置，保证翻回其它页面或 CG 缺失回退时不继承上一种布局。
        self._move_label(self.page_title, 60, 26)
        self._move_label(self.ending_title, 60, 62)
        self._set_body_layout(60.0, 92.0, theme.LINE_HEIGHT)
        self._move_label(self.page_hint, 60, 244)

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
            if not highlights:
                highlights = [self.text_db.get("ui.graduation.no_highlight")]
            self.content.set_lines(highlights)
            self.content.show()
            self.page_hint.show()
        elif page == "ending":
            ending_id = getattr(self._ending, "ending_id", None) or "ending_mediocre"
            body = [self.text_db.get(f"ending.{ending_id}.body.{i}") for i in (1, 2, 3)]
            if self._show_ending_cg(ending_id):
                # CG 自带整页构图，底部暗带负责承载可读文字；页面标题不再压在
                # 画面上方，避免遮住角色和场景焦点。
                self.panel.hide()
                self.page_title.hide()
                self._move_label(self.ending_title, 16, 190)
                self.ending_title.set_text(self.text_db.get(f"ending.{ending_id}.title"))
                self.ending_title.show()
                # 暗带从 y=184 开始，标题与正文总共只留约 78px；
                # 统一折行并同步行距，保证三段正文不溢出画布。
                wrapped = self._wrap_body(body, limit=448.0, max_lines=4, line_height=14.0)
                self._set_body_layout(16.0, 210.0, 14.0)
                self.ending_body.set_lines(wrapped)
                self.ending_body.show()
                self._move_label(self.page_hint, 360, 190)
                self.page_hint.show()
            else:
                self.page_title.set_text(self.text_db.get("ui.graduation.page3_title"))
                self._move_label(self.ending_title, 60, 62)
                self.ending_title.set_text(self.text_db.get(f"ending.{ending_id}.title"))
                self.ending_title.show()
                self._set_body_layout(60.0, 92.0, theme.LINE_HEIGHT)
                self.ending_body.set_lines(self._wrap_body(body))
                self.ending_body.show()
                self._move_label(self.page_hint, 60, 244)
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
