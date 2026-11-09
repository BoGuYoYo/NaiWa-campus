"""任务 C 独立测试用的 FakeState。

只提供 world / phase / action_slot / energy / talked_today，
不提供任何属性字段（academic / stamina / social / interest / mood），
world/ 中的代码一旦尝试读写这些字段会直接 AttributeError。

构造时可直接传 world=FakeWorldPos(...)，也可用 location_id/x/y/facing 便捷参数。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FakeWorldPos:
    location_id: str = "loc_gate"
    x: float = 40.0
    y: float = 5.0
    facing: str = "n"


class FakeState:
    def __init__(
        self,
        *,
        phase: str = "campus",
        action_slot: int = 0,
        energy: int = 84,
        talked_today=None,
        world: FakeWorldPos | None = None,
        location_id: str = "loc_gate",
        x: float = 40.0,
        y: float = 5.0,
        facing: str = "n",
    ) -> None:
        self.phase = phase
        self.action_slot = action_slot
        self.energy = energy
        self.talked_today = set(talked_today) if talked_today is not None else set()
        if world is None:
            world = FakeWorldPos(location_id=location_id, x=x, y=y, facing=facing)
        self.world = world

    def to_dict(self) -> dict:
        return {
            "phase": self.phase,
            "action_slot": self.action_slot,
            "energy": self.energy,
            "talked_today": sorted(self.talked_today),
            "world": {
                "location_id": self.world.location_id,
                "x": self.world.x,
                "y": self.world.y,
                "facing": self.world.facing,
            },
        }
