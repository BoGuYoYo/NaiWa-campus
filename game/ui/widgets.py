"""基础 UI 控件（D1/D9 第 1 周）：面板、按钮、列表、条、图标。

- 所有控件使用 480×270 逻辑像素坐标（原点左上），通过
  UITransform 换算到 aspect2d；
- **文本按「左上角」定位**：字号 12 时文字占 y .. y+12，避免所有标题
  上溢到面板边框外（旧版按基线定位，每个标题都高出一行）；
- 面板走**真九宫格**（ui_panel_9slice 切 9 块分别摆放），缺资源时
  退化为纯色面板并记录 asset.missing；
- 数值条使用 ui_bar_frame / ui_bar_fill，图标使用 ui_icon_*；
- 本模块依赖 panda3d，独立测试只 import theme / text_db。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Iterable

from panda3d.core import (
    CardMaker,
    NodePath,
    Point2,
    TextFont,
    TextNode,
    TransparencyAttrib,
)

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
        #: 画布在窗口里的居中偏移（窗口不是 16:9 时用来补边，见 theme.canvas_offset）
        self.offset_x, self.offset_y = theme.canvas_offset(scale, window_w, window_h)

    @classmethod
    def from_base(cls, base) -> "UITransform":
        # 离屏时 base.win 是 GraphicsBuffer（没有 get_properties），只能用 getXSize
        w = int(base.win.get_x_size())
        h = int(base.win.get_y_size())
        return cls(scale=w / theme.CANVAS_W, window_w=w, window_h=h)

    def to_aspect2d(self, x: float, y: float) -> tuple[float, float]:
        return theme.ui_px(
            x, y, self.scale, self.window_w, self.window_h, self.offset_x, self.offset_y
        )

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


# ----------------------------------------------------------------------
# 九宫格皮肤几何
# ----------------------------------------------------------------------
#: 面板边框着色：皮肤本身是「奶油底 + 金边」的横幅，原色直接贴会白得刺眼。
#: 压到 0.72 后金边仍清楚、奶油底色偏暖白，正好当描边；内部另外用
#: theme.PANEL_SOLID 兜底，所以正文/图标的对比度不受皮肤影响。
PANEL_FRAME_TINT = (0.72, 0.72, 0.74, 1.0)

#: 四角切边占皮肤内容框的比例（用比例而不是写死像素，换皮后自动跟着变）
_CUT_RATIO_X = 0.17
_CUT_RATIO_Y = 0.24
_CUT_MAX = 16

#: (路径, mtime) -> (内容框, 切边, 文件尺寸)；皮肤换了文件会自动失效
_skin_cache: dict[
    tuple[str, int], tuple[tuple[int, int, int, int], tuple[int, int], tuple[int, int]]
] = {}


def _as_filename(path: Path):
    from panda3d.core import Filename

    maker = getattr(Filename, "from_os_specific", None) or Filename.fromOsSpecific
    return maker(str(path))


def _alpha_content_box(image) -> tuple[int, int, int, int]:
    """皮肤里 alpha>0 的像素范围（左上原点，(x, y, w, h)）。"""
    width, height = image.get_x_size(), image.get_y_size()
    x0, y0, x1, y1 = width, height, 0, 0
    for y in range(height):
        for x in range(width):
            if image.get_alpha(x, y) > 0.0:
                x0 = min(x0, x)
                x1 = max(x1, x + 1)
                y0 = min(y0, y)
                y1 = max(y1, y + 1)
    if x1 <= x0 or y1 <= y0:
        return (0, 0, width, height)
    return (x0, y0, x1 - x0, y1 - y0)


def _clamp_cut(value: float, span: int) -> int:
    """切边限制在 1..16，并保证中间至少留 1px 可拉伸区。"""
    cut = max(1, min(int(round(value)), _CUT_MAX))
    while cut > 1 and span - 2 * cut < 1:
        cut -= 1
    return cut


def _panel_geometry(
    path: "Path | None", texture
) -> tuple[tuple[int, int, int, int], tuple[int, int], tuple[int, int]]:
    """算出皮肤的 (内容框, 切边, 文件尺寸)，单位都是源图像素。

    皮肤 png 常带一圈全透明留白（我们现在这张 48×48 的面板，真实画面只占
    中间 26 行），按整张图切会把透明留白当成边框，等于白切；所以先用 alpha
    求内容框，再按比例定四角切边。

    归一化一律用**文件尺寸**而不是 texture.getXSize()：引擎可能把纹理重采样成
    2 的幂（textures-power-2 默认 down），此时内容框与贴图尺寸对不上，
    用文件尺寸算出来的 uv 比例反而仍然正确。
    """
    width = texture.get_x_size() if texture is not None else 48
    height = texture.get_y_size() if texture is not None else 48
    size = (width, height)
    box = (0, 0, width, height)
    if path is not None:
        try:
            key = (str(path), int(path.stat().st_mtime))
            cached = _skin_cache.get(key)
            if cached is None:
                from panda3d.core import PNMImage

                image = PNMImage()
                if image.read(_as_filename(path)):
                    size = (image.get_x_size(), image.get_y_size())
                    box = _alpha_content_box(image)
                _skin_cache[key] = (box, (0, 0), size)
                cached = _skin_cache[key]
            box = cached[0]
            size = cached[2]
        except Exception as exc:  # 读不到就按整张图切，绝不能因此起不来
            _log.debug("panel skin geometry fallback（%s: %s）", type(exc).__name__, exc)
    cut = (_clamp_cut(box[2] * _CUT_RATIO_X, box[2]), _clamp_cut(box[3] * _CUT_RATIO_Y, box[3]))
    return box, cut, size


def _slice_cells(box, cut) -> list[tuple[int, int, tuple[int, int, int, int]]]:
    """把内容框切成 9 块，返回 [(col, row, (x, y, w, h))]，跳过零尺寸块。"""
    bx, by, bw, bh = box
    cx, cy = cut
    xs = ((bx, cx), (bx + cx, bw - 2 * cx), (bx + bw - cx, cx))
    ys = ((by, cy), (by + cy, bh - 2 * cy), (by + bh - cy, cy))
    cells: list[tuple[int, int, tuple[int, int, int, int]]] = []
    for row, (sy, sh) in enumerate(ys):
        for col, (sx, sw) in enumerate(xs):
            if sw > 0 and sh > 0:
                cells.append((col, row, (sx, sy, sw, sh)))
    return cells


class UIPanel(UIWidget):
    """真九宫格面板；皮肤缺失时退化为纯色卡。

    旧实现把整张 48×48 皮肤拉伸铺满矩形，再用 3px 内衬盖住中间，结果小面板
    （HUD 156×36）的金边被拉成一片拖影。现在按源图切成 9 块分别摆放：

    - 角块按源图 1:1 摆，金饰不变形；
    - 边块只沿一个方向拉伸（顶/底横向、左/右纵向）；
    - 中心块不贴皮肤，直接铺 theme.PANEL_SOLID，白字和图标对比度可控。
    """

    def __init__(
        self,
        parent: NodePath,
        transform: UITransform,
        rect: tuple[int, int, int, int],
        asset_registry=None,
        alpha: float = theme.PANEL_ALPHA,
        border: "float | tuple[float, float] | None" = None,
    ) -> None:
        x, y, w, h = rect
        self.transform = transform
        self.rect = rect
        node = parent.attach_new_node("ui_panel")
        ax, ay = transform.to_aspect2d(x, y)
        node.set_pos(ax, 0, ay)
        # 子卡片都按「面板左上角」为原点摆放，这里记下它的 aspect2d 坐标
        self._origin = (ax, ay)
        texture = None
        path = None
        if asset_registry is not None:
            try:
                texture = asset_registry.load_texture("ui_panel_9slice")
            except Exception as exc:
                _log.debug("ui_panel_9slice 读取失败（%s: %s）", type(exc).__name__, exc)
                texture = None
            if texture is not None:
                # 测试夹具的假 registry 没有 resolve_path，取不到就按贴图尺寸切
                try:
                    path = asset_registry.resolve_path("ui_panel_9slice")
                except Exception:
                    path = None
        box, cut, source_size = _panel_geometry(path, texture)
        # 边框默认按皮肤切边 1:1 摆；窄面板（HUD 36 高）传 border= 收窄，
        # 但两侧合计不能吃掉面板：最多占短边 34%
        if border is None:
            border_x, border_y = float(cut[0]), float(cut[1])
        elif isinstance(border, (int, float)):
            border_x = border_y = float(border)
        else:
            border_x, border_y = float(border[0]), float(border[1])
        border_x = min(border_x, max(1.0, w * 0.34))
        border_y = min(border_y, max(1.0, h * 0.34))
        self.border = (border_x, border_y)
        self.pieces: list[NodePath] = []
        self.card = None  # 旧版整张拉伸的底板；现在只有缺皮肤时才有
        if texture is None:
            _log.warning("asset.missing asset_id=ui_panel_9slice（使用纯色面板）")
            card = self._make_card(node, transform, x, y, w, h, theme.PANEL_TINT, bin_index=40)
            self.card = card
        else:
            self._build_frame(node, texture, source_size, box, cut, x, y, w, h, border_x, border_y)
        inner_w = max(1.0, w - 2 * border_x) if texture is not None else float(w)
        inner_h = max(1.0, h - 2 * border_y) if texture is not None else float(h)
        inner_x = x + (border_x if texture is not None else 0)
        inner_y = y + (border_y if texture is not None else 0)
        # 显式指定透明层的绘制顺序：边框(40) → 内衬(41) → 文本(default bin 之后)
        self.inner = self._make_card(
            node, transform, inner_x, inner_y, inner_w, inner_h, theme.PANEL_SOLID, bin_index=41
        )
        super().__init__(node)

    # ------------------------------------------------------------------ #
    # 构造
    # ------------------------------------------------------------------ #
    def _make_card(
        self, parent: NodePath, transform: UITransform, x: float, y: float,
        w: float, h: float, color, bin_index: int,
    ) -> NodePath:
        maker = CardMaker("panel_card")
        maker.set_frame(0, 1, -1, 0)
        card = parent.attach_new_node(maker.generate())
        card.set_color(*color)
        card.set_transparency(TransparencyAttrib.M_alpha)
        card.set_bin("fixed", bin_index)
        card.set_depth_test(False)
        card.set_depth_write(False)
        card.set_scale(transform.px(max(w, 0.001)), 1, transform.px(max(h, 0.001)))
        px_x, px_y = transform.to_aspect2d(x, y)
        card.set_pos(px_x - self._origin[0], 0, px_y - self._origin[1])
        return card

    def _build_frame(
        self, node: NodePath, texture, source_size: tuple[int, int],
        box, cut, x: float, y: float, w: float, h: float,
        border_x: float, border_y: float,
    ) -> None:
        widths = (border_x, max(1.0, w - 2 * border_x), border_x)
        heights = (border_y, max(1.0, h - 2 * border_y), border_y)
        tex_w = float(source_size[0])
        tex_h = float(source_size[1])
        for col, row, (sx, sy, sw, sh) in _slice_cells(box, cut):
            if col == 1 and row == 1:
                continue  # 中心交给 PANEL_SOLID
            maker = CardMaker("panel_piece")
            maker.set_frame(0, 1, -1, 0)
            # 图像行号自上而下，纹理 v 自下而上，所以 v 要翻过来
            maker.set_uv_range(
                Point2(sx / tex_w, 1.0 - (sy + sh) / tex_h),
                Point2((sx + sw) / tex_w, 1.0 - sy / tex_h),
            )
            piece = node.attach_new_node(maker.generate())
            piece.set_texture(texture)
            piece.set_color(*PANEL_FRAME_TINT)
            piece.set_transparency(TransparencyAttrib.M_alpha)
            piece.set_bin("fixed", 40)
            piece.set_depth_test(False)
            piece.set_depth_write(False)
            piece.set_scale(
                self.transform.px(widths[col]), 1, self.transform.px(heights[row])
            )
            dest_x = x + (0.0 if col == 0 else (border_x if col == 1 else w - border_x))
            dest_y = y + (0.0 if row == 0 else (border_y if row == 1 else h - border_y))
            px_x, px_y = self.transform.to_aspect2d(dest_x, dest_y)
            piece.set_pos(px_x - self._origin[0], 0, px_y - self._origin[1])
            self.pieces.append(piece)


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
