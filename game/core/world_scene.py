"""A 维护：把 C 的校园/室内与 D 的界面接进 SceneManager 的适配层。

分工边界：
- `game/world/*`（C）负责地图数据、移动、碰撞、触发器、交互点映射，它交的是
  **几何构建器 + 纯逻辑**，不是场景协议类；
- `game/ui/*`（D）负责界面控件，它交的是 **可组合的 widget**，也不是场景协议类；
- 场景协议（`__init__(app, **kw)` / `on_enter` / `on_exit` / `on_update` / `is_overlay`）
  与"谁来 new 谁"属于 A 的装配职责，全部落在这个文件里。

设计要点：
1. 相机只借用 C 的 `CameraRig`（死区 / 平滑 / 边界 / 1-24 米对齐），最终画面仍然由
   A 的 `LowResPipeline.align_camera()` 落到 480×270 缓冲上——C 的 `CameraController`
   会直接改 `base.cam`，与渲染管线抢镜头，因此这里不用它。
2. 输入：WASD/方向键与 Shift 由 C 的 `PlayerController.read_input()` 轮询；
   E / Tab / Esc / Space 由本层通过 `app.input`（InputRouter）绑定，退场只收回自己那份，
   覆盖层存在时 gameplay 输入统一由 SceneManager.input_locked 关掉。
3. 交互：E → C 的 `InteractionService.interact()`，返回的 kind 决定后续流程：
   activity → ResultPanel，door → C 已切场景，save → SaveMenu，inspect → 文本事件。
"""

from __future__ import annotations

import logging
import math
from typing import Any, Callable

from panda3d.core import TextNode, TextureStage

from game import config
from game.core.event_bus import TOPIC_DAY_ENDED
from game.core.results import EventView
from game.core.state import GameState
from game.systems.content_db import ContentError
from game.ui import theme
from game.ui.day_summary import DaySummary
from game.ui.event_scene import EventScene
from game.ui.graduation_scene import GraduationScene
from game.ui.hud import HUD
from game.ui.main_menu import MainMenu
from game.ui.pause_menu import PauseMenu
from game.ui.prompt import InteractionPrompt
from game.ui.result_panel import ResultPanel
from game.ui.save_menu import SaveMenu
from game.ui.settings_menu import SettingsMenu
from game.ui.tab_panel import TabPanel
from game.ui.tutorial import TutorialController, TutorialOverlay
from game.ui.widgets import UITransform

LOG = logging.getLogger("naiwa.world_scene")


# --------------------------------------------------------------------------- #
# 小适配器：把 A 的素材/音频包成 C 期望的 animator / audio
# --------------------------------------------------------------------------- #
class SpriteAnimator:
    """C 的 PlayerController 每帧调用 play(asset_id, row=朝向, fps=...)；这里落到卡片 UV。"""

    def __init__(self, card, registry) -> None:
        self.card = card
        self.registry = registry
        self._walk = None
        self._idle = None
        self._asset_id: str | None = None
        self._row = "s"
        self._fps = 8.0
        self._elapsed = 0.0
        self._frame = 0

    def _sheet(self, asset_id: str):
        if asset_id == "char_naiwan_walk":
            if self._walk is None:
                self._walk = self.registry.load_sprite(asset_id)
            return self._walk
        if self._idle is None:
            self._idle = self.registry.load_sprite(asset_id)
        return self._idle

    def play(self, asset_id: str, row: str, fps: float) -> None:
        if asset_id != self._asset_id:
            self._asset_id = asset_id
            self._elapsed = 0.0
            self._frame = 0
            sheet = self._sheet(asset_id)
            if sheet is not None:
                self.card.set_texture(sheet.texture, 1)
        if row != self._row:
            self._row = row
            self._frame = 0
            self._elapsed = 0.0
        self._fps = max(0.1, float(fps))
        # 立刻把当前帧的 UV 落到卡片上：覆盖层打开时 tick() 不会推进，
        # 少了这一步角色会一直显示整张精灵表（看上去就是"人没了"）。
        sheet = self._sheet(asset_id)
        if sheet is not None:
            self._apply(sheet)

    def tick(self, dt: float) -> None:
        if self._asset_id is None:
            return
        sheet = self._sheet(self._asset_id)
        if sheet is None:
            return
        self._elapsed += dt
        frame_time = 1.0 / self._fps
        while self._elapsed >= frame_time:
            self._elapsed -= frame_time
            self._frame += 1
        self._apply(sheet)

    def _apply(self, sheet) -> None:
        cols = max(1, int(getattr(sheet.entry, "cols", 8)))
        frame = self._frame % cols
        u0, v0, u1, v1 = sheet.frame_uv(self._row, frame)
        stage = TextureStage.getDefault()
        self.card.set_tex_offset(stage, u0, v0)
        self.card.set_tex_scale(stage, u1 - u0, v1 - v0)


class SfxAdapter:
    """C 的 PlayerController 通过 audio.play(sfx_id) 播放脚步。"""

    def __init__(self, audio) -> None:
        self.audio = audio

    def play(self, asset_id: str) -> None:
        try:
            self.audio.play_sfx(asset_id)
        except Exception:  # pragma: no cover - 音频缺失不应影响移动
            LOG.debug("sfx 播放失败: %s", asset_id)


# --------------------------------------------------------------------------- #
# 基础：世界场景（校园 / 室内共用）
# --------------------------------------------------------------------------- #
class WorldSceneBase:
    is_overlay = False
    scene_kind = "campus"

    def __init__(self, app, **kwargs: Any) -> None:
        self.app = app
        self.log = LOG
        self.root = None
        self.scene = None
        self.player = None
        self.hud = None
        self.prompt = None
        self.tracker = None
        self.tutorial = None
        self.tutorial_overlay = None
        self.debug = None
        self._tutorial_day_handler = None
        self._last_player_position: tuple[float, float] | None = None
        self._last_ia: str | None = None
        self._state: GameState | None = None

    # ------------------------------------------------------------------ 生命周期
    def on_enter(
        self,
        spawn: str | None = None,
        state: GameState | None = None,
        position: tuple[float, float, str] | None = None,
        **kwargs: Any,
    ) -> None:
        from game.world.camera_controller import CameraRig
        from game.world.interaction_service import InteractionService
        from game.world.trigger_zone import PromptTracker, make_candidates

        self._state = state if state is not None else self.app.flow.state
        self.md = self.app.map_data
        self.root = self.app.render.attachNewNode(f"{type(self).__name__}")
        self.scene = self.build_scene(self.root)
        self.rig = CameraRig()
        self.candidates = make_candidates(self.md, self.scene_id)
        self.tracker = PromptTracker()

        if self._state is not None and spawn:
            self._state.world.location_id = self._place_for(spawn)

        self.card = self.app.pipeline.make_character_card(self.root, "naiwan_card")
        self.animator = SpriteAnimator(self.card, self.app.registry)
        self.audio_adapter = SfxAdapter(self.app.audio)
        from game.world.player_controller import PlayerController

        self.player = PlayerController(
            self.md, self._state, self.card, camera=None,
            animator=self.animator, audio=self.audio_adapter,
            key_down=self._key_down,
        )
        self.player.set_scene(self.scene_id, reset=False)
        if position is not None:
            # 从室内退出时由调用方给出落点（门外 1 米、朝向背离建筑）。
            # 必须走参数而不是"场景建好之后再 teleport"：淡入回调在 fade=0 时
            # 同步执行，事后注册的钩子根本不会被调用。
            exit_x, exit_y, facing = position
            self.player.teleport(exit_x, exit_y, facing)
            if self._state is not None:
                self._state.world.x = exit_x
                self._state.world.y = exit_y
                self._state.world.facing = facing
                # 落点决定所在地点：从室内出来时必须回到室外的区域 id，
                # 否则 scene_of() 会认为玩家还在室内，户外交互点全部查不到。
                self._state.world.location_id = self.md.area_at(exit_x, exit_y) or self._state.world.location_id
        # 建好场景就把角色卡片摆到出生点并贴上待机帧：覆盖层（开场事件）在场时
        # on_update 会提前 return，卡片会一直停在原点 (0, 0)——镜头里就是"人物消失"。
        self.player.apply_pose()
        self._apply_scene_camera()

        self.hud = HUD(self.app.ui_root, self.app.ui_transform, self.app.text, self.app.registry)
        self.hud.update(self._state)
        self.prompt = InteractionPrompt(
            self.app.ui_root, self.app.ui_transform, self.app.text, self.app.registry
        )
        self.interaction = InteractionService(
            self.md,
            activity_service=self.app.services.activity,
            relationship_service=self.app.services.relationship,
            scene_manager=self.app.scenes,
            event_bus=self.app.bus,
        )
        self.tutorial = TutorialController(self._state, self.app.text)
        self.tutorial_overlay = TutorialOverlay(
            self.app.ui_root, self.app.ui_transform, self.app.text, self.app.registry
        )
        self.tutorial_overlay.attach(self.tutorial)
        self.tutorial.notify("enter_campus")
        self.tutorial_overlay.refresh()
        self._last_player_position = (self.player.motion.x, self.player.motion.y)
        self._tutorial_day_handler = self.app.bus.subscribe(
            TOPIC_DAY_ENDED, self._on_tutorial_day_ended
        )
        self.debug = self._build_debug_draw()
        self._bind_input()
        self._refresh_prompt(force=True)

    # ------------------------------------------------------------------ 调试绘制
    def _build_debug_draw(self):
        """--dev 下接 C 的 DebugDraw：F1 碰撞线框、F2 交互点、F3 状态、F5 传送、F6 时段。"""
        if not getattr(self.app.options, "dev", False):
            return None
        try:
            from game.world.debug_draw import DebugDraw

            debug = DebugDraw(
                self.md, self.root, player=self.player, state=self._state, goto=self._debug_goto
            )
            debug.set_scene(self.scene_id)
            debug.bind(self.app)
            return debug
        except Exception as exc:  # pragma: no cover - 调试工具不应阻塞开局
            self.log.warning("[WORLD] DebugDraw 不可用: %s", exc)
            return None

    def _debug_goto(self, x: float, y: float, facing: str | None = None) -> None:
        if self.player is not None:
            self.player.teleport(x, y, facing)

    def on_exit(self) -> None:
        self._unbind_input()
        if self._tutorial_day_handler is not None:
            self.app.bus.unsubscribe(TOPIC_DAY_ENDED, self._tutorial_day_handler)
            self._tutorial_day_handler = None
        if self.tutorial_overlay is not None:
            self.tutorial_overlay.destroy()
            self.tutorial_overlay = None
        self.tutorial = None
        self._last_player_position = None
        self.debug = None
        for widget in (self.hud, self.prompt):
            if widget is not None:
                widget.destroy()
        self.hud = self.prompt = None
        if self.scene is not None:
            self.scene.destroy()
            self.scene = None
        if self.root is not None and not self.root.is_empty():
            self.root.remove_node()
        self.root = None

    def on_update(self, dt: float) -> None:
        if self._state is None:
            return
        locked = self.app.scenes.input_locked
        before = (self.player.motion.x, self.player.motion.y)
        self.player.update(dt, locked=locked)
        after = (self.player.motion.x, self.player.motion.y)
        self._last_player_position = after
        distance = math.hypot(after[0] - before[0], after[1] - before[1])
        if distance > 0.0:
            self.tutorial.notify("player_moved", distance_m=distance)
        if self._state.energy < 40:
            self.tutorial.notify("low_energy")
        self.tutorial.notify("tick", dt=dt)
        if self.tutorial_overlay is not None:
            self.tutorial_overlay.refresh()
        if locked:
            # 覆盖层（对话框 / 结果面板 / 菜单）打开时把 HUD 与提示框收起来
            if self.hud is not None:
                self.hud.hide()
            if self.prompt is not None:
                self.prompt.hide_prompt()
            return
        if self.hud is not None and not self.hud.visible:
            self.hud.show()
        self.animator.tick(dt)
        self._update_scene_camera(dt, force=False)
        self._refresh_prompt()
        self.hud.update(self._state)
        self.hud.tick(dt)
        self._check_autostep()

    def _on_tutorial_day_ended(self, **_data: Any) -> None:
        if self.tutorial is not None:
            self.tutorial.notify("day_ended")
            if self.tutorial_overlay is not None:
                self.tutorial_overlay.refresh()

    # ------------------------------------------------------------------ 子类实现
    scene_id = "campus"

    def build_scene(self, parent):
        raise NotImplementedError

    def _place_for(self, spawn: str) -> str:
        return spawn

    def _apply_scene_camera(self) -> None:
        raise NotImplementedError

    def _update_scene_camera(self, dt: float, force: bool) -> None:
        raise NotImplementedError

    def _check_autostep(self) -> None:
        """室内地垫：踩上去自动回室外。"""

    # ------------------------------------------------------------------ 输入
    def _key_down(self, key: str) -> bool:
        from game.world.player_controller import key_down

        return key_down(getattr(self.app, "mouseWatcherNode", None), key)

    def _bind_input(self) -> None:
        self.bind("e", self._on_interact)
        self.bind("tab", self._on_tab)
        self.bind("escape", self._on_escape)

    def _unbind_input(self) -> None:
        # 只收回本场景绑过的键；直接 ignore 会连带拆掉上层覆盖层的绑定
        self.app.input.unbind(self)
        for key in ("f1", "f2", "f3", "f5", "f6"):
            self.app.ignore(key)

    def bind(self, event: str, handler) -> None:
        """本场景的按键绑定统一入口（归属可回收）。"""
        self.app.input.bind(self, event, handler)

    def _on_interact(self) -> None:
        if self.app.scenes.input_locked:
            return
        ia_id = self.tracker.active_id if self.tracker else None
        if not ia_id:
            return
        self.tutorial.notify("key_space")
        result = self.interaction.interact(self._state, ia_id)
        self.log.info("[WORLD] E %s -> %s", ia_id, result.kind)
        if result.kind == "activity":
            self.app.flow.handle_activity_result(result.payload)
            self.app.scenes.push("ResultPanel", result=result.payload)
            self.tutorial.notify("activity_done")
        elif result.kind == "blocked":
            self.app.audio.play_sfx("sfx_ui_cancel")

    def _on_tab(self) -> None:
        if self._state is None or self._state.phase != "campus":
            return
        if self.app.scenes.overlays:
            return
        self.tutorial.notify("tab_opened")
        self.app.scenes.push("TabPanel", state=self._state)

    def _on_escape(self) -> None:
        if self.app.scenes.overlays:
            return
        self.app.flow.set_paused(True)
        self.app.scenes.push("PauseMenu")

    # ------------------------------------------------------------------ 交互提示
    def _refresh_prompt(self, force: bool = False) -> None:
        if self._state is None or self.prompt is None:
            return
        player = self.player.motion
        candidate = self.tracker.update(self.candidates, player.x, player.y)
        ia_id = candidate.id if candidate is not None else None
        if ia_id is None:
            if self._last_ia is not None or force:
                self.prompt.hide_prompt()
            self._last_ia = None
            return
        self._last_ia = ia_id
        view = self.interaction.query(self._state, ia_id)
        self.prompt.show_prompt(view)
        self.tutorial.notify("near_interactable")


class CampusSceneAdapter(WorldSceneBase):
    scene_id = "campus"

    #: 道具 id 前缀 -> (贴图 asset_id, 世界高度米)。没登记的道具继续用方块白模。
    PROP_ART = (
        ("prop_tree", "campus_texture_prop_tree", 4.5),
        ("prop_lamp", "campus_texture_prop_lamp", 4.0),
        ("prop_bin", "campus_texture_prop_bin", 1.0),
        ("prop_gate_notice", "campus_texture_prop_sign", 2.4),
    )

    def _texture(self, asset_id: str):
        """缺资源时返回 None（而不是品红占位图），让场景退回白模。"""
        registry = self.app.registry
        if asset_id not in registry or not registry.file_exists(asset_id):
            LOG.warning("[WORLD] 贴图缺失，跳过：%s", asset_id)
            return None
        try:
            return registry.load_texture(asset_id)
        except Exception as exc:  # pragma: no cover
            LOG.warning("[WORLD] 贴图加载失败 %s: %s", asset_id, exc)
            return None

    def _prop_art(self, prop_id: str):
        for prefix, asset_id, height in self.PROP_ART:
            if prop_id.startswith(prefix):
                texture = self._texture(asset_id)
                return None if texture is None else (texture, height)
        return None

    #: 建筑 id -> 正面图 asset_id（A 的 manifest 里已有）
    BUILDING_ART = {
        "loc_dorm": "campus_texture_dorm",
        "loc_classroom": "campus_texture_teaching",
        "loc_library": "campus_texture_library",
        "loc_clubroom": "campus_texture_club",
        "loc_canteen": "campus_texture_canteen",
    }

    def _building_art(self, building_id: str):
        asset_id = self.BUILDING_ART.get(building_id)
        if asset_id is None:
            return None
        texture = self._texture(asset_id)
        if texture is None:
            return None
        from panda3d.core import SamplerState

        # 正面图是 2~3 MB 的大图，缩到游戏里必须开 mipmap，否则远处会闪
        texture.set_minfilter(SamplerState.FT_linear_mipmap_linear)
        texture.set_magfilter(SamplerState.FT_linear)
        return texture

    def build_scene(self, parent):
        from game.world.campus_scene import CampusScene

        return CampusScene(
            self.md, parent,
            dev=bool(self.app.options.dev),
            ground_texture=self._texture("campus_texture_ground"),
            prop_art=self._prop_art,
            building_art=self._building_art,
        )

    def _clamp(self, target: tuple[float, float]) -> tuple[float, float]:
        """按 A 的渲染管线 film 尺寸钳制镜头目标，保证画面不露出地图外。"""
        import math

        half_w = config.FILM_WIDTH_METERS / 2.0
        half_d = (config.FILM_HEIGHT_METERS / 2.0) / max(
            0.2, math.sin(math.radians(abs(config.CAMERA_TILT_DEGREES)))
        )
        bounds = self.md.bounds
        x = min(max(target[0], bounds.x0 + half_w), bounds.x1 - half_w)
        y = min(max(target[1], bounds.y0 + half_d), bounds.y1 - half_d)
        return (x, y)

    def _apply_scene_camera(self) -> None:
        x, y = self.player.motion.x, self.player.motion.y
        self.rig.set_outdoor((x, y))
        self.app.pipeline.align_camera(*self._clamp(self.rig.target))

    def _update_scene_camera(self, dt: float, force: bool) -> None:
        x, y = self.player.motion.x, self.player.motion.y
        self.rig.update((x, y), 1.0 if force else dt)
        self.app.pipeline.align_camera(*self._clamp(self.rig.target))


class InteriorSceneAdapter(WorldSceneBase):
    scene_id = "campus"  # 由 on_enter 覆盖

    def on_enter(self, building_id: str | None = None, state: GameState | None = None,
                 **kwargs: Any) -> None:
        self.scene_id = building_id or kwargs.get("scene") or "loc_dorm"
        super().on_enter(spawn=None, state=state)
        # 室内：location_id 必须切到建筑 id，交互点查询才会命中室内那一批
        if self._state is not None:
            self._state.world.location_id = self.scene_id
        entry_x, entry_y, facing = self.md.interior_entry(self.scene_id)
        ox, oy = self.md.interior(self.scene_id).origin
        self.player.teleport(ox + entry_x, oy + entry_y, facing)
        self.rig.set_interior((ox + self.md.interior(self.scene_id).center[0],
                               oy + self.md.interior(self.scene_id).center[1]))
        self.app.pipeline.align_camera(*self.rig.target)

    def build_scene(self, parent):
        from game.world.interior_scene import InteriorScene

        return InteriorScene(self.md, self.scene_id, parent, dev=bool(self.app.options.dev))

    def _place_for(self, spawn: str) -> str:
        return spawn

    def _apply_scene_camera(self) -> None:
        pass

    def _update_scene_camera(self, dt: float, force: bool) -> None:
        pass

    def _check_autostep(self) -> None:
        """踩到入口地垫 → 回到门外 1 米处（1 秒冷却由 C 的 update_mat 负责）。"""
        if self.scene is None or self._state is None:
            return
        motion = self.player.motion
        if not self.scene.update_mat(motion.x, motion.y, 1.0 / 60.0):
            return
        exit_x, exit_y, facing = self.scene.exit_world()
        building_id = self.scene_id
        state = self._state
        LOG.info("[WORLD] 离开 %s -> (%.1f, %.1f) %s", building_id, exit_x, exit_y, facing)
        state.world.location_id = self.md.area_at(exit_x, exit_y) or "loc_gate"
        self.app.scenes.change(
            "CampusScene",
            spawn=building_id,
            state=state,
            position=(exit_x, exit_y, facing),
        )


# --------------------------------------------------------------------------- #
# 覆盖层 / 基础界面
# --------------------------------------------------------------------------- #
class WidgetSceneBase:
    is_overlay = True
    widget_cls = None
    scene_id = ""

    def __init__(self, app, **kwargs: Any) -> None:
        self.app = app
        self.widget = None
        self.kwargs = kwargs

    def _make_widget(self):
        return self.widget_cls(
            self.app.ui_root, self.app.ui_transform, self.app.text, self.app.registry
        )

    def on_enter(self, **kwargs: Any) -> None:
        self.widget = self._make_widget()
        self.widget.show()
        self.bind_input()
        self.apply(**kwargs)

    def apply(self, **kwargs: Any) -> None:
        pass

    def bind(self, event: str, handler) -> None:
        """按键绑定的唯一入口：记下归属，退场时只收回自己那份。"""
        self.app.input.bind(self, event, handler)

    def bind_input(self) -> None:
        pass

    def unbind_input(self) -> None:
        self.app.input.unbind(self)

    def on_update(self, dt: float) -> None:
        tick = getattr(self.widget, "tick", None)
        if callable(tick):
            tick(dt)

    def on_exit(self) -> None:
        self.unbind_input()
        if self.widget is not None:
            self.widget.destroy()
            self.widget = None

    # 便捷：覆盖层关闭
    def _pop(self) -> None:
        self.app.scenes.pop()


class MainMenuSceneAdapter(WidgetSceneBase):
    is_overlay = False
    widget_cls = MainMenu
    scene_id = "MainMenu"

    def on_enter(self, **kwargs: Any) -> None:
        super().on_enter(**kwargs)
        self.widget.attach_save_manager(self.app.saves)
        self.widget.handlers.update(
            new_game=self._new_game,
            **{"continue": self._continue},
            load=self._load,
            settings=self._settings,
            quit=self.app.quit_game,
        )

    def bind_input(self) -> None:
        self.bind("arrow_up", lambda: self.widget.move(-1))
        self.bind("w", lambda: self.widget.move(-1))
        self.bind("arrow_down", lambda: self.widget.move(1))
        self.bind("s", lambda: self.widget.move(1))
        self.bind("enter", self.widget.confirm)
        self.bind("space", self.widget.confirm)
        self.bind("escape", self.app.quit_game)

    def _new_game(self) -> None:
        self.app.flow.new_game(seed=self.app.options.seed, skip_intro=self.app.options.skip_intro)

    def _continue(self) -> None:
        try:
            self.app.flow.load_game(config.AUTOSAVE_SLOT)
        except Exception as exc:
            LOG.warning("[MENU] continue 失败: %s", exc)

    def _load(self) -> None:
        self.app.scenes.push("SaveMenu", mode="load")

    def _settings(self) -> None:
        self.app.scenes.push("SettingsMenu")


class ResultPanelSceneAdapter(WidgetSceneBase):
    widget_cls = ResultPanel
    scene_id = "ResultPanel"

    def on_enter(self, **kwargs: Any) -> None:
        super().on_enter(**kwargs)
        self.widget.on_close = self._close

    def apply(self, result=None, **kwargs: Any) -> None:
        if result is not None:
            self.widget.show_result(result)

    def bind_input(self) -> None:
        # 三个「按 Space 继续」的面板都接受鼠标左键与 Esc：
        # 玩家第一反应是点一下或按 Esc，不能只有 Space 能用。
        self.bind("space", self.widget.confirm)
        self.bind("enter", self.widget.confirm)
        self.bind("mouse1", self.widget.confirm)
        self.bind("escape", self.widget.confirm)

    def _close(self) -> None:
        result = self.kwargs.get("result")
        self.app.scenes.pop()
        base_scene = self.app.scenes.base_scene
        tutorial = getattr(base_scene, "tutorial", None)
        if tutorial is not None:
            tutorial.notify("result_closed")
            overlay = getattr(base_scene, "tutorial_overlay", None)
            if overlay is not None:
                overlay.refresh()
        self.app.flow.close_result_panel(result)


class EventSceneAdapter(WidgetSceneBase):
    widget_cls = EventScene
    scene_id = "EventScene"

    def on_enter(self, **kwargs: Any) -> None:
        super().on_enter(**kwargs)
        self.widget.on_choose = self._choose
        self.widget.on_finished = self._finished

    def apply(self, event_id: str | None = None, text_id: str | None = None,
              semester: bool = False, story: bool = False, **kwargs: Any) -> None:
        self._pending_result = None
        if text_id:
            # Inspect pages are display-only: they must never enter EventService.choose.
            lines = [self.app.text.get_raw(text_id)]
            self.widget.show_simple_pages("inspect", [])
            self.widget.dialogue.show_page({"speaker": None, "portrait": None, "lines": lines})
            self._inspect_only = True
            return
        self._inspect_only = False
        self._event_id = event_id
        view = self._build_view(event_id or "")
        self.widget.load_event(view)

    def _build_view(self, event_id: str) -> EventView:
        """从事件服务取得规则计算后的视图，包含真实的锁定状态。"""
        state = self.app.flow.require_state()
        return self.app.services.event.get_view(state, event_id)

    def _show_content_error(self, event_id: str, choice_id: str, error: ContentError) -> None:
        """把服务层拒绝显示给玩家，而不是让场景回调冒泡到主循环。"""
        lock_id = f"evt.{event_id}.lock.{choice_id}"
        if self.app.text.has(lock_id):
            text = self.app.text.get_raw(lock_id)
        elif "E_CHOICE_LOCKED" in str(error):
            text = self.app.text.get("err.choice_locked")
        else:
            text = self.app.text.get("err.unknown_id", id=event_id)
        show_hint = getattr(self.widget, "_show_lock_hint", None)
        if callable(show_hint):
            show_hint(text)
        else:
            LOG.warning("事件选择被拒绝但控件没有锁定提示接口：%s", error)
        LOG.info("事件选择被拒绝 event=%s choice=%s: %s", event_id, choice_id, error)

    def bind_input(self) -> None:
        self.bind("space", self.widget.on_space)
        self.bind("enter", self.widget.on_space)
        self.bind("e", self.widget.on_space)
        self.bind("mouse1", self.widget.on_space)
        self.bind("arrow_up", lambda: self.widget.on_move(-1))
        self.bind("w", lambda: self.widget.on_move(-1))
        self.bind("arrow_down", lambda: self.widget.on_move(1))
        self.bind("s", lambda: self.widget.on_move(1))
        for digit in (1, 2, 3):
            self.bind(str(digit), lambda d=digit: self.widget.on_digit(d))
        # 事件不能中途退出，但 Esc 必须有反应：跳过打字机 / 翻页 / 关掉结果页，
        # 到了选项阶段则提示「先选一个选项」——不能像旧版那样绑一个空 lambda。
        self.bind("escape", self.widget.on_escape)

    def _choose(self, event_id: str, choice_id: str) -> None:
        if getattr(self, "_inspect_only", False):
            return
        state = self.app.flow.require_state()
        try:
            result = self.app.services.event.choose(state, event_id, choice_id)
        except ContentError as error:
            self._show_content_error(event_id, choice_id, error)
            return
        self.widget.show_event_result(result)
        self._pending_result = result

    def _finished(self, event_id: str) -> None:
        # A page-only/inspect event has no result to commit. In particular, do not
        # manufacture choice_id="none", which would look like a real settlement.
        result = getattr(self, "_pending_result", None)
        self.app.scenes.pop()
        if getattr(self, "_inspect_only", False) or result is None:
            return
        self.app.flow.handle_event_result(result)


class DaySummarySceneAdapter(WidgetSceneBase):
    widget_cls = DaySummary
    scene_id = "DaySummary"

    def on_enter(self, **kwargs: Any) -> None:
        super().on_enter(**kwargs)
        self.widget.on_close = self.app.scenes.pop

    def apply(self, result=None, **kwargs: Any) -> None:
        state = self.app.flow.state
        day = state.day if state is not None else 1
        names = [self.app.text.get_raw(f"act.{aid}.name") for aid in (self.app.flow.activity_log_today() if hasattr(self.app.flow, "activity_log_today") else [])]
        self.widget.show_summary(result, day=day, action_names=names)

    def bind_input(self) -> None:
        self.bind("space", self.widget.confirm)
        self.bind("enter", self.widget.confirm)
        self.bind("mouse1", self.widget.confirm)
        self.bind("escape", self.widget.confirm)


class TabPanelSceneAdapter(WidgetSceneBase):
    widget_cls = TabPanel
    scene_id = "TabPanel"

    def apply(self, state=None, **kwargs: Any) -> None:
        self.widget.update_state(state if state is not None else self.app.flow.state)

    def bind_input(self) -> None:
        self.bind("tab", self._pop)
        self.bind("escape", self._pop)


class PauseMenuSceneAdapter(WidgetSceneBase):
    widget_cls = PauseMenu
    scene_id = "PauseMenu"

    def on_enter(self, **kwargs: Any) -> None:
        super().on_enter(**kwargs)
        self.widget.on_resume = self._resume

    def bind_input(self) -> None:
        self.bind("arrow_up", lambda: self.widget.move(-1))
        self.bind("w", lambda: self.widget.move(-1))
        self.bind("arrow_down", lambda: self.widget.move(1))
        self.bind("s", lambda: self.widget.move(1))
        self.bind("enter", self._confirm)
        self.bind("space", self._confirm)
        self.bind("escape", self._resume)

    def _confirm(self) -> None:
        key = self.widget.confirm()
        if key == "ui.menu.settings":
            self.app.scenes.push("SettingsMenu")
        elif key == "ui.menu.save":
            self.app.scenes.push("SaveMenu", mode="save")
        elif key == "ui.menu.load":
            self.app.scenes.push("SaveMenu", mode="load")
        elif key == "ui.menu.main_menu":
            self.app.scenes.pop()  # 先关暂停
            self.app.flow.back_to_main_menu()

    def _resume(self) -> None:
        self.app.scenes.pop()
        self.app.flow.set_paused(False)


class SettingsMenuSceneAdapter(WidgetSceneBase):
    scene_id = "SettingsMenu"

    def _make_widget(self):
        return SettingsMenu(
            self.app.ui_root, self.app.ui_transform, self.app.text,
            self.app.settings, self.app.registry,
        )

    def on_enter(self, **kwargs: Any) -> None:
        super().on_enter(**kwargs)
        self.widget.on_back = self._back

    def bind_input(self) -> None:
        self.bind("arrow_up", lambda: self.widget.move(-1))
        self.bind("w", lambda: self.widget.move(-1))
        self.bind("arrow_down", lambda: self.widget.move(1))
        self.bind("s", lambda: self.widget.move(1))
        self.bind("arrow_left", lambda: self.widget.adjust(-1))
        self.bind("a", lambda: self.widget.adjust(-1))
        self.bind("arrow_right", lambda: self.widget.adjust(1))
        self.bind("d", lambda: self.widget.adjust(1))
        self.bind("enter", self.widget.confirm)
        self.bind("escape", self.widget.cancel)

    def _back(self) -> None:
        self.app.scenes.pop()


class SaveMenuSceneAdapter(WidgetSceneBase):
    widget_cls = SaveMenu
    scene_id = "SaveMenu"

    def on_enter(self, **kwargs: Any) -> None:
        super().on_enter(**kwargs)
        self.widget.on_done = lambda ok: self._back()
        self.widget.on_loaded = self._loaded

    def apply(self, mode: str = "save", **kwargs: Any) -> None:
        self.widget.open(
            mode, self.app.saves,
            state_provider=lambda: self.app.flow.state,
        )

    def bind_input(self) -> None:
        self.bind("arrow_up", lambda: self.widget.move(-1))
        self.bind("w", lambda: self.widget.move(-1))
        self.bind("arrow_down", lambda: self.widget.move(1))
        self.bind("s", lambda: self.widget.move(1))
        self.bind("enter", self.widget.confirm)
        self.bind("space", self.widget.confirm)
        self.bind("escape", self.widget.cancel)

    def _back(self) -> None:
        self.app.scenes.pop()

    def _loaded(self, state) -> None:
        self.app.flow.state = state
        self.app.scenes.pop_all()
        self.app.scenes.change("CampusScene", spawn=state.world.location_id, state=state)


class GraduationSceneAdapter(WidgetSceneBase):
    is_overlay = False
    widget_cls = GraduationScene
    scene_id = "GraduationScene"

    def on_enter(self, **kwargs: Any) -> None:
        super().on_enter(**kwargs)
        self.widget.on_back_to_menu = self.app.flow.finish_graduation

    def apply(self, ending=None, **kwargs: Any) -> None:
        state = self.app.flow.state
        snapshot = {}
        if state is not None:
            snapshot = {
                "stats": dict(state.stats), "relationships": dict(state.relationships),
                "mood": state.mood, "energy": state.energy,
            }
        self.widget.open(ending, snapshot)

    def bind_input(self) -> None:
        self.bind("space", self.widget.on_space)
        self.bind("enter", self.widget.on_space)


__all__ = [
    "CampusSceneAdapter",
    "InteriorSceneAdapter",
    "MainMenuSceneAdapter",
    "ResultPanelSceneAdapter",
    "EventSceneAdapter",
    "DaySummarySceneAdapter",
    "TabPanelSceneAdapter",
    "PauseMenuSceneAdapter",
    "SettingsMenuSceneAdapter",
    "SaveMenuSceneAdapter",
    "GraduationSceneAdapter",
]
