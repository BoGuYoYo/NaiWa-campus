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

import json
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
                # 注意不能用 self._state.world.location_id 兜底——上面按 spawn
                # 刚把它写成了建筑 id（loc_dorm 之类），兜底就等于没改。
                self._state.world.location_id = self.md.outdoor_location_at(exit_x, exit_y)
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
            self.app.ui_root, self.app.ui_transform, self.app.text, self.app.registry,
            is_locked=lambda: self.app.scenes.input_locked,
        )
        self.tutorial_overlay.attach(self.tutorial)
        self.tutorial.notify("enter_campus")
        self._last_player_position = (self.player.motion.x, self.player.motion.y)
        self._tutorial_day_handler = self.app.bus.subscribe(
            TOPIC_DAY_ENDED, self._on_tutorial_day_ended
        )
        self.debug = self._build_debug_draw()
        self._bind_input()
        self._refresh_prompt(force=True)

    def teleport(self, world) -> None:
        """把角色放到指定世界坐标（换日回出生点等由 A 触发的传送）。"""
        if self.player is None:
            return
        self.player.teleport(world.x, world.y, world.facing)
        self._last_player_position = (self.player.motion.x, self.player.motion.y)
        # 传送后镜头必须立刻落位：相机有死区和平滑，不重设的话换日之后
        # 镜头会从上一帧的位置一路平移过来（玩家看到的是黑场后的长距离滑动）。
        self._apply_scene_camera()

    def _transitioning(self) -> bool:
        """黑场（场景切换的 0.25 秒）期间为 True。"""
        return bool(getattr(self.app.scenes, "is_transitioning", lambda: False)())

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

    def _debug_goto(self, scene: str, x: float, y: float, facing: str | None = None) -> None:
        """F5 传送：DebugDraw 传的是 (场景 id, x, y)。

        旧签名只收 (x, y)，第一个位置参数收到场景 id 字符串，float() 直接抛
        ValueError —— F5 按一下就报错。跨场景时先切场景，同场景直接传送。
        """
        if self._state is None:
            return
        if not scene or scene == self.scene_id:
            if self.player is not None:
                self.player.teleport(x, y, facing)
            return
        if scene == "campus":
            self.app.scenes.change(
                "CampusScene", spawn=self.md.outdoor_location_at(x, y),
                state=self._state, position=(x, y, facing or "n"),
            )
            return
        self.app.scenes.change(
            "InteriorScene", building_id=scene, state=self._state, at=(x, y),
        )

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
        if locked:
            # 模态 UI 打开时隐藏世界 HUD、交互提示与教程横幅。
            if self.hud is not None:
                self.hud.hide()
            if self.prompt is not None:
                self.prompt.hide_prompt()
            if self.tutorial_overlay is not None:
                self.tutorial_overlay.hide()
            return
        distance = math.hypot(after[0] - before[0], after[1] - before[1])
        if distance > 0.0:
            self.tutorial.notify("player_moved", distance_m=distance)
        if self._state.energy < 40:
            self.tutorial.notify("low_energy")
        self.tutorial.notify("tick", dt=dt)
        if self.tutorial_overlay is not None:
            self.tutorial_overlay.refresh()
        if self.hud is not None and not self.hud.visible:
            self.hud.show()
        self.animator.tick(dt)
        self._update_scene_camera(dt, force=False)
        self._refresh_prompt()
        self.hud.update(self._state)
        self.hud.tick(dt)
        self._check_autostep(dt)

    def _on_tutorial_day_ended(self, **_data: Any) -> None:
        if self.tutorial is not None:
            # DaySummary is pushed immediately after this bus event; defer rendering
            # until the next frame so the modal-state guard can hide the banner.
            self.tutorial.notify("day_ended")

    # ------------------------------------------------------------------ 子类实现
    scene_id = "campus"

    def _texture(self, asset_id: str):
        """缺资源时返回 None（而不是品红占位图），让场景退回白模。"""
        registry = self.app.registry
        if asset_id not in registry or not registry.file_exists(asset_id):
            LOG.warning("[WORLD] 贴图缺失，跳过：%s", asset_id)
            return None
        try:
            texture = registry.load_texture(asset_id)
        except Exception as exc:  # pragma: no cover
            LOG.warning("[WORLD] 贴图加载失败 %s: %s", asset_id, exc)
            return None
        from panda3d.core import SamplerState

        # 平铺贴图在斜视角下会缩小很多（墙面相对镜头前倾 40°）：mag 用最近邻
        # 保持像素硬边，min 用最近邻 mipmap 避免远处闪烁。
        texture.set_magfilter(SamplerState.FT_nearest)
        texture.set_minfilter(SamplerState.FT_nearest_mipmap_linear)
        return texture

    def build_scene(self, parent):
        raise NotImplementedError

    def _place_for(self, spawn: str) -> str:
        return spawn

    def _apply_scene_camera(self) -> None:
        raise NotImplementedError

    def _update_scene_camera(self, dt: float, force: bool) -> None:
        raise NotImplementedError

    def _check_autostep(self, dt: float = 0.0) -> None:
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
        if self._transitioning():
            return
        ia_id = self.tracker.active_id if self.tracker else None
        if not ia_id:
            return
        self.tutorial.notify("key_space")
        result = self.interaction.interact(self._state, ia_id)
        self.log.info("[WORLD] E %s -> %s", ia_id, result.kind)
        if result.kind in ("activity", "npc"):
            # NPC 交谈和活动一样占用一个时段、产生数值反馈；必须走同一条
            # 结果面板/流程链路，否则教程的「按 E 互动」不会结束，交谈结果
            # 也不会进入日结算的行动摘要。
            self.app.flow.handle_activity_result(result.payload)
            self.app.scenes.push("ResultPanel", result=result.payload)
            self.tutorial.notify("activity_done")
            if self.prompt is not None:
                self.prompt.hide_prompt()
        elif result.kind == "blocked":
            self.app.audio.play_sfx("sfx_ui_cancel")

    def _on_tab(self) -> None:
        if self._state is None or self._state.phase != "campus":
            return
        if self.app.scenes.overlays:
            return
        # 黑场（场景切换的 0.25 秒）期间不能开面板：此时旧场景还在台上，
        # 覆盖层会挂到即将被销毁的场景上，关不掉也点不动（Tab 卡死的成因）。
        if self._transitioning():
            return
        self.tutorial.notify("tab_opened")
        self.app.scenes.push("TabPanel", state=self._state)

    def _on_escape(self) -> None:
        if self.app.scenes.overlays:
            return
        if self._transitioning():
            # 回主菜单的黑场里按 Esc 会把暂停菜单盖到主菜单上；直接忽略。
            return
        if self._state is None or self._state.phase not in ("campus",):
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
        try:
            self.prompt.show_prompt(view)
        except Exception as exc:  # 提示框画不出来不能让整帧 on_update 中断（E 会跟着一起死）
            self.log.exception("[WORLD] prompt render failed for %s: %s", ia_id, exc)
            self.prompt.hide_prompt()
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

    BUILDING_SIDE_ART = {
        "loc_dorm": "campus_texture_dorm_side",
        "loc_classroom": "campus_texture_teaching_side",
        "loc_library": "campus_texture_library_side",
        "loc_clubroom": "campus_texture_club_side",
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

    def _building_side_art(self, building_id: str):
        asset_id = self.BUILDING_SIDE_ART.get(building_id)
        if asset_id is None:
            return None
        texture = self._texture(asset_id)
        if texture is None:
            return None
        from panda3d.core import SamplerState

        texture.set_minfilter(SamplerState.FT_linear_mipmap_linear)
        texture.set_magfilter(SamplerState.FT_linear)
        return texture

    def build_scene(self, parent):
        from game.world.campus_scene import CampusScene

        layout_path = config.resource_root() / "content" / "world" / "building_visuals.json"
        building_visuals = (
            json.loads(layout_path.read_text(encoding="utf-8"))["buildings"]
            if layout_path.is_file() else {}
        )
        return CampusScene(
            self.md, parent,
            dev=bool(self.app.options.dev),
            ground_texture=self._texture("campus_texture_ground"),
            prop_art=self._prop_art,
            building_art=self._building_art,
            building_side_art=self._building_side_art,
            building_visuals=building_visuals,
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
    scene_id: str = "campus"  # 由 on_enter 覆盖

    #: npc_marks 里的显示名 -> 角色立绘资产名（旧名保留，兼容老存档/老地图）
    NPC_ART = {
        "符闹吃": "sumo", "苏墨": "sumo",
        "李振兴": "chenlang", "陈朗": "chenlang",
        "奈珑": "xiaoyou", "小柚": "xiaoyou",
    }

    #: 建筑 id -> 材质素材名（assets/campus/textures/interior/<名>_floor.png）
    MATERIAL_KEY = {
        "loc_dorm": "dorm",
        "loc_classroom": "teaching",
        "loc_library": "library",
        "loc_clubroom": "club",
        "loc_canteen": "canteen",
    }

    def _material(self, building_id: str, kind: str):
        """取该建筑的地板/墙面贴图、平铺尺寸（manifest.tile_m）与平均色。"""
        short = self.MATERIAL_KEY.get(building_id, building_id.removeprefix("loc_"))
        asset_id = f"interior_{kind}_{short}"
        texture = self._texture(asset_id)
        raw: dict[str, Any] = {}
        try:
            raw = dict(getattr(self.app.registry.get(asset_id), "raw", None) or {})
        except Exception:  # pragma: no cover - registry 没有 get 时用默认平铺
            raw = {}
        try:
            tile = float(raw.get("tile_m")) if raw.get("tile_m") else None
        except (TypeError, ValueError):
            tile = None
        average = raw.get("average_rgb")
        if texture is None:
            return None, None, None
        return texture, tile, average

    @staticmethod
    def _furniture_color(floor_average, wall_average) -> tuple[float, float, float, float] | None:
        """家具用材质的同色系暗调：不另做贴图也不会和墙地打架。

        地面太深时（图书馆的深胡桃地板亮度只有 0.10，直接乘系数会和地面糊成一片）
        改用墙面材质的暗调，保证家具轮廓看得见。
        """
        def _rgb(values):
            try:
                return tuple(float(value) for value in values[:3])
            except (TypeError, ValueError, IndexError):
                return None

        floor = _rgb(floor_average) if floor_average else None
        wall = _rgb(wall_average) if wall_average else None
        if floor is None:
            return None
        luminance = 0.299 * floor[0] + 0.587 * floor[1] + 0.114 * floor[2]
        base = floor if luminance >= 0.3 or wall is None else wall
        scale = 0.62
        return tuple(min(1.0, max(0.05, channel * scale)) for channel in base) + (1.0,)

    def on_enter(self, building_id: str | None = None, state: GameState | None = None,
                 at: tuple[float, float] | None = None, **kwargs: Any) -> None:
        self.scene_id = building_id or kwargs.get("scene") or "loc_dorm"
        super().on_enter(spawn=None, state=state)
        # 室内：location_id 必须切到建筑 id，交互点查询才会命中室内那一批
        if self._state is not None:
            self._state.world.location_id = self.scene_id
        entry_x, entry_y, facing = self.md.interior_entry(self.scene_id)
        ox, oy = self.md.interior(self.scene_id).origin
        if at is not None and len(at) >= 2:
            # --dev F5 传送到室内交互点：落点由调用方给（世界坐标）
            entry_x, entry_y = float(at[0]) - ox, float(at[1]) - oy
        self.player.teleport(ox + entry_x, oy + entry_y, facing)
        self.rig.set_interior((ox + self.md.interior(self.scene_id).center[0],
                               oy + self.md.interior(self.scene_id).center[1]))
        self.app.pipeline.align_camera(*self.rig.target)
        self._place_npc_sprites()

    def _place_npc_sprites(self) -> None:
        """在 npc_marks 的位置摆上 NPC 立牌。

        以前室内只画一个蓝圈表示"有人站这儿"，玩家看不到 NPC 长什么样；
        接入角色立绘后把 `char_npc_<short>_idle` 贴成正面朝相机的一张卡。
        """
        if self.scene is None:
            return
        from panda3d.core import TextureStage

        interior = self.md.interior(self.scene_id)
        ox, oy = interior.origin
        for mark in interior.npc_marks:
            short = self.NPC_ART.get(mark.name)
            if short is None:
                continue
            try:
                sheet = self.app.registry.load_sprite(f"char_npc_{short}_idle")
            except Exception as exc:  # 缺资源时保持原来的站位圈，不影响进房间
                LOG.warning("[WORLD] NPC 立绘加载失败 %s: %s", short, exc)
                continue
            if sheet is None:
                continue
            card = self.app.pipeline.make_character_card(self.scene.root, f"npc_{short}")
            card.set_texture(sheet.texture, 1)
            stage = TextureStage.getDefault()
            u0, v0, u1, v1 = sheet.frame_uv("s", 0)
            card.set_tex_offset(stage, u0, v0)
            card.set_tex_scale(stage, u1 - u0, v1 - v0)
            card.set_pos(ox + mark.x, oy + mark.y, 0.0)
            card.set_h(0.0)

    def build_scene(self, parent):
        from game.world.interior_scene import InteriorScene

        floor, floor_tile, floor_average = self._material(self.scene_id, "floor")
        wall, wall_tile, wall_average = self._material(self.scene_id, "wall")
        kwargs: dict[str, Any] = {}
        if floor_tile:
            kwargs["floor_tile_m"] = floor_tile
        if wall_tile:
            kwargs["wall_tile_m"] = wall_tile
        furniture_color = self._furniture_color(floor_average, wall_average)
        if furniture_color is not None:
            kwargs["furniture_color"] = furniture_color
        return InteriorScene(
            self.md, self.scene_id, parent, dev=bool(self.app.options.dev),
            floor_texture=floor, wall_texture=wall,
            furniture_art=self._furniture_art(), **kwargs,
        )

    def _furniture_art(self) -> dict[str, tuple[Any, float]]:
        """{furniture_id: (贴图, 高度米)}：给到的家具立成正面卡，没给的仍画盒子。

        高度 = 画布高 / 24（贴图比例已按占地宽 × 实物高做好，`make_prop_card`
        会按比例把卡片还原成占地宽度）。
        """
        short = self.MATERIAL_KEY.get(self.scene_id, self.scene_id.removeprefix("loc_"))
        out: dict[str, tuple[Any, float]] = {}
        for furn in self.md.interior(self.scene_id).furniture:
            asset_id = f"furn_{short}_{furn.id.removeprefix('furn_')}"
            texture = self._texture(asset_id)
            if texture is None:
                continue
            out[furn.id] = (texture, texture.get_y_size() / 24.0)
        return out

    def _place_for(self, spawn: str) -> str:
        return spawn

    def _apply_scene_camera(self) -> None:
        pass

    def _update_scene_camera(self, dt: float, force: bool) -> None:
        pass

    def _check_autostep(self, dt: float = 0.0) -> None:
        """踩到入口地垫 → 回到门外 1 米处（1 秒冷却由 C 的 update_mat 负责）。"""
        if self.scene is None or self._state is None:
            return
        motion = self.player.motion
        # 冷却必须用真实帧间隔：以前固定传 1/60，30fps 时冷却实际 2 秒、
        # 120fps 时只有 0.5 秒（帧率越高越容易反复进出）。
        if not self.scene.update_mat(motion.x, motion.y, dt if dt > 0.0 else 1.0 / 60.0):
            return
        exit_x, exit_y, facing = self.scene.exit_world()
        building_id = self.scene_id
        state = self._state
        LOG.info("[WORLD] 离开 %s -> (%.1f, %.1f) %s", building_id, exit_x, exit_y, facing)
        state.world.location_id = self.md.outdoor_location_at(exit_x, exit_y)
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

    # ---------------------------------------------------------------- 通用工具
    def _transitioning(self) -> bool:
        """黑场期间禁止"推进流程"的按键（避免双触发与盖层）。"""
        return bool(getattr(self.app.scenes, "is_transitioning", lambda: False)())

    def _hide_underlay(self) -> None:
        """打开子面板时隐藏下面那层控件，避免两套文字叠在同一张 480×270 画布上。"""
        overlays = [
            scene for _sid, scene in getattr(self.app.scenes, "overlays", ()) if scene is not self
        ]
        underlay = overlays[-1] if overlays else getattr(self.app.scenes, "base_scene", None)
        self._underlay_widget = getattr(underlay, "widget", None)
        if self._underlay_widget is not None:
            self._underlay_widget.hide()

    def _restore_underlay(self) -> None:
        """子面板关闭时把下层控件显回来：否则从暂停菜单存/读档返回后
        暂停菜单是"看不见但仍占着场景栈"，画面像卡死。"""
        widget, self._underlay_widget = getattr(self, "_underlay_widget", None), None
        if widget is not None:
            widget.show()

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
        self.bind("enter", self._confirm)
        self.bind("space", self._confirm)
        self.bind("escape", self.app.quit_game)

    def _confirm(self) -> None:
        # 黑场期间主菜单还在台上：连按会重复触发"新游戏/继续"（第二次直接
        # 把刚建好的存档状态又读一遍，或者叠两个校园场景）。
        if self._transitioning():
            return
        self.widget.confirm()

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
        # 文本速度来自 settings.text_speed：每个事件场景打开时同步一次，
        # 玩家在设置里改完立刻对下一段对话生效。
        self._apply_text_speed()
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
        # load_event/show_page 会重置打字机进度，但速度是要保留的
        self._apply_text_speed()

    def _apply_text_speed(self) -> None:
        hook = getattr(self.widget, "set_text_speed", None)
        if callable(hook):
            hook(getattr(self.app.settings, "text_speed", "normal"))

    def _build_view(self, event_id: str) -> EventView:
        """从规则服务取选择状态；分页默认由 TextDB 的实际正文页唯一决定。"""
        state = self.app.flow.require_state()
        service = self.app.services.event
        view = service.get_view(state, event_id)
        db = getattr(service, "db", None)
        event_spec = db.event(event_id) if db is not None else None
        if event_spec and event_spec.get("pages_source") == "rules":
            return view

        # Localized dialogue content owns the rendered pagination by default.
        # Rules may opt in explicitly when a page sequence is intentionally curated.
        dialogue_keys = getattr(self.app.text, "dialogues", {})
        prefix = f"evt.{event_id}.body."
        pages = [key for key in dialogue_keys if key.startswith(prefix)]
        pages.sort(key=lambda key: int(key.rsplit(".", 1)[-1]))
        if pages:
            view.page_text_ids = pages
        else:
            # 文案缺失（改名、拼错 id）时必须退回规则页，不能把正文清空：
            # 空列表会让对话框只剩一条翻页提示 —— 正文等于被截断掉。
            LOG.warning("[EVENT] %s 没有 evt.*.body.* 文案，退回规则页 %s",
                        event_id, view.page_text_ids)
        return view

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
        self.bind("mouse1", self.widget.on_click)
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
        self.widget.on_close = self._close

    def _close(self) -> None:
        self.app.scenes.pop()
        # 学期事件不能在日结算还没关时压上来；让 Flow 在面板关闭后
        # 再推 EventScene（或继续下一天）。
        handler = getattr(self.app.flow, "close_day_summary", None)
        if callable(handler):
            handler()

    def _action_name(self, action_id: str) -> str:
        if action_id.startswith("talk."):
            short = action_id.split(".", 1)[1].removeprefix("npc_")
            npc_name = self.app.text.get(f"npc.{short}.name")
            return self.app.text.get("ui.day_summary.talk", npc_name=npc_name)
        return self.app.text.get_raw(f"act.{action_id}.name")

    def apply(self, result=None, **kwargs: Any) -> None:
        state = self.app.flow.state
        # 天数必须由 DayEndResult.new_day_index 反推：finish_day() 里 day_index
        # 已经 +1，而 state.day 是「每学期 2 天」的取模值，拿它减 1 永远是 1
        # ——旧版标题因此一直显示"第 1 天结束"。
        new_index = getattr(result, "new_day_index", None)
        if new_index is None and state is not None:
            new_index = state.day_index
        ended_index = max(0, int(new_index) - 1) if new_index is not None else 0
        day = ended_index % config.DAYS_PER_SEMESTER + 1
        activities = (self.app.flow.activity_log_today()
                      if hasattr(self.app.flow, "activity_log_today") else [])
        names = [self._action_name(aid) for aid in activities]
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
        if key == "ui.menu.resume":
            # 「继续」以前没有任何分支：PauseMenu.confirm() 已经把控件 hide 掉，
            # 覆盖层却还留在栈上，输入被锁 —— 表现得就是"菜单不见了但人动不了"。
            self._resume()
        elif key == "ui.menu.settings":
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

    def on_enter(self, **kwargs: Any) -> None:
        # Settings is a pushed overlay for both the main menu and pause menu.
        # Hide the screen underneath while it is open, otherwise both sets of
        # labels occupy the same 480x270 canvas and appear on top of each other.
        self._hide_underlay()
        super().on_enter(**kwargs)
        self.widget.on_back = self._back

    def on_exit(self) -> None:
        super().on_exit()
        # PauseMenu.confirm hides its widget before dispatching any menu action.
        # Restore the underlying menu after settings closes, including that case.
        self._restore_underlay()
        self._apply_audio_settings()

    def _apply_audio_settings(self) -> None:
        """音量/文本速度要立刻生效：AudioManager.apply_settings() 之前没人调用，
        只有换曲时才顺手应用，玩家调小音量要等下一首才听得出变化。"""
        audio = getattr(self.app, "audio", None)
        apply = getattr(audio, "apply_settings", None)
        if callable(apply):
            try:
                apply()
            except Exception as exc:  # pragma: no cover - 音频设备缺失时忽略
                LOG.warning("[SETTINGS] apply audio settings failed: %s", exc)

    def _make_widget(self):
        return SettingsMenu(
            self.app.ui_root, self.app.ui_transform, self.app.text,
            self.app.settings, self.app.registry,
        )

    def bind_input(self) -> None:
        self.bind("arrow_up", lambda: self.widget.move(-1))
        self.bind("w", lambda: self.widget.move(-1))
        self.bind("arrow_down", lambda: self.widget.move(1))
        self.bind("s", lambda: self.widget.move(1))
        self.bind("arrow_left", lambda: self._adjust(-1))
        self.bind("a", lambda: self._adjust(-1))
        self.bind("arrow_right", lambda: self._adjust(1))
        self.bind("d", lambda: self._adjust(1))
        self.bind("enter", self.widget.confirm)
        self.bind("space", self.widget.confirm)
        self.bind("escape", self.widget.cancel)

    def _adjust(self, direction: int) -> None:
        """A/D：调整后立刻应用音量，不等换曲。"""
        self.widget.adjust(direction)
        self._apply_audio_settings()

    def _back(self) -> None:
        self.app.scenes.pop()


class SaveMenuSceneAdapter(WidgetSceneBase):
    widget_cls = SaveMenu
    scene_id = "SaveMenu"

    def on_enter(self, **kwargs: Any) -> None:
        # 从暂停菜单进来时下面那层是暂停菜单：它在 confirm() 里已经 hide 过，
        # 存档/读档界面退出后必须显回来，否则返回时画面像卡死。
        self._hide_underlay()
        super().on_enter(**kwargs)
        self.widget.on_done = lambda ok: self._back()
        self.widget.on_loaded = self._loaded

    def on_exit(self) -> None:
        super().on_exit()
        self._restore_underlay()

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
        """读档统一走 GameFlow.adopt_loaded_state。

        以前这里直接改 flow.state 再 change("CampusScene")，绕过了读档后的
        全部修复：室内存档的人卡在墙里、paused 仍是 True（游玩时长不再累计）、
        上一局的 today_activities 还在、待处理的学期事件被丢掉。
        """
        self.app.scenes.pop_all()
        self.app.flow.adopt_loaded_state(state)


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
