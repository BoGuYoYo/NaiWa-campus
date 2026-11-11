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

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT.parent / "素材" / "人物"

FRAME = 48
BODY_HEIGHT = 40
FEET_Y = 46
PORTRAIT = 96

#: 角色表里第 0 个面板是正面（FRONT）
FRONT_PANEL = 0

CHARACTERS = {
    "sumo": {"sheet": "符闹吃.jfif", "argue": "符闹吃争论.jfif", "name": "符闹吃"},
    "chenlang": {"sheet": "李振兴.jfif", "argue": "李振兴争论.jfif", "name": "李振兴"},
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


def fit_frame(figure: Image.Image) -> Image.Image:
    """缩到 40 px 高（太宽按宽度收），脚底贴 y=46，水平居中放进 48×48。"""
    scale = BODY_HEIGHT / figure.height
    if figure.width * scale > FRAME - 4:
        scale = (FRAME - 4) / figure.width
    size = (max(1, round(figure.width * scale)), max(1, round(figure.height * scale)))
    fig = figure.resize(size, Image.NEAREST)
    frame = Image.new("RGBA", (FRAME, FRAME), (0, 0, 0, 0))
    frame.alpha_composite(fig, ((FRAME - fig.width) // 2, max(0, FEET_Y - fig.height)))
    # 缩到 48 后再清一次孤立点（原始大图里的标签残渣会缩成 1~2 px）
    return _drop_specks(frame, min_area=8)


def make_portrait(figure: Image.Image) -> Image.Image:
    """头肩特写：取上方 46%，按 1:1 居中裁切。"""
    w, h = figure.size
    head_h = max(1, int(h * 0.46))
    head_w = min(w, head_h)
    left = (w - head_w) // 2
    crop = figure.crop((left, 0, left + head_w, head_h))
    side = max(crop.width, crop.height)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.alpha_composite(crop, ((side - crop.width) // 2, 0))
    return canvas.resize((PORTRAIT, PORTRAIT), Image.NEAREST)


def make_portrait_from_bust(bust: Image.Image) -> Image.Image:
    w, h = bust.size
    side = min(w, h)
    crop = bust.crop(((w - side) // 2, 0, (w - side) // 2 + side, side))
    return crop.resize((PORTRAIT, PORTRAIT), Image.NEAREST)


def process(short: str, spec: dict, *, write: bool) -> dict:
    sheet = Image.open(SRC / spec["sheet"]).convert("RGB")
    argue = Image.open(SRC / spec["argue"]).convert("RGB")
    front = cut_figure(sheet.crop(_cell_boxes(sheet.width, sheet.height)[FRONT_PANEL]))
    angry = cut_figure(argue)

    idle = fit_frame(front)
    portraits = {
        "neutral": make_portrait(front),
        "happy": make_portrait(front),
        "sad": make_portrait(front),
        "surprised": make_portrait_from_bust(angry),
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
