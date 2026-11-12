"""A 的工具：把用户生成的活动插图与表情头像落位到项目规格。

素材约定（`素材/场景/`、`素材/小表情/`）：

* 场景：每个活动一张 16:9 插图（约 2752×1536），文件名用中文活动名；
* 表情：每个表情一张 1024×1024 全身像素画，纯灰底无透明通道；
* 本工具只做“规格落位”，不改内容：场景 -> 160×90，表情 -> 96×96 半身头像。

用法：
    python tools/import_generated_art.py --scenes
    python tools/import_generated_art.py --portraits
    python tools/import_generated_art.py --all
    python tools/import_generated_art.py --all --verify    # 只生成核对图
"""

from __future__ import annotations

import argparse
import sys
from collections import deque
from pathlib import Path

from pixel_downscale import integer_downscale

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SOURCE_DIR = ROOT.parent / "素材"
SCENE_DIR = SOURCE_DIR / "场景"
PORTRAIT_DIR = SOURCE_DIR / "小表情"
CG_OUT = ROOT / "assets" / "art" / "cg"
PORTRAIT_OUT = ROOT / "assets" / "portraits" / "naiwan"

CG_SIZE = (160, 90)
PORTRAIT_SIZE = 96
PORTRAIT_CROP_RATIO = 0.56   # 取角色 bbox 上部这一比例，做成半身像
CG_COLORS = 64               # 插图保留 64 色（细节多），角色/头像仍用 32 色主调色板

# 文件名关键字 -> 活动 ID
SCENE_KEYWORDS = {
    "教室": "attend_class",
    "图书馆": "library_study",
    "打游戏": "play_games",
    "敲代码": "create_work",
    "社团": "join_club",
    "跑步": "exercise",
    "吃饭": "eat_canteen",
    "宿舍": "rest_dorm",
    "闲逛": "campus_walk",
}

# 文件名关键字 -> 表情 ID（与 manifest 的 portrait_naiwan_* 对齐）
EXPRESSION_KEYWORDS = {
    "平常": "neutral",
    "开心": "happy",
    "伤心": "sad",
    "生气": "angry",
    "无语": "speechless",
    "害羞": "shy",
    "骄傲": "proud",
    "惊讶": "surprised",
}

from tools.make_placeholders import PALETTE  # noqa: E402


def discover(directory: Path, keywords: dict[str, str]) -> dict[str, Path]:
    if not directory.is_dir():
        raise SystemExit(f"素材目录不存在: {directory}")
    found: dict[str, Path] = {}
    for path in sorted(directory.iterdir()):
        if path.suffix.lower() not in (".png", ".jpg", ".jpeg", ".jfif", ".webp"):
            continue
        for keyword, key in keywords.items():
            if keyword in path.stem:
                if key in found:
                    raise SystemExit(f"{key} 命中多个文件：{found[key].name} / {path.name}")
                found[key] = path
                break
        else:
            print(f"[WARN] 未识别的文件（跳过）: {path.name}")
    missing = [key for key in keywords.values() if key not in found]
    if missing:
        raise SystemExit(f"缺少素材：{missing}")
    return found


# --------------------------------------------------------------------------- #
# 场景：居中裁剪到 16:9 -> 160×90 -> 自适应量化
# --------------------------------------------------------------------------- #
def import_scene(path: Path) -> "object":
    from PIL import Image

    image = Image.open(path).convert("RGB")
    width, height = image.size
    target_ratio = CG_SIZE[0] / CG_SIZE[1]
    if width / height > target_ratio:          # 太宽：裁两侧
        new_width = int(round(height * target_ratio))
        left = (width - new_width) // 2
        image = image.crop((left, 0, left + new_width, height))
    else:                                       # 太高：裁上下
        new_height = int(round(width / target_ratio))
        top = (height - new_height) // 2
        image = image.crop((0, top, width, top + new_height))
    small = image.resize(CG_SIZE, Image.BOX)
    return small.convert("P", palette=Image.ADAPTIVE, colors=CG_COLORS).convert("RGB")


# --------------------------------------------------------------------------- #
# 表情：抠灰底 -> 取上半身 -> 96×96 -> 32 色量化 + 硬 alpha
# --------------------------------------------------------------------------- #
def alpha_from_gray(image):
    """从边界洪水填充纯灰背景，返回 (rgb, alpha)。"""
    import numpy as np

    array = np.asarray(image.convert("RGB"), dtype=np.int16)
    height, width = array.shape[:2]
    sat = array.max(axis=2) - array.min(axis=2)
    val = array.mean(axis=2)
    background_like = (sat < 16) & (val > 160)

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
            if 0 <= nx < width and 0 <= ny < height and background_like[ny, nx] \
                    and not visited[ny, nx]:
                visited[ny, nx] = True
                queue.append((nx, ny))
    return array, ~visited


def largest_component(alpha):
    """只留最大连通域，去掉零散噪点与文字残片。"""
    import numpy as np

    height, width = alpha.shape
    visited = np.zeros_like(alpha)
    best, best_area = None, 0
    ys, xs = np.nonzero(alpha)
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
                if 0 <= nx < width and 0 <= ny < height and alpha[ny, nx] and not visited[ny, nx]:
                    visited[ny, nx] = True
                    queue.append((nx, ny))
        if len(coords) > best_area:
            best_area, best = len(coords), coords
    out = np.zeros_like(alpha)
    for y, x in best or []:
        out[y, x] = True
    return out


def quantize_with_alpha(rgba):
    import numpy as np
    from PIL import Image

    array = np.asarray(rgba).astype(np.int32)
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


def head_crop_box(alpha, x0, x1, y0, y1):
    """按“躯干宽度”定半身像裁剪框。

    这套表情是同一个角色、同一比例，但站姿不同（手臂张开/收拢），整体 bbox 高度会差 10% 以上；
    用高度比例裁剪会让头像忽大忽小。肩宽在 8 张里最稳定，所以：
    取胸部那几行的宽度中位数当基准，半身像边长 = 肩宽 × 1.15，水平居中在 bbox 中线。
    """
    import numpy as np

    body_h = y1 - y0
    body_w = x1 - x0
    widths = []
    for y in range(int(y0 + body_h * 0.34), int(y0 + body_h * 0.56)):
        xs = np.nonzero(alpha[y, x0:x1])[0]
        if len(xs):
            widths.append(len(xs))
    chest_w = float(np.median(widths)) if widths else float(body_w)
    side = int(round(max(chest_w * 1.15, body_w * 0.62)))

    center_x = (x0 + x1) // 2
    cx0 = max(0, center_x - side // 2)
    cy0 = max(0, y0 - int(side * 0.05))
    return cx0, cy0, min(alpha.shape[1], cx0 + side), min(alpha.shape[0], cy0 + side)


def import_portrait(path: Path):
    import numpy as np
    from PIL import Image

    image = Image.open(path).convert("RGB")
    array, alpha = alpha_from_gray(image)
    alpha = largest_component(alpha)
    ys, xs = np.nonzero(alpha)
    if len(xs) == 0:
        raise SystemExit(f"{path.name}: 没有找到角色")
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y0, y1 = int(ys.min()), int(ys.max()) + 1

    cx0, cy0, cx1, cy1 = head_crop_box(alpha, x0, x1, y0, y1)
    rgb_crop = array[cy0:cy1, cx0:cx1]
    alpha_crop = alpha[cy0:cy1, cx0:cx1]

    source = Image.fromarray(
        np.dstack([rgb_crop, (alpha_crop * 255).astype(np.uint8)]).astype(np.uint8), "RGBA")
    # 素材本身就是像素画：按整数倍取块中位色降到 96×96，不再走 BOX 面积平均 + 调色板量化
    small = integer_downscale(source, PORTRAIT_SIZE)
    canvas = Image.new("RGBA", (PORTRAIT_SIZE, PORTRAIT_SIZE), (0, 0, 0, 0))
    canvas.alpha_composite(small, ((PORTRAIT_SIZE - small.width) // 2,
                                   (PORTRAIT_SIZE - small.height) // 2))
    return canvas


# --------------------------------------------------------------------------- #
def contact(sheets: list, output: Path, zoom: int = 3) -> None:
    from PIL import Image

    width = max(item.width for item in sheets) * zoom
    height = sum(item.height * zoom + 6 for item in sheets)
    canvas = Image.new("RGB", (width, height), (24, 28, 38))
    y = 0
    for item in sheets:
        canvas.paste(item.resize((item.width * zoom, item.height * zoom), Image.NEAREST), (0, y))
        y += item.height * zoom + 6
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)
    print("contact sheet ->", output, canvas.size)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="活动插图 / 表情头像落位")
    parser.add_argument("--scenes", action="store_true")
    parser.add_argument("--portraits", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--verify", action="store_true", help="只生成核对图，不写 assets")
    args = parser.parse_args(argv)
    run_all = args.all or not (args.scenes or args.portraits)

    from PIL import Image

    if run_all or args.scenes:
        scenes = discover(SCENE_DIR, SCENE_KEYWORDS)
        print("场景 -> 活动：", {key: path.name for key, path in scenes.items()})
        tiles = []
        for activity, path in scenes.items():
            image = import_scene(path)
            tiles.append(image)
            if not args.verify:
                CG_OUT.mkdir(parents=True, exist_ok=True)
                image.save(CG_OUT / f"naiwan_{activity}.png", "PNG")
                print(f"  wrote {CG_OUT.name}/naiwan_{activity}.png {image.size}")
        contact(tiles, ROOT / "build" / "_cg_final.png", zoom=3)

    if run_all or args.portraits:
        portraits = discover(PORTRAIT_DIR, EXPRESSION_KEYWORDS)
        print("表情 -> ID：", {key: path.name for key, path in portraits.items()})
        tiles = []
        for expression, path in portraits.items():
            image = import_portrait(path)
            tiles.append(image)
            if not args.verify:
                PORTRAIT_OUT.mkdir(parents=True, exist_ok=True)
                image.save(PORTRAIT_OUT / f"{expression}.png", "PNG")
                print(f"  wrote portraits/naiwan/{expression}.png {image.size}")
        contact(tiles, ROOT / "build" / "_portraits_final.png", zoom=2)

    return 0


if __name__ == "__main__":
    sys.exit(main())
