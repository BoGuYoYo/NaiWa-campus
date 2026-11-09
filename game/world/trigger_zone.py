"""任务 C4：交互点的提示范围（滞回）与最近交互点选择。"""

from __future__ import annotations

from dataclasses import dataclass

from game.world.map_data import CAMPUS_SCENE, Interactable, MapData

# 多个交互点同时在范围内时，距离相同时的选择顺序
PRIORITY = ("npc", "activity", "door", "save", "inspect")
# 隐藏滞回：距离超过 半径 + HIDE_MARGIN 才消失
HIDE_MARGIN = 0.3


@dataclass(frozen=True)
class Candidate:
    """一个交互点及其世界坐标。"""

    interactable: Interactable
    x: float
    y: float

    @property
    def id(self) -> str:
        return self.interactable.id

    @property
    def radius(self) -> float:
        return self.interactable.radius

    @property
    def type(self) -> str:
        return self.interactable.type


def candidate_distance(candidate: Candidate, x: float, y: float) -> float:
    dx = candidate.x - x
    dy = candidate.y - y
    return (dx * dx + dy * dy) ** 0.5


def make_candidates(map_data: MapData, scene: str) -> tuple[Candidate, ...]:
    """取某场景（campus 或建筑 id）下全部交互点，坐标统一换算到世界坐标。"""
    return tuple(
        Candidate(ia, *map_data.to_world(ia)) for ia in map_data.interactables_for(scene)
    )


def _priority_key(candidate: Candidate) -> int:
    return PRIORITY.index(candidate.type)


def nearest(candidates: tuple[Candidate, ...] | list[Candidate], x: float, y: float) -> Candidate | None:
    """范围内（距离 <= 半径）最近的一个；距离相同时按 PRIORITY 顺序选择。"""
    best: Candidate | None = None
    best_key: tuple[float, int, str] | None = None
    for c in candidates:
        d = candidate_distance(c, x, y)
        if d > c.radius:
            continue
        key = (d, _priority_key(c), c.id)
        if best_key is None or key < best_key:
            best, best_key = c, key
    return best


class PromptTracker:
    """按滞回规则决定当前显示的提示：距离 <= 半径时出现，超过 半径 + 0.3 米才消失。"""

    def __init__(self) -> None:
        self._active: Candidate | None = None

    @property
    def active(self) -> Candidate | None:
        return self._active

    @property
    def active_id(self) -> str | None:
        return None if self._active is None else self._active.id

    def reset(self) -> None:
        self._active = None

    def update(
        self, candidates: tuple[Candidate, ...] | list[Candidate], x: float, y: float
    ) -> Candidate | None:
        best: Candidate | None = None
        best_key: tuple[float, int, str] | None = None
        for c in candidates:
            d = candidate_distance(c, x, y)
            limit = c.radius + HIDE_MARGIN if self._active is not None and c.id == self._active.id else c.radius
            if d > limit:
                continue
            key = (d, _priority_key(c), c.id)
            if best_key is None or key < best_key:
                best, best_key = c, key
        self._active = best
        return best


def scene_of(state, map_data: MapData) -> str:
    """WorldPos.location_id 为建筑 id 时是室内，否则为室外。"""
    location_id = state.world.location_id
    return location_id if map_data.has_interior(location_id) else CAMPUS_SCENE
