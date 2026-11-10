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


def test_tutorial_banner_and_interaction_prompt_are_separated():
    from game.ui.tutorial import TutorialOverlay

    banner = TutorialOverlay.BANNER_RECT
    prompt = theme.RECTS["prompt"]
    assert not theme.rect_overlaps(banner, prompt)

    # Label glyphs occupy 12 logical pixels below their top-left anchors.
    banner_label_y = banner[1] + 6
    prompt_title_y = prompt[1] + 2
    assert banner_label_y + 12 <= prompt_title_y
    assert prompt[1] + prompt[3] <= theme.RECTS["hud_key_hint"][1]


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
