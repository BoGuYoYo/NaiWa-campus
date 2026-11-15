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


def test_stele_asset_has_no_lower_corner_specks():
    """校训石碑下缘不能把棋盘格黑块带进游戏。"""
    path = ROOT / "assets" / "campus" / "textures" / "props" / "stele.png"
    alpha = np.asarray(Image.open(path).convert("RGBA"))[:, :, 3]
    h, w = alpha.shape
    lower = alpha[round(h * 0.65):]
    assert not lower[:, : round(w * 0.12)].any()
    assert not lower[:, round(w * 0.80):].any()
