"""导入校长立绘（`素材/人物/校长.jfif`）：场景立牌 + 头像。

与 `import_npc_characters.py` 的区别：
- 素材是 **单张正面站姿**（2048×2048、纯白背景、底部带一块灰色底座），不是 4×2 角色表；
- 背景必须**从四边泛洪**去背：全局"近白=背景"会把白衬衫一起抠掉（衬衫和背景同色）；
- 底部那块灰色底座要整块切掉，否则立牌脚下会多一块板。

用法：
    python tools/import_principal_character.py --check     # 只量尺寸、出预览
    python tools/import_principal_character.py             # 写资产 + 预览图
"""

from __future__ import annotations

import argparse
import sys
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent / "素材" / "人物" / "校长.jfif"

FRAME = 48
BODY_HEIGHT = 40          # 与其它 NPC 立牌一致（48 帧里人物 40 px 高，脚点 y=46）
FEET_Y = 46
PORTRAIT = 96
HEAD_RATIO = 0.32         # 头顶往下 32% 高度做头肩特写（含西装肩线）
BG_TOLERANCE = 25         # 白背景含 JPEG 压缩边灰阶抖动，25 可清干净外轮廓且不穿透黑线进白衬衫

OUT_FIGURE = ROOT / "assets" / "characters" / "npc" / "principal_idle.png"
OUT_PORTRAIT = ROOT / "assets" / "portraits" / "principal" / "neutral.png"
OUT_PREVIEW = ROOT / "reports" / "review" / "principal" / "contact_sheet.png"


def flood_background(img: Image.Image, tolerance: int = BG_TOLERANCE) -> Image.Image:
    """从四边泛洪去背（连通），返回带 alpha 的 RGBA。"""
    rgb = np.array(img.convert("RGB")).astype(np.int16)
    h, w = rgb.shape[:2]
    # 背景色取四边像素的中位数（图片角上是纯白）
    border = np.concatenate([rgb[0, :, :], rgb[-1, :, :], rgb[:, 0, :], rgb[:, -1, :]])
    bg = np.median(border, axis=0)
    is_bg_like = np.abs(rgb - bg).max(axis=2) <= tolerance

    visited = np.zeros((h, w), dtype=bool)
    queue: deque[tuple[int, int]] = deque()
    for x in range(w):
        for y in (0, h - 1):
            if is_bg_like[y, x] and not visited[y, x]:
                visited[y, x] = True
                queue.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if is_bg_like[y, x] and not visited[y, x]:
                visited[y, x] = True
                queue.append((y, x))
    while queue:
        y, x = queue.popleft()
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= ny < h and 0 <= nx < w and not visited[ny, nx] and is_bg_like[ny, nx]:
                visited[ny, nx] = True
                queue.append((ny, nx))

    out = np.dstack([rgb, np.where(visited, 0, 255)]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def drop_base_plate(img: Image.Image) -> Image.Image:
    """切掉脚下的灰色底座。

    底座是"浅灰 + 深色描边"的一块板，比鞋子宽得多：从最底一行往上扫，
    只要这一行的不透明像素还铺得很宽（> 画面宽度的 55%）就继续往上，
    一碰到"窄行"（鞋/腿）就停 —— 停下的位置就是底座顶边。
    """
    arr = np.array(img)
    alpha = arr[:, :, 3] > 0
    widths = alpha.sum(axis=1)
    if widths.max() <= 0:
        return img
    wide = 0.55 * float(widths.max())
    y = img.height - 1
    while y >= 0 and widths[y] == 0:      # 先跳过画布底部空白行
        y -= 1
    bottom = y
    while y >= 0 and widths[y] > wide:    # 再往上吃完整的"宽板"
        y -= 1
    # 只在"底部这块板很薄"时才裁（避免把宽肩膀的人裁掉半个身子）
    if 0 < (bottom - y) < 0.10 * img.height:
        return img.crop((0, 0, img.width, y + 1))
    return img


def flood_bottom_gaps(img: Image.Image, tolerance: int = 35) -> Image.Image:
    """切掉底座后，从底边向上泛洪清理双腿之间原本被底座封住的白底。"""
    arr = np.array(img)
    rgb = arr[:, :, :3].astype(np.int16)
    alpha = arr[:, :, 3] > 0
    h, w = alpha.shape
    if h == 0 or w == 0:
        return img
    bg_like = np.abs(rgb - 255).max(axis=2) <= tolerance
    visited = ~alpha
    queue: deque[tuple[int, int]] = deque()
    for x in range(w):
        if alpha[h - 1, x] and bg_like[h - 1, x]:
            visited[h - 1, x] = True
            queue.append((h - 1, x))
    while queue:
        y, x = queue.popleft()
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= ny < h and 0 <= nx < w and not visited[ny, nx] and bg_like[ny, nx]:
                visited[ny, nx] = True
                queue.append((ny, nx))
    arr[visited, 3] = 0
    return Image.fromarray(arr, "RGBA")


def peel_edge_halo(img: Image.Image, passes: int = 4) -> Image.Image:
    """剥离深色轮廓外缘的中性浅灰 JPEG 抗锯齿毛边（保留蓝白纸张与内侧高光）。"""
    arr = np.array(img)
    for _ in range(passes):
        alpha = arr[:, :, 3] > 0
        padded = np.pad(alpha, 1, constant_values=False)
        adjacent = alpha & (
            ~padded[:-2, 1:-1] | ~padded[2:, 1:-1] | ~padded[1:-1, :-2] | ~padded[1:-1, 2:]
        )
        r = arr[:, :, 0].astype(np.int16)
        g = arr[:, :, 1].astype(np.int16)
        b = arr[:, :, 2].astype(np.int16)
        chroma = np.maximum(np.maximum(r, g), b) - np.minimum(np.minimum(r, g), b)
        luma = (r + g + b) / 3.0
        peel = adjacent & (luma > 90) & (chroma <= 14)
        if not peel.any():
            break
        arr[peel, 3] = 0
    return Image.fromarray(arr, "RGBA")


def drop_specks(img: Image.Image, min_area: int) -> Image.Image:
    a = np.array(img)
    fg = a[:, :, 3] > 0
    h, w = fg.shape
    seen = np.zeros_like(fg, dtype=bool)
    for y0 in range(h):
        for x0 in range(w):
            if not fg[y0, x0] or seen[y0, x0]:
                continue
            stack = [(y0, x0)]
            seen[y0, x0] = True
            comp = []
            while stack:
                y, x = stack.pop()
                comp.append((y, x))
                for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                    if 0 <= ny < h and 0 <= nx < w and fg[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
            if len(comp) < min_area:
                for y, x in comp:
                    a[y, x, 3] = 0
    return Image.fromarray(a)


def area_downscale(img: Image.Image, target_h: int) -> Image.Image:
    """alpha 预乘的面积缩放：AI 像素画的块边界不规整，块中位会抖，面积平均更稳。"""
    w, h = img.size
    scale = target_h / float(h)
    size = (max(1, round(w * scale)), target_h)
    a = np.array(img).astype(np.float32)
    pre = a.copy()
    pre[:, :, :3] *= a[:, :, 3:4] / 255.0
    small = np.asarray(
        Image.fromarray(np.clip(pre, 0, 255).astype(np.uint8), "RGBA").resize(size, Image.BOX)
    ).astype(np.float32)
    alpha = small[:, :, 3:4] / 255.0
    rgb = np.where(alpha > 0.02, small[:, :, :3] / np.maximum(alpha, 1e-6), 0)
    return Image.fromarray(
        np.dstack([np.clip(rgb, 0, 255), np.where(alpha[:, :, 0] > 0.5, 255, 0)]).astype(np.uint8),
        "RGBA",
    )


def quantize(img: Image.Image, colors: int = 64) -> Image.Image:
    """只对不透明前景量化到 64 色（无抖动），防止透明黑底或色数过少吞掉银发/白纸色阶。"""
    arr = np.array(img)
    alpha = arr[:, :, 3]
    fg = alpha > 0
    if not fg.any():
        return img
    fill_rgb = np.median(arr[fg, :3], axis=0).astype(np.uint8)
    work = arr[:, :, :3].copy()
    work[~fg] = fill_rgb
    rgb = Image.fromarray(work, "RGB").quantize(
        colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE
    ).convert("RGB")
    out = np.dstack([np.array(rgb), alpha]).astype(np.uint8)
    out[~fg, :3] = 0
    return Image.fromarray(out, "RGBA")


def build_figure(figure: Image.Image) -> Image.Image:
    body = area_downscale(figure, BODY_HEIGHT)
    if body.width > FRAME - 4:
        scale = (FRAME - 4) / body.width
        body = body.resize((FRAME - 4, max(1, round(body.height * scale))), Image.LANCZOS)
    body = quantize(body)
    frame = Image.new("RGBA", (FRAME, FRAME), (0, 0, 0, 0))
    frame.alpha_composite(body, ((FRAME - body.width) // 2, max(0, FEET_Y - body.height)))
    return drop_specks(frame, min_area=6)


def build_portrait(figure: Image.Image, ratio: float = HEAD_RATIO) -> Image.Image:
    w, h = figure.size
    head_h = max(1, int(h * ratio))
    head_w = min(w, head_h)
    left = (w - head_w) // 2
    crop = figure.crop((left, 0, left + head_w, head_h))
    # 身体整体可能因持稿手臂偏向一侧，按头肩特写自身的不透明外接框水平居中
    head_bbox = crop.getbbox()
    if head_bbox is not None:
        crop = crop.crop((head_bbox[0], 0, head_bbox[2], crop.height))
    side = max(crop.width, crop.height)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.alpha_composite(crop, ((side - crop.width) // 2, 0))
    small = quantize(area_downscale(canvas, PORTRAIT))
    out = Image.new("RGBA", (PORTRAIT, PORTRAIT), (0, 0, 0, 0))
    out.alpha_composite(small, ((PORTRAIT - small.width) // 2, (PORTRAIT - small.height) // 2))
    return drop_specks(out, min_area=6)


def contact_sheet(figure: Image.Image, portrait: Image.Image) -> Image.Image:
    cell = 192
    sheet = Image.new("RGBA", (cell * 3, cell + 20), (27, 31, 42, 255))
    for index, (image, scale) in enumerate(((figure, 4), (portrait, 2))):
        preview = image.resize((image.width * scale, image.height * scale), Image.NEAREST)
        x = index * cell
        sheet.alpha_composite(preview, (x, 0)) if preview.height <= cell else None
    from PIL import ImageDraw

    draw = ImageDraw.Draw(sheet)
    for index, label in enumerate(("principal_idle 48x48", "portrait 96x96")):
        draw.text((index * cell + 4, cell + 4), label, fill=(230, 230, 230, 255))
    return sheet


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="导入校长立绘与头像")
    parser.add_argument("--check", action="store_true", help="只生成预览，不写资产")
    args = parser.parse_args(argv)

    if not SOURCE.is_file():
        print(f"缺少素材：{SOURCE}", file=sys.stderr)
        return 2

    raw = Image.open(SOURCE)
    cut = flood_background(raw)
    cut = drop_base_plate(cut)
    cut = flood_bottom_gaps(cut)
    cut = peel_edge_halo(cut)
    cut = drop_specks(cut, min_area=400)
    bbox = cut.getbbox()
    if bbox is None:
        print("抠图后没有内容", file=sys.stderr)
        return 1
    figure = cut.crop(bbox)
    print(f"原图 {raw.size} → 抠图 {figure.size}（脚底已切掉灰色底座）")

    idle = build_figure(figure)
    portrait = build_portrait(figure)
    print(f"立牌 {idle.size} 不透明像素 {(np.array(idle)[:, :, 3] > 0).sum()}")
    print(f"头像 {portrait.size} 不透明像素 {(np.array(portrait)[:, :, 3] > 0).sum()}")

    OUT_PREVIEW.parent.mkdir(parents=True, exist_ok=True)
    contact_sheet(idle, portrait).save(OUT_PREVIEW)
    print("预览 →", OUT_PREVIEW)

    if args.check:
        return 0
    OUT_FIGURE.parent.mkdir(parents=True, exist_ok=True)
    OUT_PORTRAIT.parent.mkdir(parents=True, exist_ok=True)
    idle.save(OUT_FIGURE)
    portrait.save(OUT_PORTRAIT)
    print("写入 →", OUT_FIGURE)
    print("写入 →", OUT_PORTRAIT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
