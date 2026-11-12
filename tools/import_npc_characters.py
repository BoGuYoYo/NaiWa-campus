"""把用户提供的两个人物立绘接进游戏（A 侧整合工具）。

输入（`素材/人物/`）：
- `<名字>.jfif`      —— 8 方向角色表（4×2 面板：FRONT / FRONT-LEFT / … / FRONT-RIGHT）
- `<名字>争论.jfif`  —— 半身怒相，用作 surprised 头像

两张"争论"图分别是各自角色的半身怒相（符闹吃=戴帽、李振兴=不戴帽）。

输出：
- `assets/characters/npc/<short>_idle.png`   48×48 单帧立牌（正面朝镜头，脚点 y=46）
- `assets/portraits/<short>/<mood>.png`      96×96 ×4（neutral / happy / sad / surprised）

用法：
    python tools/import_npc_characters.py --verify   # 只出核对图
    python tools/import_npc_characters.py            # 写 assets
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from pixel_downscale import integer_downscale

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT.parent / "素材" / "人物"

FRAME = 48
BODY_HEIGHT = 40
FEET_Y = 46
PORTRAIT = 96

#: 角色表里第 0 个面板是正面（FRONT）
FRONT_PANEL = 0

CHARACTERS = {
    "sumo": {"sheet": "符闹吃.jfif", "argue": "符闹吃争论.jfif", "name": "符闹吃", "head_ratio": 0.46},
    "chenlang": {"sheet": "李振兴.jfif", "argue": "李振兴争论.jfif", "name": "李振兴", "head_ratio": 0.46},
    # 奈珑：素材已经是抠好的透明 PNG（全身站姿），没有 4x2 角色表
    # 奈珑是写实比例（1894px 高、宽只有 600 多），整数倍块中位会把轮廓抖成噪点，
    # 改用 alpha 预乘的面积缩放：轮廓干净，颜色也不会被 32 色板二次破坏
    "xiaoyou": {"front": "01_FRONT.png", "name": "奈珑", "head_ratio": 0.32, "head_offset": 0.01, "method": "box"},
}


def _cell_boxes(width: int, height: int) -> list[tuple[int, int, int, int]]:
    """内容区按 4×2 切（数值来自两张表的实测：x 63..2683，y 108..1440）。"""
    left, right = 63, min(2683, width - 1)
    top, bottom = 108, min(1440, height - 1)
    cw = (right - left) / 4
    ch = (bottom - top) / 2
    return [
        (int(left + c * cw), int(top + r * ch), int(left + (c + 1) * cw), int(top + (r + 1) * ch))
        for r in range(2)
        for c in range(4)
    ]


def cut_figure(cell: Image.Image) -> Image.Image:
    """去掉底色和面板标签，返回人物的 RGBA 抠图。"""
    rgb = cell.convert("RGB")
    arr = np.array(rgb).astype(int)
    colors, counts = np.unique(arr.reshape(-1, 3), axis=0, return_counts=True)
    bgc = colors[int(np.argmax(counts))]
    is_bg = np.abs(arr - bgc).max(axis=2) <= 14
    fg = ~is_bg

    # 只保留"像人物"的行：面板顶部的标签文字前景像素很少
    solid_rows = fg.sum(axis=1) > max(6, int(0.08 * arr.shape[1]))
    rows = np.where(solid_rows)[0]
    if len(rows) == 0:
        return rgb.convert("RGBA")
    top, bottom = int(rows[0]), int(rows[-1]) + 1
    solid_cols = fg[top:bottom].sum(axis=0) > 0
    cols = np.where(solid_cols)[0]
    left, right = int(cols[0]), int(cols[-1]) + 1

    arr = arr[top:bottom, left:right]
    is_bg = is_bg[top:bottom, left:right]
    out = Image.fromarray(arr.astype(np.uint8)).convert("RGBA")
    out.putalpha(Image.fromarray(np.where(is_bg, 0, 255).astype(np.uint8)))
    out = _drop_specks(out)
    bbox = out.getbbox()
    return out.crop(bbox) if bbox else out


def _drop_specks(img: Image.Image, min_area: int = 60) -> Image.Image:
    """删掉面积过小的孤立连通块（面板标签的残渣）。"""
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


def box_downscale(img: Image.Image, target_h: int) -> Image.Image:
    """alpha 预乘的面积缩放（写实比例角色用；不做调色板量化）。"""
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
    out = np.dstack([np.clip(rgb, 0, 255), np.where(alpha[:, :, 0] > 0.5, 255, 0)]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def fit_frame(figure: Image.Image, method: str = "median") -> Image.Image:
    """按整数倍降到 40 px 高（保留原图色块），脚底贴 y=46，水平居中放进 48×48。

    素材本身就是像素画，非整数倍缩放会把每个色块切碎，看起来像"二次像素化"。
    """
    fig = integer_downscale(figure, BODY_HEIGHT) if method == "median" else box_downscale(figure, BODY_HEIGHT)
    if fig.width > FRAME - 4:
        scale = (FRAME - 4) / fig.width
        fig = fig.resize((FRAME - 4, max(1, round(fig.height * scale))), Image.LANCZOS)
    frame = Image.new("RGBA", (FRAME, FRAME), (0, 0, 0, 0))
    frame.alpha_composite(fig, ((FRAME - fig.width) // 2, max(0, FEET_Y - fig.height)))
    # 缩到 48 后再清一次孤立点（原始大图里的标签残渣会缩成 1~2 px）
    return _drop_specks(frame, min_area=8)


def make_portrait(figure: Image.Image, ratio: float = 0.46, method: str = "median",
                  offset: float = 0.0) -> Image.Image:
    """头肩特写：从 offset 处往下取 ratio 高度裁方形，再降到 96×96。"""
    w, h = figure.size
    top = int(h * offset)
    head_h = max(1, int(h * ratio))
    head_h = min(head_h, h - top)
    head_w = min(w, head_h)
    left = (w - head_w) // 2
    crop = figure.crop((left, top, left + head_w, top + head_h))
    side = max(crop.width, crop.height)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.alpha_composite(crop, ((side - crop.width) // 2, 0))
    small = integer_downscale(canvas, PORTRAIT) if method == "median" else box_downscale(canvas, PORTRAIT)
    out = Image.new("RGBA", (PORTRAIT, PORTRAIT), (0, 0, 0, 0))
    out.alpha_composite(small, ((PORTRAIT - small.width) // 2, (PORTRAIT - small.height) // 2))
    return out


def make_portrait_from_bust(bust: Image.Image) -> Image.Image:
    w, h = bust.size
    side = min(w, h)
    crop = bust.crop(((w - side) // 2, 0, (w - side) // 2 + side, side))
    small = integer_downscale(crop, PORTRAIT)
    out = Image.new("RGBA", (PORTRAIT, PORTRAIT), (0, 0, 0, 0))
    out.alpha_composite(small, ((PORTRAIT - small.width) // 2, (PORTRAIT - small.height) // 2))
    return out


def _load_front_png(path: Path) -> Image.Image:
    """已经是透明背景的正面图：只要裁到 alpha bbox 再清杂点。"""
    img = Image.open(path).convert("RGBA")
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
    return _drop_specks(img, min_area=60)


def process(short: str, spec: dict, *, write: bool) -> dict:
    if "front" in spec:
        front = _load_front_png(SRC / spec["front"])
        angry = None
    else:
        sheet = Image.open(SRC / spec["sheet"]).convert("RGB")
        argue = Image.open(SRC / spec["argue"]).convert("RGB")
        front = cut_figure(sheet.crop(_cell_boxes(sheet.width, sheet.height)[FRONT_PANEL]))
        angry = cut_figure(argue)

    method = spec.get("method", "median")
    idle = fit_frame(front, method)
    head = make_portrait(front, spec.get("head_ratio", 0.46), method,
                         spec.get("head_offset", 0.0))
    portraits = {
        "neutral": head,
        "happy": head,
        "sad": head,
        "surprised": make_portrait_from_bust(angry) if angry is not None else head,
    }
    if write:
        (ROOT / "assets" / "characters" / "npc").mkdir(parents=True, exist_ok=True)
        idle.save(ROOT / "assets" / "characters" / "npc" / f"{short}_idle.png")
        for mood, img in portraits.items():
            out = ROOT / "assets" / "portraits" / short / f"{mood}.png"
            out.parent.mkdir(parents=True, exist_ok=True)
            img.save(out)
    return {"idle": idle, "portraits": portraits}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="接入两个 NPC 立绘与头像")
    parser.add_argument("--verify", action="store_true", help="只出核对图，不写 assets")
    args = parser.parse_args(argv)

    results = {short: process(short, spec, write=not args.verify) for short, spec in CHARACTERS.items()}

    cell = 96
    sheet = Image.new("RGB", (cell * 5, cell * len(results) + 18), (26, 28, 34))
    draw = ImageDraw.Draw(sheet)
    for row, (short, data) in enumerate(results.items()):
        y = 18 + row * cell
        draw.text((4, y - 14), f"{short}", fill=(240, 220, 140))
        idle = data["idle"].resize((cell, cell), Image.NEAREST)
        sheet.paste(idle, (0, y), idle)
        for i, (mood, img) in enumerate(data["portraits"].items()):
            tile = img.resize((cell, cell), Image.NEAREST)
            sheet.paste(tile, (cell * (i + 1), y), tile)
    out = ROOT / "build" / "_npc_contact.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    print("contact sheet ->", out)
    for short, data in results.items():
        print(f"{short}: idle + {len(data['portraits'])} 张头像")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
