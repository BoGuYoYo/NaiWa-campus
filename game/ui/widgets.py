"""基础 UI 控件（D1/D9 第 1 周）：面板、按钮、列表、条、图标。

- 所有控件使用 480×270 逻辑像素坐标（原点左上），通过
  UITransform 换算到 aspect2d；
- **文本按「左上角」定位**：字号 12 时文字占 y .. y+12，避免所有标题
  上溢到面板边框外（旧版按基线定位，每个标题都高出一行）；
- 面板统一使用 ui_panel_9slice 资源（AssetRegistry），缺资源时
  退化为纯色面板并记录 asset.missing；
- 数值条使用 ui_bar_frame / ui_bar_fill，图标使用 ui_icon_*；
- 本模块依赖 panda3d，独立测试只 import theme / text_db。
"""

from __future__ import annotations

import logging
from typing import Callable, Iterable

from panda3d.core import CardMaker, NodePath, TextFont, TextNode, TransparencyAttrib

from game.ui import theme

_log = logging.getLogger("naiwa.ui.widgets")

#: 正文字号（12px 逻辑像素 → 逻辑画布单位）
FONT_SIZE_BODY = 12.0
FONT_SIZE_TITLE = 24.0
FONT_LINE_HEIGHT = 16.0

#: 由 A 的 AssetRegistry 注入的默认字体（缺字体时保持 None，用引擎默认字体）
_default_font: TextFont | None = None


def set_default_font(font: "TextFont | None") -> None:
    """由集成层在启动时调用；所有 UILabel 共用这个字体。"""
    global _default_font
    _default_font = font


def default_font() -> "TextFont | None":
    return _default_font


class UITransform:
    """逻辑画布坐标 -> aspect2d 坐标。

    scale 与 A 的 render_pipeline 使用同一系数（480×270 → 窗口）。
    """

    def __init__(self, scale: float, window_w: int, window_h: int) -> None:
        self.scale = scale
        self.window_w = window_w
        self.window_h = window_h

    @classmethod
    def from_base(cls, base) -> "UITransform":
        # 离屏时 base.win 是 GraphicsBuffer（没有 get_properties），只能用 getXSize
        w = int(base.win.get_x_size())
        h = int(base.win.get_y_size())
        return cls(scale=w / theme.CANVAS_W, window_w=w, window_h=h)

    def to_aspect2d(self, x: float, y: float) -> tuple[float, float]:
        return theme.ui_px(x, y, self.scale, self.window_w, self.window_h)

    def px(self, logical_px: float) -> float:
        """逻辑像素尺寸 -> aspect2d 单位（垂直方向）。"""
        return logical_px * self.scale / (self.window_h / 2)


class UIWidget:
    """控件基类：统一管理节点显隐与销毁。

    约定：每个界面自己建一个容器节点，**所有子控件都挂在容器下**，
    这样 hide()/destroy() 能一次收干净（旧版把子控件挂在公共 parent 上，
    关闭界面后文字会留在屏幕上）。
    """

    def __init__(self, root: "NodePath | None") -> None:
        self.root = root
        self.visible = root is not None

    def show(self) -> None:
        if self.root is not None:
            self.root.show()
        self.visible = True

    def hide(self) -> None:
        if self.root is not None:
            self.root.hide()
        self.visible = False

    def is_shown(self) -> bool:
        return self.root is not None and not self.root.is_hidden()

    def destroy(self) -> None:
        if self.root is not None:
            self.root.remove_node()
            self.root = None
        self.visible = False


class UILabel(UIWidget):
    """单行文本；以「左上角」为锚点，行高由字号决定。"""

    def __init__(
        self,
        parent: NodePath,
        transform: UITransform,
        x: float,
        y: float,
        text: str,
        size: float = FONT_SIZE_BODY,
        color=theme.COLOR_TEXT,
        align: int = TextNode.A_left,
        shadow: bool = True,
        font: "TextFont | None" = None,
    ) -> None:
        self.transform = transform
        self._color = color
        self._size = size
        self.node = TextNode("ui_label")
        self.node.set_align(align)
        self.node.set_text_color(*color)
        self.node.set_text(text)
        chosen = font if font is not None else _default_font
        if chosen is not None:
            self.node.set_font(chosen)
        if shadow:
            self.node.set_shadow_color(0, 0, 0, 0.8)
            self.node.set_shadow(0.04, 0.04)
        self.text_node = parent.attach_new_node(self.node)
        self.text_node.set_scale(self.transform.px(size))
        # 文字占 y .. y+size，故基线落在 y+size
        ax, ay = transform.to_aspect2d(x, y + size)
        self.text_node.set_pos(ax, 0, ay)
        super().__init__(self.text_node)

    def set_text(self, text: str) -> None:
        self.node.set_text(text)

    def get_text(self) -> str:
        return self.node.get_text()

    def set_color(self, color) -> None:
        self._color = color
        self.node.set_text_color(*color)


class MultilineLabel(UIWidget):
    """多行文本；**可以按需增行**（旧版只能改已有行，导致正文永远空白）。"""

    def __init__(
        self,
        parent: NodePath,
        transform: UITransform,
        x: float,
        y: float,
        lines: "list[str] | None" = None,
        size: float = FONT_SIZE_BODY,
        color=theme.COLOR_TEXT,
        line_height: float = theme.LINE_HEIGHT,
    ) -> None:
        self.transform = transform
        self._x = x
        self._y = y
        self._size = size
        self._color = color
        self._line_height = line_height
        self.container = parent.attach_new_node("ui_multiline")
        self.labels: list[UILabel] = []
        super().__init__(self.container)
        if lines:
            self.set_lines(lines)

    def set_lines(self, lines: "Iterable[str]") -> None:
        wanted = list(lines)
        while len(self.labels) < len(wanted):
            index = len(self.labels)
            label = UILabel(
                self.container,
                self.transform,
                self._x,
                self._y + index * self._line_height,
                "",
                size=self._size,
                color=self._color,
            )
            self.labels.append(label)
        for i, label in enumerate(self.labels):
            if i < len(wanted):
                label.set_text(wanted[i])
                label.show()
            else:
                label.set_text("")
                label.hide()

    def set_color(self, color) -> None:
        self._color = color
        for label in self.labels:
            label.set_color(color)

    def destroy(self) -> None:
        self.labels = []
        super().destroy()


class UIPanel(UIWidget):
    """9-slice 面板；assets 缺失时退化为纯色卡。"""

    def __init__(
        self,
        parent: NodePath,
        transform: UITransform,
        rect: tuple[int, int, int, int],
        asset_registry=None,
        alpha: float = theme.PANEL_ALPHA,
    ) -> None:
        x, y, w, h = rect
        node = parent.attach_new_node("ui_panel")
        ax, ay = transform.to_aspect2d(x, y)
        node.set_pos(ax, 0, ay)
        tex = None
        if asset_registry is not None:
            try:
                tex = asset_registry.load_texture("ui_panel_9slice")
            except Exception:
                tex = None
        cm = CardMaker("panel_card")
        cm.set_frame(0, 1, -1, 0)
        card = node.attach_new_node(cm.generate())
        if tex is not None:
            # 占位皮肤的中心是浅灰，直接贴上去会把白字洗掉；先着色压暗，
            # 再盖一层内衬，让文字区的底色均匀（9-slice 的边框仍然保留）。
            card.set_texture(tex)
            card.set_color(*theme.PANEL_TINT)
        else:
            _log.warning("asset.missing asset_id=ui_panel_9slice（使用纯色面板）")
            card.set_color(*theme.PANEL_TINT)
        card.set_transparency(TransparencyAttrib.M_alpha)
        card.set_scale(transform.px(w), 1, transform.px(h))
        # 显式指定透明层的绘制顺序：外壳(40) → 内衬(41) → 文本(default bin 之后)
        card.set_bin("fixed", 40)
        card.set_depth_test(False)
        card.set_depth_write(False)
        if tex is not None:
            inset = min(3, max(1, min(w, h) // 8))
            inner_maker = CardMaker("panel_inner")
            inner_maker.set_frame(0, 1, -1, 0)
            inner = node.attach_new_node(inner_maker.generate())
            inner.set_color(*theme.PANEL_SOLID)
            inner.set_transparency(TransparencyAttrib.M_alpha)
            inner.set_bin("fixed", 41)
            inner.set_depth_test(False)
            inner.set_depth_write(False)
            inner.set_scale(
                transform.px(max(1, w - inset * 2)), 1, transform.px(max(1, h - inset * 2))
            )
            ix, iy = transform.to_aspect2d(x + inset, y + inset)
            inner.set_pos(ix - ax, 0, iy - ay)
            self.inner = inner
        self.card = card
        self.rect = rect
        super().__init__(node)


class UIIcon(UIWidget):
    """16×16 图标（ui_icon_* / ui_key_*）；缺资源时用纯色小块占位。"""

    def __init__(
        self,
        parent: NodePath,
        transform: UITransform,
        x: float,
        y: float,
        asset_id: str,
        size: float = 16.0,
        asset_registry=None,
        fallback_color=(0.55, 0.58, 0.64, 1.0),
    ) -> None:
        cm = CardMaker("ui_icon")
        cm.set_frame(0, 1, -1, 0)
        node = parent.attach_new_node(cm.generate())
        tex = None
        if asset_registry is not None:
            try:
                tex = asset_registry.load_texture(asset_id)
            except Exception:
                tex = None
        if tex is not None:
            node.set_texture(tex)
            node.set_color(1, 1, 1, 1)
        else:
            node.set_color(*fallback_color)
        node.set_transparency(TransparencyAttrib.M_alpha)
        node.set_scale(transform.px(size), 1, transform.px(size))
        ax, ay = transform.to_aspect2d(x, y)
        node.set_pos(ax, 0, ay)
        self.asset_id = asset_id
        super().__init__(node)


class StatBar(UIWidget):
    """数值条：背景 + 前景填充。

    条总宽 100 逻辑像素（HUD 规定），按 0..100 归一。
    """

    BAR_WIDTH = 100.0
    BAR_HEIGHT = 8.0

    def __init__(
        self,
        parent: NodePath,
        transform: UITransform,
        x: float,
        y: float,
        fill_color=theme.COLOR_GAIN,
        asset_registry=None,
    ) -> None:
        self.transform = transform
        self._fill_color = fill_color
        self._x = x
        self._y = y
        self._registry = asset_registry
        self.container = parent.attach_new_node("statbar")
        self.back = self._make_card(
            self.container, x, y, self.BAR_WIDTH, self.BAR_HEIGHT,
            theme.hex_to_rgba("#000000", 0.55), "ui_bar_frame", asset_registry,
        )
        self.fill = self._make_card(
            self.container, x, y, self.BAR_WIDTH, self.BAR_HEIGHT, fill_color,
            "ui_bar_fill", asset_registry,
        )
        super().__init__(self.container)

    def _make_card(self, parent, x, y, w, h, color, asset_id=None, registry=None) -> NodePath:
        cm = CardMaker("statbar_piece")
        cm.set_frame(0, 1, -1, 0)
        card = parent.attach_new_node(cm.generate())
        card.set_color(*color)
        tex = None
        if registry is not None and asset_id is not None:
            try:
                tex = registry.load_texture(asset_id)
            except Exception:
                tex = None
        if tex is not None:
            card.set_texture(tex)
        card.set_transparency(TransparencyAttrib.M_alpha)
        ax, ay = self.transform.to_aspect2d(x, y)
        card.set_pos(ax, 0, ay)
        card.set_scale(max(self.transform.px(max(w, 0.001)), 0.0001), 1, self.transform.px(h))
        return card

    def set_value(self, value: float, maximum: float = 100.0) -> None:
        ratio = 0.0 if maximum <= 0 else max(0.0, min(1.0, value / maximum))
        width = self.BAR_WIDTH * ratio
        self.fill.remove_node()
        self.fill = self._make_card(
            self.container, self._x, self._y, width, self.BAR_HEIGHT,
            self._fill_color, "ui_bar_fill", self._registry,
        )

    def set_color(self, color) -> None:
        self._fill_color = color
        self.fill.set_color(*color)


class MenuList(UIWidget):
    """纵向菜单列表（主菜单 / 暂停 / 事件选项共用）。

    entries: [(text, enabled)]；锁定项灰色、不可选。
    """

    def __init__(
        self,
        parent: NodePath,
        transform: UITransform,
        x: float,
        y: float,
        entries: list[tuple[str, bool]],
        item_height: float = 20.0,
        on_confirm: "Callable[[int], None] | None" = None,
        cursor_text_id: str = ">",
    ) -> None:
        self.transform = transform
        self.on_confirm = on_confirm
        self.item_height = item_height
        self._x = x
        self._y = y
        self.container = parent.attach_new_node("menu_list")
        self.labels: list[UILabel] = []
        self.cursor = UILabel(self.container, transform, x, y + 2, cursor_text_id,
                              color=theme.COLOR_CURSOR)
        self.index = 0
        self._entries = list(entries)
        super().__init__(self.container)
        self.refresh_colors()

    def refresh_colors(self) -> None:
        while len(self.labels) < len(self._entries):
            i = len(self.labels)
            self.labels.append(
                UILabel(self.container, self.transform, self._x + 10,
                        self._y + i * self.item_height + 2, "")
            )
        for i, (text, enabled) in enumerate(self._entries):
            self.labels[i].set_text(text)
            self.labels[i].set_color(theme.COLOR_TEXT if enabled else theme.COLOR_DISABLED)
            self.labels[i].show()
        for i in range(len(self._entries), len(self.labels)):
            self.labels[i].hide()

    def move(self, direction: int) -> None:
        n = len(self._entries)
        if n == 0:
            return
        for _ in range(n):
            self.index = (self.index + direction) % n
            if self._entries[self.index][1]:
                break
        self.refresh_colors()

    def confirm(self) -> int:
        if self._entries and self._entries[self.index][1] and self.on_confirm:
            self.on_confirm(self.index)
        return self.index

    def set_entries(self, entries: list[tuple[str, bool]]) -> None:
        self._entries = list(entries)
        self.index = 0
        self.refresh_colors()

    def show_cursor(self, show: bool) -> None:
        (self.cursor.show if show else self.cursor.hide)()
