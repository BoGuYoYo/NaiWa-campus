"""A 维护：全局常量、资源路径、命令行参数、settings.json、日志。

本模块不导入 panda3d，保证 core 层与独立测试在无图形环境、甚至无引擎安装时也能导入。
"""

from __future__ import annotations

import argparse
import json
import logging
import logging.handlers
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

APP_NAME = "NaiwaCampus"
GAME_VERSION = "0.1.0"
SAVE_VERSION = 1

# 内部画布与像素密度：全项目唯一来源，任何模块都必须从这里取。
INTERNAL_WIDTH = 480
INTERNAL_HEIGHT = 270
PIXELS_PER_METER = 24
# Keep the campus framing a little wider so adjacent buildings do not crowd the
# screen when the player is standing on the central plaza.
CAMERA_VIEW_SCALE = 1.25
FILM_WIDTH_METERS = INTERNAL_WIDTH / PIXELS_PER_METER * CAMERA_VIEW_SCALE  # 25.0
FILM_HEIGHT_METERS = INTERNAL_HEIGHT / PIXELS_PER_METER * CAMERA_VIEW_SCALE  # 14.0625
CAMERA_DISTANCE = 38.0
CLEAR_COLOR_HEX = "#1B1F2A"
CLEAR_COLOR_RGBA = (0.106, 0.122, 0.165, 1.0)  # #1B1F2A
CAMERA_TILT_DEGREES = -40.0

# 存档槽位：3 个手动 + 1 个自动。
SLOT_IDS = ("slot_1", "slot_2", "slot_3", "autosave")
MANUAL_SLOT_IDS = ("slot_1", "slot_2", "slot_3")
AUTOSAVE_SLOT = "autosave"

# 默认窗口与缩放规则参数。
DEFAULT_WINDOW_SIZE = (1280, 720)
ALLOWED_WINDOW_SIZES = ((1280, 720), (1920, 1080))
INTEGER_SCALE_MIN_RATIO = 0.85  # 480k 不足窗口宽 85% 时改为按比例拉伸

# 每学期 2 天、每学年 2 学期、共 4 学年 -> 16 天、8 个学期事件。
DAYS_PER_SEMESTER = 2
SEMESTERS_PER_YEAR = 2
TOTAL_YEARS = 4
TOTAL_DAYS = TOTAL_YEARS * SEMESTERS_PER_YEAR * DAYS_PER_SEMESTER  # 16
ACTIONS_PER_DAY = 3

TEXT_SPEED_TABLE = {"slow": 20, "normal": 40, "fast": 80, "instant": 0}
WINDOW_MODES = ("windowed", "borderless")

_LOGGER_NAME = "naiwa"

_resource_root_override: Path | None = None
_user_dir_override: Path | None = None


def resource_root() -> Path:
    """资源根目录：源码运行为仓库根，PyInstaller 运行为 sys._MEIPASS。"""
    if _resource_root_override is not None:
        return _resource_root_override
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def user_dir() -> Path:
    """用户目录：%APPDATA%\\NaiwaCampus，存档与配置只写这里，绝不写安装目录。"""
    if _user_dir_override is not None:
        base = _user_dir_override
    else:
        base = Path(os.environ.get("APPDATA") or Path.home()) / APP_NAME
    (base / "saves").mkdir(parents=True, exist_ok=True)
    (base / "logs").mkdir(parents=True, exist_ok=True)
    return base


def saves_dir() -> Path:
    path = user_dir() / "saves"
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_path() -> Path:
    return user_dir() / "settings.json"


def set_resource_root(path: str | os.PathLike[str] | None) -> None:
    """测试用：覆写资源根目录；传 None 恢复默认。"""
    global _resource_root_override
    _resource_root_override = Path(path) if path is not None else None


def set_user_dir(path: str | os.PathLike[str] | None) -> None:
    """测试用：覆写用户目录；传 None 恢复默认。"""
    global _user_dir_override
    _user_dir_override = Path(path) if path is not None else None


def content_path(*parts: str) -> Path:
    return resource_root().joinpath("content", *parts)


def assets_path(*parts: str) -> Path:
    return resource_root().joinpath("assets", *parts)


# --------------------------------------------------------------------------- #
# settings.json
# --------------------------------------------------------------------------- #
@dataclass
class Settings:
    master_volume: int = 80
    bgm_volume: int = 70
    sfx_volume: int = 80
    window_mode: str = "windowed"
    window_size: list[int] = field(default_factory=lambda: [1280, 720])
    text_speed: str = "normal"

    # 派生值
    def chars_per_second(self) -> int:
        return TEXT_SPEED_TABLE.get(self.text_speed, TEXT_SPEED_TABLE["normal"])

    def effective_bgm_volume(self) -> float:
        return (self.master_volume / 100.0) * (self.bgm_volume / 100.0)

    def effective_sfx_volume(self) -> float:
        return (self.master_volume / 100.0) * (self.sfx_volume / 100.0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "master_volume": self.master_volume,
            "bgm_volume": self.bgm_volume,
            "sfx_volume": self.sfx_volume,
            "window_mode": self.window_mode,
            "window_size": list(self.window_size),
            "text_speed": self.text_speed,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any], logger: logging.Logger | None = None) -> "Settings":
        log = logger or logging.getLogger(_LOGGER_NAME)
        defaults = cls()
        out = cls()
        for name in ("master_volume", "bgm_volume", "sfx_volume"):
            value = raw.get(name, getattr(defaults, name))
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
                log.warning("[SETTINGS] invalid %s=%r, fallback %d", name, value, getattr(defaults, name))
                value = getattr(defaults, name)
            setattr(out, name, value)

        mode = raw.get("window_mode", defaults.window_mode)
        if mode not in WINDOW_MODES:
            log.warning("[SETTINGS] invalid window_mode=%r, fallback %s", mode, defaults.window_mode)
            mode = defaults.window_mode
        out.window_mode = mode

        size = raw.get("window_size", defaults.window_size)
        ok_size = (
            isinstance(size, (list, tuple))
            and len(size) == 2
            and all(isinstance(v, int) and not isinstance(v, bool) for v in size)
            and tuple(size) in ALLOWED_WINDOW_SIZES
        )
        if not ok_size:
            log.warning("[SETTINGS] invalid window_size=%r, fallback %s", size, list(defaults.window_size))
            size = list(defaults.window_size)
        out.window_size = [int(size[0]), int(size[1])]

        speed = raw.get("text_speed", defaults.text_speed)
        if speed not in TEXT_SPEED_TABLE:
            log.warning("[SETTINGS] invalid text_speed=%r, fallback %s", speed, defaults.text_speed)
            speed = defaults.text_speed
        out.text_speed = speed
        return out

    @classmethod
    def load(cls, path: Path | None = None, logger: logging.Logger | None = None) -> "Settings":
        log = logger or logging.getLogger(_LOGGER_NAME)
        target = path or settings_path()
        if not target.exists():
            settings = cls()
            settings.save(target)
            return settings
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("settings root is not an object")
        except (OSError, ValueError) as exc:
            log.warning("[SETTINGS] cannot read %s (%s), using defaults", target, exc)
            return cls()
        return cls.from_dict(raw, log)

    def save(self, path: Path | None = None) -> None:
        target = path or settings_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, target)


# --------------------------------------------------------------------------- #
# 命令行参数
# --------------------------------------------------------------------------- #
@dataclass
class Options:
    dev: bool = False
    seed: int | None = None
    scene: str = "MainMenu"
    spawn: str = "loc_gate"
    day: int | None = None
    load: str | None = None
    skip_intro: bool = False
    windowed: tuple[int, int] = DEFAULT_WINDOW_SIZE
    offscreen: bool = False
    autoplay: bool = False
    frames: int = 6
    screenshot: str | None = None
    inspect: bool = False
    echo: bool = False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m game", description="奶娃：大学四年")
    parser.add_argument("--dev", action="store_true", help="开启调试键 F1～F4、FPS 显示，并允许下列参数")
    parser.add_argument("--seed", type=int, default=None, help="新游戏随机种子，写入 GameState.seed")
    parser.add_argument("--scene", default="MainMenu", help="直接进入 CampusScene / EventScene / GraduationScene")
    parser.add_argument("--spawn", default="loc_gate", help="CampusScene 出生地点 ID")
    parser.add_argument("--day", type=int, default=None, help="直接设定 day_index（调试用）")
    parser.add_argument("--load", default=None, help="启动后直接读取 slot_1～slot_3 或 autosave")
    parser.add_argument("--skip-intro", dest="skip_intro", action="store_true", help="跳过 story_opening")
    parser.add_argument("--windowed", nargs=2, type=int, metavar=("W", "H"), default=None, help="窗口尺寸")
    parser.add_argument("--offscreen", action="store_true", help="离屏渲染（无窗口），用于独立测试与截图")
    parser.add_argument("--autoplay", action="store_true", help="自动推进演示（冒烟测试）")
    parser.add_argument("--frames", type=int, default=6, help="--offscreen 时渲染并截图的帧数")
    parser.add_argument("--screenshot", default=None, help="离屏截图输出路径")
    parser.add_argument("--inspect", action="store_true", help="--dev 下直接打开 8 方向角色检视网格")
    parser.add_argument("--echo", action="store_true", help="日志同时输出到控制台")
    return parser


def parse_args(argv: list[str] | None = None) -> Options:
    namespace = build_parser().parse_args(argv)
    window = tuple(namespace.windowed) if namespace.windowed else DEFAULT_WINDOW_SIZE
    if window not in ALLOWED_WINDOW_SIZES:
        window = DEFAULT_WINDOW_SIZE
    return Options(
        dev=namespace.dev,
        seed=namespace.seed,
        scene=namespace.scene,
        spawn=namespace.spawn,
        day=namespace.day,
        load=namespace.load,
        skip_intro=namespace.skip_intro,
        windowed=window,
        offscreen=namespace.offscreen,
        autoplay=namespace.autoplay,
        frames=max(1, namespace.frames),
        screenshot=namespace.screenshot,
        inspect=namespace.inspect,
        echo=namespace.echo,
    )


# --------------------------------------------------------------------------- #
# 日志
# --------------------------------------------------------------------------- #
_configured = False


def setup_logging(options: Options | None = None, log_path: Path | None = None) -> logging.Logger:
    """日志写 user_dir/logs/game.log，滚动保留 5 份。"""
    global _configured
    log = logging.getLogger(_LOGGER_NAME)
    if _configured:
        return log
    log.setLevel(logging.DEBUG if (options and options.dev) else logging.INFO)
    log.propagate = False
    target = log_path or (user_dir() / "logs" / "game.log")
    target.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        target, maxBytes=1_048_576, backupCount=5, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    log.addHandler(handler)
    if options is not None and options.echo:
        stream = logging.StreamHandler(sys.stderr)
        stream.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        log.addHandler(stream)
    _configured = True
    # 只记录资源根的类别，不写本机绝对路径（A-01 验收要求日志里不出现绝对路径）
    log.info("[BOOT] %s %s python=%s root=%s",
             APP_NAME, GAME_VERSION, sys.version.split()[0],
             "meipass" if getattr(sys, "frozen", False) else "source")
    return log


def get_logger(suffix: str = "") -> logging.Logger:
    return logging.getLogger(f"{_LOGGER_NAME}.{suffix}" if suffix else _LOGGER_NAME)

