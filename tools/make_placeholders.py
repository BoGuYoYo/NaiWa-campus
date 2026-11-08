"""A 的占位资源生成器：同尺寸占位美术、音频与低模，并同步 assets/manifest.json。

正式素材由 A 按 A9 流程逐张重绘后替换同名文件；本工具只保证"尺寸、命名、许可登记"三项
与规格一致，让其它岗位可以立刻接入，不需要等美术完成。

用法（在仓库根目录执行）：
    python tools/make_placeholders.py art
    python tools/make_placeholders.py audio
    python tools/make_placeholders.py models
    python tools/make_placeholders.py manifest
    python tools/make_placeholders.py all
    python tools/make_placeholders.py check

依赖：Pillow（art）、numpy + ffmpeg（audio）、panda3d（models）。
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

# --------------------------------------------------------------------------- #
# 32 色主调色板（assets/palette.png 的唯一来源）
# --------------------------------------------------------------------------- #
PALETTE: list[tuple[str, tuple[int, int, int]]] = [
    ("outline", (0x2B, 0x22, 0x35)),
    ("bg_deep", (0x1B, 0x1F, 0x2A)),
    ("bg_mid", (0x2C, 0x34, 0x46)),
    ("bg_soft", (0x3A, 0x44, 0x58)),
    ("yellow_main", (0xF7, 0xC8, 0x1E)),
    ("yellow_light", (0xFF, 0xDD, 0x5C)),
    ("yellow_shade", (0xD9, 0xA4, 0x17)),
    ("cream_main", (0xF1, 0xE2, 0xBC)),
    ("cream_light", (0xFF, 0xF6, 0xDF)),
    ("cream_shade", (0xE3, 0xCE, 0x9E)),
    ("limb_main", (0x4C, 0x4A, 0x2F)),
    ("limb_light", (0x6A, 0x6A, 0x45)),
    ("limb_shade", (0x35, 0x33, 0x20)),
    ("eye_dark", (0x1A, 0x17, 0x12)),
    ("eye_light", (0xFF, 0xFB, 0xEE)),
    ("gold", (0xC0, 0xA1, 0x5F)),
    ("gold_light", (0xE8, 0xCF, 0x97)),
    ("white", (0xF2, 0xF2, 0xF2)),
    ("grey_light", (0xB8, 0xBF, 0xC9)),
    ("grey", (0x7A, 0x82, 0x8F)),
    ("grey_dark", (0x4A, 0x50, 0x5C)),
    ("red", (0xC0, 0x48, 0x3F)),
    ("orange", (0xE2, 0x8B, 0x3A)),
    ("green", (0x4F, 0x8A, 0x5B)),
    ("green_light", (0x8F, 0xC0, 0x8A)),
    ("blue", (0x3F, 0x6E, 0xA8)),
    ("blue_light", (0x8F, 0xB6, 0xDC)),
    ("teal", (0x8F, 0xD3, 0xC7)),
    ("purple", (0x7A, 0x5A, 0xA8)),
    ("pink", (0xE0, 0x91, 0xB0)),
    ("brown", (0x8A, 0x6A, 0x46)),
    ("skin", (0xF4, 0xD2, 0xB0)),
]
PAL = {name: rgb for name, rgb in PALETTE}
OUTLINE = PAL["outline"] + (255,)

# 角色配色方案：奶娃 + 3 名 NPC
SCHEMES = {
    "naiwan": {
        "body": "yellow_main", "light": "yellow_light", "shade": "yellow_shade",
        "belly": "cream_main", "limb": "limb_main", "accessory": None,
    },
    "npc_sumo": {
        "body": "orange", "light": "gold_light", "shade": "brown",
        "belly": "cream_shade", "limb": "limb_shade", "accessory": "headband",
    },
    "npc_chenlang": {
        "body": "blue", "light": "blue_light", "shade": "bg_mid",
        "belly": "grey_light", "limb": "bg_soft", "accessory": "glasses",
    },
    "npc_xiaoyou": {
        "body": "pink", "light": "cream_light", "shade": "purple",
        "belly": "cream_main", "limb": "purple", "accessory": "ribbon",
    },
}

DIRECTIONS = ("s", "se", "e", "ne", "n", "nw", "w", "sw")

# 已由正式素材替换的资源：generate_art() 不得覆盖它们，manifest 里也不再标 placeholder。
# 角色精灵表来自 tools/slice_reference_sheets.py，头像与活动插图来自 tools/import_generated_art.py。
FINAL_ASSETS = (
    "char_naiwan_walk", "char_naiwan_idle",
    "portrait_naiwan_neutral", "portrait_naiwan_happy", "portrait_naiwan_sad",
    "portrait_naiwan_angry", "portrait_naiwan_surprised", "portrait_naiwan_speechless",
    "portrait_naiwan_shy", "portrait_naiwan_proud",
    "cg_naiwan_attend_class", "cg_naiwan_library_study", "cg_naiwan_play_games",
    "cg_naiwan_create_work", "cg_naiwan_join_club", "cg_naiwan_exercise",
    "cg_naiwan_eat_canteen", "cg_naiwan_rest_dorm", "cg_naiwan_campus_walk",
)
FINAL_ASSET_TAGS = ("final", "sliced_from_reference")
FINAL_GENERATED_TAGS = ("final", "generated_from_user_art")
FINAL_ART_PATHS = ("characters/naiwan/walk.png", "characters/naiwan/idle.png")
FINAL_ART_PREFIXES = ("art/cg/", "portraits/naiwan/")
# wf=身体宽度系数，face=脸部横向偏移，eyes=可见眼睛数量，back=是否背向
DIR_PARAMS = {
    "s": {"wf": 1.00, "face": 0, "eyes": 2, "back": False},
    "se": {"wf": 0.92, "face": 2, "eyes": 2, "back": False},
    "e": {"wf": 0.74, "face": 5, "eyes": 1, "back": False},
    "ne": {"wf": 0.88, "face": 2, "eyes": 0, "back": True},
    "n": {"wf": 1.00, "face": 0, "eyes": 0, "back": True},
    "nw": {"wf": 0.88, "face": -2, "eyes": 0, "back": True},
    "w": {"wf": 0.74, "face": -5, "eyes": 1, "back": False},
    "sw": {"wf": 0.92, "face": -2, "eyes": 2, "back": False},
}


def rgba(name: str, alpha: int = 255) -> tuple[int, int, int, int]:
    r, g, b = PAL[name]
    return (r, g, b, alpha)


# --------------------------------------------------------------------------- #
# 角色绘制
# --------------------------------------------------------------------------- #
def draw_character(direction: str, frame: int, walking: bool, scheme: str = "naiwan",
                   size: tuple[int, int] = (48, 48)):
    """48×48 占位角色：脚点固定在 (24,46)，身高约 38 像素（y≈8..45）。

    轮廓按三视图参考：肉黄蛋形身体 + 奶油色肚皮 + 深橄榄色四肢，
    8 方向由 s/se/e/ne/n 绘制后水平镜像得到 w/sw/nw。
    """
    from PIL import Image, ImageDraw

    color = SCHEMES[scheme]
    params = DIR_PARAMS[direction]
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 循环帧：行走 0..3，待机 0..2；第 2/4 帧头顶上移 1 像素
    bob = -1 if (walking and frame % 2 == 1) or (not walking and frame == 1) else 0

    cx = 24 + params["face"] * 0.3
    half_w = 12 * params["wf"]
    top = 8 + bob
    bottom = 41

    # 脚：先画，压在身体之下；脚底贴住 pivot (24, 46)
    foot_y = 44
    lift_left = 1 if (walking and frame == 1) else 0
    lift_right = 1 if (walking and frame == 3) else 0
    feet = [(cx - 9, lift_left), (cx + 2, lift_right)] if not params["back"] else \
           [(cx - 8, lift_right), (cx + 1, lift_left)]
    for fx, lift in feet:
        draw.rounded_rectangle([fx, foot_y - 3 - lift, fx + 6, foot_y + 2 - lift],
                               radius=2, fill=rgba(color["limb"]), outline=OUTLINE)

    # 手臂：背面只露出外侧
    arm_y = 25 + bob
    if params["back"]:
        draw.rounded_rectangle([cx - half_w - 1, arm_y, cx - half_w + 2, arm_y + 9],
                               radius=2, fill=rgba(color["limb"]), outline=OUTLINE)
        draw.rounded_rectangle([cx + half_w - 2, arm_y, cx + half_w + 1, arm_y + 9],
                               radius=2, fill=rgba(color["limb"]), outline=OUTLINE)
    else:
        draw.rounded_rectangle([cx - half_w - 2, arm_y, cx - half_w + 1, arm_y + 9],
                               radius=2, fill=rgba("limb_light"), outline=OUTLINE)
        draw.rounded_rectangle([cx + half_w - 1, arm_y, cx + half_w + 2, arm_y + 9],
                               radius=2, fill=rgba("limb_light"), outline=OUTLINE)

    # 身体：一个蛋形，上部略窄，模拟头身一体的青蛙体型
    draw.ellipse([cx - half_w, top, cx + half_w, bottom], fill=rgba(color["body"]), outline=OUTLINE)
    draw.ellipse([cx - half_w + 4, top - 1, cx + half_w - 4, top + 12], fill=rgba(color["body"]))
    # 左上高光
    draw.arc([cx - half_w + 2, top + 2, cx + half_w - 2, bottom - 4], start=110, end=200,
             fill=rgba(color["light"]))
    # 右下暗部
    draw.arc([cx - half_w + 3, top + 12, cx + half_w - 1, bottom - 2], start=290, end=20,
             fill=rgba(color["shade"]))

    # 肚皮
    if not params["back"]:
        belly_shift = params["face"] * 0.12
        draw.ellipse([cx - 7 + belly_shift, top + 15, cx + 7 + belly_shift, bottom - 3],
                     fill=rgba(color["belly"]))
        draw.arc([cx - 7 + belly_shift, top + 15, cx + 7 + belly_shift, bottom - 3],
                 start=20, end=160, fill=rgba("cream_shade"))

    # 脸
    eye_y = top + 9
    ex = cx + params["face"] * 0.7
    if params["eyes"] == 2:
        for offset in (-5, 2):
            draw.rectangle([ex + offset, eye_y, ex + offset + 2, eye_y + 2], fill=rgba("eye_dark"))
            draw.point((ex + offset, eye_y), fill=rgba("eye_light"))
        draw.line([ex - 1, eye_y + 5, ex + 2, eye_y + 5], fill=rgba("limb_shade"))
        draw.point((ex, eye_y + 6), fill=rgba("limb_shade"))
    elif params["eyes"] == 1:
        draw.rectangle([ex + 2, eye_y, ex + 4, eye_y + 2], fill=rgba("eye_dark"))
        draw.point((ex + 2, eye_y), fill=rgba("eye_light"))
        draw.line([ex + 3, eye_y + 5, ex + 5, eye_y + 5], fill=rgba("limb_shade"))
    else:
        # 背面：脊线、背部高光与尾巴
        draw.arc([cx - 6, top + 4, cx + 6, top + 26], start=250, end=290, fill=rgba(color["shade"]))
        draw.arc([cx - 9, top + 6, cx + 3, bottom - 8], start=110, end=200, fill=rgba(color["light"]))
        draw.arc([cx - 3, bottom - 6, cx + 3, bottom - 1], start=20, end=160, fill=rgba(color["limb"]))

    # 配饰
    accessory = color.get("accessory")
    if accessory == "headband":
        draw.rectangle([cx - half_w + 1, top + 3, cx + half_w - 1, top + 5], fill=rgba("red"))
    elif accessory == "glasses" and params["eyes"] >= 1:
        draw.rectangle([ex - 7, eye_y - 1, ex + 6, eye_y + 3], outline=rgba("gold_light"))
    elif accessory == "ribbon" and params["back"]:
        draw.rectangle([cx - 2, top + 1, cx + 2, top + 4], fill=rgba("cream_light"))

    # 透明像素 RGB 置 0
    px = img.load()
    for y in range(size[1]):
        for x in range(size[0]):
            r, g, b, a = px[x, y]
            if a == 0 and (r or g or b):
                px[x, y] = (0, 0, 0, 0)
    return img


def build_sheet(rows: tuple[str, ...], cols: int, frame_fn, frame_size=(48, 48)):
    """按行顺序拼精灵表：行 = 方向，列 = 帧。"""
    from PIL import Image

    width, height = frame_size
    sheet = Image.new("RGBA", (width * cols, height * len(rows)), (0, 0, 0, 0))
    for row_index, direction in enumerate(rows):
        for frame in range(cols):
            sheet.paste(frame_fn(direction, frame), (frame * width, row_index * height))
    return sheet


# --------------------------------------------------------------------------- #
# 头像与插图
# --------------------------------------------------------------------------- #
EXPRESSIONS = ("neutral", "happy", "sad", "angry", "surprised", "speechless", "shy", "proud")
NPC_EXPRESSIONS = ("neutral", "happy", "sad", "surprised")


def draw_portrait(scheme: str, expression: str, size: int = 96):
    from PIL import Image, ImageDraw

    color = SCHEMES[scheme]
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([6, 30, size - 6, size + 18], fill=rgba(color["body"]), outline=OUTLINE)
    draw.ellipse([24, 52, size - 24, size - 2], fill=rgba(color["belly"]))
    draw.ellipse([14, 40, 40, 58], fill=rgba(color["light"]))
    eye_y = 46
    left, right = 30, 56
    mouth = "neutral"

    if expression == "happy":
        draw.arc([left - 5, eye_y - 6, left + 5, eye_y + 2], start=200, end=340, fill=rgba("eye_dark"), width=2)
        draw.arc([right - 5, eye_y - 6, right + 5, eye_y + 2], start=200, end=340, fill=rgba("eye_dark"), width=2)
        mouth = "smile"
    elif expression == "sad":
        for x in (left, right):
            draw.ellipse([x - 4, eye_y - 2, x + 4, eye_y + 8], fill=rgba("eye_dark"))
        draw.line([left - 6, eye_y - 8, left + 4, eye_y - 4], fill=rgba("limb_shade"), width=2)
        draw.line([right + 6, eye_y - 8, right - 4, eye_y - 4], fill=rgba("limb_shade"), width=2)
        mouth = "frown"
    elif expression == "angry":
        for x in (left, right):
            draw.ellipse([x - 4, eye_y - 1, x + 4, eye_y + 5], fill=rgba("eye_dark"))
        draw.line([left - 6, eye_y - 2, left + 4, eye_y - 7], fill=rgba("limb_shade"), width=2)
        draw.line([right + 6, eye_y - 2, right - 4, eye_y - 7], fill=rgba("limb_shade"), width=2)
        mouth = "flat"
    elif expression == "surprised":
        for x in (left, right):
            draw.ellipse([x - 6, eye_y - 6, x + 6, eye_y + 6], fill=rgba("eye_light"), outline=rgba("eye_dark"))
            draw.ellipse([x - 2, eye_y - 2, x + 2, eye_y + 2], fill=rgba("eye_dark"))
        mouth = "o"
    elif expression == "speechless":
        for x in (left, right):
            draw.line([x - 5, eye_y + 1, x + 5, eye_y + 1], fill=rgba("eye_dark"), width=2)
            draw.point((x - 3, eye_y + 3), fill=rgba("eye_dark"))
        draw.rectangle([left + 8, eye_y + 12, left + 10, eye_y + 17], fill=rgba("blue_light"))
        mouth = "small"
    elif expression == "shy":
        draw.arc([left - 5, eye_y - 2, left + 5, eye_y + 4], start=20, end=160, fill=rgba("eye_dark"), width=2)
        draw.arc([right - 5, eye_y - 2, right + 5, eye_y + 4], start=20, end=160, fill=rgba("eye_dark"), width=2)
        draw.ellipse([left - 10, eye_y + 8, left - 2, eye_y + 12], fill=rgba("pink"))
        draw.ellipse([right + 2, eye_y + 8, right + 10, eye_y + 12], fill=rgba("pink"))
        mouth = "small"
    elif expression == "proud":
        for x in (left, right):
            draw.ellipse([x - 4, eye_y - 2, x + 4, eye_y + 6], fill=rgba("eye_dark"))
            draw.point((x - 2, eye_y), fill=rgba("eye_light"))
        mouth = "smile"
    else:  # neutral
        for x in (left, right):
            draw.ellipse([x - 4, eye_y - 2, x + 4, eye_y + 6], fill=rgba("eye_dark"))
        mouth = "neutral"

    my = eye_y + 16
    if mouth == "smile":
        draw.arc([38, my - 6, 58, my + 6], start=20, end=160, fill=rgba("limb_shade"), width=2)
    elif mouth == "frown":
        draw.arc([38, my + 2, 58, my + 12], start=200, end=340, fill=rgba("limb_shade"), width=2)
    elif mouth == "o":
        draw.ellipse([44, my - 2, 52, my + 6], fill=rgba("limb_shade"))
    elif mouth == "small":
        draw.line([44, my + 2, 52, my + 2], fill=rgba("limb_shade"), width=2)
    elif mouth == "flat":
        draw.line([40, my + 2, 56, my + 2], fill=rgba("limb_shade"), width=2)
    else:
        draw.line([42, my + 2, 54, my + 2], fill=rgba("limb_shade"), width=2)

    accessory = color.get("accessory")
    if accessory == "headband":
        draw.rectangle([10, 34, size - 10, 40], fill=rgba("red"))
    elif accessory == "glasses":
        draw.rectangle([left - 8, eye_y - 6, right + 8, eye_y + 10], outline=rgba("gold_light"), width=2)
    elif accessory == "ribbon":
        draw.rectangle([size // 2 - 8, 26, size // 2 + 8, 34], fill=rgba("purple"))
    return img


CG_ACTIVITIES = (
    "attend_class", "library_study", "play_games", "create_work", "join_club",
    "exercise", "eat_canteen", "rest_dorm", "campus_walk",
)
CG_THEME = {
    "attend_class": ("bg_mid", "blue_light"),
    "library_study": ("bg_soft", "gold_light"),
    "play_games": ("purple", "teal"),
    "create_work": ("bg_deep", "teal"),
    "join_club": ("green", "cream_main"),
    "exercise": ("blue", "green_light"),
    "eat_canteen": ("orange", "cream_light"),
    "rest_dorm": ("bg_deep", "blue_light"),
    "campus_walk": ("green", "blue_light"),
}


def draw_cg(activity: str, size=(160, 90)):
    from PIL import Image, ImageDraw

    bg, accent = CG_THEME[activity]
    img = Image.new("RGBA", size, rgba(bg))
    draw = ImageDraw.Draw(img)
    # 天空/地面两段
    draw.rectangle([0, 0, size[0], int(size[1] * 0.62)], fill=rgba("bg_mid" if bg != "bg_mid" else "bg_soft"))
    draw.rectangle([0, int(size[1] * 0.62), size[0], size[1]], fill=rgba("brown"))
    draw.line([0, int(size[1] * 0.62), size[0], int(size[1] * 0.62)], fill=rgba("limb_shade"))
    # 光斑
    draw.ellipse([104, 8, 148, 52], fill=rgba(accent, 120))
    draw.rectangle([16, 12, 62, 44], fill=rgba(accent))
    draw.rectangle([16, 12, 62, 44], outline=rgba("bg_deep"))
    # 角色
    char = draw_character("s", 0, False, "naiwan")
    img.alpha_composite(char, (56, 32))
    # 道具提示
    if activity == "attend_class":
        draw.rectangle([112, 56, 150, 62], fill=rgba("cream_main"))
        draw.rectangle([118, 44, 122, 58], fill=rgba("white"))
    elif activity == "library_study":
        for index in range(4):
            draw.rectangle([108 + index * 10, 46, 114 + index * 10, 66], fill=rgba("gold_light"))
    elif activity == "play_games":
        draw.rectangle([106, 52, 138, 70], fill=rgba("bg_deep"))
        draw.rectangle([112, 56, 132, 66], fill=rgba("teal"))
    elif activity == "create_work":
        # 敲代码：左侧改成第二块代码屏，右边笔记本 + 代码行 + 咖啡
        draw.ellipse([100, 4, 152, 56], fill=rgba("bg_mid"))  # 盖掉通用光斑，改成夜里写代码的墙面
        draw.rectangle([16, 12, 62, 44], fill=rgba("bg_deep"), outline=rgba("teal"))
        draw.line([16, 16, 62, 16], fill=rgba("bg_mid"))
        for index, (y, color, x2) in enumerate((
                (20, "green_light", 44), (23, "blue_light", 38),
                (26, "cream_main", 50), (29, "teal", 34),
                (32, "gold_light", 46), (35, "blue_light", 30), (38, "green_light", 42))):
            draw.line([20, y, x2 + index, y], fill=rgba(color))
        draw.rectangle([104, 46, 146, 68], fill=rgba("bg_deep"), outline=rgba("teal"))
        draw.line([104, 50, 146, 50], fill=rgba("bg_mid"))
        for index, (y, color, x2) in enumerate((
                (54, "green_light", 130), (57, "blue_light", 122),
                (60, "cream_main", 136), (63, "teal", 116), (66, "gold_light", 128))):
            draw.line([108, y, x2 + index * 2, y], fill=rgba(color))
        draw.rectangle([132, 64, 134, 66], fill=rgba("white"))   # 光标
        draw.polygon([(100, 68), (150, 68), (144, 74), (106, 74)], fill=rgba("grey_dark"))
        draw.rectangle([150, 56, 156, 63], fill=rgba("cream_main"))  # 咖啡杯
        draw.rectangle([151, 53, 155, 56], fill=rgba("brown"))
    elif activity == "join_club":
        draw.rectangle([112, 40, 116, 74], fill=rgba("limb_main"))
        draw.rectangle([116, 40, 140, 54], fill=rgba("red"))
    elif activity == "exercise":
        draw.ellipse([116, 60, 128, 72], fill=rgba("cream_light"))
    elif activity == "eat_canteen":
        draw.rectangle([110, 58, 144, 68], fill=rgba("white"))
        draw.ellipse([116, 52, 138, 62], fill=rgba("orange"))
    elif activity == "rest_dorm":
        draw.rectangle([106, 58, 152, 74], fill=rgba("blue"))
        draw.rectangle([110, 52, 122, 58], fill=rgba("cream_light"))
    else:  # campus_walk
        for index, x in enumerate((104, 128, 146)):
            draw.rectangle([x, 46, x + 4, 66], fill=rgba("brown"))
            draw.ellipse([x - 6, 32, x + 10, 50], fill=rgba("green_light"))
    return img


# --------------------------------------------------------------------------- #
# UI 与图标
# --------------------------------------------------------------------------- #
TINY_FONT = {
    "e": ("111", "100", "110", "100", "111"),
    "w": ("101", "101", "101", "101", "111"),
    "a": ("010", "101", "111", "101", "101"),
    "s": ("111", "100", "111", "001", "111"),
    "d": ("110", "101", "101", "101", "110"),
    "p": ("111", "101", "111", "100", "100"),
    "c": ("111", "100", "100", "100", "111"),
}
KEY_GLYPHS = {
    "e": ("e",), "w": ("w",), "a": ("a",), "s": ("s",), "d": ("d",),
    "space": ("",), "tab": ("",), "esc": ("",),
}


def draw_icon(kind: str, size: int = 16):
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    if kind == "academic":
        draw.rectangle([2, 3, 13, 12], fill=rgba("cream_main"), outline=OUTLINE)
        draw.line([7, 3, 7, 12], fill=rgba("limb_shade"))
        draw.line([3, 5, 6, 5], fill=rgba("limb_shade"))
        draw.line([8, 5, 11, 5], fill=rgba("limb_shade"))
    elif kind == "stamina":
        draw.ellipse([3, 3, 12, 12], fill=rgba("red"))
        draw.rectangle([7, 5, 8, 10], fill=rgba("white"))
        draw.rectangle([6, 6, 9, 8], fill=rgba("white"))
    elif kind == "mood":
        draw.ellipse([2, 2, 13, 13], fill=rgba("yellow_main"), outline=OUTLINE)
        draw.point((6, 6), fill=rgba("eye_dark"))
        draw.point((10, 6), fill=rgba("eye_dark"))
        draw.arc([5, 7, 11, 12], start=20, end=160, fill=rgba("limb_shade"))
    elif kind == "social":
        draw.ellipse([2, 3, 8, 9], fill=rgba("blue_light"), outline=OUTLINE)
        draw.ellipse([8, 6, 14, 12], fill=rgba("teal"), outline=OUTLINE)
    elif kind == "interest":
        points = [(8, 1), (10, 6), (15, 6), (11, 9), (13, 14), (8, 11), (3, 14), (5, 9), (1, 6), (6, 6)]
        draw.polygon(points, fill=rgba("gold_light"), outline=OUTLINE)
    elif kind == "energy":
        draw.polygon([(9, 1), (4, 9), (8, 9), (6, 15), (12, 7), (8, 7)], fill=rgba("yellow_light"), outline=OUTLINE)
    elif kind == "ui_move":
        draw.polygon([(3, 2), (13, 8), (8, 8), (9, 13), (6, 13), (5, 8), (2, 10)], fill=rgba("white"), outline=OUTLINE)
    elif kind == "ui_confirm":
        draw.line([2, 8, 6, 12, 13, 3], fill=rgba("green_light"), width=3)
    elif kind == "ui_cancel":
        draw.line([3, 3, 12, 12], fill=rgba("red"), width=3)
        draw.line([12, 3, 3, 12], fill=rgba("red"), width=3)
    elif kind == "play":
        draw.polygon([(5, 2), (13, 8), (5, 14)], fill=rgba("white"), outline=OUTLINE)
    elif kind == "code":
        # 敲代码：终端窗口 + 提示符 > + 代码行 + 光标
        draw.rectangle([1, 3, 14, 12], fill=rgba("bg_deep"), outline=rgba("teal"))
        draw.rectangle([1, 3, 14, 5], fill=rgba("bg_mid"))
        draw.point((3, 4), fill=rgba("red"))
        draw.point((5, 4), fill=rgba("yellow_main"))
        draw.point((7, 4), fill=rgba("green_light"))
        draw.line([3, 7, 4, 8], fill=rgba("teal"))          # 提示符 >
        draw.line([4, 8, 3, 9], fill=rgba("teal"))
        draw.line([6, 8, 12, 8], fill=rgba("green_light"))
        draw.line([6, 10, 10, 10], fill=rgba("blue_light"))
        draw.line([11, 10, 11, 12], fill=rgba("white"))     # 光标
    elif kind == "club":
        draw.rectangle([4, 2, 5, 14], fill=rgba("limb_main"))
        draw.rectangle([5, 3, 13, 8], fill=rgba("red"))
    elif kind == "exercise":
        draw.rectangle([2, 6, 4, 10], fill=rgba("grey_dark"))
        draw.rectangle([11, 6, 13, 10], fill=rgba("grey_dark"))
        draw.rectangle([4, 7, 11, 9], fill=rgba("grey_light"))
    elif kind == "eat":
        draw.arc([2, 4, 13, 13], start=0, end=180, fill=rgba("white"), width=2)
        draw.line([2, 9, 13, 9], fill=rgba("white"), width=2)
    elif kind == "rest":
        draw.pieslice([3, 2, 12, 12], start=90, end=270, fill=rgba("blue_light"), outline=OUTLINE)
        draw.pieslice([6, 4, 15, 13], start=270, end=90, fill=(0, 0, 0, 0), outline=None)
    elif kind == "walk":
        draw.ellipse([3, 2, 6, 7], fill=rgba("cream_main"))
        draw.ellipse([8, 9, 11, 14], fill=rgba("cream_main"))
    else:  # 未知图标：问号方块
        draw.rectangle([2, 2, 13, 13], outline=rgba("gold"), fill=rgba("bg_mid"))
    return img


def draw_key_hint(key: str, size: int = 16):
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([1, 2, size - 2, size - 3], radius=2, fill=rgba("bg_mid"), outline=rgba("gold"))
    if key in TINY_FONT:
        glyph = TINY_FONT[key]
        for row, bits in enumerate(glyph):
            for col, bit in enumerate(bits):
                if bit == "1":
                    x = 5 + col
                    y = 5 + row
                    draw.rectangle([x, y, x, y], fill=rgba("white"))
    else:
        # space / tab / esc 用三条横线表示宽键
        label = {"space": 5, "tab": 3, "esc": 2}.get(key, 2)
        for index in range(label):
            y = 5 + index * 3
            draw.line([4, y, size - 5, y], fill=rgba("white"))
    return img


def draw_panel_9slice(size: int = 48, margin: int = 16):
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (size, size), rgba("bg_deep", 235))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, size - 1, size - 1], outline=rgba("gold"))
    draw.rectangle([1, 1, size - 2, size - 2], outline=rgba("bg_mid"))
    draw.rectangle([margin, margin, size - margin - 1, size - margin - 1], fill=rgba("bg_deep", 0))
    draw.line([margin, 4, margin, size - 5], fill=rgba("bg_soft"))
    return img


def draw_bar(size=(100, 8), fill_mode=False):
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    if fill_mode:
        for x in range(size[0]):
            ratio = x / max(1, size[0] - 1)
            color = PAL["green_light"] if ratio < 0.5 else PAL["yellow_main"]
            draw.line([x, 0, x, size[1] - 1], fill=color + (255,))
    else:
        draw.rectangle([0, 0, size[0] - 1, size[1] - 1], fill=rgba("bg_deep", 220), outline=rgba("gold"))
    return img


def draw_slot(full: bool, size: int = 8):
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    if full:
        draw.ellipse([0, 0, size - 1, size - 1], fill=rgba("gold_light"))
    else:
        draw.ellipse([0, 0, size - 1, size - 1], outline=rgba("grey"))
    return img


def draw_cursor(size: int = 8):
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.polygon([(0, 0), (0, 7), (2, 5), (4, 8), (6, 7), (4, 4), (7, 3)], fill=rgba("gold_light"), outline=OUTLINE)
    return img


def draw_shadow(size=(24, 8)):
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([0, 0, size[0] - 1, size[1] - 1], fill=(0, 0, 0, 102))  # 40% 不透明度
    return img


def draw_palette():
    from PIL import Image, ImageDraw

    cell = 16
    cols = 8
    rows = 4
    img = Image.new("RGBA", (cell * cols, cell * rows), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    for index, (_name, rgb) in enumerate(PALETTE[: cols * rows]):
        x = (index % cols) * cell
        y = (index // cols) * cell
        draw.rectangle([x, y, x + cell - 1, y + cell - 1], fill=rgb + (255,))
    return img


# --------------------------------------------------------------------------- #
# 资源规格表：manifest 与生成流程的唯一来源
# --------------------------------------------------------------------------- #
def asset_specs() -> list[dict]:
    specs: list[dict] = []

    def add(asset_id, kind, path, license_id, **extra):
        item = {"id": asset_id, "type": kind, "path": path, "license_id": license_id}
        item.update(extra)
        specs.append(item)

    add("char_naiwan_walk", "sprite_sheet", "characters/naiwan/walk.png", "LIC-0001",
        frame_w=48, frame_h=48, cols=8, rows=8, fps=8, pivot=[24, 46],
        row_order=list(DIRECTIONS), tags=list(FINAL_ASSET_TAGS))
    add("char_naiwan_idle", "sprite_sheet", "characters/naiwan/idle.png", "LIC-0001",
        frame_w=48, frame_h=48, cols=3, rows=8, fps=3, pivot=[24, 46],
        row_order=list(DIRECTIONS), tags=list(FINAL_ASSET_TAGS))
    add("char_shadow", "image", "characters/common/shadow.png", "LIC-0002", tags=["placeholder"])

    for expression in EXPRESSIONS:
        add(f"portrait_naiwan_{expression}", "image", f"portraits/naiwan/{expression}.png", "LIC-0006",
            tags=list(FINAL_GENERATED_TAGS))

    for activity in CG_ACTIVITIES:
        add(f"cg_naiwan_{activity}", "image", f"art/cg/naiwan_{activity}.png", "LIC-0006",
            tags=list(FINAL_GENERATED_TAGS))

    for npc in ("npc_sumo", "npc_chenlang", "npc_xiaoyou"):
        short = npc.split("_")[1]
        add(f"char_{npc}_idle", "sprite_sheet", f"characters/npc/{short}_idle.png", "LIC-0003",
            frame_w=48, frame_h=48, cols=2, rows=4, fps=2, pivot=[24, 46],
            row_order=["s", "e", "n", "w"], tags=["placeholder"])
        for expression in NPC_EXPRESSIONS:
            add(f"portrait_{npc}_{expression}", "image", f"portraits/{short}/{expression}.png",
                "LIC-0003", tags=["placeholder"])

    for index in range(1, 5):
        add(f"char_extra_{index}", "image", f"characters/extra/extra_{index}.png", "LIC-0004",
            frame_w=48, frame_h=48, cols=1, rows=1, fps=1, pivot=[24, 46], tags=["placeholder"])

    for building in ("dorm", "teaching", "library", "club", "canteen"):
        add(f"model_{building}", "model", f"campus/{building}.bam", "LIC-0201", tags=["placeholder"])
        add(f"model_interior_{building}", "model", f"campus/interior_{building}.bam", "LIC-0201",
            tags=["placeholder"])
    add("model_ground", "model", "campus/ground.bam", "LIC-0201", tags=["placeholder"])
    for prop in ("road", "tree", "lamp", "bench", "fence", "sign", "planter", "bin",
                 "bike_rack", "flag_pole", "rock", "flower_bed"):
        add(f"model_prop_{prop}", "model", f"campus/props/{prop}.bam", "LIC-0201", tags=["placeholder"])

    add("ui_panel_9slice", "image", "ui/panel_9slice.png", "LIC-0101", tags=["placeholder"])
    for attribute in ("academic", "stamina", "mood", "social", "interest", "energy"):
        add(f"ui_icon_{attribute}", "image", f"ui/icons/{attribute}.png", "LIC-0101", tags=["placeholder"])
    for activity in CG_ACTIVITIES:
        add(f"ui_icon_{activity}", "image", f"ui/icons/activity_{activity}.png", "LIC-0101",
            tags=["placeholder"])
    for key in ("e", "space", "tab", "esc", "w", "a", "s", "d"):
        add(f"ui_key_{key}", "image", f"ui/keys/{key}.png", "LIC-0101", tags=["placeholder"])
    add("ui_slot_full", "image", "ui/slot_full.png", "LIC-0101", tags=["placeholder"])
    add("ui_slot_empty", "image", "ui/slot_empty.png", "LIC-0101", tags=["placeholder"])
    add("ui_bar_frame", "image", "ui/bar_frame.png", "LIC-0101", tags=["placeholder"])
    add("ui_bar_fill", "image", "ui/bar_fill.png", "LIC-0101", tags=["placeholder"])
    add("ui_cursor", "image", "ui/cursor.png", "LIC-0101", tags=["placeholder"])
    add("palette", "image", "palette.png", "LIC-0101", tags=["placeholder"])

    add("font_ui", "font", "fonts/FusionPixel12.ttf", "LIC-0301", tags=["placeholder", "pending"])

    add("bgm_title", "music", "audio/bgm/title.ogg", "LIC-0401", loop=True, volume=0.8,
        tags=["placeholder"])
    add("bgm_campus_day", "music", "audio/bgm/campus_day.ogg", "LIC-0401", loop=True, volume=0.8,
        tags=["placeholder"])
    add("bgm_event", "music", "audio/bgm/event.ogg", "LIC-0401", loop=True, volume=0.75,
        tags=["placeholder"])
    add("bgm_graduation", "music", "audio/bgm/graduation.ogg", "LIC-0401", loop=True, volume=0.85,
        tags=["placeholder"])
    for sfx in ("ui_move", "ui_confirm", "ui_cancel", "interact", "stat_up", "stat_down",
                "footstep_ground", "footstep_floor", "door", "day_end", "semester_end", "ending"):
        add(f"sfx_{sfx}", "sound", f"audio/sfx/{sfx}.ogg", "LIC-0402", volume=0.9,
            tags=["placeholder"])
    return specs


LICENSE_ROWS = [
    {
        "license_id": "LIC-0001", "asset_ids": "char_naiwan_walk;char_naiwan_idle",
        "author": "开发者A（切片与像素化处理）；原图由用户提供",
        "source_url": "素材/向前走.jfif；右前前进.jfif；向右走.jfif；右后行走.jfif；"
                      "向后行走.jfif；左后行走.jfif；向左走.jfif；左前前进.jfif",
        "license": "用户提供的 AI 生成素材（生成工具与条款版本见素材来源说明）",
        "commercial_ok": "yes", "modified": "yes",
        "date_added": "2026-11-07",
        "notes": "由 tools/slice_reference_sheets.py 自动切片：每个方向一张 4 列 × 2 排的序列帧，"
                 "取 FRAME 01～08 八帧循环；抠背景、面积缩放统一到身高 38 像素、脚点 24,46、"
                 "1 像素描边、量化到 32 色；待机表来自 素材/待机图.jfif（同一流程，"
                 "`--idle-source` 指定）；商用范围以用户提供的生成条款为准，对外发布前需再确认一次",
    },
    {
        "license_id": "LIC-0006", "asset_ids": "portrait_naiwan_*;cg_naiwan_*",
        "author": "开发者A（规格落位与调色板量化）；原图由用户生成",
        "source_url": "素材/小表情/（8 张表情）；素材/场景/（9 张活动插图）",
        "license": "用户提供的 AI 生成素材（生成工具与条款版本见素材来源说明）",
        "commercial_ok": "yes", "modified": "yes",
        "date_added": "2026-11-08",
        "notes": "由 tools/import_generated_art.py 落位：活动插图 2752×1536 居中裁 16:9 后 "
                 "面积缩放到 160×90、自适应量化 64 色；表情 1024×1024 抠灰底、按肩宽归一裁成"
                 "半身像后缩到 96×96、量化到项目 32 色、透明像素 RGB 置 0",
    },
    {
        "license_id": "LIC-0005", "asset_ids": "portrait_naiwan_*;cg_naiwan_*",
        "author": "开发者A（占位图由 tools/make_placeholders.py 程序生成）",
        "source_url": "internal://naiwa_campus/tools/make_placeholders.py",
        "license": "项目内部原创", "commercial_ok": "yes", "modified": "yes",
        "date_added": "2026-01-05",
        "notes": "头像与活动插图仍是占位图，待按 A9 流程重绘后替换并更新本行",
    },
    {
        "license_id": "LIC-0002", "asset_ids": "char_shadow",
        "author": "开发者A", "source_url": "internal://naiwa_campus/tools/make_placeholders.py",
        "license": "项目内部原创", "commercial_ok": "yes", "modified": "no",
        "date_added": "2026-01-05", "notes": "24×8 椭圆阴影，黑色 40% 不透明度",
    },
    {
        "license_id": "LIC-0003", "asset_ids": "char_npc_*;portrait_npc_*",
        "author": "开发者A（占位图程序生成）", "source_url": "internal://naiwa_campus/tools/make_placeholders.py",
        "license": "项目内部原创", "commercial_ok": "yes", "modified": "yes",
        "date_added": "2026-01-05", "notes": "NPC 待机与头像占位，正式素材替换前不得对外宣传",
    },
    {
        "license_id": "LIC-0004", "asset_ids": "char_extra_*",
        "author": "开发者A（占位图程序生成）", "source_url": "internal://naiwa_campus/tools/make_placeholders.py",
        "license": "项目内部原创", "commercial_ok": "yes", "modified": "yes",
        "date_added": "2026-01-05", "notes": "环境 NPC 单帧占位",
    },
    {
        "license_id": "LIC-0101", "asset_ids": "ui_*;palette",
        "author": "开发者A（程序生成像素图）", "source_url": "internal://naiwa_campus/tools/make_placeholders.py",
        "license": "项目内部原创", "commercial_ok": "yes", "modified": "yes",
        "date_added": "2026-01-05", "notes": "UI 占位与 32 色调色板，第 5 周替换为正式皮肤",
    },
    {
        "license_id": "LIC-0201", "asset_ids": "model_*",
        "author": "开发者A（Panda3D 程序生成低模）", "source_url": "internal://naiwa_campus/tools/make_placeholders.py",
        "license": "项目内部原创", "commercial_ok": "yes", "modified": "yes",
        "date_added": "2026-01-05", "notes": "白模占位，正式模型由 Blender 4.x 导出 glTF 后经 tools/gltf_to_bam.py 转换",
    },
    {
        "license_id": "LIC-0301", "asset_ids": "font_ui",
        "author": "TakWolf / Fusion Pixel Font 社区",
        "source_url": "https://github.com/TakWolf/fusion-pixel-font",
        "license": "SIL OFL 1.1", "commercial_ok": "yes", "modified": "no",
        "date_added": "2026-01-05",
        "notes": "待放入 assets/fonts/FusionPixel12.ttf；缺失时 TextDB 回退引擎默认字体并写 asset.missing",
    },
    {
        "license_id": "LIC-0401", "asset_ids": "bgm_*",
        "author": "开发者A（numpy 程序合成占位音乐）",
        "source_url": "internal://naiwa_campus/tools/make_placeholders.py",
        "license": "项目内部原创", "commercial_ok": "yes", "modified": "yes",
        "date_added": "2026-01-05", "notes": "占位循环音乐，正式作曲替换前仅内部测试使用",
    },
    {
        "license_id": "LIC-0402", "asset_ids": "sfx_*",
        "author": "开发者A（numpy 程序合成占位音效）",
        "source_url": "internal://naiwa_campus/tools/make_placeholders.py",
        "license": "项目内部原创", "commercial_ok": "yes", "modified": "yes",
        "date_added": "2026-01-05", "notes": "12 个占位音效，峰值控制在 -3 dBFS 以下",
    },
]


# --------------------------------------------------------------------------- #
# 生成：美术
# --------------------------------------------------------------------------- #
def generate_art(keep_final: bool = True) -> list[str]:
    """生成占位美术；keep_final=True 时不覆盖已切好的正式角色精灵表。"""
    written: list[str] = []

    def save(img, relative: str) -> None:
        target = ASSETS / relative
        if keep_final and (relative in FINAL_ART_PATHS or relative.startswith(FINAL_ART_PREFIXES)):
            print(f"  skip final: {relative}")
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        img.save(target, "PNG")
        written.append(relative)

    walk = build_sheet(DIRECTIONS, 8, lambda d, f: draw_character(d, f, True))
    save(walk, "characters/naiwan/walk.png")
    idle = build_sheet(DIRECTIONS, 3, lambda d, f: draw_character(d, f, False))
    save(idle, "characters/naiwan/idle.png")
    save(draw_shadow(), "characters/common/shadow.png")

    for expression in EXPRESSIONS:
        save(draw_portrait("naiwan", expression), f"portraits/naiwan/{expression}.png")
    for activity in CG_ACTIVITIES:
        save(draw_cg(activity), f"art/cg/naiwan_{activity}.png")

    for scheme in ("npc_sumo", "npc_chenlang", "npc_xiaoyou"):
        short = scheme.split("_")[1]
        sheet = build_sheet(("s", "e", "n", "w"), 2, lambda d, f: draw_character(d, f, False, scheme))
        save(sheet, f"characters/npc/{short}_idle.png")
        for expression in NPC_EXPRESSIONS:
            save(draw_portrait(scheme, expression), f"portraits/{short}/{expression}.png")

    extra_schemes = ("npc_sumo", "npc_chenlang", "npc_xiaoyou", "naiwan")
    for index in range(1, 5):
        save(draw_character("s", 0, False, extra_schemes[index - 1]),
             f"characters/extra/extra_{index}.png")

    save(draw_panel_9slice(), "ui/panel_9slice.png")
    for attribute, icon in (("academic", "academic"), ("stamina", "stamina"), ("mood", "mood"),
                            ("social", "social"), ("interest", "interest"), ("energy", "energy")):
        save(draw_icon(icon), f"ui/icons/{attribute}.png")
    activity_icons = {
        "attend_class": "academic", "library_study": "academic", "play_games": "play",
        "create_work": "code", "join_club": "club", "exercise": "exercise",
        "eat_canteen": "eat", "rest_dorm": "rest", "campus_walk": "walk",
    }
    for activity, icon in activity_icons.items():
        save(draw_icon(icon), f"ui/icons/activity_{activity}.png")
    for key in ("e", "space", "tab", "esc", "w", "a", "s", "d"):
        save(draw_key_hint(key), f"ui/keys/{key}.png")
    save(draw_slot(True), "ui/slot_full.png")
    save(draw_slot(False), "ui/slot_empty.png")
    save(draw_bar(fill_mode=False), "ui/bar_frame.png")
    save(draw_bar(fill_mode=True), "ui/bar_fill.png")
    save(draw_cursor(), "ui/cursor.png")
    save(draw_palette(), "palette.png")
    return written


# --------------------------------------------------------------------------- #
# 生成：音频（numpy 合成 + ffmpeg 编码 OGG）
# --------------------------------------------------------------------------- #
BGM_SPEC = {
    "title": dict(bpm=72, seconds=60, root=220.0, scale=(0, 3, 5, 7, 10), mood="calm"),
    "campus_day": dict(bpm=108, seconds=72, root=261.63, scale=(0, 2, 4, 7, 9), mood="bright"),
    "event": dict(bpm=88, seconds=60, root=196.0, scale=(0, 2, 3, 7, 8), mood="tense"),
    "graduation": dict(bpm=80, seconds=84, root=246.94, scale=(0, 2, 4, 5, 7), mood="warm"),
}

SFX_SPEC = {
    "ui_move": dict(kind="blip", freq=880, seconds=0.06),
    "ui_confirm": dict(kind="arp", freqs=(523.25, 784.0), seconds=0.18),
    "ui_cancel": dict(kind="arp", freqs=(440.0, 294.0), seconds=0.16),
    "interact": dict(kind="blip", freq=660, seconds=0.10),
    "stat_up": dict(kind="arp", freqs=(523.25, 659.25, 784.0), seconds=0.28),
    "stat_down": dict(kind="arp", freqs=(392.0, 311.13), seconds=0.26),
    "footstep_ground": dict(kind="noise", seconds=0.09, lowpass=1800),
    "footstep_floor": dict(kind="noise", seconds=0.07, lowpass=4200),
    "door": dict(kind="noise", seconds=0.34, lowpass=900, sweep=True),
    "day_end": dict(kind="arp", freqs=(392.0, 523.25, 659.25), seconds=0.5),
    "semester_end": dict(kind="arp", freqs=(392.0, 523.25, 659.25, 784.0), seconds=0.85),
    "ending": dict(kind="chord", freqs=(261.63, 329.63, 392.0, 523.25), seconds=1.8),
}


def _synth_bgm(name: str, spec: dict, sample_rate: int = 44100):
    import numpy as np

    seconds = spec["seconds"]
    total = int(seconds * sample_rate)
    t = np.arange(total) / sample_rate
    beat = 60.0 / spec["bpm"]
    scale = spec["scale"]
    root = spec["root"]

    left = np.zeros(total)
    right = np.zeros(total)
    # 和弦铺底
    chord_len = beat * 4
    bar = 0
    while bar * chord_len < seconds:
        start = int(bar * chord_len * sample_rate)
        end = min(total, start + int(chord_len * sample_rate))
        if end <= start:
            break
        degree = scale[bar % len(scale)]
        freq = root * (2 ** (degree / 12.0))
        local_t = t[start:end] - t[start]
        env = np.minimum(1.0, local_t / 0.4) * np.minimum(1.0, (chord_len - local_t) / 0.6)
        pad = (np.sin(2 * np.pi * freq * 0.5 * local_t) * 0.20
               + np.sin(2 * np.pi * freq * 0.25 * local_t) * 0.12)
        left[start:end] += pad * env
        right[start:end] += pad * env * 0.9
        bar += 1

    # 旋律：八分音符在音阶上走
    step = 0
    note_len = beat / 2
    while step * note_len < seconds:
        start = int(step * note_len * sample_rate)
        end = min(total, start + int(note_len * sample_rate))
        if end <= start:
            break
        degree = scale[(step * 3 + (1 if spec["mood"] == "tense" else 2)) % len(scale)]
        octave = 2 if step % 4 < 2 else 1
        freq = root * octave * (2 ** (degree / 12.0))
        local_t = t[start:end] - t[start]
        env = np.exp(-local_t * 6.0) * 0.75
        wave = np.sign(np.sin(2 * np.pi * freq * local_t)) * 0.08 + np.sin(2 * np.pi * freq * local_t) * 0.16
        pan = 0.5 + 0.25 * np.sin(step * 0.7)
        left[start:end] += wave * env * (1 - pan) * 1.2
        right[start:end] += wave * env * pan * 1.2
        step += 1

    # 节拍
    beat_index = 0
    while beat_index * beat < seconds:
        start = int(beat_index * beat * sample_rate)
        end = min(total, start + int(0.05 * sample_rate))
        if end <= start:
            break
        local_t = t[start:end] - t[start]
        env = np.exp(-local_t * 60.0)
        left[start:end] += np.sin(2 * np.pi * 70 * local_t) * env * 0.25
        right[start:end] += np.sin(2 * np.pi * 70 * local_t) * env * 0.25
        beat_index += 1

    # 淡入淡出保证无缝循环
    fade = int(0.6 * sample_rate)
    if total > 2 * fade:
        ramp = np.linspace(0.0, 1.0, fade)
        for channel in (left, right):
            channel[:fade] *= ramp
            channel[-fade:] *= ramp[::-1]
    return _normalize(left, right)


def _normalize(left, right, target_dbfs: float = -16.0):
    import numpy as np

    peak = max(1e-9, float(np.max(np.abs(left))), float(np.max(np.abs(right))))
    gain = (10 ** (target_dbfs / 20.0)) / peak
    return np.clip(left * gain, -1.0, 1.0), np.clip(right * gain, -1.0, 1.0)


def _synth_sfx(name: str, spec: dict, sample_rate: int = 44100):
    import numpy as np

    seconds = spec["seconds"]
    total = max(1, int(seconds * sample_rate))
    t = np.arange(total) / sample_rate
    kind = spec["kind"]
    if kind == "blip":
        env = np.exp(-t * 40.0)
        data = np.sin(2 * np.pi * spec["freq"] * t) * env
    elif kind == "arp":
        data = np.zeros(total)
        freqs = spec["freqs"]
        segment = total // len(freqs)
        for index, freq in enumerate(freqs):
            start = index * segment
            end = total if index == len(freqs) - 1 else (index + 1) * segment
            local_t = t[start:end] - t[start]
            env = np.exp(-local_t * 12.0)
            data[start:end] = (np.sin(2 * np.pi * freq * local_t) * 0.7
                               + np.sign(np.sin(2 * np.pi * freq * local_t)) * 0.15) * env
    elif kind == "noise":
        rng = np.random.default_rng(abs(hash(name)) % (2 ** 32))
        noise = rng.normal(0, 1, total)
        # 一阶低通
        cutoff = spec.get("lowpass", 2000)
        alpha = min(0.99, 2 * np.pi * cutoff / sample_rate)
        filtered = np.zeros(total)
        acc = 0.0
        for index in range(total):
            acc = acc + alpha * (noise[index] - acc)
            filtered[index] = acc
        env = np.exp(-t * 28.0)
        if spec.get("sweep"):
            env = env * (1.0 + 0.5 * np.sin(2 * np.pi * 3 * t))
        data = filtered * env
    elif kind == "chord":
        data = np.zeros(total)
        for freq in spec["freqs"]:
            data += np.sin(2 * np.pi * freq * t) * 0.25
        env = np.minimum(1.0, t / 0.15) * np.exp(-t * 1.2)
        data *= env
    else:
        data = np.zeros(total)
    peak = max(1e-9, float(np.max(np.abs(data))))
    gain = (10 ** (-3.0 / 20.0)) / peak
    return np.clip(data * gain, -1.0, 1.0)


def generate_audio() -> list[str]:
    import wave

    try:
        import numpy  # noqa: F401
    except ImportError:
        raise SystemExit("audio 生成需要 numpy：pip install numpy")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("audio 生成需要 ffmpeg 在 PATH 中")

    written: list[str] = []
    sr = 44100
    tmp_dir = ROOT / "build" / "_audio_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    for name, spec in BGM_SPEC.items():
        left, right = _synth_bgm(name, spec, sr)
        wav = tmp_dir / f"bgm_{name}.wav"
        with wave.open(str(wav), "wb") as handle:
            handle.setnchannels(2)
            handle.setsampwidth(2)
            handle.setframerate(sr)
            interleaved = bytearray()
            for l_value, r_value in zip(left, right):
                interleaved += int(l_value * 32767).to_bytes(2, "little", signed=True)
                interleaved += int(r_value * 32767).to_bytes(2, "little", signed=True)
            handle.writeframes(bytes(interleaved))
        target = ASSETS / "audio" / "bgm" / f"{name}.ogg"
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(wav),
                        "-c:a", "libvorbis", "-q:a", "4", str(target)], check=True)
        written.append(f"audio/bgm/{name}.ogg")

    for name, spec in SFX_SPEC.items():
        data = _synth_sfx(name, spec, sr)
        wav = tmp_dir / f"sfx_{name}.wav"
        with wave.open(str(wav), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(sr)
            handle.writeframes(b"".join(int(value * 32767).to_bytes(2, "little", signed=True)
                                       for value in data))
        target = ASSETS / "audio" / "sfx" / f"{name}.ogg"
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(wav),
                        "-c:a", "libvorbis", "-q:a", "4", "-ac", "1", str(target)], check=True)
        written.append(f"audio/sfx/{name}.ogg")
    return written


# --------------------------------------------------------------------------- #
# 生成：模型（Panda3D 低模白模）
# --------------------------------------------------------------------------- #
def _box_node(name: str, size_xyz: tuple[float, float, float], offset=(0.0, 0.0, 0.0),
              color=(0.6, 0.6, 0.6, 1.0)):
    """生成一个可见网格 mesh_*：原点在西南角，Z 向上，1 单位 = 1 米。"""
    from panda3d.core import (
        Geom,
        GeomNode,
        GeomTriangles,
        GeomVertexData,
        GeomVertexFormat,
        GeomVertexWriter,
        NodePath,
        Vec4,
    )

    width, depth, height = size_xyz
    ox, oy, oz = offset
    data = GeomVertexData(name, GeomVertexFormat.getV3(), Geom.UHStatic)
    vertex = GeomVertexWriter(data, "vertex")
    corners = [
        (ox, oy, oz), (ox + width, oy, oz), (ox + width, oy + depth, oz), (ox, oy + depth, oz),
        (ox, oy, oz + height), (ox + width, oy, oz + height),
        (ox + width, oy + depth, oz + height), (ox, oy + depth, oz + height),
    ]
    for corner in corners:
        vertex.addData3(*corner)
    triangles = GeomTriangles(Geom.UHStatic)
    faces = [
        (0, 1, 2), (0, 2, 3), (4, 6, 5), (4, 7, 6),
        (0, 4, 5), (0, 5, 1), (1, 5, 6), (1, 6, 2),
        (2, 6, 7), (2, 7, 3), (3, 7, 4), (3, 4, 0),
    ]
    for face in faces:
        triangles.addVertices(*face)
    geom = Geom(data)
    geom.addPrimitive(triangles)
    node = GeomNode(f"mesh_{name}")
    node.addGeom(geom)
    path = NodePath(node)
    path.setColor(Vec4(*color))
    return path


def generate_models() -> list[str]:
    try:
        from panda3d.core import Filename, NodePath
    except ImportError:
        raise SystemExit("模型生成需要 panda3d：pip install panda3d==1.10.16")

    written: list[str] = []

    def save(root: NodePath, relative: str) -> None:
        target = ASSETS / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        # 必须用 Filename.fromOsSpecific：直接传 str 会让 Panda3D 走 model-path 并丢失非 ASCII 字符
        ok = root.writeBamFile(Filename.fromOsSpecific(str(target)))
        if not ok or not target.exists():
            raise SystemExit(f"写入 .bam 失败: {relative}")
        written.append(relative)

    buildings = {
        "dorm": (16, 12, 9, (0.72, 0.66, 0.58, 1)),
        "teaching": (20, 14, 12, (0.62, 0.66, 0.72, 1)),
        "library": (18, 16, 13, (0.70, 0.62, 0.52, 1)),
        "club": (14, 12, 8, (0.58, 0.68, 0.62, 1)),
        "canteen": (16, 12, 7, (0.74, 0.62, 0.50, 1)),
    }
    for name, (w, d, h, color) in buildings.items():
        root = NodePath(f"model_{name}")
        root.attachNewNode(_box_node(f"{name}_body", (w, d, h), color=color).node())
        roof = _box_node(f"{name}_roof", (w + 1.0, d + 1.0, 1.0), offset=(0, 0, h),
                         color=(color[0] * 0.8, color[1] * 0.8, color[2] * 0.8, 1))
        root.attachNewNode(roof.node())
        save(root, f"campus/{name}.bam")

        interior = NodePath(f"model_interior_{name}")
        interior.attachNewNode(_box_node(f"{name}_floor", (16, 10, 0.2), color=(0.55, 0.52, 0.48, 1)).node())
        interior.attachNewNode(_box_node(f"{name}_wall_n", (16, 0.4, 3.2), offset=(0, 9.6, 0),
                                        color=(0.68, 0.68, 0.70, 1)).node())
        interior.attachNewNode(_box_node(f"{name}_desk", (2.4, 1.2, 0.9), offset=(5, 4, 0.2),
                                        color=(0.60, 0.46, 0.34, 1)).node())
        interior.attachNewNode(_box_node(f"{name}_shelf", (0.6, 3.0, 2.0), offset=(0.6, 1.0, 0.2),
                                        color=(0.52, 0.40, 0.30, 1)).node())
        save(interior, f"campus/interior_{name}.bam")

    ground = NodePath("model_ground")
    ground.attachNewNode(_box_node("ground_plane", (80, 45, 0.2), offset=(-20, -15, -0.2),
                                  color=(0.40, 0.45, 0.38, 1)).node())
    save(ground, "campus/ground.bam")

    props = {
        "road": ((6, 6, 0.05), (0.32, 0.32, 0.34, 1)),
        "tree": ((1.0, 1.0, 3.2), (0.34, 0.52, 0.32, 1)),
        "lamp": ((0.3, 0.3, 4.0), (0.52, 0.52, 0.56, 1)),
        "bench": ((2.2, 0.8, 0.9), (0.56, 0.42, 0.30, 1)),
        "fence": ((2.0, 0.2, 1.4), (0.66, 0.62, 0.56, 1)),
        "sign": ((1.2, 0.2, 2.4), (0.42, 0.44, 0.50, 1)),
        "planter": ((1.4, 1.4, 0.8), (0.62, 0.44, 0.34, 1)),
        "bin": ((0.8, 0.8, 1.0), (0.38, 0.42, 0.40, 1)),
        "bike_rack": ((3.0, 0.6, 1.0), (0.46, 0.48, 0.52, 1)),
        "flag_pole": ((0.25, 0.25, 6.0), (0.72, 0.72, 0.74, 1)),
        "rock": ((1.2, 1.0, 0.7), (0.50, 0.50, 0.48, 1)),
        "flower_bed": ((2.4, 1.2, 0.5), (0.66, 0.50, 0.62, 1)),
    }
    for name, (size_xyz, color) in props.items():
        root = NodePath(f"model_prop_{name}")
        root.attachNewNode(_box_node(f"prop_{name}", size_xyz, color=color).node())
        save(root, f"campus/props/{name}.bam")
    return written


# --------------------------------------------------------------------------- #
# manifest / LICENSES
# --------------------------------------------------------------------------- #
def write_manifest() -> str:
    manifest = {"version": 1, "assets": asset_specs()}
    target = ASSETS / "manifest.json"
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return "manifest.json"


def write_licenses() -> str:
    import csv

    target = ASSETS / "LICENSES.csv"
    fieldnames = ["license_id", "asset_ids", "author", "source_url", "license",
                  "commercial_ok", "modified", "date_added", "notes"]
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in LICENSE_ROWS:
            writer.writerow(row)
    return "LICENSES.csv"


def check() -> int:
    """核对 manifest 与磁盘文件、LICENSES.csv 覆盖情况。"""
    manifest_path = ASSETS / "manifest.json"
    if not manifest_path.exists():
        print("manifest.json 缺失，先运行 manifest 子命令")
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    missing = []
    for item in manifest["assets"]:
        path = ASSETS / item["path"]
        if not path.exists() and "pending" not in item.get("tags", []):
            missing.append(item["path"])
    licenses = {}
    import csv as _csv

    with (ASSETS / "LICENSES.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        for row in _csv.DictReader(handle):
            licenses[row["license_id"]] = row
    unlicensed = [item["id"] for item in manifest["assets"]
                  if item.get("license_id") not in licenses]
    print(f"assets={len(manifest['assets'])} missing={len(missing)} unlicensed={len(unlicensed)}")
    for path in missing:
        print("  missing:", path)
    for asset_id in unlicensed:
        print("  unlicensed:", asset_id)
    return 0 if not missing and not unlicensed else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成占位美术/音频/模型并同步 manifest")
    parser.add_argument("target", choices=["art", "audio", "models", "manifest", "all", "check"])
    args = parser.parse_args(argv)

    if args.target == "check":
        return check()
    if args.target in ("art", "all"):
        written = generate_art()
        print(f"art: {len(written)} files")
    if args.target in ("audio", "all"):
        written = generate_audio()
        print(f"audio: {len(written)} files")
    if args.target in ("models", "all"):
        written = generate_models()
        print(f"models: {len(written)} files")
    if args.target in ("manifest", "all"):
        print("wrote", write_manifest(), write_licenses())
    return 0


if __name__ == "__main__":
    sys.exit(main())



