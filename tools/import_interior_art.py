"""把 `素材/建筑材质/` 的 10 张材质落成室内地板 / 地面贴图。

五栋建筑各一份地板 + 一份墙面（用户提供的 AI 生成材质）。规则：

1. 目标是像素游戏：贴图按 24 px/m 的密度落到游戏像素网格上，1 个纹素 ≈ 1 个游戏像素。
   - 地板：正方形裁剪后缩到 96×96，平铺一次覆盖 4×4 米（96 / 4 = 24 px/m）。
   - 墙面：保留原始宽高比（墙面图自带踢脚线/墙裙，压扁会把比例弄错），
     高度缩到 72×72 像素（3 米层高 = 72 px），平铺宽度按同一密度算出米数。
2. 缩图分两步（先 4 倍 LANCZOS，再 BOX）：一步到底会把瓷砖缝、木纹这些
   1 像素级细节整个抹掉；两步缩放能让缝/纹路在缩略后仍然是可辨认的暗线。
3. 之后量化到 64 色并清掉抖动（游戏是像素风，渐变噪点会被读成"脏"）。

用法：
    python tools/import_interior_art.py            # 生成 + 打印清单
    python tools/import_interior_art.py --check    # 只校验文件是否齐全
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
#: 原始素材放在仓库外的 `奶娃/素材/`（原图不入库），也允许放在仓库内 `素材/`
_SOURCE_CANDIDATES = (ROOT.parent / "素材" / "建筑材质", ROOT / "素材" / "建筑材质")
SOURCE_DIR = next((path for path in _SOURCE_CANDIDATES if path.is_dir()), _SOURCE_CANDIDATES[0])
OUT_DIR = ROOT / "assets" / "campus" / "textures" / "interior"
MANIFEST = ROOT / "assets" / "manifest.json"
LICENSE_ID = "LIC-0213"

#: 24 px/m ≈ 游戏内像素密度（config.PIXELS_PER_METER）
PX_PER_M = 24
FLOOR_TILE_M = 4.0
FLOOR_PX = int(FLOOR_TILE_M * PX_PER_M)      # 96
WALL_HEIGHT_M = 3.0
WALL_PX = int(WALL_HEIGHT_M * PX_PER_M)      # 72
PALETTE_COLORS = 64

BUILDINGS: dict[str, dict[str, str]] = {
    "dorm": {"floor": "宿舍地板.jfif", "wall": "宿舍墙面.jfif"},
    "teaching": {"floor": "教学楼地板.jfif", "wall": "教学楼墙面.jfif"},
    "library": {"floor": "图书馆地板.jfif", "wall": "图书馆墙面.jpg"},
    "club": {"floor": "社团地板.jfif", "wall": "社团中心墙面.jfif"},
    "canteen": {"floor": "饭堂地板.jpg", "wall": "饭堂墙面.jpg"},
}


def _two_stage_resize(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """先 LANCZOS 缩到 4 倍大小，再 BOX 缩到目标——保留瓷砖缝/木纹这类细线。"""
    target_w, target_h = size
    mid = (max(target_w * 4, target_w), max(target_h * 4, target_h))
    if image.width > mid[0] or image.height > mid[1]:
        image = image.resize(mid, Image.LANCZOS)
    return image.resize((target_w, target_h), Image.BOX)


def _quantize(image: Image.Image) -> Image.Image:
    """量化到 64 色（无抖动）：像素风不需要照片级渐变。"""
    return image.convert("RGB").quantize(
        colors=PALETTE_COLORS, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE
    ).convert("RGB")


def _center_square(image: Image.Image) -> Image.Image:
    side = min(image.size)
    left = (image.width - side) // 2
    top = (image.height - side) // 2
    return image.crop((left, top, left + side, top + side))


def process_floor(path: Path) -> Image.Image:
    image = _center_square(Image.open(path).convert("RGB"))
    return _quantize(_two_stage_resize(image, (FLOOR_PX, FLOOR_PX)))


def process_wall(path: Path) -> tuple[Image.Image, float]:
    """墙面：高度对齐 3 米，宽度按原比例；返回 (图, 一次平铺覆盖的米数)。"""
    image = Image.open(path).convert("RGB")
    width_px = max(1, round(WALL_PX * image.width / image.height))
    out = _quantize(_two_stage_resize(image, (width_px, WALL_PX)))
    tile_m = round(WALL_HEIGHT_M * width_px / WALL_PX, 3)
    return out, tile_m


def average_rgb(image: Image.Image) -> list[float]:
    """贴图平均色（0..1）：家具用它的暗色版，保证与地面/墙面同色系。"""
    small = image.convert("RGB").resize((16, 16), Image.BOX)
    pixels = list(small.getdata())
    count = max(1, len(pixels))
    return [round(sum(p[channel] for p in pixels) / count / 255.0, 3) for channel in range(3)]


def register_manifest(tiles: dict[str, float], average: dict[str, list[float]]) -> int:
    """把 10 条材质登记进 assets/manifest.json（幂等：已存在则更新）。

    `tile_m` 是"贴图平铺一次覆盖的米数"，游戏侧（InteriorSceneAdapter）按它算 UV，
    所以纹理密度改了就只改工具、不动代码；`average_rgb` 供室内家具取同色系暗调。
    """
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assets = data["assets"] if isinstance(data, dict) else data
    by_id = {entry["id"]: entry for entry in assets}
    added = 0
    for building in BUILDINGS:
        for kind in ("floor", "wall"):
            asset_id = f"interior_{kind}_{building}"
            entry = {
                "id": asset_id,
                "type": "image",
                "path": f"campus/textures/interior/{building}_{kind}.png",
                "license_id": LICENSE_ID,
                "tile_m": round(tiles[asset_id], 3),
                "average_rgb": average.get(asset_id, [0.5, 0.5, 0.5]),
                "tags": ["final", "material", "tileable", "user_provided"],
            }
            if asset_id in by_id:
                by_id[asset_id].update(entry)
            else:
                assets.append(entry)
                by_id[asset_id] = entry
                added += 1
    MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return added


def run(check_only: bool = False) -> int:
    missing = [name for names in BUILDINGS.values() for name in names.values()
               if not (SOURCE_DIR / name).is_file()]
    if missing:
        print("缺少素材：" + "、".join(missing), file=sys.stderr)
        return 2
    if check_only:
        print("素材齐全：%d 个文件" % sum(len(v) for v in BUILDINGS.values()))
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tiles: dict[str, float] = {}
    average: dict[str, list[float]] = {}
    rows: list[tuple[str, str, str, str]] = []
    for building, sources in BUILDINGS.items():
        floor = process_floor(SOURCE_DIR / sources["floor"])
        floor_path = OUT_DIR / f"{building}_floor.png"
        floor.save(floor_path, optimize=True)
        tiles[f"interior_floor_{building}"] = FLOOR_TILE_M
        average[f"interior_floor_{building}"] = average_rgb(floor)

        wall, wall_tile_m = process_wall(SOURCE_DIR / sources["wall"])
        wall_path = OUT_DIR / f"{building}_wall.png"
        wall.save(wall_path, optimize=True)
        tiles[f"interior_wall_{building}"] = wall_tile_m
        average[f"interior_wall_{building}"] = average_rgb(wall)

        rows.append((building, f"{floor_path.name} {floor.width}x{floor.height}",
                     f"{wall_path.name} {wall.width}x{wall.height}",
                     f"tile_m={FLOOR_TILE_M}/{wall_tile_m}"))
    added = register_manifest(tiles, average)
    width = max(len(row[0]) for row in rows)
    for building, floor, wall, tile in rows:
        print(f"{building:<{width}}  floor {floor:<24} wall {wall:<24} {tile}")
    print(f"\n输出目录：{OUT_DIR.relative_to(ROOT)}（地板 {FLOOR_PX}px = {FLOOR_TILE_M}m，"
          f"墙面高度 {WALL_PX}px = {WALL_HEIGHT_M}m，{PX_PER_M}px/m）")
    print(f"manifest：新增 {added} 条材质登记（license {LICENSE_ID}）")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="导入室内建筑材质（地板 / 墙面）")
    parser.add_argument("--check", action="store_true", help="只检查源素材是否齐全")
    args = parser.parse_args(argv)
    return run(check_only=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
