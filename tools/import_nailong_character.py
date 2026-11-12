"""Import the user-provided Nailong pixel character sheet.

The third NPC keeps its existing internal ids (`npc_xiaoyou`), so save data and
relationship rules remain compatible.  The display name is 奈珑.
"""

from __future__ import annotations

import argparse
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent / "素材" / "人物" / "奈珑八向图.jfif"
PORTRAIT_BOX = (80, 50, 700, 670)
FULL_BOX = (70, 40, 710, 1950)
PORTRAIT_SIZE = 96
FRAME_SIZE = 48
BODY_HEIGHT = 40
FEET_Y = 46


def remove_connected_background(image: Image.Image) -> Image.Image:
    """Remove white paper connected to the crop border while keeping white clothing."""
    rgb = np.asarray(image.convert("RGB"))
    pale = (rgb.min(axis=2) >= 242) & ((rgb.max(axis=2) - rgb.min(axis=2)) <= 20)
    h, w = pale.shape
    background = np.zeros_like(pale, dtype=bool)
    queue: deque[tuple[int, int]] = deque()
    for x in range(w):
        if pale[0, x]:
            queue.append((0, x))
        if pale[h - 1, x]:
            queue.append((h - 1, x))
    for y in range(h):
        if pale[y, 0]:
            queue.append((y, 0))
        if pale[y, w - 1]:
            queue.append((y, w - 1))
    while queue:
        y, x = queue.popleft()
        if background[y, x] or not pale[y, x]:
            continue
        background[y, x] = True
        if y:
            queue.append((y - 1, x))
        if y + 1 < h:
            queue.append((y + 1, x))
        if x:
            queue.append((y, x - 1))
        if x + 1 < w:
            queue.append((y, x + 1))
    rgba = np.dstack((rgb, np.where(background, 0, 255).astype(np.uint8)))
    rgba[background, :3] = 0
    result = Image.fromarray(rgba, mode="RGBA")
    bbox = result.getchannel("A").getbbox()
    return result.crop(bbox) if bbox else result


def fit_idle(full_body: Image.Image) -> Image.Image:
    scale = BODY_HEIGHT / max(1, full_body.height)
    if full_body.width * scale > FRAME_SIZE - 4:
        scale = (FRAME_SIZE - 4) / max(1, full_body.width)
    size = (max(1, round(full_body.width * scale)), max(1, round(full_body.height * scale)))
    figure = full_body.resize(size, Image.Resampling.NEAREST)
    frame = Image.new("RGBA", (FRAME_SIZE, FRAME_SIZE), (0, 0, 0, 0))
    frame.alpha_composite(figure, ((FRAME_SIZE - figure.width) // 2, FEET_Y - figure.height))
    return frame


def make_contact_sheet(idle: Image.Image, portraits: dict[str, Image.Image], target: Path) -> None:
    cell = 96
    sheet = Image.new("RGB", (cell * 5, cell + 24), (26, 28, 34))
    sheet.paste(idle.resize((cell, cell), Image.Resampling.NEAREST), (0, 24), idle.resize((cell, cell), Image.Resampling.NEAREST))
    for index, (mood, portrait) in enumerate(portraits.items(), start=1):
        tile = portrait.resize((cell, cell), Image.Resampling.NEAREST)
        sheet.paste(tile, (cell * index, 24), tile)
        ImageDraw.Draw(sheet).text((cell * index + 3, 6), mood, fill=(240, 220, 140))
    target.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(target, format="PNG", optimize=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--verify", action="store_true", help="only write the review sheet")
    args = parser.parse_args(argv)

    sheet = Image.open(args.source).convert("RGB")
    portrait = remove_connected_background(sheet.crop(PORTRAIT_BOX)).resize(
        (PORTRAIT_SIZE, PORTRAIT_SIZE), Image.Resampling.NEAREST
    )
    full_body = remove_connected_background(sheet.crop(FULL_BOX))
    idle = fit_idle(full_body)
    portraits = {mood: portrait.copy() for mood in ("neutral", "happy", "sad", "surprised")}

    review = ROOT / "reports" / "review" / "npc" / "nailong_sheet.png"
    make_contact_sheet(idle, portraits, review)
    if not args.verify:
        idle_target = ROOT / "assets" / "characters" / "npc" / "xiaoyou_idle.png"
        idle_target.parent.mkdir(parents=True, exist_ok=True)
        idle.save(idle_target, format="PNG", optimize=True)
        for mood, image in portraits.items():
            target = ROOT / "assets" / "portraits" / "xiaoyou" / f"{mood}.png"
            target.parent.mkdir(parents=True, exist_ok=True)
            image.save(target, format="PNG", optimize=True)

    print(f"idle={idle.size} portraits={PORTRAIT_SIZE}x{PORTRAIT_SIZE} review={review}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
