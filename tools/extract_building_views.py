"""Extract front and side elevations from the supplied architectural sheets.

The four source sheets are reference boards, not game textures: each contains a
front elevation, a side elevation and a roof plan.  This tool crops the two
elevations, removes only background connected to the crop border, and writes
transparent PNGs suitable for the game's two-card building renderer.
"""

from __future__ import annotations

import argparse
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT.parent / "素材" / "建筑"
DEFAULT_OUT = ROOT / "assets" / "campus" / "textures"


# Boxes are in the 2752x1536 source sheets.  They deliberately include a small
# white margin so the border flood can remove guide lines without touching the
# building outline.
VIEWS: dict[str, dict[str, tuple[int, int, int, int]]] = {
    "dorm": {
        "source": "宿舍楼三视图.jfif",
        "front": (145, 55, 1790, 850),
        "side": (1870, 55, 2690, 820),
    },
    "library": {
        "source": "图书馆三视图.jfif",
        "front": (170, 45, 1370, 710),
        "side": (1690, 45, 2635, 710),
    },
    "club": {
        "source": "社团中心三视图.jfif",
        "front": (205, 85, 1640, 710),
        "side": (1690, 55, 2650, 710),
    },
    "teaching": {
        "source": "教学楼三视图.jfif",
        "front": (120, 45, 1570, 740),
        "side": (1680, 45, 2680, 740),
    },
}


def _background_mask(rgb: np.ndarray) -> np.ndarray:
    """Return pixels that can belong to the pale sheet background."""
    lo = rgb.min(axis=2).astype(np.int16)
    hi = rgb.max(axis=2).astype(np.int16)
    # White paper and light grey construction guides.  The flood step below
    # keeps enclosed cream walls and windows even when their colors are close.
    return (lo >= 215) & ((hi - lo) <= 18)


def _flood_background(rgb: np.ndarray) -> np.ndarray:
    """Mark background pixels connected to any crop edge."""
    candidate = _background_mask(rgb)
    h, w = candidate.shape
    seen = np.zeros_like(candidate, dtype=bool)
    queue: deque[tuple[int, int]] = deque()

    for x in range(w):
        if candidate[0, x]:
            queue.append((0, x))
        if candidate[h - 1, x]:
            queue.append((h - 1, x))
    for y in range(h):
        if candidate[y, 0]:
            queue.append((y, 0))
        if candidate[y, w - 1]:
            queue.append((y, w - 1))

    while queue:
        y, x = queue.popleft()
        if seen[y, x] or not candidate[y, x]:
            continue
        seen[y, x] = True
        if y:
            queue.append((y - 1, x))
        if y + 1 < h:
            queue.append((y + 1, x))
        if x:
            queue.append((y, x - 1))
        if x + 1 < w:
            queue.append((y, x + 1))
    return seen


def _remove_small_components(alpha: np.ndarray, min_area: int = 2000) -> np.ndarray:
    """Drop isolated guide marks and dimension dashes left inside a crop."""
    mask = alpha > 0
    h, w = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    keep = np.zeros_like(mask, dtype=bool)
    components: list[list[tuple[int, int]]] = []
    for y, x in zip(*np.nonzero(mask)):
        if seen[y, x]:
            continue
        stack = [(int(y), int(x))]
        seen[y, x] = True
        component: list[tuple[int, int]] = []
        while stack:
            cy, cx = stack.pop()
            component.append((cy, cx))
            for ny, nx in (
                (cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1),
                (cy - 1, cx - 1), (cy - 1, cx + 1),
                (cy + 1, cx - 1), (cy + 1, cx + 1),
            ):
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
        components.append(component)
    if not components:
        return alpha
    largest = max(range(len(components)), key=lambda i: len(components[i]))
    for index, component in enumerate(components):
        if index == largest or len(component) >= min_area:
            for cy, cx in component:
                keep[cy, cx] = True
    result = alpha.copy()
    result[~keep] = 0
    return result


def extract_view(image: Image.Image, box: tuple[int, int, int, int]) -> Image.Image:
    crop = image.crop(box).convert("RGB")
    rgb = np.asarray(crop)
    background = _flood_background(rgb)
    alpha = np.where(background, 0, 255).astype(np.uint8)
    alpha = _remove_small_components(alpha)
    rgba = np.dstack((rgb, alpha))
    rgba[alpha == 0, :3] = 0
    result = Image.fromarray(rgba, mode="RGBA")
    bbox = result.getchannel("A").getbbox()
    if bbox is None:
        raise RuntimeError(f"empty crop {box}")
    # Keep a transparent breathing room around the outline so filtering in the
    # game does not clip roof edges or entrance steps.
    pad = 4
    x0 = max(0, bbox[0] - pad)
    y0 = max(0, bbox[1] - pad)
    x1 = min(result.width, bbox[2] + pad)
    y1 = min(result.height, bbox[3] + pad)
    return result.crop((x0, y0, x1, y1))


def _sheet(items: list[tuple[str, Image.Image]], out: Path) -> None:
    scale = 0.30
    gap = 30
    label_h = 42
    widths = [round(im.width * scale) for _, im in items]
    heights = [round(im.height * scale) + label_h for _, im in items]
    canvas = Image.new("RGB", (sum(widths) + gap * (len(items) + 1), max(heights) + gap), (27, 31, 42))
    draw = ImageDraw.Draw(canvas)
    x = gap
    for label, im in items:
        thumb = im.resize((round(im.width * scale), round(im.height * scale)), Image.Resampling.LANCZOS)
        canvas.paste(thumb, (x, gap), thumb)
        draw.text((x, gap + thumb.height + 8), label, fill=(240, 240, 240))
        x += thumb.width + gap
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, format="PNG", optimize=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--only", choices=sorted(VIEWS))
    parser.add_argument("--preview", type=Path, default=ROOT / "reports" / "review" / "building_views_sheet.png")
    args = parser.parse_args(argv)

    selected = [args.only] if args.only else list(VIEWS)
    previews: list[tuple[str, Image.Image]] = []
    for name in selected:
        spec = VIEWS[name]
        source = args.source / spec["source"]
        image = Image.open(source).convert("RGB")
        for view_name in ("front", "side"):
            result = extract_view(image, spec[view_name])
            if view_name == "side":
                # The sheets label the side elevation as the building's left
                # side; mirror it before using it as the game's right side.
                result = ImageOps.mirror(result)
            target = args.out / f"{name}_{view_name}.png"
            target.parent.mkdir(parents=True, exist_ok=True)
            result.save(target, format="PNG", optimize=True)
            previews.append((f"{name} {view_name} {result.size[0]}x{result.size[1]}", result))
            print(f"OK {name}_{view_name} {source.name} -> {target.name} {result.size[0]}x{result.size[1]}")

    _sheet(previews, args.preview)
    print(f"PREVIEW {args.preview}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
