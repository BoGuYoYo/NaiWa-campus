"""按整数倍做像素画降采样（保持原图色块，不做插值混合）。

用户给的素材本身就是像素画（每个"美术像素"是源图上的 N×N 色块）。要把它放进
48×48 的角色帧里，正确做法是**整数倍**抽取：每 N×N 块取该块不透明像素的中位色，
这样游戏里的 1 个像素对应原图 1 个色块，边缘依旧是硬边，不会被"二次像素化"糊掉。

用法：
    from pixel_downscale import integer_downscale
    small = integer_downscale(rgba_image, target_h=40)
"""

from __future__ import annotations

import numpy as np
from PIL import Image


def integer_downscale(img: Image.Image, target_h: int, target_w: int | None = None) -> Image.Image:
    """把 RGBA 图按整数倍缩到高度约 target_h（宽度按同一倍数缩，保持比例）。"""
    if target_h <= 0:
        return img
    w, h = img.size
    factor = max(1, int(round(h / float(target_h))))
    if factor <= 1:
        return img
    a = np.array(img.convert("RGBA")).astype(np.int16)
    hh, ww = (h // factor) * factor, (w // factor) * factor
    if hh == 0 or ww == 0:
        return img
    a = a[:hh, :ww]
    blocks = (
        a.reshape(hh // factor, factor, ww // factor, factor, 4)
        .transpose(0, 2, 1, 3, 4)
        .reshape(hh // factor, ww // factor, factor * factor, 4)
    )
    alpha = blocks[:, :, :, 3]
    opaque = alpha > 127
    counts = opaque.sum(axis=2)
    rgb = np.where(opaque[:, :, :, None], blocks[:, :, :, :3], 0)
    # 每块取不透明像素的中位色（色块是纯色，中位数就是原色；边缘块也不会糊成灰）
    median = np.median(np.where(opaque[:, :, :, None], rgb, np.nan), axis=2)
    median = np.nan_to_num(median, nan=0.0)
    out_alpha = np.where(counts * 2 >= factor * factor, 255, 0)
    out = np.dstack([median, out_alpha]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")
