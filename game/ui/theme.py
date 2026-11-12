"""UI 主题与视觉规范（D1）——纯逻辑模块，不依赖 panda3d。

所有数值都来自《任务分工手册 3.0》D1/D2 节，不得自行修改：
- 逻辑画布 480×270，原点左上；
- 正文 #F4F1E8，次要 #A8A39A，面板底 #1B1F2A（透明度 90%），
  增益 #6ABE30，减益 #D95763，警告 / 选中 #F2C14E；
- 正文行高 16，标题 2 倍字号（24px）；
- 数值格式：名称 + 空格 + 带符号整数，0 不显示；
  顺序固定为精力、心情、学业、体力、社交、兴趣、关系。
"""

from __future__ import annotations

from typing import Callable, Iterable

# ----------------------------------------------------------------------
# 画布
# ----------------------------------------------------------------------
CANVAS_W = 480
CANVAS_H = 270
LINE_HEIGHT = 16
TITLE_SIZE = 24  # 正文字号 12px 的 2 倍
MAX_LINES_PER_PAGE = 4  # 对话框正文区最多 4 行（与 text_db 的排版上限一致）

# ----------------------------------------------------------------------
# 颜色（十六进制 + Panda3D 使用的 RGBA 元组）
# ----------------------------------------------------------------------
HEX = {
    "text": "#F4F1E8",
    "secondary": "#A8A39A",
    "panel": "#1B1F2A",
    "gain": "#6ABE30",
    "loss": "#D95763",
    "warn": "#F2C14E",
    "cursor": "#F2C14E",
}


def hex_to_rgba(hex_str: str, alpha: float = 1.0) -> tuple[float, float, float, float]:
    """'#RRGGBB' -> (r, g, b, a)，各分量 0..1（Panda3D 颜色格式）。"""
    h = hex_str.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"非法颜色值: {hex_str}")
    return (
        int(h[0:2], 16) / 255.0,
        int(h[2:4], 16) / 255.0,
        int(h[4:6], 16) / 255.0,
        alpha,
    )


COLOR_TEXT = hex_to_rgba(HEX["text"])
COLOR_SECONDARY = hex_to_rgba(HEX["secondary"])
COLOR_PANEL = hex_to_rgba(HEX["panel"], 0.90)
COLOR_GAIN = hex_to_rgba(HEX["gain"])
COLOR_LOSS = hex_to_rgba(HEX["loss"])
COLOR_WARN = hex_to_rgba(HEX["warn"])
COLOR_CURSOR = hex_to_rgba(HEX["warn"])
COLOR_DISABLED = hex_to_rgba(HEX["secondary"], 0.6)

PANEL_ALPHA = 0.90
#: 9-slice 占位皮肤的中心偏亮，直接贴会把白字洗掉；用它把整张皮肤压暗到面板色域。
#: 9-slice 占位皮肤的中心偏亮，直接贴会把白字洗掉；用它把整张皮肤压暗到面板色域。
#: 不透明度取 1.0：面板下面就是 3D 场景，留一点透明度都会透出建筑/道具，正文读不清。
PANEL_TINT = (0.30, 0.33, 0.42, 1.0)
PANEL_SOLID = (0.106, 0.122, 0.165, 1.0)
PANEL_PADDING = 8  # 9-slice 内边距，逻辑像素
PANEL_GAP_MIN = 4  # 面板之间最小间隔

# ----------------------------------------------------------------------
# 界面布局矩形（D2，逻辑像素 x, y, w, h；原点左上）
# ----------------------------------------------------------------------
RECTS: dict[str, tuple[int, int, int, int]] = {
    # HUD 两块底板 40 高：内容上下各留 8 px，文字/图标不再压到金边上
    "hud_date": (4, 4, 156, 40),
    "hud_gauges": (320, 4, 156, 40),
    "hud_key_hint": (4, 252, 200, 16),
    # 提示框底部居中：标题 + 最多三行实测明细，避开底部按键提示。
    "prompt": (130, 186, 220, 64),
    "result": (100, 40, 280, 190),
    "result_illustration": (160, 48, 160, 90),
    "dialogue": (4, 166, 472, 100),
    # Portrait stays inside the dialogue panel's 8 px inner padding instead of
    # touching the outer frame, which made full-body art look like it spilled out.
    "dialogue_portrait": (12, 174, 84, 84),
    "dialogue_name": (108, 170, 360, 16),
    "dialogue_body": (108, 188, 362, 72),
    "event_choices": (276, 92, 200, 68),
    "day_summary": (120, 60, 240, 144),
    "tab_panel": (40, 24, 400, 180),
    "main_menu": (180, 150, 120, 90),
    "graduation": (0, 0, 480, 270),
}


def rect_in_canvas(rect: tuple[int, int, int, int]) -> bool:
    """D-ST-01：所有矩形必须完整落在 480×270 内。"""
    x, y, w, h = rect
    return x >= 0 and y >= 0 and w >= 0 and h >= 0 and x + w <= CANVAS_W and y + h <= CANVAS_H


def rect_overlaps(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return not (ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay)


def canvas_offset(scale: float, window_w: int, window_h: int) -> tuple[float, float]:
    """480×270 逻辑画布在窗口里的居中偏移（像素）。

    窗口不是 16:9 时（例如 1282×752、或被拖大），画布按宽度等比缩放后高度
    小于窗口；不补偏移的话整块 UI 会贴着窗口顶部，Tab 状态面板看起来"偏上"。
    这里把剩余空间均分到两侧，水平方向同理。
    """
    return (
        (window_w - CANVAS_W * scale) / 2.0,
        (window_h - CANVAS_H * scale) / 2.0,
    )


def ui_px(
    x: float,
    y: float,
    scale: float,
    window_w: int,
    window_h: int,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
) -> tuple[float, float]:
    """把逻辑画布坐标换算到 aspect2d 坐标。

    scale 是 A 的 render_pipeline 提供的最近邻放大系数
    （例如 480→1920 时 scale=4）。offset_x/offset_y 是画布居中偏移，
    见 canvas_offset()。返回 (ax, ay)：aspect2d 的 y 向上为正，
    而逻辑画布 y 向下为正。
    """
    px = x * scale + offset_x
    py = y * scale + offset_y
    ax = (px - window_w / 2) / (window_h / 2)
    ay = (window_h / 2 - py) / (window_h / 2)
    return ax, ay


# ----------------------------------------------------------------------
# 数值格式化（D-ST-02）
# ----------------------------------------------------------------------
#: 固定顺序：精力、心情、学业、体力、社交、兴趣；关系固定在最后
DELTA_ORDER = ("energy", "mood", "academic", "stamina", "social", "interest")
STAT_KEYS = DELTA_ORDER

#: 属性名 -> strings.json 中的名称 text_id
STAT_NAME_IDS = {
    "energy": "stat.energy.name",
    "mood": "stat.mood.name",
    "academic": "stat.academic.name",
    "stamina": "stat.stamina.name",
    "social": "stat.social.name",
    "interest": "stat.interest.name",
}

#: 状态面板（Tab）左侧的 5 条属性；精力单独作为「上限」显示
PANEL_STAT_KEYS = ("academic", "stamina", "social", "interest", "mood")

#: 属性 -> 图标 asset_id（A 的 manifest 已交付 15 个 ui_icon_*）
STAT_ICON_IDS = {
    "energy": "ui_icon_energy",
    "mood": "ui_icon_mood",
    "academic": "ui_icon_academic",
    "stamina": "ui_icon_stamina",
    "social": "ui_icon_social",
    "interest": "ui_icon_interest",
}

#: 交互提示里门 / 存档点的文案（C 的 InteractionService 产出这两个 ID）
PROMPT_ENTER_ID = "ui.prompt.enter"
PROMPT_SAVE_ID = "ui.prompt.save"


def _rel_sort_key(key: str) -> tuple[str, str]:
    """关系键（rel.<npc_id> / rel_<npc_id> / relationship:<npc_id> 等）。"""
    for prefix in ("rel.", "rel_", "relationship:", "relationship_", "relationship."):
        if key.startswith(prefix):
            return ("", key[len(prefix):])
    return ("~", key)  # 未知键排在关系之后


def ordered_deltas(deltas: dict[str, int]) -> list[tuple[str, int]]:
    """按手册规定顺序排列非零 deltas；0 一律不显示。"""
    result: list[tuple[str, int]] = []
    for key in DELTA_ORDER:
        value = deltas.get(key, 0)
        if value != 0:
            result.append((key, value))
    others = sorted(
        ((k, v) for k, v in deltas.items() if k not in DELTA_ORDER and v != 0),
        key=lambda kv: _rel_sort_key(kv[0]),
    )
    result.extend(others)
    return result


def format_delta(stat_name: str, value: int) -> str:
    """“学业 +5”“精力 -20”：名称 + 空格 + 带符号整数。"""
    sign = "+" if value > 0 else "-"
    return f"{stat_name} {sign}{abs(value)}"


def wrap_prompt_details(
    parts: Iterable[str], max_width: float, measure_text: Callable[[str], float]
) -> list[str]:
    """Greedily wrap prompt deltas using the active font's measured pixel width."""
    lines: list[str] = []
    current = ""
    for part in parts:
        candidate = f"{current}  {part}" if current else part
        if current and measure_text(candidate) > max_width:
            lines.append(current)
            current = part
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def wrap_cjk(text: str, max_width: float, measure_text: Callable[[str], float]) -> list[str]:
    """按像素宽度给中文（无空格）文本折行。

    对话框正文、查看点说明这类文本是一整段中文，没有空格可断；
    ``str.wrap`` 式的按字符贪心更靠谱。宽度用调用方给的实际字体测量。
    """
    if not text:
        return [""]
    if measure_text(text) <= max_width:
        return [text]
    lines: list[str] = []
    current = ""
    for char in text:
        candidate = current + char
        if current and measure_text(candidate) > max_width:
            lines.append(current)
            current = char
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def format_deltas(
    deltas: dict[str, int],
    name_of: "dict[str, str] | None" = None,
) -> list[tuple[str, int, str]]:
    """返回 [(键, 值, “学业 +5”)]，键用于选择颜色（gain/loss）。

    name_of 把数值键映射为中文名；未提供时对标准属性使用
    STAT_NAME_IDS 的键名占位，关系键直接使用“关系”。
    """
    name_of = dict(name_of or {})
    formatted: list[tuple[str, int, str]] = []
    for key, value in ordered_deltas(deltas):
        if key in name_of:
            stat_name = name_of[key]
        elif key in STAT_NAME_IDS:
            stat_name = key  # 调用方可用 name_of 填入中文名
        elif _rel_sort_key(key)[0] == "":
            stat_name = "关系"
        else:
            stat_name = key
        formatted.append((key, value, format_delta(stat_name, value)))
    return formatted


def delta_color(value: int) -> tuple[float, float, float, float]:
    """增益 #6ABE30，减益 #D95763（0 不会出现在 deltas 里）。"""
    return COLOR_GAIN if value > 0 else COLOR_LOSS


# ----------------------------------------------------------------------
# 菜单 / 事件选项的纯逻辑（D3 键盘规则、D-ST-04）
# ----------------------------------------------------------------------
class MenuCursor:
    """键盘光标：W/S 或 ↑/↓ 循环移动；数字 1/2/3 直接选择；
    锁定项不可选中、不可确认，确认时给出锁定原因。

    items: [(choice_id, enabled, lock_reason_id | None)]
    """

    def __init__(self, items: "Iterable[tuple[str, bool, str | None]]") -> None:
        self.items: list[tuple[str, bool, str | None]] = list(items)
        self.index = self._first_enabled()

    def _first_enabled(self) -> int:
        for i, (_, enabled, _) in enumerate(self.items):
            if enabled:
                return i
        return 0  # 全部锁定时停在第一项（仅展示）

    def _enabled_indices(self) -> list[int]:
        return [i for i, (_, enabled, _) in enumerate(self.items) if enabled]

    def move(self, direction: int) -> bool:
        """向上/向下循环移动（跳过锁定项）。返回是否移动成功。"""
        enabled = self._enabled_indices()
        if not enabled or self.index not in enabled:
            self.index = self._first_enabled()
            return True
        pos = enabled.index(self.index)
        pos = (pos + direction) % len(enabled)
        self.index = enabled[pos]
        return True

    def select_digit(self, digit: int) -> tuple[str, str | None] | None:
        """数字 1/2/3 直接选择；锁定项无效，返回 (choice_id, reason)。"""
        i = digit - 1
        if not 0 <= i < len(self.items):
            return None
        choice_id, enabled, reason = self.items[i]
        if not enabled:
            return (choice_id, reason or "locked")
        return (choice_id, None)

    def confirm(self) -> tuple[str, str | None] | None:
        """确认当前项；锁定项无效。"""
        if not self.items:
            return None
        choice_id, enabled, reason = self.items[self.index]
        if not enabled:
            return (choice_id, reason or "locked")
        return (choice_id, None)

    @property
    def lock_reason(self) -> str | None:
        """当前项为锁定项时返回原因（用于显示锁定提示）。"""
        if not self.items:
            return None
        _, enabled, reason = self.items[self.index]
        return None if enabled else (reason or "locked")


# ----------------------------------------------------------------------
# 打字机速度（settings.text_speed -> 每秒字符数）
# 取值与 game/config.py 的 TEXT_SPEED_TABLE 完全一致：
#   slow 20 / normal 40 / fast 80 / instant 0（0 = 立即显示整页）
# ----------------------------------------------------------------------
TEXT_SPEEDS = {
    "slow": 20.0,
    "normal": 40.0,
    "fast": 80.0,
    "instant": 0.0,
}
TEXT_SPEED_ORDER = ("slow", "normal", "fast", "instant")
DEFAULT_TEXT_SPEED = "normal"


def chars_per_second(text_speed: str) -> float:
    """每秒字符数；instant 返回 0，调用方按「立即显示整页」处理。"""
    return TEXT_SPEEDS.get(text_speed, TEXT_SPEEDS[DEFAULT_TEXT_SPEED])


# ----------------------------------------------------------------------
# 教程（D7）的纯逻辑在 tutorial.py；此处只放时长常量
# ----------------------------------------------------------------------
TUTORIAL_TAB_TIMEOUT_SECONDS = 30.0
KEY_HINT_DAYS = 3  # 按键提示仅前 3 天显示
