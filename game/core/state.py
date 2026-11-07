"""A 维护：GameState / WorldPos（公共数据结构，全员只读依赖）。

日期以 day_index 为唯一权威字段；year / semester / day / semester_no 全部为派生属性，
禁止单独写入。数值截断由 B 的 effects.apply() 负责，本模块只做读档时的兜底钳制。
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Iterable

from ..config import ACTIONS_PER_DAY, DAYS_PER_SEMESTER, SEMESTERS_PER_YEAR, TOTAL_DAYS

STAT_KEYS = ("academic", "stamina", "social", "interest")
RELATIONSHIP_KEYS = ("npc_sumo", "npc_chenlang", "npc_xiaoyou")
STAT_MIN = 0
STAT_MAX = 100
MOOD_MIN = 0
MOOD_MAX = 100
FACINGS = ("s", "se", "e", "ne", "n", "nw", "w", "sw")
PHASES = ("campus", "event", "graduation", "finished")

DEFAULT_SPAWN_LOCATION = "loc_gate"
DEFAULT_SPAWN_X = 40.0
DEFAULT_SPAWN_Y = 5.0


@dataclass
class WorldPos:
    """当前所在地点与世界坐标（米）。"""

    location_id: str = DEFAULT_SPAWN_LOCATION
    x: float = DEFAULT_SPAWN_X
    y: float = DEFAULT_SPAWN_Y
    facing: str = "n"

    def to_dict(self) -> dict[str, Any]:
        return {
            "location_id": self.location_id,
            "x": round(float(self.x), 4),
            "y": round(float(self.y), 4),
            "facing": self.facing if self.facing in FACINGS else "n",
        }

    @classmethod
    def from_dict(cls, raw: Any) -> "WorldPos":
        if not isinstance(raw, dict):
            return cls()
        facing = raw.get("facing", "n")
        return cls(
            location_id=str(raw.get("location_id", DEFAULT_SPAWN_LOCATION)) or DEFAULT_SPAWN_LOCATION,
            x=_as_float(raw.get("x"), DEFAULT_SPAWN_X),
            y=_as_float(raw.get("y"), DEFAULT_SPAWN_Y),
            facing=facing if facing in FACINGS else "n",
        )


def _as_int(value: Any, default: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return int(value)


def _as_float(value: Any, default: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return float(value)


@dataclass
class GameState:
    save_version: int = 1
    seed: int = 42
    day_index: int = 0
    action_slot: int = 0
    stats: dict[str, int] = field(
        default_factory=lambda: {"academic": 10, "stamina": 20, "social": 10, "interest": 10}
    )
    mood: int = 60
    energy: int = 84
    relationships: dict[str, int] = field(
        default_factory=lambda: {key: 0 for key in RELATIONSHIP_KEYS}
    )
    flags: set[str] = field(default_factory=set)
    counters: dict[str, int] = field(default_factory=dict)
    today_counts: dict[str, int] = field(default_factory=dict)
    talked_today: set[str] = field(default_factory=set)
    event_log: list[str] = field(default_factory=list)
    pending_event_id: str | None = None
    phase: str = "campus"
    ending_id: str | None = None
    world: WorldPos = field(default_factory=WorldPos)
    tutorial_done: set[str] = field(default_factory=set)
    play_seconds: float = 0.0

    # ------------------------------------------------------------------ #
    # 派生属性（只读）
    # ------------------------------------------------------------------ #
    @property
    def year(self) -> int:
        return self.day_index // (DAYS_PER_SEMESTER * SEMESTERS_PER_YEAR) + 1

    @property
    def semester(self) -> int:
        return (self.day_index // DAYS_PER_SEMESTER) % SEMESTERS_PER_YEAR + 1

    @property
    def day(self) -> int:
        return self.day_index % DAYS_PER_SEMESTER + 1

    @property
    def semester_no(self) -> int:
        return self.day_index // DAYS_PER_SEMESTER + 1

    @property
    def actions_left(self) -> int:
        return max(0, ACTIONS_PER_DAY - self.action_slot)

    @property
    def day_finished(self) -> bool:
        return self.action_slot >= ACTIONS_PER_DAY

    @property
    def is_last_day(self) -> bool:
        return self.day_index >= TOTAL_DAYS - 1

    def max_energy(self) -> int:
        return 80 + self.stats.get("stamina", 0) // 5

    def snapshot(self) -> "GameState":
        return copy.deepcopy(self)

    def clamp(self) -> None:
        """读档/外部写入后的兜底钳制；正常流程由 B 的 effects 处理。"""
        self.save_version = _as_int(self.save_version, 1)
        self.day_index = max(0, min(TOTAL_DAYS - 1, _as_int(self.day_index, 0)))
        self.action_slot = max(0, min(ACTIONS_PER_DAY, _as_int(self.action_slot, 0)))
        for key in STAT_KEYS:
            self.stats[key] = max(STAT_MIN, min(STAT_MAX, _as_int(self.stats.get(key), 10)))
        for key in RELATIONSHIP_KEYS:
            self.relationships[key] = max(0, min(STAT_MAX, _as_int(self.relationships.get(key), 0)))
        self.mood = max(MOOD_MIN, min(MOOD_MAX, _as_int(self.mood, 60)))
        self.energy = max(0, min(self.max_energy(), _as_int(self.energy, self.max_energy())))
        self.play_seconds = max(0.0, _as_float(self.play_seconds, 0.0))
        if self.phase not in PHASES:
            self.phase = "campus"

    # ------------------------------------------------------------------ #
    # 序列化：set 序列化为排序后的 list
    # ------------------------------------------------------------------ #
    def to_dict(self) -> dict[str, Any]:
        return {
            "save_version": int(self.save_version),
            "seed": int(self.seed),
            "day_index": int(self.day_index),
            "action_slot": int(self.action_slot),
            "stats": {key: int(self.stats.get(key, 0)) for key in STAT_KEYS},
            "mood": int(self.mood),
            "energy": int(self.energy),
            "relationships": {key: int(self.relationships.get(key, 0)) for key in RELATIONSHIP_KEYS},
            "flags": sorted(self.flags),
            "counters": {k: int(v) for k, v in sorted(self.counters.items())},
            "today_counts": {k: int(v) for k, v in sorted(self.today_counts.items())},
            "talked_today": sorted(self.talked_today),
            "event_log": list(self.event_log),
            "pending_event_id": self.pending_event_id,
            "phase": self.phase,
            "ending_id": self.ending_id,
            "world": self.world.to_dict(),
            "tutorial_done": sorted(self.tutorial_done),
            "play_seconds": round(float(self.play_seconds), 3),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "GameState":
        if not isinstance(raw, dict):
            raise ValueError("state 必须是 JSON 对象")
        state = cls()
        state.save_version = _as_int(raw.get("save_version"), 1)
        state.seed = _as_int(raw.get("seed"), 42)
        state.day_index = _as_int(raw.get("day_index"), 0)
        state.action_slot = _as_int(raw.get("action_slot"), 0)
        stats = raw.get("stats") if isinstance(raw.get("stats"), dict) else {}
        state.stats = {key: _as_int(stats.get(key), {"academic": 10, "stamina": 20, "social": 10, "interest": 10}[key]) for key in STAT_KEYS}
        state.mood = _as_int(raw.get("mood"), 60)
        state.energy = _as_int(raw.get("energy"), 84)
        rel = raw.get("relationships") if isinstance(raw.get("relationships"), dict) else {}
        state.relationships = {key: _as_int(rel.get(key), 0) for key in RELATIONSHIP_KEYS}
        state.flags = _as_str_set(raw.get("flags"))
        counters = raw.get("counters") if isinstance(raw.get("counters"), dict) else {}
        state.counters = {str(k): _as_int(v, 0) for k, v in counters.items()}
        today = raw.get("today_counts") if isinstance(raw.get("today_counts"), dict) else {}
        state.today_counts = {str(k): _as_int(v, 0) for k, v in today.items()}
        state.talked_today = _as_str_set(raw.get("talked_today"))
        state.event_log = _as_str_list(raw.get("event_log"))
        pending = raw.get("pending_event_id")
        state.pending_event_id = str(pending) if pending else None
        phase = raw.get("phase", "campus")
        state.phase = phase if phase in PHASES else "campus"
        ending = raw.get("ending_id")
        state.ending_id = str(ending) if ending else None
        state.world = WorldPos.from_dict(raw.get("world"))
        state.tutorial_done = _as_str_set(raw.get("tutorial_done"))
        state.play_seconds = _as_float(raw.get("play_seconds"), 0.0)
        state.clamp()
        return state

    def summary(self) -> dict[str, Any]:
        """读档界面直接显示的摘要；与 state 分离，便于快速渲染。"""
        return {
            "year": self.year,
            "semester": self.semester,
            "day": self.day,
            "semester_no": self.semester_no,
            "day_index": self.day_index,
            "play_seconds": round(self.play_seconds, 1),
            "stats": {key: int(self.stats.get(key, 0)) for key in STAT_KEYS},
            "mood": int(self.mood),
            "energy": int(self.energy),
            "phase": self.phase,
            "ending_id": self.ending_id,
        }


def _as_str_set(value: Any) -> set[str]:
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes)):
        return set()
    return {str(item) for item in value if item is not None}


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes)):
        return []
    return [str(item) for item in value if item is not None]


def new_state(seed: int = 42) -> GameState:
    """新游戏初始状态：day_index=0，slot=0，出生于 loc_gate (40, 5)。"""
    state = GameState(seed=int(seed))
    state.world = WorldPos()
    state.clamp()
    state.energy = state.max_energy()
    return state
