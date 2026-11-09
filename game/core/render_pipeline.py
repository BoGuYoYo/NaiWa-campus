"""A 维护：480×270 低分辨率离屏渲染管线（已验证方案）。

要点：
1. 480×270 离屏缓冲，纹理放大/缩小过滤都是 nearest，清屏色 #1B1F2A；
2. 正交镜头 film size 25 × 14.0625 米（每米 24 像素，视野放大 1.25 倍），near/far = 1/200，主窗口相机停用；
3. render2d 上一张全屏卡片显示缓冲纹理，按整数倍优先 / 比例拉伸兜底居中加黑边；
4. 相机每帧对齐 1/24 米网格，避免像素闪烁；
5. 像素 UI 用同一套 480×270 逻辑坐标（ui_px）；
6. 角色是 2×2 米卡片，P 轴按相机俯角倾斜，透明用 TransparencyAttrib.MBinary。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .. import config

# CardMaker 生成的卡片默认立在 XZ 平面、法线朝 -Y；把 P 轴转到相机俯角 -40°，
# 卡片法线与相机视方向正好反向，像素不会被斜切压缩。
# 实测记录：P=+50 会让卡片与视方向平行（完全看不见），不要改成正角度。
CHARACTER_CARD_PITCH = config.CAMERA_TILT_DEGREES
CHARACTER_CARD_SIZE_METERS = (2.0, 2.0)
GRID = 1.0 / config.PIXELS_PER_METER


@dataclass(frozen=True)
class Viewport:
    """缓冲纹理在窗口中的摆放：scale 为放大倍数，offset 为居中偏移（屏幕像素）。"""

    scale: float
    offset_x: float
    offset_y: float
    integer: bool

    @property
    def width(self) -> float:
        return config.INTERNAL_WIDTH * self.scale

    @property
    def height(self) -> float:
        return config.INTERNAL_HEIGHT * self.scale


def compute_viewport(win_w: int, win_h: int) -> Viewport:
    """缩放规则：整数倍 k = min(w//480, h//270)；若 480k < 0.85w 改为按比例拉伸。"""
    win_w = max(1, int(win_w))
    win_h = max(1, int(win_h))
    k = min(win_w // config.INTERNAL_WIDTH, win_h // config.INTERNAL_HEIGHT)
    if k >= 1 and config.INTERNAL_WIDTH * k >= config.INTEGER_SCALE_MIN_RATIO * win_w:
        scale = float(k)
        integer = True
    else:
        scale = min(win_w / config.INTERNAL_WIDTH, win_h / config.INTERNAL_HEIGHT)
        integer = False
    offset_x = (win_w - config.INTERNAL_WIDTH * scale) / 2.0
    offset_y = (win_h - config.INTERNAL_HEIGHT * scale) / 2.0
    return Viewport(scale=scale, offset_x=offset_x, offset_y=offset_y, integer=integer)


def snap_to_pixel_grid(value: float, grid: float = GRID) -> float:
    return round(value / grid) * grid


class LowResPipeline:
    """持有离屏缓冲、正交相机与显示卡片；所有改动都在 resize()/align() 中收敛。"""

    def __init__(self, app, logger: logging.Logger | None = None) -> None:
        self.app = app
        self.log = logger or logging.getLogger("naiwa.render")
        self.buffer = None
        self.texture = None
        self.camera = None
        self.camera_np = None
        self.card = None
        self.viewport = compute_viewport(*self.window_size())
        self.camera_target = (0.0, 0.0)

    # ------------------------------------------------------------------ #
    def window_size(self) -> tuple[int, int]:
        """离屏模式下 win 是 GraphicsBuffer，没有 getProperties，只能用 getXSize。"""
        win = getattr(self.app, "win", None)
        if win is not None:
            try:
                width, height = int(win.getXSize()), int(win.getYSize())
                if width > 0 and height > 0:
                    return width, height
            except Exception:
                pass
        return config.DEFAULT_WINDOW_SIZE

    def setup(self) -> None:
        from panda3d.core import (
            OrthographicLens,
            SamplerState,
            TransparencyAttrib,
            Vec4,
        )

        app = self.app
        self.buffer = app.win.makeTextureBuffer(
            "lowres", config.INTERNAL_WIDTH, config.INTERNAL_HEIGHT
        )
        self.buffer.setClearColorActive(True)
        self.buffer.setClearColor(Vec4(*config.CLEAR_COLOR_RGBA))

        self.texture = self.buffer.getTexture()
        self.texture.setMagfilter(SamplerState.FT_nearest)
        self.texture.setMinfilter(SamplerState.FT_nearest)
        self.texture.setWrapU(SamplerState.WM_clamp)
        self.texture.setWrapV(SamplerState.WM_clamp)

        self.camera_np = app.makeCamera(self.buffer, sort=-10)
        self.camera_np.setName("lowres_cam")
        self.camera = self.camera_np.node()
        self.camera.setScene(app.render)
        lens = OrthographicLens()
        lens.setFilmSize(config.FILM_WIDTH_METERS, config.FILM_HEIGHT_METERS)
        lens.setNearFar(1.0, 200.0)
        self.camera.setLens(lens)
        self.camera_np.setPos(0, -30, 20)
        self.camera_np.setHpr(0, config.CAMERA_TILT_DEGREES, 0)

        # 主窗口默认相机停用，画面只来自离屏缓冲。
        try:
            app.camNode.setActive(False)
        except AttributeError:
            self.log.warning("[RENDER] main camera node unavailable")

        self._build_card()
        self.resize()

    def _build_card(self) -> None:
        from panda3d.core import CardMaker, TransparencyAttrib

        maker = CardMaker("lowres_display")
        maker.setFrame(-1.0, 1.0, -1.0, 1.0)
        self.card = self.app.render2d.attachNewNode(maker.generate())
        self.card.setTexture(self.texture, 1)
        self.card.setTransparency(TransparencyAttrib.MNone)
        self.card.setLightOff()
        self.card.setDepthTest(False)
        self.card.setDepthWrite(False)
        self.card.setBin("fixed", 0)

    def resize(self, win_w: int | None = None, win_h: int | None = None) -> Viewport:
        if win_w is None or win_h is None:
            win_w, win_h = self.window_size()
        viewport = compute_viewport(win_w, win_h)
        self.viewport = viewport
        if self.card is not None:
            # aspect2d 与窗口同比例，坐标范围 -1..1。
            sx = (config.INTERNAL_WIDTH * viewport.scale) / float(win_w)
            sy = (config.INTERNAL_HEIGHT * viewport.scale) / float(win_h)
            self.card.setScale(sx, 1.0, sy)
            self.card.setPos(
                (viewport.offset_x / win_w) * 2.0,
                0.0,
                (viewport.offset_y / win_h) * 2.0,
            )
        self.log.info(
            "[RENDER] window=%dx%d scale=%.4f integer=%s offset=(%.1f, %.1f)",
            win_w, win_h, viewport.scale, viewport.integer, viewport.offset_x, viewport.offset_y,
        )
        return viewport

    # ------------------------------------------------------------------ #
    def align_camera(self, x: float, y: float) -> tuple[float, float]:
        """相机目标对齐 1/24 米网格，避免像素抖动。"""
        sx = snap_to_pixel_grid(x)
        sy = snap_to_pixel_grid(y)
        self.camera_target = (sx, sy)
        if self.camera_np is None:
            return (sx, sy)
        # 视方向 forward = (0, cos p, sin p)；相机沿 -forward 后退。
        # 正交镜头的可视范围由 film size 控制，距离仍保持更远以留出深度余量。
        distance = config.CAMERA_DISTANCE
        pitch = config.CAMERA_TILT_DEGREES
        self.camera_np.setPos(
            sx - 0.0 * distance,
            sy - _cos(pitch) * distance,
            0.0 - _sin(pitch) * distance,
        )
        self.camera_np.setHpr(0, pitch, 0)
        return (sx, sy)

    # ------------------------------------------------------------------ #
    def ui_px(self, value: float) -> float:
        """把 480×270 逻辑像素换算为 aspect2d 坐标（-1..1，纵向按 270 归一）。"""
        return value / (config.INTERNAL_HEIGHT / 2.0)

    def ui_rect(self, x: float, y: float) -> tuple[float, float]:
        """逻辑像素左上角坐标 -> aspect2d 坐标（原点在屏幕中心，y 向上）。"""
        return (
            x / (config.INTERNAL_WIDTH / 2.0) - 1.0,
            1.0 - y / (config.INTERNAL_HEIGHT / 2.0),
        )

    # ------------------------------------------------------------------ #
    def make_character_card(self, parent, name: str = "char_card"):
        """2×2 米角色卡片：脚点位于卡片原点的底部中心。"""
        from panda3d.core import CardMaker, TransparencyAttrib

        maker = CardMaker(name)
        maker.setFrame(
            -CHARACTER_CARD_SIZE_METERS[0] / 2.0,
            CHARACTER_CARD_SIZE_METERS[0] / 2.0,
            0.0,
            CHARACTER_CARD_SIZE_METERS[1],
        )
        card = parent.attachNewNode(maker.generate())
        card.setTransparency(TransparencyAttrib.MBinary)
        card.setP(CHARACTER_CARD_PITCH)
        card.setLightOff()
        return card

    def save_buffer_screenshot(self, path: str) -> bool:
        """离屏截图：优先取缓冲纹理本身（480×270），失败再退到窗口。

        Panda3D 1.10.16 的 GraphicsOutput.getScreenshot() 返回 Texture（1.11 才返回 PNMImage），
        两种都兼容。
        """
        from pathlib import Path

        from panda3d.core import PNMImage, Texture

        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        for source in (self.buffer, self.app.win):
            if source is None:
                continue
            try:
                shot = source.getScreenshot()
            except Exception as exc:
                self.log.warning("[RENDER] getScreenshot failed: %s", exc)
                continue
            if shot is None:
                continue
            try:
                if isinstance(shot, Texture):
                    if shot.getXSize() == 0:
                        continue
                    image = PNMImage()
                    if not shot.store(image):
                        self.log.warning("[RENDER] texture.store failed")
                        continue
                    image.write(_os_filename(target))
                    width, height = image.getXSize(), image.getYSize()
                else:
                    if getattr(shot, "isEmpty", lambda: True)():
                        continue
                    shot.write(_os_filename(target))
                    width, height = shot.getXSize(), shot.getYSize()
            except Exception as exc:
                self.log.warning("[RENDER] screenshot write failed: %s", exc)
                continue
            self.log.info("[RENDER] screenshot %s (%dx%d)", target, width, height)
            return True
        self.log.error("[RENDER] screenshot failed for %s", target)
        return False


def _cos(degrees: float) -> float:
    import math

    return math.cos(math.radians(degrees))


def _sin(degrees: float) -> float:
    import math

    return math.sin(math.radians(degrees))

def _os_filename(path) -> object:
    """Panda3D 只有 Filename.fromOsSpecific 能正确处理绝对路径与非 ASCII 字符。"""
    from panda3d.core import Filename

    return Filename.fromOsSpecific(str(path))

