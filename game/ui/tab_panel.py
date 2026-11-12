"""Tab 状态面板（D2）：主体 40, 24, 400, 222。

- 左侧：5 条属性（学业 / 体力 / 社交 / 兴趣 / 心情）+ 精力上限；
- 右侧：3 名 NPC 关系（没见过的 NPC 显示 ？？？）+ 本学期剩余天数；
- Tab 开关；对话/事件期间无效（由集成层按 phase 判断）。
"""

from __future__ import annotations

from game.ui import theme
from game.ui.widgets import UILabel, StatBar, UIIcon, UIPanel, UITransform, UIWidget

NPC_IDS = ("npc_sumo", "npc_chenlang", "npc_xiaoyou")
REL_MAX = 100


class TabPanel(UIWidget):
    def __init__(self, parent, transform: UITransform, text_db, asset_registry=None) -> None:
        self.text_db = text_db
        self.transform = transform
        self.assets = asset_registry
        root = parent.attach_new_node("tab_panel")
        rect = theme.RECTS["tab_panel"]
        self.panel = UIPanel(root, transform, rect, asset_registry)
        x, y, w, h = rect

        self.title = UILabel(root, transform, x + 8, y + 6, text_db.get("ui.tab.title"),
                             size=theme.TITLE_SIZE / 2)

        # 左侧 5 属性
        self.stat_bars: dict[str, StatBar] = {}
        self.stat_values: dict[str, UILabel] = {}
        stats_x = x + 8
        for i, key in enumerate(theme.PANEL_STAT_KEYS):
            row_y = y + 6 + 2 * theme.LINE_HEIGHT + i * (theme.LINE_HEIGHT + 6)
            UIIcon(root, transform, stats_x, row_y + 1, theme.STAT_ICON_IDS[key], 12.0, asset_registry)
            UILabel(root, transform, stats_x + 16, row_y, text_db.get_raw(theme.STAT_NAME_IDS[key]))
            self.stat_bars[key] = StatBar(root, transform, stats_x + 62, row_y + 3,
                                          asset_registry=asset_registry)
            self.stat_values[key] = UILabel(root, transform, stats_x + 62 + 106, row_y, "0")
        self.energy_max_label = UILabel(
            root, transform, stats_x,
            y + 6 + 2 * theme.LINE_HEIGHT + len(theme.PANEL_STAT_KEYS) * (theme.LINE_HEIGHT + 6) + 4,
            "", color=theme.COLOR_SECONDARY,
        )

        # 右侧关系
        rel_x = x + w // 2 + 12
        UILabel(root, transform, rel_x, y + 6 + 2 * theme.LINE_HEIGHT,
                text_db.get("ui.tab.rel_title"), color=theme.COLOR_SECONDARY)
        self.rel_labels: dict[str, UILabel] = {}
        for i, npc_id in enumerate(NPC_IDS):
            row_y = y + 6 + 3 * theme.LINE_HEIGHT + 4 + i * theme.LINE_HEIGHT
            self.rel_labels[npc_id] = UILabel(root, transform, rel_x, row_y, "")
        self.semester_left_label = UILabel(
            root, transform, rel_x, y + 6 + 6 * theme.LINE_HEIGHT + 6,
            "", color=theme.COLOR_SECONDARY,
        )
        self.close_hint = UILabel(
            root, transform, x + w - 96, y + h - 26,
            text_db.get("ui.tab.close_hint"), color=theme.COLOR_SECONDARY,
        )
        super().__init__(root)
        self.hide()

    # ------------------------------------------------------------------
    def update_state(self, state) -> None:
        """state: GameState（鸭子类型）。"""
        stats = getattr(state, "stats", {}) or {}
        for key in theme.PANEL_STAT_KEYS:
            if key == "mood":
                value = int(getattr(state, "mood", 0))
            else:
                value = int(stats.get(key, 0))
            self.stat_values[key].set_text(str(value))
            self.stat_bars[key].set_value(value, float(REL_MAX))
        self.energy_max_label.set_text(
            self.text_db.get("ui.tab.energy_max", max=state.max_energy())
        )

        relationships = getattr(state, "relationships", {}) or {}
        for npc_id in NPC_IDS:
            short = npc_id.replace("npc_", "")
            value = int(relationships.get(npc_id, 0))
            if value > 0:
                name = self.text_db.get(f"npc.{short}.name")
                self.rel_labels[npc_id].set_text(f"{name}  {value}")
            else:
                # 三行一模一样的「？？？」没有任何信息量；按常驻地点给个线索
                clue_id = f"ui.tab.unknown.{short}"
                if self.text_db.has(clue_id):
                    self.rel_labels[npc_id].set_text(self.text_db.get(clue_id))
                else:
                    self.rel_labels[npc_id].set_text(self.text_db.get("ui.tab.unknown_npc"))

        # 每学期 2 天；当天还没过完，所以剩余天数要含今天（旧版第 2 天显示 0 天）
        days_left = max(0, 2 - state.day + 1)
        self.semester_left_label.set_text(
            self.text_db.get("ui.tab.semester_left", days=days_left)
        )

    def toggle(self) -> bool:
        if self.visible:
            self.hide()
        else:
            self.show()
        return self.visible
