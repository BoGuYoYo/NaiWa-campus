"""固定策略与随机策略（开发者 B，手册 B9）。

固定策略规则：
    第 i 个行动（i = day_index*3 + action_slot）先判断是否轮到交谈；
    否则执行 cycle[i % 6]；该动作不可执行时先试 eat_canteen，再执行 rest_dorm。
    学期事件优先 prefs 中的选项，被锁时按表中顺序取第一个可用项。
"""

from __future__ import annotations

from typing import Any

from game.core.results import EventView
from game.core.state import GameState
from game.systems import rng as rng_mod
from game.systems import spec_data
from game.systems.content_db import ContentDB, get_db


class Services:
    """服务容器，避免策略层逐个 import 具体服务实现。"""

    def __init__(self, db: ContentDB | None = None) -> None:
        from game.systems.activity_service import ActivityService
        from game.systems.calendar_service import CalendarService
        from game.systems.ending_service import EndingService
        from game.systems.event_service import EventService
        from game.systems.relationship_service import RelationshipService

        self.db = db or get_db()
        self.activities = ActivityService(self.db)
        self.calendar = CalendarService(self.db)
        self.relationships = RelationshipService(self.db)
        self.events = EventService(self.db)
        self.endings = EndingService(self.db)


class BaseStrategy:
    name: str = "base"
    expected_ending: str | None = None

    def next_action(self, state: GameState, services: Services) -> tuple[str, str]:
        """返回 ("activity", activity_id) 或 ("talk", npc_id)。"""
        raise NotImplementedError

    def choose_event_option(self, state: GameState, view: EventView,
                            services: Services) -> str:
        raise NotImplementedError


class FixedStrategy(BaseStrategy):
    def __init__(self, name: str, config: dict[str, Any]) -> None:
        self.name = name
        self.cycle: list[str] = list(config["cycle"])
        self.talk_npc: str | None = config.get("talk_npc")
        self.talk_every: int = int(config.get("talk_every") or 0)
        self.prefs: dict[int, str] = {int(k): v for k, v in (config.get("prefs") or {}).items()}
        self.expected_ending = config.get("expected_ending")

    def next_action(self, state: GameState, services: Services) -> tuple[str, str]:
        index = state.day_index * spec_data.SLOTS_PER_DAY + state.action_slot
        if (self.talk_npc and self.talk_every > 0 and index % self.talk_every == 0
                and self.talk_npc not in state.talked_today
                and state.energy >= spec_data.TALK_REQUIRED_ENERGY):
            ok, _ = services.relationships.can_talk(state, self.talk_npc)
            if ok:
                return "talk", self.talk_npc
        candidate = self.cycle[index % len(self.cycle)]
        ok, _ = services.activities.can_start(state, candidate)
        if ok:
            return "activity", candidate
        ok, _ = services.activities.can_start(state, "eat_canteen")
        if ok:
            return "activity", "eat_canteen"
        return "activity", "rest_dorm"

    def choose_event_option(self, state: GameState, view: EventView,
                            services: Services) -> str:
        event = services.db.event(view.event_id) or {}
        semester_no = event.get("semester_no")
        preferred = self.prefs.get(int(semester_no)) if semester_no is not None else None
        if preferred:
            for choice in view.choices:
                if choice.choice_id == preferred and choice.enabled:
                    return preferred
        for choice in view.choices:
            if choice.enabled:
                return choice.choice_id
        raise RuntimeError(f"{view.event_id} 没有可用选项")


class RandomStrategy(BaseStrategy):
    """每步从 9 个活动 + 3 名 NPC 中均匀抽取可执行项；学期事件随机选。"""

    name = "random"
    expected_ending = None

    def __init__(self, seed: int) -> None:
        self.seed = seed

    def next_action(self, state: GameState, services: Services) -> tuple[str, str]:
        rng = rng_mod.random_strategy_rng(self.seed, state.day_index, state.action_slot)
        candidates: list[tuple[str, str]] = []
        for activity_id in spec_data.ACTIVITY_IDS:
            ok, _ = services.activities.can_start(state, activity_id)
            if ok:
                candidates.append(("activity", activity_id))
        for npc_id in spec_data.NPC_IDS:
            ok, _ = services.relationships.can_talk(state, npc_id)
            if ok:
                candidates.append(("talk", npc_id))
        if not candidates:
            return "activity", "rest_dorm"
        return rng.choice(candidates)

    def choose_event_option(self, state: GameState, view: EventView,
                            services: Services) -> str:
        rng = rng_mod.event_choice_rng(self.seed, view.event_id)
        enabled = [c.choice_id for c in view.choices if c.enabled]
        if not enabled:
            raise RuntimeError(f"{view.event_id} 没有可用选项")
        return rng.choice(enabled)


def build_strategy(name: str, seed: int = 42) -> BaseStrategy:
    if name == "random":
        return RandomStrategy(seed)
    if name not in spec_data.STRATEGIES:
        raise KeyError(f"未知策略：{name}")
    return FixedStrategy(name, spec_data.STRATEGIES[name])
