"""把 `素材/场外物品/` 生成的操场/广场素材接进游戏（A 侧整合工具）。

两类输入：

1. **道具立牌**（11 张）：去背景 → 裁到物体 → 按占地宽度缩放到 24 px/m
   → `assets/campus/textures/props/<名>.png`。卡片宽度 = 占地宽度，
   渲染高度写进 manifest 的 `raw.height_m`（= 画布高 / 24）。
2. **场地地面**（2 张）：
   - `操场` 去掉白边后等比缩到 288×336（12 m × 14 m）；
   - `中心广场地面` 居中裁到 20:16 再缩到 480×384（20 m × 16 m），整块铺满广场。

背景有四种：棋盘格（浅/深）、纯白、纯灰、纯黑。做法统一成：
采样边缘环的主要颜色 → 从四边泛洪 → 剩下的连通块里"含两种边缘色"的判成棋盘格口袋
→ 外扩 1 px 吃掉抗锯齿光晕 → 只保留大块前景 → 裁到物体。

用法：
    python tools/import_outdoor_props.py --verify   # 只出核对图
    python tools/import_outdoor_props.py            # 写 assets 并更新 manifest
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
SRC_CANDIDATES = (ROOT.parent / "素材" / "场外物品", ROOT / "素材" / "场外物品")
SRC = next((p for p in SRC_CANDIDATES if p.is_dir()), SRC_CANDIDATES[0])
OUT_DIR = ROOT / "assets" / "campus" / "textures"
LICENSE_ID = "LIC-0215"

#: 源文件名 -> (输出名, 占地宽度米)
PROPS: dict[str, tuple[str, float]] = {
    "足球门.jfif": ("goal", 3.0),
    "篮筐.jfif": ("basket", 2.0),
    "栏架.jfif": ("hurdle", 1.5),
    "计分板.jfif": ("scoreboard", 2.0),
    "场边长椅.jfif": ("bench_sport", 2.0),
    "广场长椅.jfif": ("bench_plaza", 2.0),
    "花坛.jfif": ("flowerbed", 3.0),
    "喷泉.jfif": ("fountain", 5.0),
    "校训石碑.jfif": ("stele", 2.4),
    "公告亭.jfif": ("kiosk", 2.4),
}

#: 地面：源文件名 -> (输出名, 目标像素 (w, h), 是否抠背景)
GROUNDS: dict[str, tuple[str, tuple[int, int], bool]] = {
    # 操场那张四周是白边，要抠掉；广场那张是满幅铺装，抠了会把砖缝当背景
    "操场.jfif": ("ground_playground", (288, 336), True),
    "中心广场地面.jfif": ("ground_plaza", (480, 384), False),
}

PX_PER_M = 24


# ---------------------------------------------------------------------------
# 去背景
# ---------------------------------------------------------------------------
def _border_tones(rgb: np.ndarray) -> list[tuple[int, int, int]]:
    """采样边缘环，返回出现最多的 1~3 种颜色（棋盘格会有两种）。"""
    h, w, _ = rgb.shape
    ring = []
    step = max(1, w // 200)
    for x in range(0, w, step):
        ring.append(tuple(rgb[0, x]))
        ring.append(tuple(rgb[h - 1, x]))
    step = max(1, h // 200)
    for y in range(0, h, step):
        ring.append(tuple(rgb[y, 0]))
        ring.append(tuple(rgb[y, w - 1]))
    quant = Counter((r // 8 * 8, g // 8 * 8, b // 8 * 8) for r, g, b in ring)
    total = len(ring)
    tones = [tone for tone, count in quant.most_common(3) if count >= total * 0.08]
    return tones or [quant.most_common(1)[0][0]]


def _tone_mask(rgb: np.ndarray, tones, tol: int = 14) -> np.ndarray:
    mask = np.zeros(rgb.shape[:2], dtype=bool)
    for tone in tones:
        diff = np.abs(rgb.astype(int) - np.array(tone, dtype=int)).max(axis=2)
        mask |= diff <= tol
    return mask


def _flood_from_border(mask: np.ndarray) -> np.ndarray:
    """在 mask 上从四边泛洪，返回与外界连通的像素。"""
    h, w = mask.shape
    canvas = Image.fromarray(np.where(mask, 255, 0).astype(np.uint8), "L").convert("RGB")
    arr = np.array(canvas)
    seeds = [(x, y) for x in range(1, w - 1, max(1, w // 120)) for y in (1, h - 2)]
    seeds += [(x, y) for y in range(1, h - 1, max(1, h // 120)) for x in (1, w - 2)]
    for seed in seeds:
        if arr[seed[1], seed[0], 0] == 255:
            ImageDraw.floodfill(canvas, seed, (128, 128, 128), thresh=0)
            arr = np.array(canvas)
    return arr[:, :, 0] == 128


def _keep_large(fg: np.ndarray, min_area_ratio: float = 0.02) -> np.ndarray:
    """保留够大的连通块（相对最大块面积），丢掉碎屑——碎屑会把 bbox 撑大。"""
    canvas = Image.fromarray(np.where(fg, 255, 0).astype(np.uint8), "L").convert("RGB")
    work = np.array(canvas)[:, :, 0].copy()
    comps: list[np.ndarray] = []
    while True:
        idx = np.argwhere(work == 255)
        if not len(idx):
            break
        y0, x0 = int(idx[0][0]), int(idx[0][1])
        ImageDraw.floodfill(canvas, (x0, y0), (128, 128, 128), thresh=0)
        arr = np.array(canvas)[:, :, 0]
        comps.append(arr == 128)
        canvas = Image.fromarray(np.where(arr == 255, 255, 0).astype(np.uint8), "L").convert("RGB")
        work = np.array(canvas)[:, :, 0]
    if not comps:
        return fg
    biggest = max(int(c.sum()) for c in comps)
    threshold = max(64, int(biggest * min_area_ratio))
    kept = np.zeros_like(fg)
    for comp in comps:
        if comp.sum() >= threshold:
            kept |= comp
    return kept


def _close_mask(mask: np.ndarray, radius: int = 4) -> np.ndarray:
    """闭运算：把棋盘格的细格线（1~3 px）连起来，让泛洪能走完整块背景。"""
    size = radius * 2 + 1
    img = Image.fromarray(np.where(mask, 255, 0).astype(np.uint8), "L")
    img = img.filter(ImageFilter.MaxFilter(size)).filter(ImageFilter.MinFilter(size))
    return np.array(img) > 0


def cut_background(img: Image.Image, tol: int = 26) -> Image.Image:
    rgb = np.array(img.convert("RGB"))
    tones = _border_tones(rgb)
    mask = _tone_mask(rgb, tones, tol)

    # 1) 闭运算后再从四边泛洪：棋盘格的细格线会把背景切成互不相连的格子，
    #    不闭一下的话泛洪只能在贴边的几个格子里打转（实测 55% 的候选只淹到 12%）。
    bg = _flood_from_border(_close_mask(mask))

    # 2) 被物体围住的背景口袋（长椅条板之间、凉亭立柱之间的空格）：
    #    连通块颜色落在边缘色上、且面积不大，就一并抠掉。
    flat = rgb.astype(int)
    for _ in range(120):
        rest = mask & ~bg
        if not rest.any():
            break
        ys, xs = np.nonzero(rest)
        seed = (int(xs[0]), int(ys[0]))
        canvas = Image.fromarray(np.where(rest, 255, 0).astype(np.uint8), "L").convert("RGB")
        ImageDraw.floodfill(canvas, seed, (128, 128, 128), thresh=0)
        comp = np.array(canvas)[:, :, 0] == 128
        area = comp.mean()
        hit = False
        for tone in tones:
            diff = np.abs(flat[comp] - np.array(tone, dtype=int)).max(axis=1)
            if (diff <= tol + 6).mean() >= 0.80 and area < 0.05:
                hit = True
                break
        if hit:
            bg |= comp
        mask = mask & ~comp

    # 3) 外扩 2 px，吃掉抗锯齿光晕（只吃同样接近边缘色的像素）
    grown = np.array(Image.fromarray(np.where(bg, 255, 0).astype(np.uint8), "L")
                     .filter(ImageFilter.MaxFilter(5))) > 0
    bg = bg | (grown & mask)

    fg = _keep_large(~bg)

    out = img.convert("RGBA")
    out.putalpha(Image.fromarray(np.where(fg, 255, 0).astype(np.uint8), "L"))
    bbox = out.getbbox()
    return out.crop(bbox) if bbox else out


# ---------------------------------------------------------------------------
# 落位
# ---------------------------------------------------------------------------
def _fit_width(obj: Image.Image, width_px: int) -> Image.Image:
    scale = width_px / obj.width
    size = (max(1, width_px), max(1, round(obj.height * scale)))
    return obj.resize(size, Image.NEAREST if scale >= 1 else Image.LANCZOS)


def _fit_exact(obj: Image.Image, size: tuple[int, int]) -> Image.Image:
    return obj.resize(size, Image.LANCZOS)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="导入操场/广场素材")
    parser.add_argument("--verify", action="store_true", help="只出核对图，不写 assets")
    args = parser.parse_args(argv)

    results: list[tuple[str, str, Image.Image, float]] = []
    missing: list[str] = []

    for name, (short, width_m) in PROPS.items():
        src = SRC / name
        if not src.exists():
            missing.append(name)
            continue
        art = _fit_width(cut_background(Image.open(src)), round(width_m * PX_PER_M))
        results.append(("props", short, art, width_m))

    for name, (short, size, need_cut) in GROUNDS.items():
        src = SRC / name
        if not src.exists():
            missing.append(name)
            continue
        cut = cut_background(Image.open(src)) if need_cut else Image.open(src).convert("RGBA")
        # 居中裁到目标比例，再缩到目标像素（避免拉伸变形）
        target_ratio = size[0] / size[1]
        w, h = cut.size
        if w / h > target_ratio:
            new_w = round(h * target_ratio)
            cut = cut.crop(((w - new_w) // 2, 0, (w - new_w) // 2 + new_w, h))
        else:
            new_h = round(w / target_ratio)
            cut = cut.crop((0, (h - new_h) // 2, w, (h - new_h) // 2 + new_h))
        art = _fit_exact(cut, size)
        results.append(("areas", short, art, size[0] / PX_PER_M))

    # 核对图：品红底上看抠图边缘
    zoom = 2
    rows = results
    width = max(a.width for _, _, a, _ in rows) * zoom + 240
    height = sum(a.height * zoom + 14 for _, _, a, _ in rows) + 30
    sheet = Image.new("RGB", (width, height), (26, 28, 34))
    draw = ImageDraw.Draw(sheet)
    y = 20
    for kind, short, art, _w in rows:
        tile = art.resize((art.width * zoom, art.height * zoom), Image.NEAREST)
        draw.text((4, y), f"{kind}/{short} {art.width}x{art.height}", fill=(240, 220, 140))
        box = Image.new("RGB", tile.size, (230, 40, 230))
        box.paste(tile, (0, 0), tile)
        sheet.paste(box, (230, y))
        y += tile.height + 14
    out = ROOT / "build" / "_outdoor_props.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    print("contact sheet ->", out)

    if missing:
        print("缺图:", "、".join(missing))

    if not args.verify:
        for kind, short, art, _w in results:
            path = (OUT_DIR / "props" / f"{short}.png") if kind == "props" \
                else (OUT_DIR / f"{short}.png")
            path.parent.mkdir(parents=True, exist_ok=True)
            art.save(path)
        _update_manifest(results)

    for kind, short, art, width_m in results:
        print(f"{kind:6s} {short:12s} {art.width}x{art.height}  "
              f"宽 {art.width / PX_PER_M:.2f} m  高 {art.height / PX_PER_M:.2f} m  目标宽 {width_m} m")
    return 0


def _update_manifest(results) -> None:
    mp = ROOT / "assets" / "manifest.json"
    man = json.loads(mp.read_text(encoding="utf-8"))
    items = man["assets"] if isinstance(man, dict) and "assets" in man else man
    by_id = {entry["id"]: entry for entry in items}
    added = 0
    for kind, short, art, _w in results:
        asset_id = (f"campus_texture_prop_{short}" if kind == "props"
                    else f"campus_texture_area_{short.removeprefix('ground_')}")
        rel = (f"campus/textures/props/{short}.png" if kind == "props"
               else f"campus/textures/{short}.png")
        entry = {
            "id": asset_id,
            "type": "image",
            "path": rel,
            "license_id": LICENSE_ID,
            "tags": ["final", "generated_from_user_art"],
            "raw": {
                "canvas": [art.width, art.height],
                "width_m": round(art.width / PX_PER_M, 3),
                "height_m": round(art.height / PX_PER_M, 3),
            },
        }
        if asset_id in by_id:
            by_id[asset_id].update(entry)
        else:
            items.append(entry)
            added += 1
    mp.write_text(json.dumps(man, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"manifest: {len(results)} 条，其中新增 {added}")


if __name__ == "__main__":
    raise SystemExit(main())
