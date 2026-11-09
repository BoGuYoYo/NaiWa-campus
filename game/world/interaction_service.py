"""任务 C7：把交互点转换为对 B / 场景服务的调用。

C 只负责映射，不做任何数值计算：
- activity -> ActivityService.can_start / preview / start
- npc      -> RelationshipService.talk
- door     -> SceneManager.change("InteriorScene", building_id=...)
- save     -> SceneManager.push("SaveMenu", mode="save")
- inspect  -> SceneManager.push("EventScene", ...)
本模块禁止出现任何属性字段（academic / stamina / social / interest / mood / energy）的读写。
"""

from __future__ import annotations

import time
from typing import Any, Callable

from game.core.results import InteractionResult, PromptView
from game.world.map_data import CAMPUS_SCENE, Interactable, MapData, MapDataError
from game.world.trigger_zone import scene_of

REPEAT_LOCK_SECONDS = 0.3  # E 键 0.3 秒内的重复按键忽略

E_UNKNOWN_ID = "E_UNKNOWN_ID"
E_ALREADY_TALKED = "E_ALREADY_TALKED"
E_LOW_ENERGY = "E_LOW_ENERGY"   # 由 B 的 RelationshipService 返回，C 只透传


class InteractionService:
    """query(state, ia_id) -> PromptView / interact(state, ia_id) -> InteractionResult。"""

    def __init__(
        self,
        map_data: MapData,
        activity_service: Any = None,
        relationship_service: Any = None,
        scene_manager: Any = None,
        event_bus: Any = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.map_data = map_data
        self._activity = activity_service
        self._relationship = relationship_service
        self._scene = scene_manager
        self._bus = event_bus
        self._clock = clock
        self._last_interact = float("-inf")

    # ---------------------------------------------------------------- 查询

    def query(self, state, interactable_id: str) -> PromptView:
        ia = self._lookup(state, interactable_id)
        if ia is None:
            return PromptView(
                interactable_id=interactable_id,
                label_text_id=f"ia.{interactable_id}.name",
                enabled=False,
                reason_code=E_UNKNOWN_ID,
                cost_preview={},
            )

        enabled = True
        reason: str | None = None
        cost: dict[str, int] = {}

        if ia.type == "activity":
            ok, error_code = self._activity.can_start(state, ia.target)
            cost = dict(self._activity.preview(state, ia.target))
            enabled = bool(ok)
            reason = None if ok else error_code
            label = f"act.{ia.target}.name"
        elif ia.type == "npc":
            if ia.target in state.talked_today:
                enabled, reason = False, E_ALREADY_TALKED
            else:
                # 能不能聊由 B 的 RelationshipService 判定；C 不读任何属性字段
                can_talk = getattr(self._relationship, "can_talk", None)
                if callable(can_talk):
                    ok, error_code = can_talk(state, ia.target)
                    enabled = bool(ok)
                    reason = None if ok else error_code
            preview = getattr(self._relationship, "preview", None)
            if callable(preview):
                cost = dict(preview(state, ia.target) or {})
            label = f"npc.{ia.target.removeprefix('npc_')}.talk"
        elif ia.type == "door":
            label = "ui.prompt.enter"
        elif ia.type == "save":
            label = "ui.prompt.save"
        elif ia.type == "inspect":
            label = f"insp.{self._inspect_short_id(ia)}.name"
        else:  # pragma: no cover - MapData 已在加载时校验 type
            raise MapDataError(f"未知交互点类型：{ia.type}")

        return PromptView(
            interactable_id=ia.id,
            label_text_id=label,
            enabled=enabled,
            reason_code=reason,
            cost_preview=cost,
        )

    def preview_for(self, state, interactable_id: str) -> PromptView:
        """与 query 等价，供 D 的提示框直接使用。"""
        return self.query(state, interactable_id)

    # ---------------------------------------------------------------- 交互

    def interact(self, state, interactable_id: str) -> InteractionResult:
        now = self._clock()
        if now - self._last_interact < REPEAT_LOCK_SECONDS:
            return InteractionResult(kind="blocked", payload=None)

        prompt = self.query(state, interactable_id)
        ia = self._lookup(state, interactable_id)
        if ia is None or not prompt.enabled:
            # enabled=False 时由 D 播放 sfx_ui_cancel 并抖动提示框，C 不调用 B
            return InteractionResult(kind="blocked", payload=prompt.reason_code)

        self._last_interact = now

        if ia.type == "activity":
            result = self._activity.start(state, ia.target)
            self._emit("activity.done", result=result)
            return InteractionResult(kind="activity", payload=result)
        if ia.type == "npc":
            result = self._relationship.talk(state, ia.target)
            self._emit("activity.done", result=result)
            return InteractionResult(kind="npc", payload=result)
        if ia.type == "door":
            self._scene.change("InteriorScene", building_id=ia.target)
            return InteractionResult(kind="door", payload=ia.target)
        if ia.type == "save":
            self._scene.push("SaveMenu", mode="save")
            return InteractionResult(kind="save", payload=None)
        if ia.type == "inspect":
            self._scene.push("EventScene", event_id=None, text_id=f"insp.{self._inspect_short_id(ia)}.body")
            return InteractionResult(kind="inspect", payload=None)
        raise MapDataError(f"未知交互点类型：{ia.type}")  # pragma: no cover

    # ---------------------------------------------------------------- 内部

    def _lookup(self, state, interactable_id: str) -> Interactable | None:
        """按当前场景查交互点；场景不匹配视为未知 ID。"""
        try:
            ia = self.map_data.interactable(interactable_id)
        except MapDataError:
            return None
        return ia if ia.scene == scene_of(state, self.map_data) else None

    @staticmethod
    def _inspect_short_id(ia: Interactable) -> str:
        return ia.target.split(".")[-1] if ia.target.startswith("inspect.") else ia.target

    def _emit(self, topic: str, **data) -> None:
        if self._bus is not None:
            self._bus.emit(topic, **data)


__all__ = ["InteractionService", "CAMPUS_SCENE", "REPEAT_LOCK_SECONDS"]
