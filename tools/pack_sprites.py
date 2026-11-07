"""A 的工具：把单帧 PNG 拼成精灵表，并输出预览 GIF。

约定（A7 / A9）：
* 行顺序固定 s se e ne n nw w sw，列顺序 = 帧序号；
* 每帧 48×48，脚点 (24,46)；
* 输出 PNG 为 RGBA 8 位，透明像素 RGB 必须为 0；
* 角色单帧不超过 12 色（可用 --max-colors 关闭）。

用法：
    python tools/pack_sprites.py --input docs/art/frames/naiwan_walk --output assets/characters/naiwan/walk.png \
        --cols 4 --frame 48x48 --preview docs/art/preview/naiwan_walk.gif

输入目录里帧文件命名为 <方向>_<序号>.png，例如 s_0.png、s_1.png、ne_3.png。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

DIRECTION_ORDER = ("s", "se", "e", "ne", "n", "nw", "w", "sw")


def parse_size(text: str) -> tuple[int, int]:
    try:
        width, height = text.lower().split("x")
        return int(width), int(height)
    except (ValueError, AttributeError) as exc:
        raise argparse.ArgumentTypeError(f"尺寸必须写成 48x48，收到 {text!r}") from exc


def collect_frames(input_dir: Path, cols: int, frame_size: tuple[int, int]):
    """返回 {方向: [Path|None, ...]}，缺失帧填 None 并在报告中列出。"""
    from PIL import Image

    frames: dict[str, list[Path | None]] = {}
    missing: list[str] = []
    for direction in DIRECTION_ORDER:
        row: list[Path | None] = []
        for index in range(cols):
            candidate = input_dir / f"{direction}_{index}.png"
            if candidate.exists():
                with Image.open(candidate) as probe:
                    if probe.size != frame_size:
                        raise SystemExit(
                            f"{candidate.name} 尺寸 {probe.size} 与要求 {frame_size} 不一致")
                row.append(candidate)
            else:
                row.append(None)
                missing.append(f"{direction}_{index}")
        frames[direction] = row
    return frames, missing


def check_transparent_rgb(image) -> int:
    """返回透明但 RGB 非 0 的像素数量（A7 要求为 0）。"""
    illegal = 0
    pixels = image.load()
    width, height = image.size
    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            if a == 0 and (r or g or b):
                illegal += 1
    return illegal


def count_colors(image) -> int:
    colors = set()
    pixels = image.load()
    width, height = image.size
    for y in range(height):
        for x in range(width):
            color = pixels[x, y]
            if color[3] > 0:
                colors.add(color)
    return len(colors)


def build_sheet(frames, cols: int, frame_size: tuple[int, int], fallback: Path | None):
    from PIL import Image

    width, height = frame_size
    sheet = Image.new("RGBA", (width * cols, height * len(DIRECTION_ORDER)), (0, 0, 0, 0))
    filled = 0
    for row_index, direction in enumerate(DIRECTION_ORDER):
        for column in range(cols):
            source = frames[direction][column]
            if source is None:
                if fallback is None:
                    continue
                source = fallback
            else:
                filled += 1
            with Image.open(source) as frame:
                sheet.paste(frame.convert("RGBA"), (column * width, row_index * height))
    return sheet, filled


def build_preview(sheet, frame_size: tuple[int, int], cols: int, fps: float, output: Path) -> None:
    from PIL import Image

    width, height = frame_size
    frames = []
    for column in range(cols):
        strip = Image.new("RGBA", (width, height * len(DIRECTION_ORDER)), (0, 0, 0, 0))
        for row_index in range(len(DIRECTION_ORDER)):
            frame = sheet.crop((column * width, row_index * height,
                                (column + 1) * width, (row_index + 1) * height))
            strip.paste(frame, (0, row_index * height))
        frames.append(strip)
    output.parent.mkdir(parents=True, exist_ok=True)
    duration = max(20, int(1000 / max(1.0, fps)))
    frames[0].save(output, "GIF", save_all=True, append_images=frames[1:],
                   duration=duration, loop=0, disposal=2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="拼接角色精灵表并生成预览 GIF")
    parser.add_argument("--input", required=True, help="单帧 PNG 目录")
    parser.add_argument("--output", required=True, help="输出精灵表 PNG")
    parser.add_argument("--cols", type=int, default=4, help="每个方向的帧数")
    parser.add_argument("--frame", type=parse_size, default=(48, 48), help="单帧尺寸，默认 48x48")
    parser.add_argument("--fps", type=float, default=8.0, help="预览 GIF 帧率")
    parser.add_argument("--preview", default=None, help="预览 GIF 输出路径")
    parser.add_argument("--max-colors", type=int, default=0,
                        help="每帧最大颜色数，0 表示不检查（角色建议 12）")
    parser.add_argument("--allow-missing", action="store_true", help="允许缺失帧（用首帧占位）")
    args = parser.parse_args(argv)

    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        raise SystemExit("需要 Pillow：pip install pillow")

    input_dir = Path(args.input)
    if not input_dir.is_dir():
        raise SystemExit(f"输入目录不存在: {input_dir}")

    frames, missing = collect_frames(input_dir, args.cols, args.frame)
    if missing and not args.allow_missing:
        raise SystemExit("缺少帧: " + ", ".join(missing) + "（可加 --allow-missing 用首帧占位）")

    fallback = None
    for direction in DIRECTION_ORDER:
        present = [item for item in frames[direction] if item is not None]
        if present:
            fallback = present[0]
            break

    sheet, filled = build_sheet(frames, args.cols, args.frame, fallback)

    # 规格检查
    illegal_transparent = check_transparent_rgb(sheet)
    if illegal_transparent:
        print(f"[WARN] 有 {illegal_transparent} 个透明像素 RGB 非 0（应按 A7 置 0）")
    if args.max_colors:
        colors = count_colors(sheet)
        if colors > args.max_colors:
            print(f"[WARN] 精灵表共 {colors} 色，超过 {args.max_colors} 色上限")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, "PNG")
    print(f"sheet: {output} ({sheet.width}x{sheet.height}, {filled}/{args.cols * len(DIRECTION_ORDER)} 帧)")

    if args.preview:
        build_preview(sheet, args.frame, args.cols, args.fps, Path(args.preview))
        print(f"preview: {args.preview}")

    if missing:
        print("缺失帧已用首帧占位: " + ", ".join(missing))
    return 0


if __name__ == "__main__":
    sys.exit(main())
