"""Import Nailong from the user-provided transparent direction PNGs.

The third NPC keeps its existing `xiaoyou` asset ids for save compatibility.
Only `01_FRONT.png` is used for the current portrait and scene card; the other
transparent views remain available for a future directional animation sheet.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT.parent / "素材" / "人物"
FRONT_SOURCE = "01_FRONT.png"
PORTRAIT_BOX = (20, 0, 620, 600)
PORTRAIT_SIZE = 96
FRAME_SIZE = 48
BODY_HEIGHT = 40
FEET_Y = 46


def load_front(source_dir: Path) -> Image.Image:
    source = source_dir / FRONT_SOURCE
    image = Image.open(source).convert("RGBA")
    bbox = image.getchannel("A").getbbox()
    if bbox is None:
        raise RuntimeError(f"{source}: alpha channel is empty")
    return image.crop(bbox)


def fit_idle(full_body: Image.Image) -> Image.Image:
    scale = BODY_HEIGHT / max(1, full_body.height)
    if full_body.width * scale > FRAME_SIZE - 4:
        scale = (FRAME_SIZE - 4) / max(1, full_body.width)
    size = (max(1, round(full_body.width * scale)), max(1, round(full_body.height * scale)))
    figure = full_body.resize(size, Image.Resampling.NEAREST)
    frame = Image.new("RGBA", (FRAME_SIZE, FRAME_SIZE), (0, 0, 0, 0))
    frame.alpha_composite(figure, ((FRAME_SIZE - figure.width) // 2, FEET_Y - figure.height))
    return frame


def make_portrait(source: Image.Image) -> Image.Image:
    x0, y0, x1, y1 = PORTRAIT_BOX
    crop = source.crop((x0, y0, min(x1, source.width), min(y1, source.height)))
    side = max(crop.width, crop.height)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.alpha_composite(crop, ((side - crop.width) // 2, 0))
    return canvas.resize((PORTRAIT_SIZE, PORTRAIT_SIZE), Image.Resampling.NEAREST)


def make_contact_sheet(idle: Image.Image, portraits: dict[str, Image.Image], target: Path) -> None:
    cell = 96
    sheet = Image.new("RGB", (cell * 5, cell + 24), (26, 28, 34))
    draw = ImageDraw.Draw(sheet)
    sheet.paste(idle.resize((cell, cell), Image.Resampling.NEAREST), (0, 24), idle.resize((cell, cell), Image.Resampling.NEAREST))
    for index, (mood, portrait) in enumerate(portraits.items(), start=1):
        tile = portrait.resize((cell, cell), Image.Resampling.NEAREST)
        sheet.paste(tile, (cell * index, 24), tile)
        draw.text((cell * index + 3, 6), mood, fill=(240, 220, 140))
    target.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(target, format="PNG", optimize=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE_DIR)
    parser.add_argument("--verify", action="store_true", help="only write the review sheet")
    args = parser.parse_args(argv)

    front = load_front(args.source)
    idle = fit_idle(front)
    portrait = make_portrait(front)
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
