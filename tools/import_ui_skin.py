"""Import the generated UI skin into the existing ``assets/ui`` paths.

The current delivery is a set of JPEG sheets rather than 29 same-named PNGs:
six standalone icons, a 3x3 activity sheet, one shared keycap, a five-element
dot/bar/cursor sheet, and a panel.  Source files stay read-only.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DEFAULT = ROOT.parent / "素材" / "UI"
UI_ROOT = ROOT / "assets" / "ui"
SHEET_OUT = ROOT / "reports" / "review" / "ui_skin_sheet.png"
LICENSE_ID = "LIC-0210"
SOURCE_SIZES: dict[str, tuple[int, int]] = {}

ASSETS = {
    "ui_panel_9slice": ("ui/panel_9slice.png", (48, 48)),
    "ui_icon_academic": ("ui/icons/academic.png", (16, 16)),
    "ui_icon_stamina": ("ui/icons/stamina.png", (16, 16)),
    "ui_icon_mood": ("ui/icons/mood.png", (16, 16)),
    "ui_icon_social": ("ui/icons/social.png", (16, 16)),
    "ui_icon_interest": ("ui/icons/interest.png", (16, 16)),
    "ui_icon_energy": ("ui/icons/energy.png", (16, 16)),
    "ui_icon_attend_class": ("ui/icons/activity_attend_class.png", (16, 16)),
    "ui_icon_library_study": ("ui/icons/activity_library_study.png", (16, 16)),
    "ui_icon_play_games": ("ui/icons/activity_play_games.png", (16, 16)),
    "ui_icon_create_work": ("ui/icons/activity_create_work.png", (16, 16)),
    "ui_icon_join_club": ("ui/icons/activity_join_club.png", (16, 16)),
    "ui_icon_exercise": ("ui/icons/activity_exercise.png", (16, 16)),
    "ui_icon_eat_canteen": ("ui/icons/activity_eat_canteen.png", (16, 16)),
    "ui_icon_rest_dorm": ("ui/icons/activity_rest_dorm.png", (16, 16)),
    "ui_icon_campus_walk": ("ui/icons/activity_campus_walk.png", (16, 16)),
    "ui_key_e": ("ui/keys/e.png", (16, 16)),
    "ui_key_w": ("ui/keys/w.png", (16, 16)),
    "ui_key_a": ("ui/keys/a.png", (16, 16)),
    "ui_key_s": ("ui/keys/s.png", (16, 16)),
    "ui_key_d": ("ui/keys/d.png", (16, 16)),
    "ui_key_space": ("ui/keys/space.png", (16, 16)),
    "ui_key_tab": ("ui/keys/tab.png", (16, 16)),
    "ui_key_esc": ("ui/keys/esc.png", (16, 16)),
    "ui_slot_full": ("ui/slot_full.png", (8, 8)),
    "ui_slot_empty": ("ui/slot_empty.png", (8, 8)),
    "ui_bar_frame": ("ui/bar_frame.png", (100, 8)),
    "ui_bar_fill": ("ui/bar_fill.png", (100, 8)),
    "ui_cursor": ("ui/cursor.png", (8, 8)),
}

SINGLE = {
    "ui_icon_academic": "学士帽.jfif",
    "ui_icon_stamina": "哑铃.jfif",
    "ui_icon_mood": "爱心.jfif",
    "ui_icon_social": "气泡.jfif",
    "ui_icon_interest": "星星.jfif",
    "ui_icon_energy": "闪电.jfif",
}
ACTIVITY_IDS = (
    "ui_icon_attend_class", "ui_icon_library_study", "ui_icon_play_games",
    "ui_icon_create_work", "ui_icon_join_club", "ui_icon_exercise",
    "ui_icon_eat_canteen", "ui_icon_rest_dorm", "ui_icon_campus_walk",
)
KEYS = {
    "ui_key_e": "E", "ui_key_w": "W", "ui_key_a": "A", "ui_key_s": "S",
    "ui_key_d": "D", "ui_key_space": "SPACE", "ui_key_tab": "TAB", "ui_key_esc": "ESC",
}
PALETTE = [
    (0x2B, 0x22, 0x35), (0x1B, 0x1F, 0x2A), (0x2C, 0x34, 0x46), (0x3A, 0x44, 0x58),
    (0xF7, 0xC8, 0x1E), (0xFF, 0xDD, 0x5C), (0xD9, 0xA4, 0x17), (0xF1, 0xE2, 0xBC),
    (0xFF, 0xF6, 0xDF), (0xE3, 0xCE, 0x9E), (0x4C, 0x4A, 0x2F), (0x6A, 0x6A, 0x45),
    (0x35, 0x33, 0x20), (0x1A, 0x17, 0x12), (0xFF, 0xFB, 0xEE), (0xC0, 0xA1, 0x5F),
    (0xE8, 0xCF, 0x97), (0xF2, 0xF2, 0xF2), (0xB8, 0xBF, 0xC9), (0x7A, 0x82, 0x8F),
    (0x4A, 0x50, 0x5C), (0xC0, 0x48, 0x3F), (0xE2, 0x8B, 0x3A), (0x4F, 0x8A, 0x5B),
    (0x8F, 0xC0, 0x8A), (0x3F, 0x6E, 0xA8), (0x8F, 0xB6, 0xDC), (0x8F, 0xD3, 0xC7),
    (0x7A, 0x5A, 0xA8), (0xE0, 0x91, 0xB0), (0x8A, 0x6A, 0x46), (0xF4, 0xD2, 0xB0),
]
FONT_3X5 = {
    "A": ("010", "101", "111", "101", "101"), "B": ("110", "101", "110", "101", "110"),
    "D": ("110", "101", "101", "101", "110"),
    "E": ("111", "100", "110", "100", "111"), "S": ("011", "100", "010", "001", "110"),
    "T": ("111", "010", "010", "010", "010"), "W": ("101", "101", "111", "111", "101"),
    "C": ("011", "100", "100", "100", "011"),
}
FONT_2X3 = {
    "S": ("11", "10", "01"), "P": ("11", "11", "10"), "A": ("01", "10", "11"),
    "C": ("11", "10", "11"), "E": ("11", "11", "10"),
}


def source_file(source: Path, name: str) -> Path | None:
    p = source / name
    if p.exists():
        return p
    for ext in (".jfif", ".jpg", ".jpeg", ".png", ".webp"):
        p = (source / Path(name).stem).with_suffix(ext)
        if p.exists():
            return p
    return None


def load_rgba(path: Path) -> Image.Image:
    return Image.open(path).convert("RGBA")


def _background_mask(rgb: np.ndarray) -> np.ndarray:
    """Flood-fill neutral light/gray pixels connected to the image border."""
    data = rgb.astype(np.int16)
    sat = data.max(axis=2) - data.min(axis=2)
    lum = data.mean(axis=2)
    candidate = (sat <= 28) & (lum >= 100) & (lum <= 255)
    h, w = candidate.shape
    seen = np.zeros((h, w), dtype=bool)
    q: deque[tuple[int, int]] = deque()
    for x in range(w):
        for y in (0, h - 1):
            if candidate[y, x]:
                seen[y, x] = True; q.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if candidate[y, x] and not seen[y, x]:
                seen[y, x] = True; q.append((y, x))
    while q:
        y, x = q.popleft()
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= ny < h and 0 <= nx < w and candidate[ny, nx] and not seen[ny, nx]:
                seen[ny, nx] = True; q.append((ny, nx))
    return seen


def remove_baked_background(image: Image.Image) -> Image.Image:
    if "A" in image.getbands() and image.getchannel("A").getextrema() != (255, 255):
        return image
    rgb = np.asarray(image.convert("RGB"))
    alpha = np.where(_background_mask(rgb), 0, 255).astype(np.uint8)
    rgba = np.dstack((rgb, alpha))
    rgba[alpha == 0, :3] = 0
    return Image.fromarray(rgba, "RGBA")


def trim(image: Image.Image) -> Image.Image:
    box = image.getchannel("A").getbbox()
    if box is None:
        raise ValueError("没有检测到前景")
    return image.crop(box)


def _runs(flags: np.ndarray) -> list[tuple[int, int]]:
    out = []; start = None
    for i, flag in enumerate(flags):
        if flag and start is None: start = i
        if not flag and start is not None: out.append((start, i)); start = None
    if start is not None: out.append((start, len(flags)))
    return out


def components(image: Image.Image, min_area_ratio: float = 0.0003) -> list[tuple[int, int, int, int]]:
    alpha = np.asarray(image.getchannel("A")) > 0
    boxes = []
    min_area = max(64, int(alpha.size * min_area_ratio))
    for y0, y1 in _runs(alpha.any(axis=1)):
        for x0, x1 in _runs(alpha[y0:y1].any(axis=0)):
            if (x1 - x0) * (y1 - y0) >= min_area:
                boxes.append((x0, y0, x1, y1))
    return boxes


def crop_sheet(image: Image.Image, count: int, *, min_area_ratio: float = 0.0003) -> list[Image.Image]:
    boxes = components(image, min_area_ratio)
    if len(boxes) != count:
        raise ValueError(f"合成图期望 {count} 个元素，实际检测到 {len(boxes)} 个：{boxes}")
    return [trim(image.crop(box)) for box in boxes]


def fit_nearest(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Fit on an integer-multiple canvas, then reduce by an integer factor."""
    w, h = size
    factor = max(math.ceil(image.width / w), math.ceil(image.height / h), 1)
    canvas = Image.new("RGBA", (w * factor, h * factor), (0, 0, 0, 0))
    canvas.alpha_composite(image.convert("RGBA"), ((canvas.width - image.width) // 2,
                                                     (canvas.height - image.height) // 2))
    return canvas.resize(size, Image.Resampling.NEAREST)


def palette_image() -> Image.Image:
    pal = Image.new("P", (1, 1)); flat = [v for rgb in PALETTE for v in rgb]
    pal.putpalette(flat + [0] * (768 - len(flat)))
    return pal


def quantize(image: Image.Image) -> Image.Image:
    rgb = np.asarray(image.convert("RGB"), dtype=np.int16)
    palette = np.asarray(PALETTE, dtype=np.int16)
    distances = ((rgb[:, :, None, :] - palette[None, None, :, :]) ** 2).sum(axis=3)
    reduced = palette[np.argmin(distances, axis=2)].astype(np.uint8)
    alpha = np.asarray(image.getchannel("A"))
    rgba = np.dstack((reduced, alpha))
    rgba[alpha == 0, :3] = 0
    return Image.fromarray(rgba, "RGBA")


def draw_key(image: Image.Image, text: str) -> Image.Image:
    out = image.copy(); color = (255, 246, 223, 255)
    if text == "SPACE":
        width = 5 * 2 + 4
        x0 = (16 - width) // 2
        for i, ch in enumerate(text):
            for y, row in enumerate(FONT_2X3[ch]):
                for x, bit in enumerate(row):
                    if bit == "1": out.putpixel((x0 + i * 3 + x, 6 + y), color)
        return out
    width = len(text) * 3 + max(0, len(text) - 1)
    x0 = (16 - width) // 2
    for n, ch in enumerate(text):
        glyph = FONT_3X5.get(ch)
        if glyph is None: continue
        for row, line in enumerate(glyph):
            for col, bit in enumerate(line):
                if bit == "1": out.putpixel((x0 + n * 4 + col, 5 + row), color)
    return out


def panel_9slice(image: Image.Image) -> Image.Image:
    # The supplied panel is already a complete frame. Keep the large artwork
    # but normalize it to the requested 48x48 target with nearest sampling.
    out = fit_nearest(trim(remove_baked_background(image)), (48, 48))
    # Normalize the corners and the stretchable center after quantization-sized
    # fitting. This keeps the existing UI consumer safe even before it gains a
    # true runtime nine-slice implementation.
    data = np.asarray(out).copy()
    corner = data[:16, :16].copy()
    data[:16, -16:] = corner[:, ::-1]
    data[-16:, :16] = corner[::-1, :]
    data[-16:, -16:] = corner[::-1, ::-1]
    data[16:32, 16:32] = data[24, 24]
    return Image.fromarray(data, "RGBA")


def process(source: Path, only: str | None = None) -> tuple[dict[str, Image.Image], list[str], list[str]]:
    result: dict[str, Image.Image] = {}; skipped: list[str] = []; failed: list[str] = []
    def need(asset: str, filename: str) -> Path | None:
        p = source_file(source, filename)
        if p is None:
            skipped.append(asset); print(f"SKIP {asset}（源文件不存在：{filename}）")
        return p
    def note_source(ids: tuple[str, ...] | list[str], path: Path) -> None:
        size = Image.open(path).size
        for asset_id in ids:
            SOURCE_SIZES[asset_id] = size
    selected = set(ASSETS if only is None else [only])

    if selected.intersection(SINGLE):
        for aid, filename in SINGLE.items():
            if aid not in selected: continue
            p = need(aid, filename)
            if p:
                try:
                    note_source([aid], p)
                    result[aid] = quantize(fit_nearest(trim(remove_baked_background(load_rgba(p))), (16, 16)))
                except Exception as exc: failed.append(aid); print(f"FAIL {aid}: {exc}")

    if selected.intersection(ACTIVITY_IDS):
        p = need("ui_icon_attend_class", "活动图标.jfif")
        if p:
            try:
                note_source(list(ACTIVITY_IDS), p)
                sprites = crop_sheet(remove_baked_background(load_rgba(p)), 9, min_area_ratio=0.0008)
                for aid, sprite in zip(ACTIVITY_IDS, sprites):
                    if aid in selected: result[aid] = quantize(fit_nearest(sprite, (16, 16)))
            except Exception as exc:
                for aid in ACTIVITY_IDS:
                    if aid in selected: failed.append(aid)
                print(f"FAIL activity_sheet: {exc}")

    if selected.intersection(KEYS):
        p = need("ui_key_e", "按钮.jfif")
        if p:
            try:
                note_source(list(KEYS), p)
                key = fit_nearest(trim(remove_baked_background(load_rgba(p))), (16, 16))
                for aid, label in KEYS.items():
                    if aid in selected: result[aid] = quantize(draw_key(key, label))
            except Exception as exc:
                for aid in KEYS:
                    if aid in selected: failed.append(aid)
                print(f"FAIL keycap: {exc}")

    sheet_ids = {"ui_slot_full", "ui_slot_empty", "ui_bar_frame", "ui_bar_fill", "ui_cursor"}
    if selected.intersection(sheet_ids):
        p = need("ui_slot_full", "时段点  数值条  光标.jfif")
        if p:
            try:
                note_source(["ui_slot_full", "ui_slot_empty", "ui_bar_frame", "ui_bar_fill", "ui_cursor"], p)
                sprites = crop_sheet(remove_baked_background(load_rgba(p)), 5, min_area_ratio=0.0002)
                sizes = [(8, 8), (8, 8), (100, 8), (100, 8), (8, 8)]
                for aid, sprite, size in zip(("ui_slot_full", "ui_slot_empty", "ui_bar_frame", "ui_bar_fill", "ui_cursor"), sprites, sizes):
                    if aid in selected: result[aid] = quantize(fit_nearest(sprite, size))
            except Exception as exc:
                for aid in sheet_ids:
                    if aid in selected: failed.append(aid)
                print(f"FAIL dot_bar_cursor_sheet: {exc}")

    if "ui_panel_9slice" in selected:
        p = need("ui_panel_9slice", "面板.jfif")
        if p:
            try:
                note_source(["ui_panel_9slice"], p)
                result["ui_panel_9slice"] = quantize(panel_9slice(load_rgba(p)))
            except Exception as exc: failed.append("ui_panel_9slice"); print(f"FAIL ui_panel_9slice: {exc}")
    return result, skipped, failed


def write_assets(assets: dict[str, Image.Image]) -> None:
    for aid, image in assets.items():
        rel, _ = ASSETS[aid]; path = ROOT / "assets" / rel; path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path, "PNG", optimize=True)
        colors = len(image.convert("RGBA").getcolors(maxcolors=1_000_000) or [])
        source_size = SOURCE_SIZES.get(aid)
        source_label = f"{source_size[0]}x{source_size[1]} -> " if source_size else ""
        print(f"OK {aid} {source_label}{image.width}x{image.height} colors={colors}")


def update_registry() -> None:
    manifest_path = ROOT / "assets" / "manifest.json"
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    ui_ids = set(ASSETS)
    for entry in raw["assets"]:
        if entry.get("id") in ui_ids:
            entry["license_id"] = LICENSE_ID
            entry["tags"] = ["final", "ui", "generated_from_user_art"]
    manifest_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    licenses_path = ROOT / "assets" / "LICENSES.csv"
    rows = []
    with licenses_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows = [row for row in rows if row.get("license_id") != LICENSE_ID]
    rows.append({
        "license_id": LICENSE_ID,
        "asset_ids": ";".join(ASSETS),
        "author": "用户提供的 AI 生成素材（UI 皮肤）",
        "source_url": "素材/UI/",
        "license": "用户提供的 AI 生成素材（生成工具与条款版本见素材来源说明）",
        "commercial_ok": "yes",
        "modified": "yes",
        "date_added": "2026-11-09",
        "notes": "由 tools/import_ui_skin.py 去背/最近邻缩放/量化到 32 色；面板 48×48 边距 16、图标 16×16、键帽 16×16、点 8×8、条 100×8",
    })
    fields = ["license_id", "asset_ids", "author", "source_url", "license", "commercial_ok", "modified", "date_added", "notes"]
    with licenses_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\r\n")
        writer.writeheader(); writer.writerows(rows)


def _symmetry(data: np.ndarray, border: int = 16) -> bool:
    b = data[:border, :border]
    return np.array_equal(b, data[:border, -border:][:, ::-1]) and np.array_equal(b, data[-border:, :border][::-1, :]) and np.array_equal(b, data[-border:, -border:][::-1, ::-1])


def verify() -> int:
    problems = 0
    print("asset_id | 尺寸 | 颜色数 | 有 alpha | 四角对称 | 结论")
    for aid, (rel, size) in ASSETS.items():
        path = ROOT / "assets" / rel
        if not path.exists():
            print(f"{aid} | - | - | - | - | MISSING"); problems += 1; continue
        original = Image.open(path)
        rgba_ok = original.format == "PNG" and original.mode == "RGBA"
        im = original.convert("RGBA"); data = np.asarray(im); colors = len(im.getcolors(maxcolors=1_000_000) or [])
        alpha = data[:, :, 3]; alpha_ok = alpha.min() == 0 and alpha.max() == 255
        binary_alpha_ok = set(np.unique(alpha)).issubset({0, 255})
        transparent_rgb_ok = bool(np.all(data[alpha == 0, :3] == 0))
        corner = _symmetry(data) if aid == "ui_panel_9slice" else True
        colors_ok = {tuple(int(c) for c in p[:3]) for p in data.reshape(-1, 4) if p[3] > 0}.issubset(set(PALETTE))
        bar_ok = True
        if aid in {"ui_bar_frame", "ui_bar_fill"}:
            bar_ok = np.array_equal(data[:, :2], data[:, -2:])
        center_ok = True
        if aid == "ui_panel_9slice":
            center_ok = len({tuple(v) for v in data[16:32, 16:32, :3].reshape(-1, 3)}) <= 3
        ok = (im.size == size and rgba_ok and alpha_ok and binary_alpha_ok and transparent_rgb_ok
              and corner and bar_ok and center_ok and colors_ok)
        if not ok: problems += 1
        detail = "OK" if ok else "FAIL"
        print(f"{aid} | {im.width}x{im.height} | {colors} | {'yes' if alpha_ok else 'no'} | {'yes' if corner else 'no'} | {detail}")
    print(f"{len(ASSETS)-problems}/{len(ASSETS)} 通过")
    return 0 if problems == 0 else 1


def contact_sheet() -> None:
    ids = list(ASSETS); cell_w, cell_h, scale, cols = 420, 120, 4, 8
    rows = (len(ids) + cols - 1) // cols
    sheet = Image.new("RGBA", (cols * cell_w, rows * cell_h), (27, 31, 42, 255)); draw = ImageDraw.Draw(sheet)
    for i, aid in enumerate(ids):
        rel, _ = ASSETS[aid]; path = ROOT / "assets" / rel
        if not path.exists(): continue
        im = Image.open(path).convert("RGBA"); big = im.resize((im.width * scale, im.height * scale), Image.Resampling.NEAREST)
        x = (i % cols) * cell_w + (cell_w - big.width) // 2; y = (i // cols) * cell_h + 4
        sheet.alpha_composite(big, (x, y)); draw.text(((i % cols) * cell_w + 4, (i // cols) * cell_h + 88), aid.replace("ui_", ""), fill=(244,241,232,255))
    SHEET_OUT.parent.mkdir(parents=True, exist_ok=True); sheet.save(SHEET_OUT, "PNG", optimize=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=SOURCE_DEFAULT)
    parser.add_argument("--only")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    if args.verify: return verify()
    assets, skipped, failed = process(args.source, args.only)
    write_assets(assets); contact_sheet()
    if args.only is None and assets:
        update_registry()
    if failed: print("失败:", ", ".join(sorted(set(failed))), file=sys.stderr); return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
