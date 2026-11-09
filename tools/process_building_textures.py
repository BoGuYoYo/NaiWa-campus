"""Import the five user-supplied front elevations as transparent PNG textures.

The supplied JPEGs have a checkerboard baked into their RGB pixels. Their pale
walls are the same colors as the backdrop, so color-keying cannot distinguish
them. These outlines were traced against the five 2752x1536 originals. Only the
outside of each building is removed; all facade artwork remains unchanged.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


BUILDINGS = {
    "teaching": "教学楼.jfif",
    "dorm": "宿舍楼.jfif",
    "library": "图书馆.jfif",
    "club": "社团中心.jfif",
    "canteen": "食堂.jfif",
}

# Coordinates on half-size (1376x768) reference images, including rooftop
# equipment and entrance steps. These describe the five supplied images,
# not a general-purpose background remover for future artwork.
OUTLINES = {
    "teaching": (
        (618, 47), (757, 47), (763, 94), (763, 104),
        (756, 104), (756, 169), (762, 169), (767, 238),
        (1167, 238), (1209, 311), (1210, 338), (1213, 339),
        (1213, 350), (1208, 350), (1208, 685), (1212, 687),
        (1212, 721), (982, 721), (960, 699), (852, 699),
        (857, 713), (857, 720), (519, 720), (519, 713),
        (525, 699), (414, 699), (398, 722), (164, 722),
        (164, 687), (168, 685), (168, 350), (163, 350),
        (163, 339), (166, 338), (166, 312), (208, 238),
        (608, 238), (613, 169), (620, 169), (620, 104),
        (614, 104), (614, 84),
    ),
    "dorm": (
        (256, 103), (832, 103), (832, 93), (837, 90),
        (870, 90), (872, 103), (891, 103), (894, 62),
        (898, 57), (905, 53), (911, 53), (923, 57),
        (943, 60), (946, 63), (946, 93), (959, 93),
        (959, 103), (965, 103), (966, 84), (971, 80),
        (1009, 80), (1010, 103), (1095, 103),
        (1177, 239), (1176, 249), (1168, 251), (1168, 696),
        (504, 696), (498, 712), (477, 712), (477, 710),
        (385, 710), (384, 712), (368, 712), (368, 696),
        (183, 696), (183, 251), (176, 250), (175, 240),
    ),
    "library": (
        (394, 95), (462, 95), (462, 82), (463, 79),
        (468, 78), (472, 80), (472, 95), (487, 95),
        (488, 80), (491, 78), (495, 78), (498, 80),
        (498, 95), (860, 95), (860, 93), (882, 93),
        (882, 95), (983, 95), (1132, 157), (1137, 157),
        (1137, 295), (1129, 298), (1127, 502), (1132, 538),
        (1128, 540), (1132, 680), (870, 680), (870, 725),
        (828, 725), (828, 721), (549, 721), (549, 725),
        (506, 725), (506, 680), (243, 680), (249, 540),
        (245, 539), (249, 299), (238, 296), (238, 158),
        (244, 157),
    ),
    "club": (
        (320, 122), (1121, 132), (1110, 284), (1110, 325),
        (1127, 325), (1128, 346), (1110, 401), (1110, 521),
        (1128, 521), (1128, 558), (1095, 656), (779, 652),
        (779, 647), (737, 645), (737, 642), (636, 642),
        (636, 644), (597, 644), (597, 649), (261, 644),
        (261, 608), (278, 578), (278, 435), (261, 434),
        (261, 415), (279, 383), (279, 274), (267, 272),
        (267, 225),
    ),
    "canteen": (
        (1061, 39), (1226, 39), (1234, 83), (1272, 83),
        (1292, 184), (1292, 194), (1287, 194), (1288, 239),
        (1278, 239), (1278, 578), (1282, 580), (1282, 595),
        (1277, 595), (1277, 720), (1247, 720), (1247, 718),
        (1046, 718), (1046, 720), (1015, 720), (1015, 718),
        (858, 718), (858, 742), (517, 742), (517, 718),
        (360, 718), (360, 720), (330, 720), (330, 718),
        (130, 718), (130, 720), (100, 720), (100, 595),
        (95, 595), (95, 583), (99, 578), (99, 239),
        (88, 239), (88, 225), (90, 194), (84, 194),
        (84, 184), (103, 83), (1053, 83), (1053, 64),
        (1055, 58), (1060, 54),
    ),
}


def process_one(name: str, source: Path, target: Path) -> dict[str, object]:
    image = Image.open(source).convert("RGB")
    if image.size != (2752, 1536):
        raise ValueError(f"{source}: outline expects 2752x1536, got {image.size}")

    # Draw at double the original resolution for a one-pixel antialiased edge.
    mask = Image.new("L", (image.width * 2, image.height * 2))
    ImageDraw.Draw(mask).polygon([(round(x * 4), round(y * 4)) for x, y in OUTLINES[name]], fill=255)
    mask = mask.resize(image.size, Image.Resampling.LANCZOS)
    alpha = np.asarray(mask).copy()
    alpha[alpha < 16] = 0
    alpha[alpha > 239] = 255
    rgba = np.dstack((np.asarray(image), alpha))
    rgba[alpha == 0, :3] = 0
    result = Image.fromarray(rgba)
    bbox = result.getchannel("A").getbbox()
    if bbox is None:
        raise RuntimeError(f"empty outline for {source}")
    # Narrow padding keeps filtering away from the opposite edge; the lowest
    # stair pixel is nearly at the ground-level origin of the rendered card.
    pad = 4
    crop = (max(0, bbox[0] - pad), max(0, bbox[1] - pad),
            min(result.width, bbox[2] + pad), min(result.height, bbox[3] + pad))
    result = result.crop(crop)
    target.parent.mkdir(parents=True, exist_ok=True)
    result.save(target, format="PNG", optimize=True)
    return {"source": str(source), "target": str(target), "size": result.size, "crop": crop}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[2] / "素材" / "建筑")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "assets" / "campus" / "textures")
    args = parser.parse_args()
    for name, filename in BUILDINGS.items():
        print(process_one(name, args.source / filename, args.out / f"{name}_front.png"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
