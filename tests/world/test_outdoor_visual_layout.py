"""校园户外素材与摆放的可见性回归。"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[2]


def test_playground_basket_sits_right_of_track(map_data):
    """篮球架的完整贴图在跑道外侧，其余运动道具留在内场。"""
    safe = map_data.area("loc_playground").rect
    # 跑道贴图的内场安全区；足球门位于北侧门线，不纳入这一组检查。
    inset = type(safe)(safe.x0 + 4.0, safe.y0 + 2.5,
                       safe.x1 - 2.2, safe.y1 - 3.7)
    props = {p.id: p.rect for p in map_data.props}
    for prop_id in ("prop_hurdle", "prop_scoreboard", "prop_bench_sport"):
        rect = props[prop_id]
        assert (rect.x0 >= inset.x0 and rect.y0 >= inset.y0
                and rect.x1 <= inset.x1 and rect.y1 <= inset.y1), (
            f"{prop_id} 仍靠近跑道：{rect}，安全区为 {inset}"
        )

    basket = props["prop_basket"]
    basket_art = Image.open(ROOT / "assets" / "campus" / "textures" / "props" / "basket.png")
    visual_width = 4.21 * basket_art.width / basket_art.height
    visual_left = (basket.x0 + basket.x1) / 2.0 - visual_width / 2.0
    assert visual_left >= safe.x1, (
        f"篮球架贴图仍覆盖跑道：左边缘 {visual_left:.2f}，跑道右边界 {safe.x1}"
    )
    assert basket.y0 >= inset.y0 and basket.y1 <= inset.y1, (
        f"篮球架纵向偏离操场中段：{basket}，安全区为 {inset}"
    )


def test_stele_asset_keeps_the_whole_pedestal():
    """石碑必须保留柱身 + 底座。

    旧抠图按颜色容差，底座下层 (74,76,88) 与棋盘深格 (72,72,80) 只差 4，
    整块底座被当背景抠掉，只剩一根柱子悬空；下缘还会残留黑渣。
    现在按"冷灰"（B-R>11）分离，这两类问题一起消失。
    """
    path = ROOT / "assets" / "campus" / "textures" / "props" / "stele.png"
    rgba = np.asarray(Image.open(path).convert("RGBA"))
    alpha = rgba[:, :, 3]
    h, w = alpha.shape
    # 底座：下 35% 必须有足够宽的实心不透明区（旧版这里只剩一条残片）
    lower = alpha[round(h * 0.65):]
    widest = max(int(row.astype(bool).sum()) for row in lower)
    assert widest >= w * 0.55, f"石碑底座缺失：最宽一行只有 {widest}/{w} 像素"
    # 底座本身就该铺满下缘，只需确认不是"一根柱子 + 两侧残留"的形态：
    # 最宽行之外不应再出现孤立的透明缺口把底座切开。
    bottom = alpha[-1].astype(bool)
    assert bottom.sum() >= w * 0.5, "石碑底座没有铺到画布下缘"
