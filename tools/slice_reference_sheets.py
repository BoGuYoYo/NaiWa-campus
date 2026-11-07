"""A 的工具：把素材目录里的单方向行走序列帧切成 48×48 精灵表。

素材约定（用户 2026-11-07 更新后）：

* 每个方向一张图，标题写明方向，例如 `向前走.jfif` 为 `WALK CYCLE - FRONT（向前行走）`；
* 一张图里 2 排 × 4 列 = FRAME 01～08，八帧一个完整循环；
* 文件名按方向命名：向前走 / 右前前进 / 向右走 / 右后行走 / 向后行走 / 左后行走 /
  向左走 / 左前前进（文件名里的错别字不影响匹配，按关键字识别）。

流程：黄色身子掩码 -> 降采样连通域找角色 -> 按行/列排序成帧 -> 全分辨率抠背景
（边界洪水填充 + 形态学去噪）-> 整表统一“块内众数”降采样到身高 38 像素、脚点 (24,46)
-> 1 像素描边 -> 量化到 32 色 -> 按行顺序 s se e ne n nw w sw 拼表。

用法：
    python tools/slice_reference_sheets.py --verify   # 只生成核对图
    python tools/slice_reference_sheets.py            # 写入 assets/characters/naiwan/
"""

from __future__ import annotations

import argparse
import sys
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SOURCE_DIR = ROOT.parent / "素材"
ASSET_DIR = ROOT / "assets" / "characters" / "naiwan"

CANVAS = 48
BODY_HEIGHT = 38
PIVOT = (24, 46)  # 脚点

ROW_ORDER = ("s", "se", "e", "ne", "n", "nw", "w", "sw")

# 关键字 -> 方向（相机朝北：屏幕右 = 东；文件名指“角色面朝/走向”的屏幕方位）
DIRECTION_KEYWORDS = {
    "向前": "s",
    "右前": "se",
    "向右": "e",
    "右后": "ne",
    "向后": "n",
    "左后": "nw",
    "向左": "w",
    "左前": "sw",
}

from tools.make_placeholders import PALETTE  # noqa: E402


# --------------------------------------------------------------------------- #
# 检测
# --------------------------------------------------------------------------- #
def yellow_mask(im):
    """黄色身体掩码（排除灰色背景、深灰文字与深色描边）。"""
    import numpy as np

    array = np.asarray(im.convert("RGB"), dtype=np.int16)
    return (array.max(axis=2) - array.min(axis=2)) > 30


def find_characters(mask, coarse: int = 4, min_area: int = 250):
    """降采样后做连通域，返回 [(x0, y0, x1, y1, area), ...]（全分辨率坐标）。"""
    import numpy as np

    height, width = mask.shape
    hh, ww = height // coarse, width // coarse
    block = mask[: hh * coarse, : ww * coarse].reshape(hh, coarse, ww, coarse).max(axis=(1, 3))
    visited = np.zeros_like(block)
    blobs = []
    for y in range(hh):
        for x in range(ww):
            if not block[y, x] or visited[y, x]:
                continue
            queue = deque([(x, y)])
            visited[y, x] = True
            xs, ys, area = [], [], 0
            while queue:
                cx, cy = queue.popleft()
                area += 1
                xs.append(cx)
                ys.append(cy)
                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if 0 <= nx < ww and 0 <= ny < hh and block[ny, nx] and not visited[ny, nx]:
                        visited[ny, nx] = True
                        queue.append((nx, ny))
            if area >= min_area:
                blobs.append((min(xs) * coarse, min(ys) * coarse,
                              (max(xs) + 1) * coarse, (max(ys) + 1) * coarse, area))
    return blobs


def cluster(values, tol):
    groups = []
    start = 0
    for index in range(1, len(values)):
        if values[index] - values[index - 1] > tol:
            groups.append(list(range(start, index)))
            start = index
    groups.append(list(range(start, len(values))))
    return groups


def order_frames(blobs, row_tol=60, min_per_row=3):
    """把一张单方向图里的角色块按“先分行、再按 x”排成 01..0N；杂物行会被丢掉。"""
    ordered = sorted(blobs, key=lambda b: (b[1] + b[3]) / 2)
    centers = [(b[1] + b[3]) / 2 for b in ordered]
    rows = []
    for group in cluster(centers, row_tol):
        row = [ordered[index] for index in group]
        if len(row) >= min_per_row:
            rows.append(sorted(row, key=lambda b: (b[0] + b[2]) / 2))
    frames = [blob for row in rows for blob in row]
    return frames, len(rows)


# --------------------------------------------------------------------------- #
# 抠图与像素化
# --------------------------------------------------------------------------- #
def flood_background(im, box):
    """从 bbox 边界洪水填充灰色背景，返回 (alpha 布尔图, RGB 数组)。"""
    import numpy as np

    x0, y0, x1, y1 = box
    array = np.asarray(im.convert("RGB"), dtype=np.int16)
    crop = array[y0:y1, x0:x1]
    height, width = crop.shape[:2]
    sat = crop.max(axis=2) - crop.min(axis=2)
    val = crop.mean(axis=2)
    background_like = (sat < 18) & (val > 150)

    visited = np.zeros((height, width), dtype=bool)
    queue: deque[tuple[int, int]] = deque()
    for x in range(width):
        for y in (0, height - 1):
            if background_like[y, x] and not visited[y, x]:
                visited[y, x] = True
                queue.append((x, y))
    for y in range(height):
        for x in (0, width - 1):
            if background_like[y, x] and not visited[y, x]:
                visited[y, x] = True
                queue.append((x, y))
    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < width and 0 <= ny < height and not visited[ny, nx] \
                    and background_like[ny, nx]:
                visited[ny, nx] = True
                queue.append((nx, ny))
    return ~visited, crop


def _shift_or(mask, kernel=1):
    import numpy as np

    padded = np.pad(mask, kernel, mode="constant", constant_values=False)
    out = np.zeros_like(mask)
    for dy in range(-kernel, kernel + 1):
        for dx in range(-kernel, kernel + 1):
            out |= padded[kernel + dy:kernel + dy + mask.shape[0],
                          kernel + dx:kernel + dx + mask.shape[1]]
    return out


def _shift_and(mask, kernel=1):
    import numpy as np

    padded = np.pad(mask, kernel, mode="constant", constant_values=False)
    out = np.ones_like(mask)
    for dy in range(-kernel, kernel + 1):
        for dx in range(-kernel, kernel + 1):
            out &= padded[kernel + dy:kernel + dy + mask.shape[0],
                          kernel + dx:kernel + dx + mask.shape[1]]
    return out


def clean_alpha(alpha, kernel=1, pad=8, min_area_ratio=0.02):
    """形态学开+闭去噪后，保留“贴着身体”的连通域。

    只留最大连通域会把与身体分离的手臂/手/脚丢掉（背面视图尤其明显）；
    放宽太多又会把相邻帧的手臂、面板边框细线带进来。所以用两个条件收敛：
    主连通域 bbox 外扩 pad 像素，且面积不小于主连通域的 min_area_ratio。
    """
    import numpy as np

    opened = _shift_or(_shift_and(alpha, kernel), kernel)
    closed = _shift_and(_shift_or(opened, kernel), kernel)
    if not closed.any():
        return closed

    height, width = closed.shape
    visited = np.zeros_like(closed)
    components = []
    ys, xs = np.nonzero(closed)
    for sy, sx in zip(ys, xs):
        if visited[sy, sx]:
            continue
        queue = deque([(sx, sy)])
        visited[sy, sx] = True
        coords = []
        while queue:
            cx, cy = queue.popleft()
            coords.append((cy, cx))
            for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                if 0 <= nx < width and 0 <= ny < height and closed[ny, nx] and not visited[ny, nx]:
                    visited[ny, nx] = True
                    queue.append((nx, ny))
        components.append(coords)
    if not components:
        return closed

    main = max(components, key=len)
    main_ys = [point[0] for point in main]
    main_xs = [point[1] for point in main]
    y0, y1 = min(main_ys), max(main_ys)
    x0, x1 = min(main_xs), max(main_xs)
    min_area = max(16, int(len(main) * min_area_ratio))
    out = np.zeros_like(closed)
    for coords in components:
        if len(coords) < min_area:
            continue
        cy0 = min(point[0] for point in coords)
        cy1 = max(point[0] for point in coords)
        cx0 = min(point[1] for point in coords)
        cx1 = max(point[1] for point in coords)
        intersects = not (cy1 < y0 - pad or cy0 > y1 + pad or cx1 < x0 - pad or cx0 > x1 + pad)
        if intersects:
            for y, x in coords:
                out[y, x] = True
    return out


def trim(alpha):
    import numpy as np

    ys, xs = np.nonzero(alpha)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def add_outline(image, color=(0x2B, 0x22, 0x35)):
    """1 像素深色描边（A7：角色统一 1 像素描边 #2B2235）。"""
    import numpy as np
    from PIL import Image

    array = np.asarray(image)
    alpha = array[:, :, 3] > 0
    padded = np.pad(alpha, 1, mode="constant", constant_values=False)
    dilated = np.zeros_like(alpha)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            dilated |= padded[1 + dy:1 + dy + alpha.shape[0], 1 + dx:1 + dx + alpha.shape[1]]
    edge = dilated & ~alpha
    out = array.copy()
    out[edge, 0], out[edge, 1], out[edge, 2], out[edge, 3] = color[0], color[1], color[2], 255
    return Image.fromarray(out, "RGBA")


def quantize_palette(image):
    """量化到 32 色调色板；透明像素 RGB 置 0。平方距离用 int32，int16 会溢出成黑色。"""
    import numpy as np
    from PIL import Image

    array = np.asarray(image.convert("RGBA")).astype(np.int32)
    rgb, alpha = array[:, :, :3], array[:, :, 3]
    palette = np.array([color for _name, color in PALETTE], dtype=np.int32)
    flat = rgb.reshape(-1, 3)
    distances = ((flat[:, None, :] - palette[None, :, :]) ** 2).sum(axis=2)
    matched = palette[distances.argmin(axis=1)].reshape(rgb.shape)
    out = np.zeros(array.shape, dtype=np.uint8)
    opaque = alpha > 128
    out[:, :, :3] = np.where(opaque[:, :, None], matched, 0)
    out[:, :, 3] = np.where(opaque, 255, 0)
    return Image.fromarray(out, "RGBA")


def render_frame(rgb_crop, alpha, scale: float):
    """按统一 scale 做面积（BOX）缩放 -> 48×48 画布（脚点 24,46）-> 描边 -> 调色板量化。

    用面积缩放而不是块众数：新素材的放大倍数不是整数（约 15.3），块众数会随网格漂移，
    细小的眼睛/描边会被“少数服从多数”吃掉；面积平均后再量化反而更稳。
    缩放前先 alpha 预乘，避免透明区的灰底混进边缘。
    """
    import numpy as np
    from PIL import Image

    height, width = alpha.shape
    target_w = max(1, int(round(width * scale)))
    target_h = max(1, int(round(height * scale)))

    rgba = np.dstack([rgb_crop, (alpha * 255).astype(np.int16)]).astype(np.float32)
    premultiplied = rgba.copy()
    premultiplied[:, :, :3] *= rgba[:, :, 3:4] / 255.0
    source = Image.fromarray(np.clip(premultiplied, 0, 255).astype(np.uint8), "RGBA")
    small = np.asarray(source.resize((target_w, target_h), Image.BOX)).astype(np.float32)
    small_alpha = small[:, :, 3:4] / 255.0
    rgb_out = np.where(small_alpha > 0.02, small[:, :, :3] / np.maximum(small_alpha, 1e-6), 0.0)
    opaque = np.where(small_alpha[:, :, 0] > 0.5, 255, 0)
    composed = Image.fromarray(
        np.dstack([np.clip(rgb_out, 0, 255), opaque]).astype(np.uint8), "RGBA")

    if target_w > CANVAS - 2 or target_h > CANVAS - 1:
        factor = min((CANVAS - 2) / target_w, (CANVAS - 1) / target_h)
        composed = composed.resize((max(1, int(target_w * factor)), max(1, int(target_h * factor))),
                                   Image.NEAREST)
        target_w, target_h = composed.size

    canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    left = min(max(0, PIVOT[0] - target_w // 2), max(0, CANVAS - target_w))
    canvas.alpha_composite(composed, (left, max(0, PIVOT[1] - target_h)))
    return quantize_palette(add_outline(canvas))


# --------------------------------------------------------------------------- #
# 素材 -> 方向
# --------------------------------------------------------------------------- #
def discover_sources(source_dir: Path) -> dict[str, Path]:
    """按文件名关键字给每个方向找序列帧；重复或缺失都明确报错。"""
    found: dict[str, Path] = {}
    for path in sorted(source_dir.glob("*.jfif")):
        for keyword, direction in DIRECTION_KEYWORDS.items():
            if keyword in path.stem:
                if direction in found:
                    raise SystemExit(
                        f"方向 {direction} 命中多个文件：{found[direction].name} / {path.name}")
                found[direction] = path
                break
    missing = [direction for direction in ROW_ORDER if direction not in found]
    if missing:
        raise SystemExit(f"缺少方向的素材：{missing}（命名约定见 DIRECTION_KEYWORDS）")
    return found


def slice_direction(path: Path):
    """返回 (frames, row_count)；frames 为 [(rgb, alpha, 原图左上角坐标), ...]。"""
    from PIL import Image

    im = Image.open(path).convert("RGB")
    blobs = find_characters(yellow_mask(im))
    if not blobs:
        raise SystemExit(f"{path.name}: 未找到角色")
    ordered, row_count = order_frames(blobs)
    frames = []
    for blob in ordered:
        margin = 40  # 黄色掩码只覆盖身体，手臂/腿是深橄榄色，必须放大 bbox 再抠
        box = (max(0, blob[0] - margin), max(0, blob[1] - margin),
               blob[2] + margin, blob[3] + margin)
        alpha, crop = flood_background(im, box)
        alpha = clean_alpha(alpha)
        trimmed = trim(alpha)
        if trimmed is None:
            continue
        x0, y0, x1, y1 = trimmed
        # 记录该帧在原图中的左上角，供按原图网格对齐取样（避免逐帧 1 像素抖动）
        frames.append((crop[y0:y1, x0:x1], alpha[y0:y1, x0:x1], (box[0] + x0, box[1] + y0)))
    return frames, row_count


def build_sheet(rows: dict[str, list], columns: int):
    from PIL import Image

    sheet = Image.new("RGBA", (CANVAS * columns, CANVAS * len(ROW_ORDER)), (0, 0, 0, 0))
    for row, direction in enumerate(ROW_ORDER):
        frames = rows[direction]
        for column in range(columns):
            sheet.paste(frames[column % len(frames)], (column * CANVAS, row * CANVAS))
    return sheet


def contact_sheet(sheets: dict, output: Path, zoom: int = 5) -> None:
    from PIL import Image, ImageDraw

    for name, sheet in sheets.items():
        cols = sheet.width // CANVAS
        big = sheet.resize((sheet.width * zoom, sheet.height * zoom), Image.NEAREST)
        canvas = Image.new("RGB", (big.width, big.height + 22), (24, 28, 38))
        canvas.paste(big, (0, 22))
        draw = ImageDraw.Draw(canvas)
        draw.text((4, 6), f"{name}: {cols} frames x 8 dirs (rows s se e ne n nw w sw)",
                  fill=(240, 240, 240))
        for column in range(cols + 1):
            draw.line([(column * CANVAS * zoom, 22), (column * CANVAS * zoom, canvas.height)],
                      fill=(70, 80, 100))
        for row in range(9):
            draw.line([(0, 22 + row * CANVAS * zoom), (canvas.width, 22 + row * CANVAS * zoom)],
                      fill=(70, 80, 100))
        target = output.with_name(f"{output.stem}_{name}{output.suffix}")
        target.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(target)
        print("contact sheet ->", target, canvas.size)


def render_idle_source(path: Path, scale: float, columns: int = 3):
    """有专门待机素材时用它（格式与行走图相同：单方向 4 列 × 2 排）。"""
    frames, _rows = slice_direction(path)
    if len(frames) < columns:
        raise SystemExit(f"{path.name}: 待机帧不足 {columns} 帧（实际 {len(frames)}）")
    return [render_frame(rgb, alpha, scale) for rgb, alpha, _origin in frames[:columns]]


def idle_from_walk(frames: list, columns: int = 3):
    """没有待机素材时的兜底：行走首帧 + 1 像素呼吸位移。"""
    from PIL import Image

    base = frames[0]
    up = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    up.alpha_composite(base, (0, -1))
    pattern = [base, up, base]
    return [pattern[index % len(pattern)] for index in range(columns)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="把单方向行走序列帧切成 48×48 精灵表")
    parser.add_argument("--source-dir", default=str(SOURCE_DIR))
    parser.add_argument("--out-dir", default=str(ASSET_DIR))
    parser.add_argument("--columns", type=int, default=0,
                        help="每个方向输出的帧数，0=取各方向素材帧数的最小值")
    parser.add_argument("--idle-source", default=None,
                        help="单独的待机序列帧（格式同行走图），缺省用行走首帧呼吸")
    parser.add_argument("--verify", action="store_true", help="只输出核对图，不覆盖正式资源")
    args = parser.parse_args(argv)

    source_dir = Path(args.source_dir)
    if not source_dir.is_dir():
        raise SystemExit(f"素材目录不存在: {source_dir}")

    sources = discover_sources(source_dir)
    print("素材 -> 方向：", {direction: path.name for direction, path in sources.items()})

    raw: dict[str, list] = {}
    heights = []
    for direction in ROW_ORDER:
        frames, rows = slice_direction(sources[direction])
        raw[direction] = frames
        heights.extend(frame[1].shape[0] for frame in frames)
        print(f"  {direction:<3} {sources[direction].name:<16} 行数={rows} 帧数={len(frames)}")

    counts = [len(frames) for frames in raw.values()]
    columns = args.columns or min(counts)
    if any(len(frames) < columns for frames in raw.values()):
        raise SystemExit(f"某些方向帧数不足 {columns}: {counts}")

    heights.sort()
    median_height = heights[len(heights) // 2]
    scale = BODY_HEIGHT / median_height
    print(f"统一缩放 {scale:.4f}（中位身高 {median_height}px -> {BODY_HEIGHT}px），每方向 {columns} 帧")

    walk_rows = {
        direction: [render_frame(rgb, alpha, scale) for rgb, alpha, _origin in raw[direction][:columns]]
        for direction in ROW_ORDER
    }
    walk_sheet = build_sheet(walk_rows, columns)

    # 待机：本次素材只有行走图。有 --idle-source 就用它，否则用行走首帧做呼吸循环，
    # 保证 8 个方向同一套画风（混用旧素材会出现身形跳变）。
    front_idle = None
    if args.idle_source:
        idle_path = Path(args.idle_source)
        if idle_path.exists():
            front_idle = render_idle_source(idle_path, scale, 3)
        else:
            print(f"[WARN] --idle-source 不存在，改用行走首帧: {idle_path}")
    idle_rows = {}
    for direction in ROW_ORDER:
        if direction == "s" and front_idle is not None:
            idle_rows[direction] = front_idle
        else:
            idle_rows[direction] = idle_from_walk(walk_rows[direction], 3)
    idle_sheet = build_sheet(idle_rows, 3)

    contact_sheet({"walk": walk_sheet, "idle": idle_sheet},
                  ROOT / "build" / "_slice_contact.png")

    if args.verify:
        return 0

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    walk_sheet.save(out_dir / "walk.png", "PNG")
    idle_sheet.save(out_dir / "idle.png", "PNG")
    print(f"wrote {out_dir / 'walk.png'} {walk_sheet.size}")
    print(f"wrote {out_dir / 'idle.png'} {idle_sheet.size}")
    return 0


if __name__ == "__main__":
    sys.exit(main())



