"""A 维护：ShowBase 子类、任务调度与场景装配（组合根）。

任务 sort 顺序固定：input_poll 10(C)、world_update 20(C)、interaction_scan 30(C)、
ui_update 40(D)、flow_tick 45(A)、其他 >= 50。本文件只注册 flow_tick(45) 与调试任务(>=50)。
"""

from __future__ import annotations

import importlib
import json
import logging
from pathlib import Path
from typing import Any

from direct.showbase.ShowBase import ShowBase  # type: ignore

from . import config
from .core.asset_registry import AssetRegistry
from .core.audio import AudioManager
from .core.event_bus import (
    TOPIC_DAY_ENDED,
    TOPIC_GAME_GRADUATED,
    TOPIC_SCENE_CHANGED,
    EventBus,
)
from .core.flow import GameFlow, resolve_services
from .core.input_router import InputRouter
from .core.render_pipeline import LowResPipeline
from .core.results import ActivityResult, DayEndResult, EndingResult, EventResult
from .core.save_manager import SaveLoadError, SaveManager
from .core.scene_manager import SceneManager
from .core.state import WorldPos

# 任务 sort 常量（其他人只读）
SORT_INPUT_POLL = 10
SORT_WORLD_UPDATE = 20
SORT_INTERACTION_SCAN = 30
SORT_UI_UPDATE = 40
SORT_FLOW_TICK = 45
SORT_MIN_OTHER = 50

LOG = logging.getLogger("naiwa.app")

# 场景 ID -> (模块, 类名)。C/D 的正式实现由 game/core/world_scene.py 的适配层装配；
# 适配层本身导入失败时退回 A 的替身场景。
SCENE_MODULES: dict[str, tuple[str, str]] = {
    "MainMenu": ("game.core.world_scene", "MainMenuSceneAdapter"),
    "CampusScene": ("game.core.world_scene", "CampusSceneAdapter"),
    "InteriorScene": ("game.core.world_scene", "InteriorSceneAdapter"),
    "EventScene": ("game.core.world_scene", "EventSceneAdapter"),
    "ResultPanel": ("game.core.world_scene", "ResultPanelSceneAdapter"),
    "DaySummary": ("game.core.world_scene", "DaySummarySceneAdapter"),
    "TabPanel": ("game.core.world_scene", "TabPanelSceneAdapter"),
    "PauseMenu": ("game.core.world_scene", "PauseMenuSceneAdapter"),
    "SettingsMenu": ("game.core.world_scene", "SettingsMenuSceneAdapter"),
    "SaveMenu": ("game.core.world_scene", "SaveMenuSceneAdapter"),
    "GraduationScene": ("game.core.world_scene", "GraduationSceneAdapter"),
}


def apply_prc(options: config.Options, settings: config.Settings) -> None:
    """ShowBase 实例化前写入 PRC，窗口尺寸与离屏模式都在这里决定。"""
    from panda3d.core import loadPrcFileData

    width, height = options.windowed
    loadPrcFileData("", f"win-size {width} {height}")
    loadPrcFileData("", "window-title 奶娃：大学四年")
    loadPrcFileData("", "sync-video false")
    loadPrcFileData("", "framebuffer-srgb false")
    loadPrcFileData("", "notify-level-display error")
    loadPrcFileData("", "textures-power-2 none")
    loadPrcFileData("", "default-fov 40")
    if options.offscreen:
        loadPrcFileData("", "window-type offscreen")
        loadPrcFileData("", "audio-library-name null")
    if settings.window_mode == "borderless" and not options.offscreen:
        loadPrcFileData("", "undecorated true")


class NaiwaApp(ShowBase):
    """程序骨架：资源、渲染、场景、存档、音频、流程的唯一装配点。"""

    def __init__(self, options: config.Options) -> None:
        self.options = options
        self.log = LOG
        self.settings = config.Settings.load()
        super().__init__()

        # 按键绑定统一走路由：ignore() 是全局接口，场景退场时不能把别人的绑定一起拆掉
        self.input = InputRouter(self.accept, self.ignore)
        self.bus = EventBus(logger=logging.getLogger("naiwa.bus"), strict_topics=options.dev)
        self.registry = AssetRegistry(loader=self, bus=self.bus)
        self.pipeline = LowResPipeline(self)
        self.pipeline.setup()
        self.audio = AudioManager(self.registry, self.settings, enabled=not options.offscreen)
        self.saves = SaveManager()
        self.scenes = SceneManager(self, factory=self.make_scene, bus=self.bus)
        self.services = resolve_services()

        # D 的文本库与 UI 坐标系：界面全部画在 aspect2d 之上，与 480×270 同比例
        from .ui.text_db import TextDB
        from .ui.widgets import UITransform, set_default_font

        self.text = TextDB.load(str(config.resource_root() / "content"))
        set_default_font(self.registry.load_ui_font())
        self.ui_root = self.aspect2d.attach_new_node("ui_root")
        self.ui_transform = UITransform.from_base(self)

        # C 的地图数据：缺失时 C 的适配层装配失败，自动退回 A 的替身场景
        from .world.map_data import MapData

        try:
            self.map_data = MapData.from_content_root(config.resource_root() / "content")
        except Exception as exc:
            self.map_data = None
            self.log.warning("[APP] content/world 加载失败（%s），校园退到替身场景", exc)

        self.flow = GameFlow(self, self.scenes, self.saves, self.bus,
                             services=self.services, registry=self.registry)
        self._fade_card = self._build_fade_overlay()
        self._frame_count = 0
        self._shutdown_done = False
        self.exit_code = 0

        self._wire_events()
        self._register_tasks()
        self._apply_settings_to_window()
        self.accept("window-event", self._on_window_event)

        if options.dev:
            # F1~F6 归 C 的 DebugDraw（碰撞线框 / 交互点 / 状态 / 传送 / 时段），
            # A 自己的 FPS 开关让到 F7，避免 f1 被两边同时 accept。
            self.accept("f7", self._debug_toggle_fps)
            self.accept("f4", self._debug_inspect_character)

        self.log.info("[APP] ready offscreen=%s scene=%s", options.offscreen, options.scene)
        self._start_initial_scene()

    # ------------------------------------------------------------------ #
    # 装配
    # ------------------------------------------------------------------ #
    def _wire_events(self) -> None:
        self.bus.subscribe(TOPIC_SCENE_CHANGED, self.audio.on_scene_changed)
        self.bus.subscribe(TOPIC_DAY_ENDED, self.audio.on_day_ended)
        self.bus.subscribe(TOPIC_GAME_GRADUATED, self.audio.on_graduated)

    def _register_tasks(self) -> None:
        self.taskMgr.add(self._flow_tick, "flow_tick", sort=SORT_FLOW_TICK)
        if self.options.offscreen:
            self.taskMgr.add(self._offscreen_capture, "offscreen_capture", sort=SORT_MIN_OTHER + 10)
        if self.options.autoplay:
            self.taskMgr.add(self._autoplay_step, "autoplay", sort=SORT_MIN_OTHER + 20)

    def add_owned_task(self, func, name: str, sort: int):
        """其他人注册任务必须走这里；禁止新增 sort < 50 的任务。"""
        if sort < SORT_MIN_OTHER:
            raise ValueError(f"task {name} uses sort={sort}: sort<50 只能由 A/C/D 的约定任务占用")
        return self.taskMgr.add(func, name, sort=sort)

    def _apply_settings_to_window(self) -> None:
        if self.options.offscreen or not hasattr(self, "win") or self.win is None:
            return
        if not hasattr(self.win, "getProperties"):
            return
        props = self.win.getProperties()
        width, height = self.settings.window_size
        if (props.getXSize(), props.getYSize()) == (width, height):
            return
        from panda3d.core import WindowProperties

        new_props = WindowProperties()
        new_props.setSize(int(width), int(height))
        if self.settings.window_mode == "borderless":
            new_props.setUndecorated(True)
        self.win.requestProperties(new_props)

    # ------------------------------------------------------------------ #
    # 主循环
    # ------------------------------------------------------------------ #
    def _flow_tick(self, task):
        dt = min(globalClock.getDt(), 1.0 / 30.0)  # type: ignore[name-defined]
        self.scenes.update(dt)
        self.scenes.update_scenes(dt)
        self.flow.tick(dt)
        self._update_fade()
        self._frame_count += 1
        return task.cont

    def _update_fade(self) -> None:
        if self._fade_card is None:
            return
        alpha = self.scenes.fade_alpha
        self._fade_card.setColorScale(0, 0, 0, alpha)
        if alpha <= 0.001:
            self._fade_card.hide()
        else:
            self._fade_card.show()

    def _build_fade_overlay(self):
        from panda3d.core import CardMaker, TransparencyAttrib

        maker = CardMaker("fade_overlay")
        maker.setFrame(-1.2, 1.2, -1.2, 1.2)
        card = self.aspect2d.attachNewNode(maker.generate())
        card.setTransparency(TransparencyAttrib.MAlpha)
        card.setColorScale(0, 0, 0, 0)
        card.setBin("fixed", 100)
        card.setDepthTest(False)
        card.setDepthWrite(False)
        card.hide()
        return card

    def _on_window_event(self, window) -> None:
        """窗口事件：自己处理关闭请求，不依赖 ShowBase 的默认分支。

    两个关键点（都在 1.10.16 上实测过）：
    1. 判断关闭用的是 ``WindowProperties.getOpen()`` 变 False；
       ``getCloseRequested()`` 在这个版本的 WindowProperties 上根本不存在，
       直接在 handler 里调用会抛异常，把 ShowBase 自己的 windowEvent 也一起带崩，
       表现就是“点了 X 窗口关不掉、BGM 还在响”。
    2. 退出前必须显式停音频：否则窗口先销毁、OpenAL 的循环 BGM 会继续播到进程结束。
    """
        try:
            props = window.getProperties()
            if not props.getOpen():
                self.log.info("[APP] window closed by user")
                self.quit_game(exit_code=0)
                return
        except Exception as exc:
            self.log.debug("[APP] window-event props unavailable: %s", exc)
        try:
            width, height = int(window.getXSize()), int(window.getYSize())
            self.pipeline.resize(width, height)
            from .ui.widgets import UITransform

            self.ui_transform = UITransform.from_base(self)
            self.log.debug("[APP] resize %dx%d ui_scale=%.3f", width, height, self.ui_transform.scale)
        except Exception as exc:
            self.log.warning("[APP] resize failed: %s", exc)

    # ------------------------------------------------------------------ #
    # 场景装配
    # ------------------------------------------------------------------ #
    def make_scene(self, scene_id: str, kwargs: dict[str, Any]):
        spec = SCENE_MODULES.get(scene_id)
        if spec is not None:
            module_name, class_name = spec
            try:
                module = importlib.import_module(module_name)
                cls = getattr(module, class_name)
                return cls(self, **kwargs)
            except Exception as exc:  # 装配失败绝不能让主循环崩
                self.log.warning("[SCENE] %s 装配失败（%s: %s），退到替身场景",
                                 scene_id, type(exc).__name__, exc)
                self.log.debug("[SCENE] traceback", exc_info=True)
        stub = STUB_SCENES.get(scene_id)
        if stub is None:
            raise KeyError(f"unknown scene id: {scene_id}")
        return stub(self, **kwargs)

    def _start_initial_scene(self) -> None:
        options = self.options
        if options.load:
            try:
                self.flow.load_game(options.load)
            except SaveLoadError as exc:
                self.log.error("[APP] load %s failed: %s", options.load, exc)
                self.scenes.start("MainMenu")
            return
        if options.scene in ("CampusScene", "InteriorScene"):
            self.flow.new_game(seed=options.seed, skip_intro=True)
            if options.day is not None:
                state = self.flow.require_state()
                state.day_index = max(0, min(config.TOTAL_DAYS - 1, int(options.day)))
            if options.inspect:
                self._debug_inspect_character()
            return
        if options.scene == "EventScene":
            self.scenes.start("CampusScene")
            return
        self.scenes.start(options.scene)

    # ------------------------------------------------------------------ #
    # 离屏截图与冒烟
    # ------------------------------------------------------------------ #
    def _offscreen_capture(self, task):
        if self._frame_count < self.options.frames:
            return task.cont
        target = self.options.screenshot or "reports/standalone/A/offscreen.png"
        path = Path(config.resource_root()) / target
        ok = self.pipeline.save_buffer_screenshot(str(path))
        self.log.info("[APP] offscreen capture frames=%d ok=%s path=%s",
                      self._frame_count, ok, path)
        self.quit_game(exit_code=0 if ok else 2)
        return task.done

    def _autoplay_step(self, task):
        driver = getattr(self, "_driver", None)
        if driver is None:
            driver = self._driver = AutoplayDriver(self)
        done = driver.step()
        if done:
            self.quit_game(exit_code=0 if driver.ok else 3)
            return task.done
        return task.cont

    # ------------------------------------------------------------------ #
    def stop_audio(self) -> None:
        """关掉所有声音（音乐 + 音效 + 引擎侧 sfx manager），退出前必须调用。"""
        try:
            self.audio.stop_all()
        except Exception as exc:
            self.log.warning("[APP] audio stop failed: %s", exc)
        for manager in getattr(self, "sfxManagerList", []) or []:
            try:
                manager.disableAllSounds()
            except Exception:
                pass

    def quit_game(self, exit_code: int = 0) -> None:
        """请求退出：ShowBase.shutdown() 是引擎生命周期方法，不能覆盖，故另起名字。"""
        if self._shutdown_done:
            return
        self._shutdown_done = True
        self.exit_code = int(exit_code)
        # 先停声音再拆场景：否则窗口先没了、OpenAL 的循环 BGM 还会继续播到进程结束
        self.stop_audio()
        self.flow.back_to_main_menu()
        self.log.info("[APP] quit exit_code=%d frames=%d", exit_code, self._frame_count)
        self.userExit()

    # ------------------------------------------------------------------ #
    # --dev 调试
    # ------------------------------------------------------------------ #
    def _debug_toggle_fps(self) -> None:
        current = self.render.analyze()
        self.log.info("[DEBUG] render analyze: %s", current)

    def _debug_inspect_character(self) -> None:
        scene = self.scenes.base_scene
        hook = getattr(scene, "inspect_character", None)
        if callable(hook):
            hook()


# --------------------------------------------------------------------------- #
# A 的替身场景：C/D 的正式实现合入后自动被替换。只用于独立验收与骨架演示。
# --------------------------------------------------------------------------- #
class StubScene:
    is_overlay = False

    def __init__(self, app: NaiwaApp, **kwargs: Any) -> None:
        self.app = app
        self.kwargs = kwargs
        self.log = LOG
        self.root = None

    def on_enter(self, **kwargs: Any) -> None:
        pass

    def on_exit(self) -> None:
        # 只收回自己绑的键：直接 ignore 会把上层场景/覆盖层的绑定一起拆掉
        self.app.input.unbind(self)
        if self.root is not None and not self.root.isEmpty():
            self.root.removeNode()
        self.root = None

    def bind(self, event: str, handler) -> None:
        self.app.input.bind(self, event, handler)

    def on_update(self, dt: float) -> None:
        pass

    def _panel(self, text: str, pos: tuple[float, float] = (0.0, 0.0)):
        from direct.gui.OnscreenText import OnscreenText

        # mayChange=False 会建 StaticTextNode，之后不能再 setPos，所以位置必须在这里给
        return OnscreenText(
            text=text,
            parent=self.app.aspect2d,
            pos=pos,
            scale=0.06,
            fg=(0.95, 0.95, 0.95, 1),
            bg=(0.05, 0.06, 0.09, 0.75),
            align=0,
            mayChange=False,
        )


class StubMainMenu(StubScene):
    def on_enter(self, **kwargs: Any) -> None:
        self.root = self.app.render2d.attachNewNode("stub_main_menu")
        self.label = self._panel("NAIWA CAMPUS  |  Enter: New Game   Esc: Quit")
        self.bind("enter", self._start)
        self.bind("escape", self.app.quit_game)

    def _start(self) -> None:
        self.app.flow.new_game(seed=self.app.options.seed, skip_intro=self.app.options.skip_intro)


class StubCampus(StubScene):
    """校园：正面建筑贴图、立体地面和道具、角色卡片与跟随相机。"""

    SPEED = 4.0  # 米/秒

    def on_enter(self, **kwargs: Any) -> None:
        from panda3d.core import KeyboardButton, LineSegs

        self.root = self.app.render.attachNewNode("stub_campus")
        self._build_ground()
        self._build_buildings()
        state = self.app.flow.state
        world = state.world if state is not None else WorldPos()
        self.pos = [world.x, world.y]
        self.facing = world.facing
        self.anim_time = 0.0
        self.sprite = self.app.registry.load_sprite("char_naiwan_walk")
        self.idle_sprite = self.app.registry.load_sprite("char_naiwan_idle")
        self.card = self.app.pipeline.make_character_card(self.root, "naiwan_card")
        self.card.setTexture(self.sprite.texture, 1)
        self.card.setPos(self.pos[0], self.pos[1], 0)
        self.app.pipeline.align_camera(self.pos[0], self.pos[1])
        self._apply_frame()
        self.keys = {
            "w": KeyboardButton.asciiKey("w"),
            "s": KeyboardButton.asciiKey("s"),
            "a": KeyboardButton.asciiKey("a"),
            "d": KeyboardButton.asciiKey("d"),
        }
        self.bind("e", self._interact)
        self.bind("escape", self._pause)
        self.bind("tab", self._tab)

    # ------------------------------------------------------------------ #
    # 校园布景：建筑优先用透明正面图，缺失时回退 BAM；道具仍使用模型。
    # ------------------------------------------------------------------ #
    BUILDINGS = (
        # (asset 名, 中心 x, 中心 y, 占地宽, 占地深)
        # 地面模型的路：南北向 x 38~44、东西向 y 6~11，出生点 (40,5) 在路口南侧广场
        ("teaching", 23.0, 23.0, 20.0, 14.0),
        ("dorm", 56.0, 23.0, 16.0, 12.0),
        ("library", 21.0, -8.0, 18.0, 16.0),
        ("club", 56.0, -5.0, 14.0, 12.0),
        ("canteen", 54.0, -25.0, 16.0, 12.0),
    )
    BUILDING_TEXTURES = {
        "teaching": "campus_texture_teaching",
        "dorm": "campus_texture_dorm",
        "library": "campus_texture_library",
        "club": "campus_texture_club",
        "canteen": "campus_texture_canteen",
    }
    PROPS = (
        # (asset 名, x, y, 朝向 z 旋转) —— 都摆在广场四周，避开路面（x 38~44 / y 6~11）与建筑占地
        ("tree", 33.0, 4.0, 0), ("tree", 48.0, 4.0, 0),
        ("tree", 33.0, 12.5, 0), ("tree", 48.0, 12.5, 0), ("tree", 16.0, 4.0, 0),
        ("lamp", 36.5, 4.5, 0), ("lamp", 45.5, 4.5, 180),
        ("lamp", 36.5, 12.5, 180), ("lamp", 45.5, 12.5, 0),
        ("bench", 35.5, 3.2, 90), ("bench", 46.5, 2.0, 90),
        ("bin", 34.0, 2.4, 0), ("planter", 36.2, 2.4, 0),
        ("flag_pole", 47.0, 13.4, 0), ("sign", 44.9, 12.2, 0),
        ("flower_bed", 48.6, 2.0, 0), ("bike_rack", 46.2, 4.4, 0),
        ("fence", 20.0, 12.0, 0), ("fence", 22.0, 12.0, 0),
    )

    def _build_ground(self) -> None:
        from panda3d.core import CardMaker

        # Keep grass under the wider campus layout. The original ground BAM
        # covers x=-20..60, y=-15..30; the southern/eastern facades extend past it.
        x0 = min(-20.0, min(cx - width / 2 for _, cx, _, width, _ in self.BUILDINGS)) - 16.0
        x1 = max(60.0, max(cx + width / 2 for _, cx, _, width, _ in self.BUILDINGS)) + 16.0
        y0 = min(-15.0, min(cy - depth / 2 for _, _, cy, _, depth in self.BUILDINGS)) - 12.0
        y1 = max(30.0, max(cy + depth / 2 for _, _, cy, _, depth in self.BUILDINGS)) + 18.0
        for name, frame, color, z in (
            ("campus_grass_extension", (x0, x1, y0, y1), (0.32, 0.51, 0.31, 1), -0.03),
            ("campus_main_road_extension", (38, 44, y0, y1), (0.62, 0.60, 0.56, 1), -0.02),
            ("campus_cross_road_extension", (x0, x1, 6, 11), (0.62, 0.60, 0.56, 1), -0.02),
        ):
            maker = CardMaker(name)
            maker.setFrame(*frame)
            ground = self.root.attachNewNode(maker.generate())
            ground.setP(-90)
            ground.setZ(z)
            ground.setColor(*color)
            ground.setLightOff()

        model = self.app.registry.load_model("model_ground")
        if model is not None and not model.isEmpty():
            model.reparentTo(self.root)
            model.setPos(-20.0, -15.0, 0.0)

    def _build_buildings(self) -> None:
        from panda3d.core import CardMaker, LineSegs, SamplerState, TransparencyAttrib

        maker = CardMaker("block")
        maker.setFrame(-0.5, 0.5, -0.5, 0.5)
        for name, cx, cy, width, depth in self.BUILDINGS:
            texture_id = self.BUILDING_TEXTURES.get(name)
            texture = self.app.registry.load_texture(texture_id) if texture_id else None
            if texture_id and texture is not None and texture_id not in self.app.registry.missing:
                # The generated art is a front elevation. Match the character
                # card pitch so the facade faces the moving orthographic camera.
                image_ratio = texture.getYSize() / max(1, texture.getXSize())
                card_height = width * image_ratio
                # Average fine facade details when shrinking the large source
                # art into the game canvas, avoiding nearest-sampling shimmer.
                texture.setMinfilter(SamplerState.FT_linear_mipmap_linear)
                texture.setMagfilter(SamplerState.FT_linear)
                texture_maker = CardMaker(f"{name}_front_texture")
                texture_maker.setFrame(-width / 2.0, width / 2.0, 0.0, card_height)
                card = self.root.attachNewNode(texture_maker.generate())
                card.setTexture(texture, 1)
                # Cutout depth lets a character walk both in front of and
                # behind a facade, without transparent corners hiding it.
                card.setTransparency(TransparencyAttrib.MBinary)
                card.setP(config.CAMERA_TILT_DEGREES)
                card.setPos(cx, cy - depth / 2.0, 0.0)
                card.setLightOff()
                card.setDepthTest(True)
                card.setDepthWrite(True)
                continue
            model = self.app.registry.load_model(f"model_{name}")
            if model is not None and not model.isEmpty():
                # .bam 的原点在占地西南角，所以按中心点减去半个占地摆放
                model.reparentTo(self.root)
                model.setPos(cx - width / 2.0, cy - depth / 2.0, 0.0)
                continue
            # 退路：占位方块 + 金色占地框
            block = self.root.attachNewNode(maker.generate())
            block.setP(-90)
            block.setScale(width, depth, 1)
            block.setPos(cx, cy, 0.02)
            block.setColorScale(0.42, 0.47, 0.56, 1)
            seg = LineSegs(name + "_line")
            seg.setThickness(1.5)
            seg.setColor(0.86, 0.75, 0.45, 1)
            x0, y0 = cx - width / 2, cy - depth / 2
            seg.moveTo(x0, y0, 0.05)
            seg.drawTo(x0 + width, y0, 0.05)
            seg.drawTo(x0 + width, y0 + depth, 0.05)
            seg.drawTo(x0, y0 + depth, 0.05)
            seg.drawTo(x0, y0, 0.05)
            self.root.attachNewNode(seg.create())

        for asset_name, px, py, heading in self.PROPS:
            prop = self.app.registry.load_model(f"model_prop_{asset_name}")
            if prop is None or prop.isEmpty():
                continue
            prop.reparentTo(self.root)
            prop.setPos(px, py, 0.0)
            prop.setH(heading)

    # ------------------------------------------------------------------ #
    def on_update(self, dt: float) -> None:
        import math

        from panda3d.core import Vec2

        if self.app.scenes.input_locked:
            return
        watcher = getattr(self.app, "mouseWatcherNode", None)
        if watcher is None:
            return
        move = Vec2(0, 0)
        if watcher.isButtonDown(self.keys["w"]):
            move.y += 1
        if watcher.isButtonDown(self.keys["s"]):
            move.y -= 1
        if watcher.isButtonDown(self.keys["a"]):
            move.x -= 1
        if watcher.isButtonDown(self.keys["d"]):
            move.x += 1
        if move.lengthSquared() == 0:
            self.anim_time += dt
            self._apply_frame(idle=True)
            return
        move.normalize()
        self.pos[0] += move.x * self.SPEED * dt
        self.pos[1] += move.y * self.SPEED * dt
        self.anim_time += dt
        self.facing = _facing_from_vector(move.x, move.y)
        self.card.setPos(self.pos[0], self.pos[1], 0)
        self.app.pipeline.align_camera(self.pos[0], self.pos[1])
        self._apply_frame()
        state = self.app.flow.state
        if state is not None:
            state.world = WorldPos(location_id=state.world.location_id, x=self.pos[0],
                                   y=self.pos[1], facing=self.facing)

    def _apply_frame(self, idle: bool = False) -> None:
        """静止用待机表（3 fps，正面呼吸/眨眼），移动用行走表（8 fps）。"""
        from panda3d.core import TextureStage

        sheet = self.idle_sprite if idle else self.sprite
        frame = int(self.anim_time * sheet.fps) % max(1, sheet.entry.cols)
        uv = sheet.frame_uv(self.facing, frame)
        self.card.setTexture(sheet.texture, 1)
        self.card.setTexOffset(TextureStage.getDefault(), uv[0], uv[1])
        self.card.setTexScale(TextureStage.getDefault(), uv[2] - uv[0], uv[3] - uv[1])

    def _interact(self) -> None:
        flow = self.app.flow
        state = flow.state
        if state is None or state.phase != "campus":
            return
        service = self.app.services.activity
        result = service.start(state, "campus_walk")
        if not isinstance(result, ActivityResult):
            return
        flow.handle_activity_result(result)
        self.app.scenes.push("ResultPanel", result=result)

    def _pause(self) -> None:
        self.app.flow.set_paused(True)
        self.app.scenes.push("PauseMenu")

    def _tab(self) -> None:
        self.app.scenes.push("TabPanel")

    def teleport(self, world: WorldPos) -> None:
        self.pos = [world.x, world.y]
        self.facing = world.facing
        if getattr(self, "card", None) is not None:
            self.card.setPos(self.pos[0], self.pos[1], 0)
            self.app.pipeline.align_camera(self.pos[0], self.pos[1])

    def inspect_character(self) -> None:
        """F4：8 方向检视网格（A-09 验收用），再次按 F4 关闭。"""
        from panda3d.core import TextureStage

        existing = getattr(self, "inspect_root", None)
        if existing is not None and not existing.isEmpty():
            existing.removeNode()
            self.inspect_root = None
            self.log.info("[DEBUG] character inspect closed")
            return
        root = self.app.render.attachNewNode("char_inspect")
        self.inspect_root = root
        for index, direction in enumerate(("s", "se", "e", "ne", "n", "nw", "w", "sw")):
            column = index % 4
            row = index // 4
            card = self.app.pipeline.make_character_card(root, f"inspect_{direction}")
            card.setPos(32.0 + column * 5.0, 11.0 - row * 5.0, 0)
            card.setTexture(self.sprite.texture, 1)
            uv = self.sprite.frame_uv(direction, 0)
            card.setTexOffset(TextureStage.getDefault(), uv[0], uv[1])
            card.setTexScale(TextureStage.getDefault(), uv[2] - uv[0], uv[3] - uv[1])
        self.log.info("[DEBUG] character inspect grid: 8 directions x %d frames", self.sprite.entry.cols)


def _facing_from_vector(x: float, y: float) -> str:
    """输入向量 -> 8 方向（s 面朝镜头，n 背向镜头）。"""
    import math

    angle = math.degrees(math.atan2(y, x)) % 360.0
    sectors = (
        (22.5, "e"), (67.5, "ne"), (112.5, "n"), (157.5, "nw"),
        (202.5, "w"), (247.5, "sw"), (292.5, "s"), (337.5, "se"),
    )
    for limit, facing in sectors:
        if angle < limit:
            return facing
    return "e"


def _unused_to_aspect_x(world_x: float) -> float:
    """世界 X（米）近似换算到 aspect2d 坐标，仅用于调试标签摆放。"""
    return (world_x - 40.0) / 10.0


def _unused_to_aspect_z(world_y: float) -> float:
    return (world_y - 5.0) / 8.8


class StubResultPanel(StubScene):
    def on_enter(self, **kwargs: Any) -> None:
        result = kwargs.get("result")
        self.root = self.app.render2d.attachNewNode("stub_result")
        text = ""
        if isinstance(result, ActivityResult):
            text = f"ACTIVITY {result.activity_id}\n" + "\n".join(
                f"{k} {v:+d}" for k, v in result.deltas.items()
            )
        self.label = self._panel(text or "结果", pos=(-0.72, -0.52))
        self.cg = None
        if isinstance(result, ActivityResult):
            self.cg = self._show_cg(result.activity_id)
        self.bind("enter", self._close)

    def _show_cg(self, activity_id: str):
        """活动结果配图：cg_naiwan_<activity>，缺失时 registry 会自动回退占位图。"""
        from direct.gui.OnscreenImage import OnscreenImage
        from panda3d.core import SamplerState

        asset_id = f"cg_naiwan_{activity_id}"
        try:
            texture = self.app.registry.load_texture(asset_id)
        except Exception as exc:
            self.log.warning("[UI] cg %s failed: %s", asset_id, exc)
            return None
        if texture is None:
            return None
        image = OnscreenImage(image=texture, parent=self.app.aspect2d,
                              pos=(0.0, 0.0, 0.30), scale=(0.46, 1.0, 0.259))
        image.setTransparency(True)
        for tex in image.findAllTextures():
            tex.setMagfilter(SamplerState.FT_nearest)
            tex.setMinfilter(SamplerState.FT_nearest)
        return image

    def on_exit(self) -> None:
        if self.cg is not None:
            self.cg.destroy()
            self.cg = None
        super().on_exit()

    def _close(self) -> None:
        result = self.kwargs.get("result")
        self.app.scenes.pop()
        self.app.flow.close_result_panel(result)


class StubEventScene(StubScene):
    def on_enter(self, **kwargs: Any) -> None:
        self.event_id = kwargs.get("event_id", "story_opening")
        state = self.app.flow.state
        pages: list[str] = []
        if state is not None:
            service = self.app.services.event
            view = service.get_view(state, self.event_id)
            pages = list(getattr(view, "page_text_ids", [])) or [f"evt.{self.event_id}.body.1"]
            self.choices = list(getattr(view, "choices", []))
        else:
            pages = [f"evt.{self.event_id}.body.1"]
            self.choices = []
        self.root = self.app.render2d.attachNewNode("stub_event")
        self.label = self._panel(
            f"[EVENT] {self.event_id}\n" + "\n".join(pages)
            + "\n\nEnter / Space / Click: continue"
        )
        # The overlay intentionally locks walking. Accept the common movement keys too,
        # so a player who tries WASD is taken through the opening instead of feeling stuck.
        for event in ("enter", "space", "mouse1", "w", "a", "s", "d"):
            self.bind(event, self._choose)

    def _choose(self) -> None:
        self.app.scenes.pop()
        state = self.app.flow.state
        if state is None:
            return
        choice_id = self.choices[0].choice_id if self.choices else "ok"
        service = self.app.services.event
        result = service.choose(state, self.event_id, choice_id)
        if not isinstance(result, EventResult):
            result = EventResult(event_id=self.event_id, choice_id=choice_id)
        self.app.flow.handle_event_result(result)
        if self.kwargs.get("story"):
            self.app.flow.enter_campus()


class StubDaySummary(StubScene):
    def on_enter(self, **kwargs: Any) -> None:
        result = kwargs.get("result")
        lines = []
        if isinstance(result, DayEndResult):
            lines = [f"{k} {v:+d}" for k, v in result.deltas.items()]
            lines.append(f"next day_index={result.new_day_index}")
            if result.semester_event_id:
                lines.append(f"semester event: {result.semester_event_id}")
            if result.graduated:
                lines.append("毕业")
        self.root = self.app.render2d.attachNewNode("stub_summary")
        self.label = self._panel("DAY SUMMARY\n" + "\n".join(lines) + "\n\nEnter: close")
        self.bind("enter", self._close)

    def _close(self) -> None:
        self.app.scenes.pop()


class StubPauseMenu(StubScene):
    def on_enter(self, **kwargs: Any) -> None:
        self.root = self.app.render2d.attachNewNode("stub_pause")
        self.label = self._panel("PAUSED\nEnter: resume   S: save   L: load")
        self.bind("enter", self._resume)
        self.bind("s", self._save)
        self.bind("l", self._load)

    def _resume(self) -> None:
        self.app.scenes.pop()
        self.app.flow.set_paused(False)

    def _save(self) -> None:
        ok = self.app.flow.request_save("slot_1")
        self.label.setText(f"SAVED {'ok' if ok else 'failed'}\nEnter: resume")

    def _load(self) -> None:
        """Load the first save slot without leaving the pause overlay half-open."""
        try:
            self.app.flow.load_game("slot_1")
        except (SaveLoadError, RuntimeError) as exc:
            self.label.setText(f"LOAD FAILED\n{type(exc).__name__}\nEnter: resume")
            return
        self.app.scenes.pop_all()
        self.app.flow.set_paused(False)


class StubTabPanel(StubScene):
    def on_enter(self, **kwargs: Any) -> None:
        state = self.app.flow.state
        text = "STATUS"
        if state is not None:
            stats = "  ".join(f"{k}={v}" for k, v in state.stats.items())
            text = f"{state.year} 年 {state.semester} 学期 第 {state.day} 天\n{stats}\n心情={state.mood} 精力={state.energy}\nTab 关闭"
        self.root = self.app.render2d.attachNewNode("stub_tab")
        self.label = self._panel(text)
        self.bind("tab", lambda: self.app.scenes.pop())


class StubGraduation(StubScene):
    def on_enter(self, **kwargs: Any) -> None:
        ending = kwargs.get("ending")
        ending_id = ending.ending_id if isinstance(ending, EndingResult) else str(ending)
        self.root = self.app.render2d.attachNewNode("stub_grad")
        state = self.app.flow.state
        stats = "  ".join(f"{k}={v}" for k, v in state.stats.items()) if state else ""
        self.label = self._panel(f"GRADUATION: {ending_id}\n{stats}\n\nEnter: back to menu")
        self.bind("enter", self._back)

    def _back(self) -> None:
        self.app.flow.finish_graduation()


class AutoplayDriver:
    """--autoplay：一帧一步的脚本化通关，用于 A-06 与冒烟流程自检。"""

    MAX_STEPS = 800
    PREFERRED_ACTIVITIES = (
        "attend_class",
        "library_study",
        "exercise",
        "join_club",
        "play_games",
        "create_work",
        "eat_canteen",
        "rest_dorm",
        "campus_walk",
    )

    def __init__(self, app: NaiwaApp) -> None:
        self.app = app
        self.log = LOG
        self.steps = 0
        self.phase_trail: list[str | None] = []
        self.activity_log: list[str] = []
        self.event_log: list[str] = []
        self.errors: list[str] = []
        self.ok = False
        self.done = False
        self.ending_id: str | None = None
        self.final_day_index: int | None = None
        self.final_play_seconds: float | None = None
        self.app.scenes.pop_all()
        seed = app.options.seed if app.options.seed is not None else 42
        self.app.flow.new_game(seed=seed, skip_intro=True)
        self._record_phase()

    # ------------------------------------------------------------------ #
    def _record_phase(self) -> None:
        state = self.app.flow.state
        phase = state.phase if state is not None else "finished"
        if not self.phase_trail or self.phase_trail[-1] != phase:
            self.phase_trail.append(phase)

    def step(self) -> bool:
        if self.done:
            return True
        self.steps += 1
        flow = self.app.flow
        scenes = self.app.scenes
        if self.steps > self.MAX_STEPS:
            self.errors.append("step limit reached")
            return self._finish(False)
        state = flow.state
        if state is None:
            return self._finish(self.ok)

        while scenes.overlays and scenes.top_overlay_id != "EventScene":
            scenes.pop()

        if state.phase == "graduation":
            self.ending_id = state.ending_id
            self.final_day_index = state.day_index
            self.final_play_seconds = round(state.play_seconds, 2)
            self._record_phase()
            flow.finish_graduation()
            self.ok = self.ending_id is not None
            return self._finish(self.ok)

        if state.phase == "event":
            event_id = state.pending_event_id or flow.story_opening_id
            service = self.app.services.event
            view = service.get_view(state, event_id)
            choices = list(getattr(view, "choices", []))
            choice_id = "ok"
            for choice in choices:
                if getattr(choice, "enabled", True):
                    choice_id = choice.choice_id
                    break
            result = service.choose(state, event_id, choice_id)
            if not isinstance(result, EventResult):
                result = EventResult(event_id=event_id, choice_id=choice_id)
            if scenes.top_overlay_id == "EventScene":
                scenes.pop()
            flow.handle_event_result(result)
            self.event_log.append(f"{event_id}:{choice_id}")
            self._record_phase()
            return False

        if state.day_finished:
            flow.finish_day()
            self._record_phase()
            return False

        service = self.app.services.activity
        chosen = None
        for activity_id in self.PREFERRED_ACTIVITIES:
            can, _error = service.can_start(state, activity_id)
            if can:
                chosen = activity_id
                break
        if chosen is None:
            self.errors.append(f"no startable activity at day={state.day_index}")
            return self._finish(False)
        result = service.start(state, chosen)
        flow.handle_activity_result(result)
        self.activity_log.append(f"{state.day_index}:{chosen}")
        flow.close_result_panel(result)
        self._record_phase()
        return False

    # ------------------------------------------------------------------ #
    def _finish(self, ok: bool) -> bool:
        self.ok = bool(ok)
        self.done = True
        flow = self.app.flow
        state = flow.state
        report = {
            "ok": self.ok,
            "steps": self.steps,
            "phase_trail": self.phase_trail,
            "activities": len(self.activity_log),
            "events": self.event_log,
            "ending_id": self.ending_id,
            "day_index": self.final_day_index if self.final_day_index is not None
            else (state.day_index if state is not None else None),
            "play_seconds": self.final_play_seconds if self.final_play_seconds is not None
            else (round(state.play_seconds, 2) if state is not None else None),
            "errors": self.errors,
            "missing_assets": sorted(self.app.registry.missing),
            "save_slots": [info.slot for info in self.app.saves.list_slots()],
        }
        target = Path(config.resource_root()) / "reports" / "standalone" / "A" / "autoplay.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        self.log.info("[AUTOPLAY] ok=%s steps=%d phases=%s -> %s", self.ok, self.steps,
                      self.phase_trail, target)
        return True


STUB_SCENES = {
    "MainMenu": StubMainMenu,
    "CampusScene": StubCampus,
    "InteriorScene": StubCampus,
    "EventScene": StubEventScene,
    "ResultPanel": StubResultPanel,
    "DaySummary": StubDaySummary,
    "TabPanel": StubTabPanel,
    "PauseMenu": StubPauseMenu,
    "SettingsMenu": StubPauseMenu,
    "SaveMenu": StubPauseMenu,
    "GraduationScene": StubGraduation,
}


def run(options: config.Options) -> int:
    apply_prc(options, config.Settings.load())
    app = NaiwaApp(options)
    try:
        app.run()
    finally:
        # 无论从哪条路径退出（窗口关闭 / Esc / 截图完成 / 异常），都先停声音再销毁引擎
        app.stop_audio()
        try:
            app.destroy()
        except Exception:
            pass
    return int(getattr(app, "exit_code", 0))



