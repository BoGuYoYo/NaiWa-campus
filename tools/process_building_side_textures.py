"""Copy the four user-supplied PNGs directly into the game's side textures.

Preserve the original PNG bytes, alpha channel, dimensions and artwork.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT.parent / "建筑_侧面" / "侧面裁切"
DEFAULT_OUT = ROOT / "assets" / "campus" / "textures"
SOURCES = {
    "teaching": "教学楼侧视图.png",
    "dorm": "宿舍楼侧视图.png",
    "library": "图书馆侧视图.png",
    "club": "社团中心侧视图.png",
}


def process_one(name: str, source: Path, target: Path) -> dict[str, str]:
    original = source / SOURCES[name]
    target.parent.mkdir(parents=True, exist_ok=True)
    if original.resolve() != target.resolve():
        shutil.copy2(original, target)
    return {"source": str(original), "target": str(target)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--only", choices=sorted(SOURCES))
    args = parser.parse_args()
    for name in [args.only] if args.only else SOURCES:
        print(process_one(name, args.source, args.out / f"{name}_side.png"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
