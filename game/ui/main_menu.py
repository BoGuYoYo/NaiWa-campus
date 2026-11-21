"""主菜单（D2）：列表 180, 150, 120, 90。

新游戏 / 继续（无 autosave 时置灰）/ 读档 / 设置 / 退出。
"""

from __future__ import annotations

from typing import Callable

from game.ui import theme
from game.ui.widgets import UILabel, UIPanel, UITransform, UIWidget

ITEM_HEIGHT = 16

ITEMS = (
    ("ui.menu.new_game", "new_game"),
    ("ui.menu.continue", "continue"),
    ("ui.menu.load", "load"),
    ("ui.menu.settings", "settings"),
    ("ui.menu.quit", "quit"),
)


class MainMenu(UIWidget):
    def __init__(self, parent, transform: UITransform, text_db, asset_registry=None) -> None:
        self.text_db = text_db
        self.transform = transform
        root = parent.attach_new_node("main_menu")
        # 背景封面铺满 480×270 画布。面板用 fixed bin 40/41，背景必须压在它们
        # 下面（bin 30），否则半透明的面板内衬会把图糊掉。
        self.background = self._make_background(root, transform, asset_registry)
        self.panel = UIPanel(root, transform, theme.RECTS["main_menu"], asset_registry)
        rect = theme.RECTS["main_menu"]
        x, y = rect[0], rect[1]

        # 有封面时标题顶到画面上沿单独占一条，避免压在角色脸上；
        # 没有封面时保持旧的左侧布局（纯色背景上下都空）。
        title_x = 24 if self._has_cover else 90
        title_y = 18 if self._has_cover else 40
        self.title = UILabel(
            root, transform, title_x, title_y, text_db.get("ui.main_menu.title"),
            size=theme.TITLE_SIZE, color=theme.COLOR_TEXT,
        )
        self.subtitle = UILabel(
            root, transform, title_x, title_y + 36, text_db.get("ui.main_menu.subtitle"),
            color=theme.COLOR_SECONDARY,
        )

        self.enabled = {key: True for _tid, key in ITEMS}
        self.labels: list[UILabel] = []
        for i, (text_id, _key) in enumerate(ITEMS):
            self.labels.append(UILabel(root, transform, x + 18, y + 5 + i * ITEM_HEIGHT, text_db.get_raw(text_id)))
        self.cursor = UILabel(root, transform, x + 8, y + 5, ">", color=theme.COLOR_CURSOR)

        self.save_manager = None
        self.handlers: dict[str, Callable[[], None]] = {}
        self.index = 0
        super().__init__(root)
        self.refresh()

    # ------------------------------------------------------------------
    def _make_background(self, root, transform: UITransform, asset_registry):
        """整张封面图铺满画布；素材缺失时退回纯色，不挡菜单。"""
        from panda3d.core import CardMaker, TransparencyAttrib

        maker = CardMaker("main_menu_bg")
        maker.set_frame(0, 1, -1, 0)
        node = root.attach_new_node(maker.generate())
        node.set_bin("fixed", 30)
        node.set_depth_test(False)
        node.set_depth_write(False)
        node.set_transparency(TransparencyAttrib.M_alpha)
        texture = None
        available = False
        if asset_registry is not None:
            # 必须先问 has_texture：load_texture 对缺失资源返回品红占位图，
            # 直接判 `texture is not None` 会把占位图当封面，整屏洋红棋盘。
            checker = getattr(asset_registry, "has_texture", None)
            available = bool(checker("ui_menu_bg")) if callable(checker) else True
            if available:
                try:
                    texture = asset_registry.load_texture("ui_menu_bg")
                except Exception:
                    texture = None
                    available = False
        self._has_cover = available and texture is not None
        if self._has_cover:
            node.set_texture(texture)
            node.set_color(1, 1, 1, 1)
            # 封面是浅色插画，白字直接压上去完全看不清。整张压暗一档，
            # 让标题与菜单保持可读，又不至于把角色糊成黑块。
            self._make_scrim(root, transform)
        else:
            node.set_color(*theme.PANEL_TINT)
        # CardMaker 本地坐标是 x 0..1、z -1..0（底边在 -1，顶边在 0）。
        # 直接按"左上角"定位会把整张图往下多画一倍；用画布两个角算出
        # 实际宽度/高度，再把本地顶边（z=0）对齐到画布上沿。
        ax0, ay0 = transform.to_aspect2d(0, 0)
        ax1, ay1 = transform.to_aspect2d(theme.CANVAS_W, theme.CANVAS_H)
        node.set_scale(ax1 - ax0, 1, ay0 - ay1)
        node.set_pos(ax0, 0, ay0)
        # 背景不参与 hide()/destroy() 之外的交互，但仍挂在 root 下统一回收
        self._background_node = node
        return node

    def _make_scrim(self, root, transform: UITransform) -> None:
        """在封面之上、菜单之下加一层半透明黑，保证文字对比度。"""
        from panda3d.core import CardMaker, TransparencyAttrib

        maker = CardMaker("main_menu_scrim")
        maker.set_frame(0, 1, -1, 0)
        node = root.attach_new_node(maker.generate())
        node.set_bin("fixed", 31)
        node.set_depth_test(False)
        node.set_depth_write(False)
        node.set_transparency(TransparencyAttrib.M_alpha)
        node.set_color(0.06, 0.07, 0.10, 0.55)
        ax0, ay0 = transform.to_aspect2d(0, 0)
        ax1, ay1 = transform.to_aspect2d(theme.CANVAS_W, theme.CANVAS_H)
        node.set_scale(ax1 - ax0, 1, ay0 - ay1)
        node.set_pos(ax0, 0, ay0)
        self._scrim_node = node

    def attach_save_manager(self, save_manager) -> None:
        self.save_manager = save_manager
        self.refresh()

    def _has_autosave(self) -> bool:
        """只在自动存档"确实能读"时点亮「继续」。

        以前只判文件存在：v1 存档在 v2 客户端里继续按钮亮着，按下去
        什么也没发生（load 抛 E_SAVE_VERSION 只写日志）。
        """
        return self._autosave_state() == "ok"

    def _autosave_state(self) -> str:
        """none = 没有存档；ok = 可读；incompatible = 有文件但版本不支持。"""
        if self.save_manager is None:
            return "none"
        try:
            if self.save_manager.peek("autosave"):
                return "ok"
        except Exception:
            return "none"
        try:
            return "incompatible" if self.save_manager.exists("autosave") else "none"
        except Exception:
            return "none"

    def refresh(self) -> None:
        state = self._autosave_state()
        self.enabled["continue"] = state == "ok"
        for i, (text_id, key) in enumerate(ITEMS):
            enabled = self.enabled[key]
            if enabled:
                self.labels[i].set_text(self.text_db.get_raw(text_id))
            elif key == "continue" and state == "incompatible":
                # 单独标出来：玩家上一版的存档还在，但这一版打不开。
                self.labels[i].set_text(
                    f"{self.text_db.get_raw(text_id)}"
                    f"（{self.text_db.get('ui.menu.reason.incompatible_save')}）"
                )
            else:
                self.labels[i].set_text(
                    f"{self.text_db.get_raw(text_id)}"
                    f"（{self.text_db.get('ui.menu.reason.no_save_short')}）"
                )
            self.labels[i].set_color(theme.COLOR_TEXT if enabled else theme.COLOR_DISABLED)
        if not self.enabled[ITEMS[self.index][1]]:
            self.index = 0
        ax, ay = self.transform.to_aspect2d(
            theme.RECTS["main_menu"][0] + 8, theme.RECTS["main_menu"][1] + 5 + self.index * ITEM_HEIGHT + 12
        )
        self.cursor.root.set_pos(ax, 0, ay)

    def show(self) -> None:
        super().show()
        self.refresh()

    def move(self, direction: int) -> None:
        n = len(ITEMS)
        for _ in range(n):
            self.index = (self.index + direction) % n
            if self.enabled[ITEMS[self.index][1]]:
                break
        self.refresh()

    def confirm(self) -> str | None:
        text_id, key = ITEMS[self.index]
        if not self.enabled[key]:
            return None
        handler = self.handlers.get(key)
        if handler:
            handler()
        return key
