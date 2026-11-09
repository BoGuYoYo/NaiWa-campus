"""把「素材/建筑」里新增的草坪贴图与 4 个道具图接入游戏资源。

输入（用户素材，只读）：
    素材/建筑/草坪贴图.jfif   2048×2048 可平铺草地
    素材/建筑/树.jfif         1792×2400 白底正面图
    素材/建筑/路灯.jfif       同上
    素材/建筑/垃圾桶.jfif     同上
    素材/建筑/告示牌.jfif     同上

输出（仓库资源）：
    assets/campus/textures/ground_grass.png   512×512 平铺贴图
    assets/campus/textures/props/tree.png     高 256 的 RGBA 卡片
    assets/campus/textures/props/lamp.png
    assets/campus/textures/props/bin.png
    assets/campus/textures/props/sign.png

处理要点：
1. 白底用「从四边泛洪」而不是全局色键——道具内部也有接近白色的部分
   （路灯灯罩、告示牌板面），全局抠会把它们打穿。
2. 图里烧进了一块灰色地面投影，贴在草地上会变成一块灰斑：在对象包围盒
   底部 12% 内，把「低饱和 + 中亮」的像素一并去掉（树干棕色、灯座深灰、
   轮子近黑都远低于这个亮度区间，不会被误伤）。
3. 每张按内容裁切后等比缩放到统一高度，卡片在游戏里再按米缩放。
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT.parent / "素材" / "建筑"
DEFAULT_OUT = ROOT / "assets" / "campus" / "textures"

#: 道具：源文件名 -> (输出名, 输出像素高度)
PROPS: dict[str, tuple[str, int]] = {
    "树.jfif": ("props/tree.png", 256),
    "路灯.jfif": ("props/lamp.png", 256),
    "垃圾桶.jfif": ("props/bin.png", 160),
    "告示牌.jfif": ("props/sign.png", 200),
}

GRASS = ("草坪贴图.jfif", "ground_grass.png", 512)

WHITE_MIN = 0.90      # 三个通道都 >= 0.90 视为白底
WHITE_SAT = 0.06      # 且饱和度足够低（纯白/灰白）
SHADOW_LUMA = (0.55, 0.95)
SHADOW_SAT = 0.10
SHADOW_BAND = 0.12


def _flood_background(rgb: np.ndarray) -> np.ndarray:
    """从四边泛洪标记背景，返回 bool 掩码（True = 背景）。"""
    h, w, _ = rgb.shape
    near_white = (
        (rgb.min(axis=2) >= WHITE_MIN)
        & ((rgb.max(axis=2) - rgb.min(axis=2)) <= WHITE_SAT)
    )
    background = np.zeros((h, w), dtype=bool)
    stack = []
    for x in range(w):
        for y in (0, h - 1):
            if near_white[y, x]:
                stack.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if near_white[y, x]:
                stack.append((y, x))
    while stack:
        y, x = stack.pop()
        if background[y, x] or not near_white[y, x]:
            continue
        background[y, x] = True
        if y > 0:
            stack.append((y - 1, x))
        if y + 1 < h:
            stack.append((y + 1, x))
        if x > 0:
            stack.append((y, x - 1))
        if x + 1 < w:
            stack.append((y, x + 1))
    return background


def _drop_ground_shadow(rgb: np.ndarray, alpha: np.ndarray) -> None:
    """去掉包围盒底部那条烘焙的灰色投影（就地修改 alpha）。"""
    ys, xs = np.nonzero(alpha)
    if len(ys) == 0:
        return
    y0, y1 = ys.min(), ys.max()
    band = y0 + int((y1 - y0) * (1.0 - SHADOW_BAND))
    luma = rgb.mean(axis=2)
    sat = rgb.max(axis=2) - rgb.min(axis=2)
    zone = np.zeros(alpha.shape, dtype=bool)
    zone[band : y1 + 1, :] = True
    shadow = zone & (luma >= SHADOW_LUMA[0]) & (luma <= SHADOW_LUMA[1]) & (sat <= SHADOW_SAT)
    alpha[shadow] = 0


def _drop_enclosed_white_at_base(rgb: np.ndarray, alpha: np.ndarray) -> None:
    """去掉树根/轮子之间被围住的纯白空隙。

    这些空隙和背景不连通，泛洪抠不到；但它们只在「内容包围盒最底部 20%」出现，
    而路灯灯罩那种要保留的浅色在顶部，所以按位置限定，不会误伤。
    """
    ys, _xs = np.nonzero(alpha)
    if len(ys) == 0:
        return
    y0, y1 = ys.min(), ys.max()
    cutoff = y0 + int((y1 - y0) * 0.55)
    pure_white = (rgb.min(axis=2) >= 0.97) & ((rgb.max(axis=2) - rgb.min(axis=2)) <= 0.02)
    candidates = pure_white & (alpha > 0)
    candidates[:cutoff, :] = False

    h, w = candidates.shape
    seen = np.zeros_like(candidates)
    for y in range(h):
        for x in range(w):
            if not candidates[y, x] or seen[y, x]:
                continue
            stack = [(y, x)]
            blob = []
            while stack:
                cy, cx = stack.pop()
                if seen[cy, cx] or not candidates[cy, cx]:
                    continue
                seen[cy, cx] = True
                blob.append((cy, cx))
                for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                    if 0 <= ny < h and 0 <= nx < w and not seen[ny, nx]:
                        stack.append((ny, nx))
            for cy, cx in blob:
                alpha[cy, cx] = 0


def process_prop(source: Path, target: Path, height: int) -> dict[str, object]:
    image = Image.open(source).convert("RGB")
    rgb = np.asarray(image).astype(np.float32) / 255.0
    background = _flood_background(rgb)
    alpha = np.where(background, 0, 255).astype(np.uint8)
    _drop_ground_shadow(rgb, alpha)
    _drop_enclosed_white_at_base(rgb, alpha)

    # 收缩 1 像素，避免残留的白边在缩小时变灰
    a = Image.fromarray(alpha).filter(ImageFilter.MinFilter(3))
    alpha = np.asarray(a).copy()

    rgba = np.dstack((np.asarray(image), alpha))
    rgba[alpha == 0, :3] = 0
    result = Image.fromarray(rgba)
    bbox = result.getchannel("A").getbbox()
    if bbox is None:
        raise RuntimeError(f"{source}: 抠图后没有内容")
    result = result.crop(bbox)
    scale = height / result.height
    width = max(1, round(result.width * scale))
    result = result.resize((width, height), Image.Resampling.LANCZOS)
    target.parent.mkdir(parents=True, exist_ok=True)
    result.save(target, format="PNG", optimize=True)
    return {"source": source.name, "target": str(target.relative_to(ROOT)), "size": result.size}


def process_grass(source: Path, target: Path, size: int) -> dict[str, object]:
    image = Image.open(source).convert("RGB")
    if image.width != image.height:
        raise ValueError(f"{source}: 平铺贴图应为正方形，实际 {image.size}")
    result = image.resize((size, size), Image.Resampling.LANCZOS)
    # 轻微量化压掉 JPEG 噪点，保持和其他占位图一致的“像素感”
    result = result.quantize(colors=64, method=Image.Quantize.MEDIANCUT).convert("RGB")
    target.parent.mkdir(parents=True, exist_ok=True)
    result.save(target, format="PNG", optimize=True)
    return {"source": source.name, "target": str(target.relative_to(ROOT)), "size": result.size}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="导入草坪贴图与 4 个道具图")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--grass", action="store_true", help="只处理草坪贴图")
    parser.add_argument("--props", action="store_true", help="只处理道具")
    args = parser.parse_args(argv)

    do_grass = args.grass or not args.props
    do_props = args.props or not args.grass

    if do_grass:
        name, out_name, size = GRASS
        print(process_grass(args.source / name, args.out / out_name, size))
    if do_props:
        for name, (out_name, height) in PROPS.items():
            print(process_prop(args.source / name, args.out / out_name, height))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
