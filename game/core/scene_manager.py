"""A 维护：场景管理（基础场景 change + 覆盖层 push/pop + 0.25 秒黑场淡入淡出）。

引擎无关：由 app 的 flow_tick 每帧调用 update(dt) 推进淡入淡出，便于 core 单元测试。
覆盖层存在时 input_locked 为 True，C 的 input_poll 必须忽略移动与 E 键。
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Protocol

from .event_bus import TOPIC_SCENE_CHANGED, EventBus

FADE_SECONDS = 0.25
BASE_SCENES = ("MainMenu", "CampusScene", "InteriorScene", "GraduationScene")
OVERLAY_SCENES = (
    "EventScene",
    "ResultPanel",
    "DaySummary",
    "TabPanel",
    "PauseMenu",
    "SettingsMenu",
    "SaveMenu",
)


class SceneProtocol(Protocol):
    def on_enter(self, **kwargs: Any) -> None: ...

    def on_exit(self) -> None: ...


SceneFactory = Callable[[str, Any], Any]


class SceneManager:
    def __init__(
        self,
        app: Any,
        factory: SceneFactory,
        bus: EventBus | None = None,
        logger: logging.Logger | None = None,
        fade_seconds: float = FADE_SECONDS,
    ) -> None:
        self.app = app
        self.factory = factory
        self.bus = bus
        self.log = logger or logging.getLogger("naiwa.scene")
        self.fade_seconds = max(0.0, float(fade_seconds))
        self.base_scene: Any = None
        self.base_id: str | None = None
        self.overlays: list[tuple[str, Any]] = []
        self.fade_alpha = 0.0
        self._phase = "idle"  # idle / out / in
        self._timer = 0.0
        self._pending: tuple[str, dict[str, Any]] | None = None
        self._on_ready: Callable[[], None] | None = None
        self.history: list[str] = []

    # ------------------------------------------------------------------ #
    @property
    def input_locked(self) -> bool:
        """淡入淡出期间或存在覆盖层时锁定玩法输入。"""
        return self._phase != "idle" or bool(self.overlays)

    @property
    def current_id(self) -> str | None:
        return self.base_id

    @property
    def top_overlay_id(self) -> str | None:
        return self.overlays[-1][0] if self.overlays else None

    def is_transitioning(self) -> bool:
        return self._phase != "idle"

    def blocks_input(self, owner: Any) -> bool:
        """InputRouter 的遮挡判断：这个绑定主人现在还能不能收到按键。

        覆盖层存在时，只有最上层覆盖层自己的绑定有效 —— 否则设置界面
        没绑定的键（例如 Space）会落到主菜单，在面板背后开新游戏。
        基础场景总是被遮挡；同一覆盖层的多个控件之间仍按后绑定优先。
        """
        if not self.overlays:
            return False
        return owner is not self.overlays[-1][1]

    # ------------------------------------------------------------------ #
    def start(self, scene_id: str, on_ready: Callable[[], None] | None = None,
              **kwargs: Any) -> None:
        """首个场景：无淡出，直接建立并淡入。

        on_ready 在淡入结束（画面已可操作）时回调一次；淡出被跳过时立刻回调。
        """
        self.log.info("[SCENE] start %s", scene_id)
        scene = self.factory(scene_id, kwargs)
        self.base_scene = scene
        self.base_id = scene_id
        self.history.append(scene_id)
        self._enter(scene, kwargs)
        self._on_ready = on_ready
        if self.fade_seconds > 0:
            self._phase = "in"
            self._timer = 0.0
            self.fade_alpha = 1.0
        else:
            self._phase = "idle"
            self._ready_callback()
        self._emit(scene_id, scene_id)

    def change(self, scene_id: str, on_ready: Callable[[], None] | None = None,
               **kwargs: Any) -> None:
        """基础场景切换：0.25 秒黑场淡出 → 退出旧场景 → 建立新场景 → 淡入。

        on_ready 会在新场景建立且淡入结束后回调——覆盖层（开场事件、日结算）
        必须挂在这个回调里，不能抢在淡出途中 push：那时旧场景还没退出，
        旧场景的 on_exit 会把新覆盖层的按键绑定一起清掉。
        """
        if self.base_scene is None and self._pending is None:
            # 首个场景没有可淡出的旧场景，直接建立，避免启动时白等 0.25 秒
            self.start(scene_id, on_ready=on_ready, **kwargs)
            return
        if self._pending is not None:
            # 淡出途中又来了新的切换请求：以后来的为准，避免毕业/读档被旧请求吞掉
            self.log.info("[SCENE] pending change %s replaced by %s", self._pending[0], scene_id)
            self._pending = (scene_id, dict(kwargs))
            self._on_ready = on_ready
            return
        if self.base_id == scene_id and not kwargs and self._phase == "idle":
            self.log.debug("[SCENE] change(%s) is a no-op", scene_id)
            self._on_ready = on_ready
            self._ready_callback()
            return
        self.log.info("[SCENE] change %s -> %s", self.base_id, scene_id)
        self._pending = (scene_id, dict(kwargs))
        self._on_ready = on_ready
        if self.fade_seconds <= 0:
            self._run_pending()
            return
        self._phase = "out"
        self._timer = 0.0

    def push(self, overlay_id: str, **kwargs: Any) -> None:
        if self.overlays and self.overlays[-1][0] == overlay_id:
            self.log.warning("[SCENE] push(%s) ignored, already on top", overlay_id)
            return
        self.log.info("[SCENE] push %s", overlay_id)
        overlay = self.factory(overlay_id, kwargs)
        self.overlays.append((overlay_id, overlay))
        self._enter(overlay, kwargs)

    def pop(self) -> str | None:
        if not self.overlays:
            return None
        overlay_id, overlay = self.overlays.pop()
        self.log.info("[SCENE] pop %s", overlay_id)
        self._exit(overlay)
        return overlay_id

    def pop_all(self) -> list[str]:
        popped: list[str] = []
        while self.overlays:
            top = self.pop()
            if top:
                popped.append(top)
        return popped

    def replace_overlay(self, overlay_id: str, **kwargs: Any) -> None:
        self.pop()
        self.push(overlay_id, **kwargs)

    # ------------------------------------------------------------------ #
    def update(self, dt: float) -> None:
        if self._phase == "idle":
            return
        self._timer += dt
        progress = 1.0 if self.fade_seconds <= 0 else min(1.0, self._timer / self.fade_seconds)
        if self._phase == "out":
            self.fade_alpha = progress
            if progress >= 1.0:
                self._run_pending()
        else:  # in
            self.fade_alpha = 1.0 - progress
            if progress >= 1.0:
                self.fade_alpha = 0.0
                self._phase = "idle"
                self._ready_callback()

    def _ready_callback(self) -> None:
        """执行并清空 on_ready（只会跑一次；异常不能拖垮主循环）。"""
        callback, self._on_ready = self._on_ready, None
        if callback is None:
            return
        try:
            callback()
        except Exception as exc:
            self.log.exception("[SCENE] on_ready failed: %s", exc)

    def _run_pending(self) -> None:
        if self._pending is None:
            self._phase = "idle"
            self.fade_alpha = 0.0
            return
        scene_id, kwargs = self._pending
        self._pending = None
        if self.base_scene is not None:
            self._exit(self.base_scene)
        scene = self.factory(scene_id, kwargs)
        self.base_scene = scene
        self.base_id = scene_id
        self.history.append(scene_id)
        self._enter(scene, kwargs)
        self._emit(self.history[-2] if len(self.history) > 1 else scene_id, scene_id)
        self._phase = "in" if self.fade_seconds > 0 else "idle"
        self._timer = 0.0
        self.fade_alpha = 1.0 if self.fade_seconds > 0 else 0.0
        if self.fade_seconds <= 0:
            self._ready_callback()

    def _enter(self, scene: Any, kwargs: dict[str, Any]) -> None:
        hook = getattr(scene, "on_enter", None)
        if callable(hook):
            hook(**kwargs)

    def _exit(self, scene: Any) -> None:
        hook = getattr(scene, "on_exit", None)
        if callable(hook):
            try:
                hook()
            except Exception as exc:
                self.log.exception("[SCENE] on_exit failed: %s", exc)

    def _emit(self, old: str | None, new: str) -> None:
        if self.bus is not None:
            self.bus.emit(TOPIC_SCENE_CHANGED, old=old, new=new)

    # ------------------------------------------------------------------ #
    def update_scenes(self, dt: float) -> None:
        """把 dt 转发给当前基础场景与全部覆盖层（可选钩子）。"""
        targets = [self.base_scene] + [scene for _, scene in self.overlays]
        for scene in targets:
            hook = getattr(scene, "on_update", None)
            if callable(hook):
                try:
                    hook(dt)
                except Exception as exc:
                    self.log.exception("[SCENE] on_update failed: %s", exc)
