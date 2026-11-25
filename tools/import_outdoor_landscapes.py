"""导入 `素材/景观植物/` 中的新景观与植物贴图到游戏资源中。

用法：
    python tools/import_outdoor_landscapes.py --verify   # 只生成核对图，不写 assets
    python tools/import_outdoor_landscapes.py            # 写 assets/campus/textures/props/*.png 并更新 manifest 与 LICENSES
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
SRC_CANDIDATES = (ROOT.parent / "素材" / "景观植物", ROOT / "素材" / "景观植物")
SRC = next((p for p in SRC_CANDIDATES if p.is_dir()), SRC_CANDIDATES[0])
OUT_DIR = ROOT / "assets" / "campus" / "textures" / "props"
LICENSE_ID = "LIC-0219"

#: 源文件名 -> (props 输出名, 目标 PNG 高度像素, 游戏世界高度米, 是否移除内部纯白镂空)
LANDSCAPE_SPECS: dict[str, tuple[str, int, float, bool]] = {
    "樱花树.jpg": ("cherry_tree", 256, 4.4, True),
    "银杏树.jpg": ("ginkgo_tree", 256, 4.5, True),
    "雪松.jpg": ("pine_tree", 256, 4.8, False),
    "垂柳.jpg": ("willow_tree", 256, 4.6, True),
    "翠竹丛.jpg": ("bamboo", 200, 3.4, True),
    "灌木丛.jpg": ("bush", 88, 1.2, False),
    "花丛.jpg": ("flower_shrub", 96, 1.3, False),
    "绿篱.jpg": ("hedge", 84, 1.1, False),
    "石盆栽.jpg": ("potted_plant", 120, 1.6, False),
    "凉亭.jpg": ("pavilion", 232, 4.0, True),
    "假山景石.jpg": ("rockery", 128, 1.9, True),
    "荷花池.jpg": ("lotus_pond", 180, 3.6, False),
}


def _flood_outer_white(rgb: np.ndarray, min_val: int = 232, max_sat: int = 18) -> np.ndarray:
    """从四条边向内泛洪标记纯白/近白背景。"""
    h, w, _ = rgb.shape
    cmin = rgb.min(axis=2)
    cmax = rgb.max(axis=2)
    near_white = (cmin >= min_val) & ((cmax - cmin) <= max_sat)
    bg = np.zeros((h, w), dtype=bool)
    q: deque[tuple[int, int]] = deque()

    for x in range(w):
        for y in (0, h - 1):
            if near_white[y, x] and not bg[y, x]:
                bg[y, x] = True
                q.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if near_white[y, x] and not bg[y, x]:
                bg[y, x] = True
                q.append((y, x))

    while q:
        cy, cx = q.popleft()
        for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
            if 0 <= ny < h and 0 <= nx < w and not bg[ny, nx] and near_white[ny, nx]:
                bg[ny, nx] = True
                q.append((ny, nx))
    return bg


def _remove_interior_white_pockets(
    rgb: np.ndarray, bg: np.ndarray, min_val: int = 242, max_sat: int = 12
) -> np.ndarray:
    """移除被树枝、凉亭立柱或竹竿围住的纯白镂空区域。"""
    h, w, _ = rgb.shape
    cmin = rgb.min(axis=2)
    cmax = rgb.max(axis=2)
    pure_white = (cmin >= min_val) & ((cmax - cmin) <= max_sat) & (~bg)
    visited = np.zeros((h, w), dtype=bool)
    out_bg = bg.copy()

    ys, xs = np.nonzero(pure_white)
    for sy, sx in zip(ys.tolist(), xs.tolist()):
        if visited[sy, sx]:
            continue
        q: deque[tuple[int, int]] = deque([(sy, sx)])
        visited[sy, sx] = True
        comp: list[tuple[int, int]] = []
        while q:
            cy, cx = q.popleft()
            comp.append((cy, cx))
            for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                if 0 <= ny < h and 0 <= nx < w and not visited[ny, nx] and pure_white[ny, nx]:
                    visited[ny, nx] = True
                    q.append((ny, nx))
        if len(comp) >= 6:
            for cy, cx in comp:
                out_bg[cy, cx] = True
    return out_bg


def _dehalo_and_crop(img: Image.Image, drop_pockets: bool, target_h: int) -> Image.Image:
    rgb = np.asarray(img.convert("RGB"), dtype=np.int16)
    bg = _flood_outer_white(rgb)
    if drop_pockets:
        bg = _remove_interior_white_pockets(rgb, bg)

    # 吃掉紧贴外轮廓 1~2px 的亮白抗锯齿光晕（只在亮度高、饱和度低时吃掉）
    alpha = np.where(bg, 0, 255).astype(np.uint8)
    for _ in range(2):
        dilated_bg = np.asarray(
            Image.fromarray(np.where(alpha == 0, 255, 0).astype(np.uint8)).filter(
                ImageFilter.MaxFilter(3)
            )
        ) > 0
        cmin = rgb.min(axis=2)
        cmax = rgb.max(axis=2)
        halo = dilated_bg & (alpha > 0) & (cmin >= 185) & ((cmax - cmin) <= 28)
        if not halo.any():
            break
        alpha[halo] = 0

    rgba = np.dstack((rgb.astype(np.uint8), alpha))
    rgba[alpha == 0, :3] = 0
    cut = Image.fromarray(rgba, "RGBA")
    bbox = cut.getchannel("A").getbbox()
    if bbox is None:
        raise RuntimeError("抠图后无前景内容")
    cut = cut.crop(bbox)

    # 预乘 alpha 缩放，避免白/黑边缘溢色，然后二值化 alpha 适配 M_binary
    arr = np.asarray(cut, dtype=np.float32)
    a = arr[:, :, 3:4] / 255.0
    premul = np.concatenate([arr[:, :, :3] * a, arr[:, :, 3:4]], axis=2)
    target_w = max(1, round(cut.width * target_h / cut.height))

    # 分通道做 Lanczos 缩放
    scaled_channels = []
    for ch in range(4):
        ch_img = Image.fromarray(np.clip(premul[:, :, ch], 0, 255).astype(np.uint8), "L")
        ch_scaled = ch_img.resize((target_w, target_h), Image.Resampling.LANCZOS)
        scaled_channels.append(np.asarray(ch_scaled, dtype=np.float32))
    sa = scaled_channels[3]
    keep = sa >= 128.0
    out_rgb = np.zeros((target_h, target_w, 3), dtype=np.uint8)
    factor = np.where(keep, 255.0 / np.maximum(sa, 1.0), 0.0)
    for ch in range(3):
        out_rgb[:, :, ch] = np.clip(np.round(scaled_channels[ch] * factor), 0, 255).astype(np.uint8)
    out_alpha = np.where(keep, 255, 0).astype(np.uint8)

    out_rgba = np.dstack((out_rgb, out_alpha))
    out_rgba[out_alpha == 0, :3] = 0
    result = Image.fromarray(out_rgba, "RGBA")
    final_bbox = result.getchannel("A").getbbox()
    return result.crop(final_bbox) if final_bbox else result


def _make_contact_sheet(results: list[tuple[str, Image.Image, float]], out_path: Path) -> None:
    zoom = 2
    max_w = max(im.width for _, im, _ in results) * zoom
    total_h = sum(im.height * zoom + 16 for _, im, _ in results) + 24
    sheet = Image.new("RGB", (max_w * 2 + 260, total_h), (28, 30, 36))
    draw = ImageDraw.Draw(sheet)
    y = 16
    for short, im, hm in results:
        tile = im.resize((im.width * zoom, im.height * zoom), Image.Resampling.NEAREST)
        draw.text((8, y + 4), f"{short}\n{im.width}x{im.height}px\n{hm:.2f}m H", fill=(240, 224, 150))
        mag = Image.new("RGB", tile.size, (230, 40, 230))
        mag.paste(tile, (0, 0), tile)
        sheet.paste(mag, (220, y))
        grass = Image.new("RGB", tile.size, (105, 140, 74))
        grass.paste(tile, (0, 0), tile)
        sheet.paste(grass, (232 + max_w, y))
        y += tile.height + 16
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path)


def _update_manifest_and_licenses(results: list[tuple[str, Image.Image, float]]) -> None:
    mp = ROOT / "assets" / "manifest.json"
    man = json.loads(mp.read_text(encoding="utf-8"))
    items = man["assets"] if isinstance(man, dict) and "assets" in man else man
    by_id = {entry["id"]: entry for entry in items}
    asset_ids: list[str] = []
    added = 0
    for short, im, height_m in results:
        asset_id = f"campus_texture_prop_{short}"
        asset_ids.append(asset_id)
        width_m = round(height_m * im.width / max(1, im.height), 3)
        entry = {
            "id": asset_id,
            "type": "image",
            "path": f"campus/textures/props/{short}.png",
            "license_id": LICENSE_ID,
            "tags": ["final", "prop_card", "generated_landscape"],
            "raw": {
                "canvas": [im.width, im.height],
                "width_m": width_m,
                "height_m": height_m,
            },
        }
        if asset_id in by_id:
            by_id[asset_id].update(entry)
        else:
            items.append(entry)
            added += 1
    mp.write_text(json.dumps(man, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lp = ROOT / "assets" / "LICENSES.csv"
    with lp.open("r", encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
        fieldnames = list(rows[0].keys())
    new_row = {
        "license_id": LICENSE_ID,
        "asset_ids": ";".join(asset_ids),
        "author": "AI 生成与项目整合（景观植物扩展）",
        "source_url": "素材/景观植物/",
        "license": "项目内 AI 生成景观植物素材",
        "commercial_ok": "yes",
        "modified": "yes",
        "date_added": "2026-11-25",
        "notes": "由 tools/import_outdoor_landscapes.py 去白底/镂空去背/二值 alpha 缩放导入，共 12 种室外景观与植物立牌",
    }
    replaced = False
    for row in rows:
        if row.get("license_id") == LICENSE_ID:
            row.update(new_row)
            replaced = True
            break
    if not replaced:
        rows.append(new_row)
    with lp.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"manifest updated: {len(results)} assets (added {added}), license {LICENSE_ID} synced")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="导入室外景观与植物素材")
    parser.add_argument("--verify", action="store_true", help="只输出核对图")
    parser.add_argument(
        "--preview-path",
        type=Path,
        default=ROOT / "build" / "_outdoor_landscapes_preview.png",
    )
    args = parser.parse_args(argv)

    results: list[tuple[str, Image.Image, float]] = []
    for filename, (short, target_h, height_m, drop_pockets) in LANDSCAPE_SPECS.items():
        src = SRC / filename
        if not src.exists():
            raise FileNotFoundError(f"缺少源文件: {src}")
        art = _dehalo_and_crop(Image.open(src), drop_pockets=drop_pockets, target_h=target_h)
        results.append((short, art, height_m))

    _make_contact_sheet(results, args.preview_path)
    print("preview ->", args.preview_path)

    if not args.verify:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        for short, art, height_m in results:
            target = OUT_DIR / f"{short}.png"
            art.save(target, format="PNG", optimize=True)
            w_m = height_m * art.width / max(1, art.height)
            print(f"  saved {short:14s} {art.width:3d}x{art.height:3d} px -> {w_m:.2f}m W x {height_m:.2f}m H")
        _update_manifest_and_licenses(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
