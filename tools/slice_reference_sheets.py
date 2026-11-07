"""A 的工具：把参考图里的 8 方向序列帧切成 48×48 精灵表。

素材来源（用户提供，AI 生成；许可见 assets/LICENSES.csv）：

* `8 方向行走动画序列帧.jif`/`jfif` —— 4 面板列 × 2 面板行，每个面板含两排角色，
  上排是面板标签方向（FRONT / FRONT-LEFT / LEFT / BACK-LEFT / BACK / BACK-RIGHT /
  RIGHT / FRONT-RIGHT），每排 01～04 四帧；
* `8 方向待机动画序列帧.jfif` —— 标题 IDLE ANIMATION (FRONT)，8 个面板即 FRAME 01～08。

流程：黄色身子掩码 -> 降采样连通域找角色 -> 按行/列分组到方向 -> 全分辨率抠背景
（边界洪水填充）-> 统一缩放到身高 38 像素、脚点 (24,46) -> 量化到 32 色 -> 拼表。

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
WALK_SOURCE = SOURCE_DIR / "8 方向行走动画序列帧.jfif"
IDLE_SOURCE = SOURCE_DIR / "8 方向待机动画序列帧.jfif"

CANVAS = 48
BODY_HEIGHT = 38
PIVOT = (24, 46)  # 脚点

# 面板标签 -> 游戏内方向（相机朝北：屏幕右 = 东，屏幕左 = 西）
PANEL_TO_DIRECTION = {
    "FRONT": "s",
    "FRONT-RIGHT": "se",
    "RIGHT": "e",
    "BACK-RIGHT": "ne",
    "BACK": "n",
    "BACK-LEFT": "nw",
    "LEFT": "w",
    "FRONT-LEFT": "sw",
}
PANEL_ORDER = ("FRONT", "FRONT-LEFT", "LEFT", "BACK-LEFT",
               "BACK", "BACK-RIGHT", "RIGHT", "FRONT-RIGHT")
ROW_ORDER = ("s", "se", "e", "ne", "n", "nw", "w", "sw")

from tools.make_placeholders import PALETTE  # noqa: E402


# --------------------------------------------------------------------------- #
# 检测
# --------------------------------------------------------------------------- #
def yellow_mask(im):
    """黄色身体掩码（排除灰色背景、深灰文字与深色描边）。"""
    import numpy as np

    array = np.asarray(im.convert("RGB"), dtype=np.int16)
    high = array.max(axis=2)
    low = array.min(axis=2)
    return (high - low) > 30


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
            xs = []
            ys = []
            area = 0
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
    """把排序后的一维坐标聚成组，返回每组的下标区间列表。"""
    groups = []
    start = 0
    for index in range(1, len(values)):
        if values[index] - values[index - 1] > tol:
            groups.append(list(range(start, index)))
            start = index
    groups.append(list(range(start, len(values))))
    return groups


def group_blobs(blobs, row_tol=60, col_tol=170):
    """按 y 分行、再按 x 分面板列，返回 [[blob, ...], ...]（行优先）。

    col_tol=170 介于同面板内帧间距（~156px）与面板间距（~192px）之间，
    这样一行的 16 个角色会聚成 4 个面板，每个面板 4 帧。
    """
    ordered = sorted(blobs, key=lambda b: (b[1] + b[3]) / 2)
    centers_y = [(b[1] + b[3]) / 2 for b in ordered]
    rows = []
    for group in cluster(centers_y, row_tol):
        rows.append([ordered[index] for index in group])
    if col_tol is None:
        col_tol = 40
    grid = []
    for row in rows:
        row.sort(key=lambda b: (b[0] + b[2]) / 2)
        centers_x = [(b[0] + b[2]) / 2 for b in row]
        for group in cluster(centers_x, col_tol):
            grid.append([row[index] for index in group])
    return grid, rows


# --------------------------------------------------------------------------- #
# 抠图与缩放
# --------------------------------------------------------------------------- #
def flood_background(im, box):
    """从 bbox 边界洪水填充灰色背景，返回 (alpha 布尔图, RGB 数组)。"""
    import numpy as np

    x0, y0, x1, y1 = box
    array = np.asarray(im.convert("RGB"), dtype=np.int16)
    crop = array[y0:y1, x0:x1]
    height, width = crop.shape[:2]
    high = crop.max(axis=2)
    low = crop.min(axis=2)
    sat = high - low
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


def trim(alpha):
    import numpy as np

    ys, xs = np.nonzero(alpha)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def quantize_palette(image):
    """量化到 32 色主调色板；透明像素 RGB 置 0（A7 规定）。

    注意：平方距离必须用 int32，int16 会在 (255)^2 * 3 处溢出，导致黄色被映射成黑色。
    """
    import numpy as np
    from PIL import Image

    array = np.asarray(image.convert("RGBA")).astype(np.int32)
    rgb = array[:, :, :3]
    alpha = array[:, :, 3]
    palette = np.array([color for _name, color in PALETTE], dtype=np.int32)
    flat = rgb.reshape(-1, 3)
    distances = ((flat[:, None, :] - palette[None, :, :]) ** 2).sum(axis=2)
    index = distances.argmin(axis=1)
    matched = palette[index].reshape(rgb.shape)
    out = np.zeros(array.shape, dtype=np.uint8)
    opaque = alpha > 128
    out[:, :, :3] = np.where(opaque[:, :, None], matched, 0)
    out[:, :, 3] = np.where(opaque, 255, 0)
    return Image.fromarray(out, "RGBA")


def add_outline(image, color=(0x2B, 0x22, 0x35)):
    """给不透明区域加 1 像素深色描边（A7：角色统一 1 像素描边 #2B2235）。"""
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
    out[edge, 0] = color[0]
    out[edge, 1] = color[1]
    out[edge, 2] = color[2]
    out[edge, 3] = 255
    return Image.fromarray(out, "RGBA")


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


def clean_alpha(alpha, kernel=1):
    """形态学开+闭去噪，再只保留最大连通域（去掉文字残片与孤立噪点）。"""
    import numpy as np

    opened = _shift_or(_shift_and(alpha, kernel), kernel)
    closed = _shift_and(_shift_or(opened, kernel), kernel)
    if not closed.any():
        return closed

    height, width = closed.shape
    visited = np.zeros_like(closed)
    best = None
    best_area = 0
    ys, xs = np.nonzero(closed)
    for start in zip(ys, xs):
        sy, sx = start
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
        if len(coords) > best_area:
            best_area = len(coords)
            best = coords
    out = np.zeros_like(closed)
    for y, x in best or []:
        out[y, x] = True
    return out


def downsample_pixel_art(rgb_crop, alpha, block: int):
    """按“块内众数”降采样：参考图本身就是放大的像素画（约 6 倍），
    用块众数能保住硬边、去掉 JPEG 振铃，比 LANCZOS 锐利得多。

    block 由整张表统一给出：同一张表里所有帧必须同比例，否则帧间会忽大忽小。
    """
    import numpy as np
    from PIL import Image

    height, width = alpha.shape
    block = max(1, int(block))
    pad_h = (-height) % block
    pad_w = (-width) % block
    rgb = np.pad(rgb_crop, ((0, pad_h), (0, pad_w), (0, 0)), mode="edge")
    mask = np.pad(alpha, ((0, pad_h), (0, pad_w)), mode="constant", constant_values=False)
    oh, ow = rgb.shape[0] // block, rgb.shape[1] // block

    palette = np.array([color for _name, color in PALETTE], dtype=np.int32)
    flat = rgb.reshape(-1, 3).astype(np.int32)
    distances = ((flat[:, None, :] - palette[None, :, :]) ** 2).sum(axis=2)
    index = distances.argmin(axis=1).reshape(rgb.shape[:2])

    blocks_index = index.reshape(oh, block, ow, block).transpose(0, 2, 1, 3).reshape(oh, ow, -1)
    blocks_mask = mask.reshape(oh, block, ow, block).transpose(0, 2, 1, 3).reshape(oh, ow, -1)

    out = np.zeros((oh, ow, 4), dtype=np.uint8)
    for y in range(oh):
        for x in range(ow):
            covered = blocks_mask[y, x]
            opaque_ratio = covered.mean()
            if opaque_ratio < 0.45:
                continue
            values = blocks_index[y, x][covered]
            counts = np.bincount(values, minlength=len(palette))
            color = palette[counts.argmax()]
            out[y, x, :3] = color
            out[y, x, 3] = 255
    return Image.fromarray(out, "RGBA")


def render_frame(rgb_crop, alpha, block: int):
    """块众数降采样 -> 48×48 画布（脚点 24,46）-> 1 像素描边 -> 调色板量化。"""
    from PIL import Image

    small = downsample_pixel_art(rgb_crop, alpha, block)
    width, height = small.size
    if width > CANVAS - 2 or height > CANVAS - 1:
        factor = min((CANVAS - 2) / width, (CANVAS - 1) / height)
        small = small.resize((max(1, int(width * factor)), max(1, int(height * factor))),
                             Image.NEAREST)
        width, height = small.size
    canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    left = min(max(0, PIVOT[0] - width // 2), max(0, CANVAS - width))
    top = max(0, PIVOT[1] - height)
    canvas.alpha_composite(small, (left, top))
    return quantize_palette(add_outline(canvas))


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def slice_sheet(source: Path, frames_per_panel: int):
    """切出整张图里 8 个方向面板（每个面板取 4 帧或 1 帧）。

    行走图：4 排角色，其中第 1、3 排是面板标签方向，第 2、4 排画的是各自的对立面，
    因此只看 headline 行（0 和 2）。待机图只有 2 排角色，两排都是面板本身。
    """
    from PIL import Image

    im = Image.open(source).convert("RGB")
    mask = yellow_mask(im)
    blobs = find_characters(mask)
    if not blobs:
        raise SystemExit(f"{source.name}: 未找到角色")
    grid, rows = group_blobs(blobs)
    headline_rows = (0, 2) if len(rows) >= 4 else (0, 1)

    crops = []
    tallest, widest = 1, 1
    for headline_index, row_index in enumerate(headline_rows):
        panels = grid[row_index * 4:(row_index + 1) * 4]
        if len(panels) != 4:
            raise SystemExit(f"{source.name}: 第 {row_index} 排面板列数异常 {len(panels)}")
        for column, panel in enumerate(panels):
            frames = sorted(panel, key=lambda b: b[0])[:frames_per_panel]
            if len(frames) < frames_per_panel:
                raise SystemExit(
                    f"{source.name}: 面板 {column} 只有 {len(frames)} 帧，需要 {frames_per_panel}")
            for index, blob in enumerate(frames):
                # 黄色掩码只覆盖身体，手臂/腿是深橄榄色，必须把 bbox 放大后再抠图
                margin = 40
                box = (max(0, blob[0] - margin), max(0, blob[1] - margin),
                       blob[2] + margin, blob[3] + margin)
                alpha, crop = flood_background(im, box)
                alpha = clean_alpha(alpha)
                trimmed = trim(alpha)
                if trimmed is None:
                    raise SystemExit(f"{source.name}: 面板 {column} 第 {index} 帧为空")
                tx0, ty0, tx1, ty1 = trimmed
                alpha_crop = alpha[ty0:ty1, tx0:tx1]
                rgb_crop = crop[ty0:ty1, tx0:tx1]
                crops.append((headline_index, column, index, rgb_crop, alpha_crop))
                tallest = max(tallest, alpha_crop.shape[0])
                widest = max(widest, alpha_crop.shape[1])

    # 整张表统一 block：用全部帧的中位身高折算到 38 像素（A7）
    heights = sorted(crop[4].shape[0] for crop in crops)
    median_height = heights[len(heights) // 2]
    block = max(1, int(round(median_height / BODY_HEIGHT)))

    frames: dict[str, list] = {}
    sizes = []
    for headline_index, column, index, rgb_crop, alpha_crop in crops:
        label = PANEL_ORDER[headline_index * 4 + column]
        direction = PANEL_TO_DIRECTION[label]
        rendered = render_frame(rgb_crop, alpha_crop, block)
        frames.setdefault(direction, [None] * frames_per_panel)[index] = rendered
        sizes.append(rendered)
    return frames, block, [PANEL_ORDER[ordinal * 4:(ordinal + 1) * 4]
                           for ordinal, _row in enumerate(headline_rows)]


def build_sheet(frames: dict[str, list], columns: int):
    from PIL import Image

    sheet = Image.new("RGBA", (CANVAS * columns, CANVAS * len(ROW_ORDER)), (0, 0, 0, 0))
    for row, direction in enumerate(ROW_ORDER):
        row_frames = frames[direction]
        for column in range(columns):
            sheet.paste(row_frames[column % len(row_frames)], (column * CANVAS, row * CANVAS))
    return sheet


def contact_sheet(sheets: dict, output: Path, zoom: int = 6) -> None:
    """放大拼核对图（每张精灵表一张），带每帧分隔线，便于肉眼检查方向映射。"""
    from PIL import Image, ImageDraw

    for name, sheet in sheets.items():
        cols = sheet.width // CANVAS
        big = sheet.resize((sheet.width * zoom, sheet.height * zoom), Image.NEAREST)
        canvas = Image.new("RGB", (big.width, big.height + 22), (24, 28, 38))
        canvas.paste(big, (0, 22))
        draw = ImageDraw.Draw(canvas)
        draw.text((4, 6), f"{name}: {cols} frames x 8 dirs (rows s se e ne n nw w sw)",
                  fill=(240, 240, 240))
        for column in range(cols):
            draw.line([(column * CANVAS * zoom, 22), (column * CANVAS * zoom, canvas.height)],
                      fill=(70, 80, 100))
        for row in range(9):
            draw.line([(0, 22 + row * CANVAS * zoom), (canvas.width, 22 + row * CANVAS * zoom)],
                      fill=(70, 80, 100))
        target = output.with_name(f"{output.stem}_{name}{output.suffix}")
        target.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(target)
        print("contact sheet ->", target, canvas.size)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="把 8 方向序列帧切成 48×48 精灵表")
    parser.add_argument("--walk-source", default=str(WALK_SOURCE))
    parser.add_argument("--idle-source", default=str(IDLE_SOURCE))
    parser.add_argument("--out-dir", default=str(ROOT / "assets" / "characters" / "naiwan"))
    parser.add_argument("--verify", action="store_true", help="只输出核对图，不覆盖正式资源")
    args = parser.parse_args(argv)

    walk_source = Path(args.walk_source)
    idle_source = Path(args.idle_source)
    for path in (walk_source, idle_source):
        if not path.exists():
            raise SystemExit(f"素材不存在: {path}")

    from PIL import Image

    walk_frames, walk_scale, walk_labels = slice_sheet(walk_source, frames_per_panel=4)
    walk_sheet = build_sheet(walk_frames, 4)

    # 待机图是 8 个单帧面板（FRAME 01～08），按阅读顺序取第 1/3/5 帧做 s 方向呼吸循环；
    # 其余方向用该方向行走第 1 帧 + 1 像素呼吸位移，保证 8 方向都有 3 帧（A8：144×384）。
    idle_panels, idle_scale, _ = slice_sheet(idle_source, frames_per_panel=1)
    reading_order = [idle_panels[PANEL_TO_DIRECTION[label]][0] for label in PANEL_ORDER]
    idle_rows: dict[str, list] = {}
    for direction in ROW_ORDER:
        if direction == "s":
            idle_rows[direction] = [reading_order[0], reading_order[2], reading_order[4]]
        else:
            base = walk_frames[direction][0]
            up = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
            up.alpha_composite(base, (0, -1))
            idle_rows[direction] = [base, up, base]
    idle_sheet = build_sheet(idle_rows, 3)

    contact_sheet({"walk": walk_sheet, "idle": idle_sheet},
                  ROOT / "build" / "_slice_contact.png")
    print(f"walk block={walk_scale} idle block={idle_scale} panels={walk_labels}")

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


