"""主题 / 布局 / 数值格式化测试。

D-ST-01：布局均在 480×270 内；
D-ST-02：academic +5、energy -20 的顺序、符号、颜色和格式正确。
"""

from __future__ import annotations

import pytest

from game.ui import theme


def test_all_layout_rects_in_canvas():
    """D-ST-01：手册中登记的每个界面矩形必须完整落在画布内。"""
    for name, rect in theme.RECTS.items():
        assert theme.rect_in_canvas(rect), f"{name} 越界: {rect}"


def test_panels_do_not_overlap_when_co_visible():
    """同时可见的面板（HUD 与对话框、对话框与选项）不得互相覆盖。"""
    assert not theme.rect_overlaps(theme.RECTS["hud_gauges"], theme.RECTS["dialogue"])
    assert not theme.rect_overlaps(theme.RECTS["dialogue"], theme.RECTS["event_choices"])


def test_dialogue_portrait_stays_inside_panel_padding():
    panel = theme.RECTS["dialogue"]
    portrait = theme.RECTS["dialogue_portrait"]
    padding = theme.PANEL_PADDING
    assert portrait[0] >= panel[0] + padding
    assert portrait[1] >= panel[1] + padding
    assert portrait[0] + portrait[2] <= panel[0] + panel[2] - padding
    assert portrait[1] + portrait[3] <= panel[1] + panel[3] - padding


def test_tutorial_banner_and_interaction_prompt_are_separated():
    from game.ui.tutorial import TutorialOverlay

    banner = TutorialOverlay.BANNER_RECT
    prompt = theme.RECTS["prompt"]
    assert not theme.rect_overlaps(banner, prompt)
    assert not theme.rect_overlaps(banner, theme.RECTS["dialogue"])
    assert not theme.rect_overlaps(banner, theme.RECTS["event_choices"])
    assert not theme.rect_overlaps(banner, theme.RECTS["hud_date"])
    assert not theme.rect_overlaps(banner, theme.RECTS["hud_gauges"])
    assert not theme.rect_overlaps(banner, theme.RECTS["hud_key_hint"])

    # Label glyphs occupy 12 logical pixels below their top-left anchors.
    banner_label_y = banner[1] + 6
    prompt_title_y = prompt[1] + 2
    assert banner_label_y + 12 <= prompt_title_y
    assert prompt[1] + prompt[3] <= theme.RECTS["hud_key_hint"][1]


def test_prompt_details_wrap_to_measured_width():
    measured = {
        "精力 -12": 54.0,
        "精力 -12  心情 -2": 116.0,
        "精力 -12  心情 -2  社交 +4": 171.0,
        "精力 -12  心情 -2  社交 +4  兴趣 +1": 240.1,
        "兴趣 +1": 50.0,
        "兴趣 +1  与陈朗的关系 +3": 122.0,
    }
    lines = theme.wrap_prompt_details(
        ["精力 -12", "心情 -2", "社交 +4", "兴趣 +1", "与陈朗的关系 +3"],
        204.0,
        measured.__getitem__,
    )
    assert lines == ["精力 -12  心情 -2  社交 +4", "兴趣 +1  与陈朗的关系 +3"]
    assert all(measured[line] <= 204.0 for line in lines)


def test_rel_dot_prefix_is_sorted_and_formatted_as_relationship():
    key = "rel.npc_chenlang"
    assert theme._rel_sort_key(key)[0] == ""
    assert theme.ordered_deltas({key: 3, "social": 4}) == [
        ("social", 4), (key, 3),
    ]
    formatted = theme.format_deltas(
        {key: 3}, {key: "与陈朗的关系"}
    )
    assert formatted[0][2] == "与陈朗的关系 +3"
    assert "rel." not in formatted[0][2]


def test_format_deltas_order_and_sign():
    """D-ST-02：顺序 = 精力、心情、学业……；格式 = 名称 + 带符号整数。"""
    name_of = {k: k for k in theme.STAT_NAME_IDS}
    formatted = theme.format_deltas(
        {"academic": 5, "energy": -20}, name_of
    )
    assert formatted[0][0] == "energy"
    assert formatted[0][2] == "energy -20"
    assert formatted[1][2] == "academic +5"


def test_zero_deltas_hidden():
    assert theme.ordered_deltas({"academic": 0, "mood": 3}) == [("mood", 3)]


def test_relationship_sorted_last():
    result = theme.ordered_deltas({"rel_npc_sumo": 1, "academic": 2, "energy": -1})
    assert [key for key, _ in result] == ["energy", "academic", "rel_npc_sumo"]


def test_delta_color_gain_and_loss():
    assert theme.delta_color(+5) == theme.COLOR_GAIN
    assert theme.delta_color(-3) == theme.COLOR_LOSS


def test_colors_match_spec():
    assert theme.HEX["text"] == "#F4F1E8"
    assert theme.HEX["panel"] == "#1B1F2A"
    assert theme.HEX["gain"] == "#6ABE30"
    assert theme.HEX["loss"] == "#D95763"
    assert theme.HEX["warn"] == "#F2C14E"
    assert theme.PANEL_ALPHA == pytest.approx(0.90)


def test_typewriter_speed_settings():
    """文本速度必须与 A 的 config.TEXT_SPEED_TABLE 完全一致。"""
    from game.config import TEXT_SPEED_TABLE

    for name, cps in TEXT_SPEED_TABLE.items():
        assert theme.chars_per_second(name) == float(cps), name
    assert theme.chars_per_second("slow") < theme.chars_per_second("normal")
    assert theme.chars_per_second("normal") < theme.chars_per_second("fast")
    assert theme.chars_per_second("instant") == 0.0  # 0 = 立即显示整页
    assert theme.chars_per_second("unknown") == theme.chars_per_second("normal")
    assert set(theme.TEXT_SPEED_ORDER) == set(TEXT_SPEED_TABLE)


def test_hud_panels_leave_inner_padding_for_content():
    """HUD 两块底板：上下各留 8 px，内容不再压到金边（40 = 8 + 12/8 + 8 + 余量）。"""
    for name in ("hud_date", "hud_gauges"):
        _x, _y, _w, h = theme.RECTS[name]
        assert h >= 40, f"{name} 太矮，放不下 8 px 内边距 + 两行内容"


def test_canvas_offset_centers_non_16_9_window():
    """非 16:9 窗口（如 1282×752）画布要垂直居中，Tab 面板才不会看起来偏上。"""
    window_w, window_h = 1282, 752
    scale = window_w / theme.CANVAS_W
    offset_x, offset_y = theme.canvas_offset(scale, window_w, window_h)
    assert offset_x == pytest.approx(0.0)
    assert offset_y == pytest.approx((window_h - theme.CANVAS_H * scale) / 2.0)
    assert offset_y > 0  # 窗口比 16:9 高，多出来的高度平均分到上下

    # 16:9 窗口不应有偏移
    assert theme.canvas_offset(1280 / theme.CANVAS_W, 1280, 720) == pytest.approx((0.0, 0.0))
