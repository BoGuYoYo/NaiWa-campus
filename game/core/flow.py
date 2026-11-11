"""A 维护：GameFlow —— 日结算、自动存档与场景串联（主流程状态机的唯一实现）。

约定：B/C/D 只调用本类暴露的方法与事件总线，不自行推进 day_index 或切换基础场景。
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass, field
from typing import Any

from .. import config
from .asset_registry import AssetRegistry
from .event_bus import (
    TOPIC_ACTIVITY_DONE,
    TOPIC_DAY_ENDED,
    TOPIC_DAY_STARTED,
    TOPIC_EVENT_FINISHED,
    TOPIC_EVENT_STARTED,
    TOPIC_GAME_GRADUATED,
    TOPIC_SAVE_WRITTEN,
    EventBus,
)
from .results import ActivityResult, DayEndResult, EndingResult, EventResult
from .scene_manager import SceneManager
from .state import DEFAULT_SPAWN_LOCATION, GameState, WorldPos, new_state

LOG = logging.getLogger("naiwa.flow")

#: B 的「日常事件」前缀。这类事件在规则层就已立即结算（B_delivery 第 3 节第 5 条），
#: 不进 EventScene —— 否则 A 会把 phase 置成 event，B 的 end_day 阶段守卫会拒绝结算，
#: 当天就再也过不去了（第四周整合时踩到的锁死问题）。
IMMEDIATE_EVENT_PREFIX = "daily_"


def is_immediate_event(event_id: str | None) -> bool:
    return bool(event_id) and event_id.startswith(IMMEDIATE_EVENT_PREFIX)


# --------------------------------------------------------------------------- #
# 独立运行替身服务：仅当 B 的 game.systems.* 尚未合入时启用，数值不代表正式平衡。
# --------------------------------------------------------------------------- #
FAKE_ACTIVITY_TABLE: dict[str, dict[str, Any]] = {
    "attend_class": {"energy": 12, "mood": -4, "stats": {"academic": 6}},
    "library_study": {"energy": 10, "mood": -3, "stats": {"academic": 5, "interest": 2}},
    "play_games": {"energy": 6, "mood": 8, "stats": {"interest": 5}},
    "create_work": {"energy": 9, "mood": 3, "stats": {"interest": 6, "academic": 2}},
    "join_club": {"energy": 8, "mood": 5, "stats": {"social": 6, "interest": 3}},
    "exercise": {"energy": 10, "mood": 4, "stats": {"stamina": 4, "social": 1}},
    "eat_canteen": {"energy": -18, "mood": 5, "stats": {}},
    "rest_dorm": {"energy": -25, "mood": 6, "stats": {}},
    "campus_walk": {"energy": 3, "mood": 3, "stats": {"social": 1}},
}
FAKE_DAILY_LIMIT = {"eat_canteen": 2}


class FallbackActivityService:
    """standalone 替身：只保证流程能跑通，数值与 B 正式表无关。"""

    def __init__(self, state_ref: GameState | None = None) -> None:
        self.state = state_ref

    def can_start(self, state: GameState, activity_id: str) -> tuple[bool, str | None]:
        if activity_id not in FAKE_ACTIVITY_TABLE:
            return False, "E_UNKNOWN_ID"
        if state.phase != "campus":
            return False, "E_WRONG_PHASE"
        if state.day_finished:
            return False, "E_NO_SLOT"
        limit = FAKE_DAILY_LIMIT.get(activity_id)
        if limit is not None and state.today_counts.get(activity_id, 0) >= limit:
            return False, "E_DAILY_LIMIT"
        cost = FAKE_ACTIVITY_TABLE[activity_id]["energy"]
        if cost > 0 and state.energy < cost:
            return False, "E_LOW_ENERGY"
        return True, None

    def preview(self, state: GameState, activity_id: str) -> dict[str, int]:
        data = FAKE_ACTIVITY_TABLE.get(activity_id)
        if not data:
            return {}
        deltas = dict(data["stats"])
        if data["energy"]:
            deltas["energy"] = -data["energy"]
        if data["mood"]:
            deltas["mood"] = data["mood"]
        return deltas

    def start(self, state: GameState, activity_id: str) -> ActivityResult:
        ok, error = self.can_start(state, activity_id)
        if not ok:
            return ActivityResult(ok=False, activity_id=activity_id, error_code=error)
        data = FAKE_ACTIVITY_TABLE[activity_id]
        deltas: dict[str, int] = {}
        state.energy = max(0, min(state.max_energy(), state.energy - data["energy"]))
        deltas["energy"] = -data["energy"]
        for key, value in data["stats"].items():
            state.stats[key] = max(0, min(100, state.stats.get(key, 0) + value))
            deltas[key] = value
        if data["mood"]:
            state.mood = max(0, min(100, state.mood + data["mood"]))
            deltas["mood"] = data["mood"]
        state.action_slot = min(config.ACTIONS_PER_DAY, state.action_slot + 1)
        state.today_counts[activity_id] = state.today_counts.get(activity_id, 0) + 1
        state.counters[f"{activity_id}_count"] = state.counters.get(f"{activity_id}_count", 0) + 1
        return ActivityResult(
            ok=True,
            activity_id=activity_id,
            error_code=None,
            deltas=deltas,
            added_flags=[],
            text_ids=[],
            triggered_event_id=None,
            day_finished=state.day_finished,
        )


class FallbackCalendarService:
    """standalone 替身：日结算只保证流程闭环，数值不代表正式平衡。"""

    def end_day(self, state: GameState) -> DayEndResult:
        state.action_slot = 0
        state.today_counts.clear()
        state.talked_today.clear()
        previous_energy = state.energy
        state.energy = state.max_energy()
        state.day_index += 1
        semester_event = None
        graduated = False
        if state.day_index >= config.TOTAL_DAYS:
            state.day_index = config.TOTAL_DAYS - 1
            graduated = True
            semester_event = f"sem_{config.TOTAL_DAYS // config.DAYS_PER_SEMESTER}_placeholder"
        elif state.day == 1:
            # 刚结束的是某学期第 2 天：触发该学期关键事件
            semester_event = f"sem_{state.day_index // config.DAYS_PER_SEMESTER}_placeholder"
        return DayEndResult(
            deltas={"energy": state.energy - previous_energy},
            new_day_index=state.day_index,
            semester_event_id=semester_event,
            graduated=graduated,
        )


class FallbackEndingService:
    def evaluate(self, state: GameState) -> EndingResult:
        ranked = sorted(state.stats.items(), key=lambda kv: kv[1], reverse=True)
        mapping = {
            "academic": "ending_academic",
            "social": "ending_club_leader",
            "interest": "ending_creator",
            "stamina": "ending_vibrant",
        }
        best_key, best_value = ranked[0]
        if best_value < 30:
            return EndingResult(ending_id="ending_balanced", matched=["balance"], highlights=[])
        return EndingResult(ending_id=mapping.get(best_key, "ending_balanced"),
                            matched=[f"stat:{best_key}"], highlights=[])


class FallbackEventService:
    def get_view(self, state: GameState, event_id: str):
        from .results import ChoiceView, EventView

        return EventView(
            event_id=event_id,
            kind="placeholder",
            speaker=None,
            page_text_ids=[f"evt.{event_id}.body.1"],
            choices=[ChoiceView(choice_id="ok", text_id="ui.continue")],
        )

    def choose(self, state: GameState, event_id: str, choice_id: str) -> EventResult:
        return EventResult(event_id=event_id, choice_id=choice_id)


class FallbackRelationshipService:
    """B 未合入时的交谈替身：只保证"能聊、有反馈、占一次行动"。

    规则与数值都来自 A 的替身表，不代表正式平衡；正式版由 B 覆盖。
    """

    NPC_TALK_ENERGY = 5
    NPC_TALK_SOCIAL = 2

    def can_talk(self, state: GameState, npc_id: str) -> tuple[bool, str | None]:
        if npc_id in state.talked_today:
            return False, "E_ALREADY_TALKED"
        if state.energy < self.NPC_TALK_ENERGY:
            return False, "E_LOW_ENERGY"
        if state.day_finished:
            return False, "E_NO_SLOT"
        return True, None

    def preview(self, state: GameState, npc_id: str) -> dict[str, int]:
        return {"energy": -self.NPC_TALK_ENERGY, "social": self.NPC_TALK_SOCIAL}

    def talk(self, state: GameState, npc_id: str) -> ActivityResult:
        ok, code = self.can_talk(state, npc_id)
        if not ok:
            return ActivityResult(ok=False, activity_id=f"talk.{npc_id}", error_code=code)
        state.energy = max(0, state.energy - self.NPC_TALK_ENERGY)
        state.stats["social"] = min(100, state.stats.get("social", 0) + self.NPC_TALK_SOCIAL)
        state.talked_today.add(npc_id)
        state.relationships[npc_id] = min(100, state.relationships.get(npc_id, 0) + 1)
        state.action_slot = min(config.ACTIONS_PER_DAY, state.action_slot + 1)
        short = npc_id.replace("npc_", "")
        return ActivityResult(
            ok=True,
            activity_id=f"talk.{npc_id}",
            deltas={"energy": -self.NPC_TALK_ENERGY, "social": self.NPC_TALK_SOCIAL},
            text_ids=[f"npc.{short}.greet.1"],
            day_finished=state.day_finished,
        )


# --------------------------------------------------------------------------- #
@dataclass
class Services:
    activity: Any = None
    calendar: Any = None
    event: Any = None
    ending: Any = None
    relationship: Any = None
    interaction: Any = None
    origins: dict[str, str] = field(default_factory=dict)


def resolve_services(log: logging.Logger | None = None) -> Services:
    """按约定导入 B/C 的服务；缺失时使用替身，并在日志中明确标注（便于整合期定位）。"""
    logger = log or LOG
    services = Services()
    plan = {
        "activity": ("game.systems.activity_service", "ActivityService", FallbackActivityService),
        "calendar": ("game.systems.calendar_service", "CalendarService", FallbackCalendarService),
        "event": ("game.systems.event_service", "EventService", FallbackEventService),
        "ending": ("game.systems.ending_service", "EndingService", FallbackEndingService),
        "relationship": ("game.systems.relationship_service", "RelationshipService", FallbackRelationshipService),
        "interaction": ("game.world.interaction_service", "InteractionService", None),
    }
    for attr, (module_name, class_name, fallback) in plan.items():
        try:
            module = importlib.import_module(module_name)
            cls = getattr(module, class_name)
            instance = cls() if not _needs_app(cls) else None
            setattr(services, attr, instance if instance is not None else cls)
            services.origins[attr] = "real"
        except (ImportError, AttributeError) as exc:
            setattr(services, attr, fallback() if fallback is not None else None)
            services.origins[attr] = "fallback" if fallback is not None else "missing"
            logger.debug("[FLOW] %s -> %s (%s)", attr, services.origins[attr], exc)
    logger.info("[FLOW] services: %s", services.origins)
    return services


def _needs_app(cls: Any) -> bool:
    try:
        import inspect

        params = inspect.signature(cls.__init__).parameters
    except (TypeError, ValueError):
        return False
    return len([p for p in params.values() if p.name != "self" and p.default is p.empty]) > 0


# --------------------------------------------------------------------------- #
class GameFlow:
    def __init__(
        self,
        app: Any,
        scenes: SceneManager,
        saves: Any,
        bus: EventBus,
        services: Services | None = None,
        registry: AssetRegistry | None = None,
    ) -> None:
        self.app = app
        self.scenes = scenes
        self.saves = saves
        self.bus = bus
        self.services = services or resolve_services()
        self.registry = registry
        self.state: GameState | None = None
        self.paused = False
        self.story_opening_id = "story_opening"
        self.last_activity_result: ActivityResult | None = None
        self.today_activities: list[str] = []   # 当天已完成的行动（日结算面板用）
        self._day_start_emitted_for: int | None = None
        self._pending_day_start = False
        self._pending_graduation = False

    # ------------------------------------------------------------------ #
    # 新游戏 / 读档
    # ------------------------------------------------------------------ #
    def new_game(self, seed: int | None = None, skip_intro: bool = False) -> GameState:
        actual_seed = int(seed) if seed is not None else _random_seed()
        state = new_state(actual_seed)
        self.state = state
        self.paused = False
        LOG.info("[FLOW] new game seed=%d skip_intro=%s", actual_seed, skip_intro)
        self.bus.emit(TOPIC_DAY_STARTED, state=state, day_index=state.day_index)
        self._day_start_emitted_for = state.day_index
        if skip_intro:
            self.enter_campus()
        else:
            # 开场事件必须等校园场景真正建立、淡入结束后再 push：
            # 淡出途中 push 的话，主菜单的 on_exit 会把对话框的按键绑定清掉
            # （对话框看得见、按什么都没反应，Esc 也失效）。
            self.scenes.change(
                "CampusScene",
                spawn="loc_gate",
                state=state,
                on_ready=lambda: self._open_story_opening(state),
            )
        return state

    def _open_story_opening(self, state: GameState) -> None:
        """校园场景就绪后弹出开场剧情（只在这次新游戏仍然是当前状态时执行）。"""
        if self.state is not state:
            return
        state.phase = "event"
        state.pending_event_id = self.story_opening_id
        self.bus.emit(TOPIC_EVENT_STARTED, event_id=self.story_opening_id)
        self.scenes.push("EventScene", event_id=self.story_opening_id, story=True)

    def load_game(self, slot: str, collision_check=None) -> GameState:
        state = self.saves.load(slot, collision_check=collision_check)
        self.state = state
        self.paused = False
        state.phase = "campus"
        self._restore_outdoor_after_indoor_save(state)
        self.enter_campus(spawn=state.world.location_id, keep_position=True)
        LOG.info("[FLOW] loaded %s day=%d slot=%d", slot, state.day_index, state.action_slot)
        return state

    def _restore_outdoor_after_indoor_save(self, state: GameState) -> None:
        """存档是在室内存的：读档后必须落回门外，并把地点改成室外区域。

        存档里的坐标是室内世界坐标（200+），location_id 是建筑 id。直接拿去建
        校园场景会让玩家站在房间坐标上、scene_of() 判成室内，户外交互点全部
        显示「内容缺失」。
        """
        md = getattr(self.app, "map_data", None)
        if md is None or not md.has_interior(state.world.location_id):
            return
        building_id = state.world.location_id
        exit_x, exit_y, facing = md.exit_point(building_id)
        state.world.x = exit_x
        state.world.y = exit_y
        state.world.facing = facing
        state.world.location_id = md.outdoor_location_at(exit_x, exit_y)
        LOG.info("[FLOW] load from indoor %s -> outdoor %s (%.2f, %.2f)",
                 building_id, state.world.location_id, exit_x, exit_y)

    def require_state(self) -> GameState:
        if self.state is None:
            raise RuntimeError("GameFlow.state is None: 先调用 new_game() 或 load_game()")
        return self.state

    # ------------------------------------------------------------------ #
    # 场景串联
    # ------------------------------------------------------------------ #
    def enter_campus(self, spawn: str | None = None, keep_position: bool = False) -> None:
        state = self.require_state()
        if not keep_position:
            state.world = WorldPos(location_id=spawn or DEFAULT_SPAWN_LOCATION, x=40.0, y=5.0,
                                   facing="n")
        state.phase = "campus"
        self.scenes.change("CampusScene", spawn=state.world.location_id, state=state)

    def teleport_to_spawn(self) -> None:
        state = self.require_state()
        state.world = WorldPos(location_id=DEFAULT_SPAWN_LOCATION, x=40.0, y=5.0, facing="n")
        campus = self.scenes.base_scene
        hook = getattr(campus, "teleport", None)
        if callable(hook):
            hook(state.world)

    # ------------------------------------------------------------------ #
    # 活动结果
    # ------------------------------------------------------------------ #
    def handle_activity_result(self, result: ActivityResult) -> None:
        """活动结束（C 调用）：只广播与记账，流程推进交给 ResultPanel 关闭时。"""
        state = self.require_state()
        self.last_activity_result = result
        self.bus.emit(TOPIC_ACTIVITY_DONE, result=result)
        if result.ok and result.activity_id:
            self.today_activities.append(result.activity_id)
        LOG.info("[FLOW] activity %s ok=%s deltas=%s slot=%d",
                 result.activity_id, result.ok, result.deltas, state.action_slot)
        if result.ok and result.triggered_event_id:
            if is_immediate_event(result.triggered_event_id):
                # B 的日常事件是"立即结算"，不进 EventScene（见 B_delivery 第 3 节第 5 条）。
                # 效果已经在 start() 里结算过，这里只把文案补成结果面板的第二行。
                result.text_ids.append(f"evt.{result.triggered_event_id}.body.1")
                LOG.info("[FLOW] immediate event %s（不推 EventScene）", result.triggered_event_id)
            else:
                state.pending_event_id = result.triggered_event_id

    def activity_log_today(self) -> list[str]:
        """当天已完成的 action_id 列表（顺序即执行顺序），供日结算面板显示。"""
        return list(self.today_activities)

    def close_result_panel(self, result: ActivityResult | None = None) -> None:
        """ResultPanel 关闭时调用：事件优先，其次是日结算。"""
        state = self.require_state()
        payload = result or getattr(self, "last_activity_result", None)
        if not isinstance(payload, ActivityResult) or not payload.ok:
            return
        if payload.triggered_event_id:
            if is_immediate_event(payload.triggered_event_id):
                # 日常事件已经在规则层结算完，这里只推进日期，不能改 phase
                state.pending_event_id = None
                if payload.day_finished:
                    self.finish_day()
                return
            state.pending_event_id = payload.triggered_event_id
            state.phase = "event"
            self.scenes.push("EventScene", event_id=payload.triggered_event_id)
            return
        if payload.day_finished:
            self.finish_day()

    def finish_day(self) -> DayEndResult:
        state = self.require_state()
        calendar = self.services.calendar
        result = calendar.end_day(state)
        state.energy = min(state.max_energy(), max(0, state.energy))
        state.pending_event_id = None
        self.bus.emit(TOPIC_DAY_ENDED, result=result, state=state)
        self._autosave(state, reason="day_end")

        if self.scenes.top_overlay_id == "DaySummary":
            self.scenes.pop()  # 上一天的结算面板还没关，先替换掉
        self.scenes.push("DaySummary", result=result)
        if result.semester_event_id:
            self._pending_day_start = not result.graduated
            self._pending_graduation = result.graduated
            # 第 8 学期事件属于最后一天：先播事件，事件关闭后再进毕业界面
            self._handle_semester_event(state, result)
            return result
        if result.graduated:
            self._handle_graduation(state)
            return result
        self._begin_next_day(state)
        return result

    def _handle_semester_event(self, state: GameState, result: DayEndResult) -> None:
        event_id = result.semester_event_id
        self._autosave(state, reason="pre_event")
        state.phase = "event"
        state.pending_event_id = event_id
        state.event_log.append(event_id)
        self.bus.emit(TOPIC_EVENT_STARTED, event_id=event_id)
        self.scenes.push("EventScene", event_id=event_id, semester=True)

    def _handle_graduation(self, state: GameState) -> None:
        ending_service = self.services.ending
        ending = ending_service.evaluate(state)
        if not isinstance(ending, EndingResult):
            ending = EndingResult(ending_id=str(ending))
        state.phase = "graduation"
        state.ending_id = ending.ending_id
        self.bus.emit(TOPIC_GAME_GRADUATED, ending=ending, state=state)
        self.scenes.pop_all()
        self.scenes.change("GraduationScene", ending=ending)
        LOG.info("[FLOW] graduated ending=%s", ending.ending_id)

    def _begin_next_day(self, state: GameState) -> None:
        state.action_slot = 0
        state.phase = "campus"
        self.today_activities = []
        self.teleport_to_spawn()
        self.bus.emit(TOPIC_DAY_STARTED, state=state, day_index=state.day_index)
        self._day_start_emitted_for = state.day_index
        LOG.info("[FLOW] new day index=%d (year=%d sem=%d day=%d)",
                 state.day_index, state.year, state.semester, state.day)

    # ------------------------------------------------------------------ #
    # 事件结果
    # ------------------------------------------------------------------ #
    def handle_event_result(self, result: EventResult) -> None:
        state = self.require_state()
        state.pending_event_id = None
        self.bus.emit(TOPIC_EVENT_FINISHED, result=result)
        if state.phase == "event":
            state.phase = "campus"
        if state.ending_id:
            return
        self._autosave(state, reason="post_event")
        if self._pending_graduation:
            self._pending_graduation = False
            self._pending_day_start = False
            self._handle_graduation(state)
            return
        if self._pending_day_start:
            # 学期事件结束后才开始新的一天（DaySummary/EventScene 关闭后由调用方保证顺序）
            self._pending_day_start = False
            self._begin_next_day(state)

    def request_save(self, slot: str, manual: bool = True) -> bool:
        state = self.require_state()
        if manual:
            allowed, reason = self.saves.can_manual_save(state)
            if not allowed:
                LOG.warning("[FLOW] manual save rejected: %s", reason)
                return False
        self._autosave(state, reason="manual", slot=slot)
        return True

    def _autosave(self, state: GameState, reason: str, slot: str = config.AUTOSAVE_SLOT) -> None:
        try:
            path = self.saves.save(state, slot, reason=reason)
        except OSError as exc:
            LOG.error("[FLOW] autosave failed (%s): %s", reason, exc)
            return
        self.bus.emit(TOPIC_SAVE_WRITTEN, slot=slot, path=str(path), reason=reason)

    # ------------------------------------------------------------------ #
    # 暂停与毕业收尾
    # ------------------------------------------------------------------ #
    def set_paused(self, paused: bool) -> None:
        if paused and self.state is None:
            return
        self.paused = bool(paused)

    def toggle_pause(self) -> bool:
        self.set_paused(not self.paused)
        return self.paused

    def back_to_main_menu(self) -> None:
        self.state = None
        self.paused = False
        self.scenes.pop_all()
        self.scenes.change("MainMenu")

    def finish_graduation(self) -> None:
        state = self.require_state()
        state.phase = "finished"
        self.back_to_main_menu()

    # ------------------------------------------------------------------ #
    def tick(self, dt: float) -> None:
        """flow_tick：只在非暂停、非主菜单状态下累计 play_seconds。"""
        if self.state is None or self.paused:
            return
        if self.state.phase in ("campus", "event"):
            self.state.play_seconds += dt


def _random_seed() -> int:
    import time

    return time.time_ns() % (2 ** 31)


