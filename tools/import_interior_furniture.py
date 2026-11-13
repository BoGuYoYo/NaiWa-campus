"""把 `素材/家具/` 生成的家具图接进室内场景（A 侧整合工具）。

每张图：去棋盘格底 → 裁到物体 → 等比缩进规格画布（底边贴齐、水平居中）→
写 `assets/interior/<building>/furn_<short>.png` + 更新 manifest。

画布尺寸 = 占地宽度 × （实物高 + 0.34 × 可视进深），24 px/米；
渲染时 `height = 画布高 / 24`，`make_prop_card` 会按贴图比例还原成占地宽度。

用法：
    python tools/import_interior_furniture.py --verify   # 只出核对图
    python tools/import_interior_furniture.py            # 写 assets 并更新 manifest
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SRC_CANDIDATES = (ROOT.parent / "素材" / "家具", ROOT / "素材" / "家具")
SRC = next((p for p in SRC_CANDIDATES if p.is_dir()), SRC_CANDIDATES[0])

#: 文件名 -> (building 短名, furniture 短 id, 画布尺寸)
#: building 短名与地板/墙面贴图保持一致：dorm / teaching / library / club / canteen
FURNITURE = {
    "上下铺": ("dorm", "bed", (96, 60)),
    "书桌": ("dorm", "dorm_desk", (72, 34)),
    "书柜": ("dorm", "wardrobe", (32, 52)),           # 交的是「书柜」，占衣柜的位置
    "课桌连排（北）": ("teaching", "desk_row_n", (144, 28)),
    "课桌连排（南）": ("teaching", "desk_row_s", (144, 28)),
    "讲台": ("teaching", "podium", (96, 32)),
    "阅览长桌": ("library", "reading_table", (96, 36)),
    "书架（西）": ("library", "shelf_w", (24, 49)),
    "书架（北）": ("library", "shelf_n", (120, 50)),
    "服务台": ("library", "service_desk", (72, 31)),
    "电脑桌": ("club", "pc_desk", (72, 35)),
    "画架": ("club", "easel", (30, 40)),
    "公告板": ("club", "notice_board", (48, 22)),
    "沙发": ("club", "sofa", (72, 28)),
    "打饭窗口": ("canteen", "food_window", (192, 41)),
    "长餐桌（东）": ("canteen", "table_e", (120, 29)),
    "长餐桌（西）": ("canteen", "table_w", (120, 29)),
}
LICENSE_ID = "LIC-0212"


def _checker_colors(img: Image.Image) -> tuple[int, int, int]:
    """估出棋盘格两档灰度与方格边长。

    两档取"中性灰像素里出现最多的两个值"（比只看第一行稳，行首可能正好压在格子缝上）；
    边长取多条行扫描的中位数。
    """
    arr = np.array(img.convert("RGB")).astype(int)
    bright = arr[:, :, 1]
    neutral = (arr.max(axis=2) - arr.min(axis=2)) <= 10
    values = bright[neutral]
    if values.size == 0:
        return 47, 109, 32
    hist = np.bincount(values.astype(np.uint8), minlength=256)
    tone0 = int(np.argmax(hist))
    masked = hist.copy()
    masked[max(0, tone0 - 18):min(256, tone0 + 19)] = 0
    tone1 = int(np.argmax(masked)) if masked.sum() > 0 else tone0 + 60

    runs = []
    for y in range(2, 12):
        row = arr[y, :, 1]
        changes = [x for x in range(1, len(row)) if abs(int(row[x]) - int(row[x - 1])) > 20]
        runs += [changes[i + 1] - changes[i] for i in range(min(6, max(0, len(changes) - 1)))]
    square = int(np.median(runs)) if runs else 32
    return tone0, tone1, max(8, square)


def _flood_from_border(band: np.ndarray) -> np.ndarray:
    """在 band 掩码上从四边 floodfill，返回与外界连通的背景像素。"""
    mask = Image.fromarray(
        np.stack([np.where(band, 255, 0).astype(np.uint8)] * 3, axis=2), "RGB"
    )
    w, h = mask.size
    arr = np.array(mask)
    seeds = [(x, y) for x in range(2, w - 2, 12) for y in (2, 3, h - 4, h - 3)]
    seeds += [(x, y) for y in range(2, h - 2, 12) for x in (2, 3, w - 4, w - 3)]
    for seed in seeds:
        if arr[seed[1], seed[0], 0] == 255:
            ImageDraw.floodfill(mask, seed, (128, 128, 128), thresh=0)
            arr = np.array(mask)
    return arr[:, :, 0] == 128


def _cut_object(img: Image.Image) -> Image.Image:
    """去棋盘格底。

    棋盘格是两档灰；只按颜色抠会连家具的深灰一起吃掉，只按连通抠又填不到
    "桌子底下"这种被围住的口袋。做法分三步：
      1. 用两档灰构成的 band 从四边 floodfill，拿到外部背景；
      2. 剩下的 band 连通块逐块判断：同时出现两种棋盘灰 → 是口袋（也抠掉），
         只有一种灰 → 是家具自己的灰（保留）；
      3. 背景外扩 4 px 并只吃中性灰，补掉格子缝。
    """
    from PIL import ImageFilter

    rgb = img.convert("RGB")
    arr = np.array(rgb).astype(int)
    v = arr[:, :, 1]
    neutral = (arr.max(axis=2) - arr.min(axis=2)) <= 12
    t0, t1, _square = _checker_colors(rgb)
    low, high = min(t0, t1), max(t0, t1)
    band = neutral & (v >= low - 6) & (v <= high + 6)

    bg = _flood_from_border(band)

    # 2) 被围住的棋盘格口袋
    for _ in range(60):
        rest = band & ~bg
        if not rest.any():
            break
        ys, xs = np.nonzero(rest)
        seed = (int(xs[0]), int(ys[0]))
        mask = Image.fromarray(
            np.stack([np.where(rest, 255, 0).astype(np.uint8)] * 3, axis=2), "RGB"
        )
        ImageDraw.floodfill(mask, seed, (128, 128, 128), thresh=0)
        comp = np.array(mask)[:, :, 0] == 128
        near0 = (np.abs(v[comp] - t0) <= 8).mean()
        near1 = (np.abs(v[comp] - t1) <= 8).mean()
        if near0 >= 0.15 and near1 >= 0.15:      # 两种灰都在 → 棋盘格
            bg |= comp
        else:
            bg |= comp & False                    # 保留（家具自己的灰）
            band = band & ~comp                    # 从候选里摘掉，避免反复扫到

    # 3) 补格子缝
    grown = np.array(
        Image.fromarray(np.where(bg, 255, 0).astype(np.uint8)).filter(ImageFilter.MaxFilter(9))
    ) > 0
    bg = bg | (grown & neutral)

    # 只保留足够大的前景块：碎片会把 bbox 撑到整张图，家具被缩得很小
    fg = ~bg
    fg = _keep_large(fg, min_area_ratio=0.02)

    out = rgb.convert("RGBA")
    out.putalpha(Image.fromarray(np.where(fg, 255, 0).astype(np.uint8)))
    bbox = out.getbbox()
    return out.crop(bbox) if bbox else out


def _keep_large(fg: np.ndarray, min_area_ratio: float = 0.02) -> np.ndarray:
    """保留最大的若干连通块，丢掉零散碎片（面积小于最大块 2% 的都算碎片）。"""
    mask = Image.fromarray(np.stack([np.where(fg, 255, 0).astype(np.uint8)] * 3, axis=2), "RGB")
    work = np.array(mask)[:, :, 0].copy()
    total = int(fg.sum())
    kept = np.zeros_like(fg)
    min_area = max(64, int(total * min_area_ratio))
    while True:
        idx = np.argwhere(work == 255)
        if not len(idx):
            break
        y0, x0 = int(idx[0][0]), int(idx[0][1])
        ImageDraw.floodfill(mask, (x0, y0), (128, 128, 128), thresh=0)
        arr = np.array(mask)[:, :, 0]
        comp = arr == 128
        if comp.sum() >= min_area:
            kept |= comp
        mask = Image.fromarray(np.stack([np.where(arr == 255, 255, 0).astype(np.uint8)] * 3, axis=2), "RGB")
        work = np.array(mask)[:, :, 0]
    return kept


def _fit(obj: Image.Image, size: tuple[int, int]) -> Image.Image:
    """缩到画布尺寸（铺满；AI 出图比例本来就和占地比例不完全一致）。

    先按宽度缩、高度超了再按高度缩，最后居中放进去——保证不裁掉任何部分。
    """
    cw, ch = size
    canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    scale = min(cw / obj.width, ch / obj.height)
    new_size = (max(1, round(obj.width * scale)), max(1, round(obj.height * scale)))
    resized = obj.resize(new_size, Image.LANCZOS)
    canvas.alpha_composite(resized, ((cw - new_size[0]) // 2, ch - new_size[1]))
    return canvas


def _trim(obj: Image.Image) -> Image.Image:
    """裁掉透明留白。

    留白不能留：渲染时 `height = 画布高 / 24`、宽度按贴图比例反推，
    多出来的透明边会被算进实物尺寸里——打饭窗口就是这样变成
    "8 米宽的空画布中间摆一个 2.7 米的小台子"。
    裁到物体之后画布 = 实物，比例才是真的。
    """
    bbox = obj.getbbox()
    return obj.crop(bbox) if bbox else obj



def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="导入室内家具图")
    parser.add_argument("--verify", action="store_true", help="只出核对图，不写 assets")
    args = parser.parse_args(argv)

    results = []
    missing = []
    for name, (building, short, size) in FURNITURE.items():
        src = SRC / f"{name}.jfif"
        if not src.exists():
            missing.append(name)
            continue
        art = _trim(_fit(_cut_object(Image.open(src)), size))
        results.append((building, short, art.size, art))
        if not args.verify:
            out = ROOT / "assets" / "interior" / building / f"furn_{short}.png"
            out.parent.mkdir(parents=True, exist_ok=True)
            art.save(out)

    zoom = 2
    rows = sorted(results, key=lambda item: (item[0], -item[2][0]))
    height = sum(size[1] * zoom + 12 for _, _, size, _ in rows) + 24
    width = max(size[0] for _, _, size, _ in rows) * zoom + 200
    sheet = Image.new("RGB", (width, height), (26, 28, 34))
    draw = ImageDraw.Draw(sheet)
    y = 18
    for building, short, size, art in rows:
        tile = art.resize((size[0] * zoom, size[1] * zoom), Image.NEAREST)
        draw.text((4, y), f"{building}/{short} {size[0]}x{size[1]}", fill=(240, 220, 140))
        sheet.paste(tile, (190, y), tile)
        y += size[1] * zoom + 12
    out = ROOT / "build" / "_interior_furniture.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    print("contact sheet ->", out)

    if missing:
        print("缺图（保留盒子占位）:", "、".join(missing))
    if not args.verify:
        _update_manifest(results)
    print(f"处理 {len(results)} 件家具")
    return 0


def _update_manifest(results) -> None:
    mp = ROOT / "assets" / "manifest.json"
    man = json.loads(mp.read_text(encoding="utf-8"))
    items = man["assets"] if isinstance(man, dict) and "assets" in man else man
    by_id = {entry["id"]: entry for entry in items}
    added = 0
    for building, short, size, _art in results:
        asset_id = f"furn_{building}_{short}"
        entry = {
            "id": asset_id,
            "type": "image",
            "path": f"interior/{building}/furn_{short}.png",
            "license_id": "LIC-0214",
            "tags": ["final", "generated_from_user_art"],
            "raw": {"canvas": list(size), "height_m": round(size[1] / 24.0, 3)},
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
