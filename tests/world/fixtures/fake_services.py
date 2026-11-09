"""任务 C 独立测试用的替身服务：只记录调用，不做任何数值计算。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FakeActivityResult:
    ok: bool = True
    activity_id: str = ""
    error_code: str | None = None
    deltas: dict = field(default_factory=dict)
    added_flags: list = field(default_factory=list)
    text_ids: list = field(default_factory=list)
    triggered_event_id: str | None = None
    day_finished: bool = False


class FakeActivityService:
    """记录 activity_id；blocked 里的活动返回不可开始与对应错误码。"""

    def __init__(self, blocked: dict[str, str] | None = None, costs: dict[str, dict] | None = None):
        self.blocked = dict(blocked or {})
        self.costs = dict(costs or {})
        self.can_start_calls: list[tuple[str, str]] = []
        self.preview_calls: list[tuple[str, str]] = []
        self.start_calls: list[tuple[str, str]] = []

    def can_start(self, state, activity_id):
        self.can_start_calls.append((state.world.location_id, activity_id))
        if activity_id in self.blocked:
            return (False, self.blocked[activity_id])
        return (True, None)

    def preview(self, state, activity_id):
        self.preview_calls.append((state.world.location_id, activity_id))
        return dict(self.costs.get(activity_id, {"energy": -1}))

    def start(self, state, activity_id):
        self.start_calls.append((state.world.location_id, activity_id))
        return FakeActivityResult(activity_id=activity_id, text_ids=[f"act.{activity_id}.result.1"])


class FakeRelationshipService:
    """替身：交谈规则由用例注入（C 不再自己判断精力）。"""

    def __init__(
        self,
        blocked: dict[str, str] | None = None,
        can_talk=None,
        preview: dict[str, dict] | None = None,
    ):
        self.blocked = dict(blocked or {})
        self.talk_calls: list[tuple[str, str]] = []
        self._can_talk = can_talk
        self._preview = dict(preview or {})

    def can_talk(self, state, npc_id):
        if self._can_talk is None:
            return (True, None)
        return self._can_talk(state, npc_id)

    def preview(self, state, npc_id):
        return dict(self._preview.get(npc_id, {}))

    def talk(self, state, npc_id):
        self.talk_calls.append((state.world.location_id, npc_id))
        if npc_id in self.blocked:
            return FakeActivityResult(ok=False, activity_id=f"talk.{npc_id}", error_code=self.blocked[npc_id])
        return FakeActivityResult(activity_id=f"talk.{npc_id}")


class FakeTextDB:
    def get(self, text_id, **fmt):
        return f"#{text_id}"


class FakeSceneManager:
    def __init__(self) -> None:
        self.changes: list[tuple[str, dict]] = []
        self.pushes: list[tuple[str, dict]] = []

    def change(self, scene_id, **kw):
        self.changes.append((scene_id, kw))
        return scene_id

    def push(self, overlay_id, **kw):
        self.pushes.append((overlay_id, kw))
        return overlay_id

    def pop(self):
        return None


class FakeEventBus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def emit(self, topic, **data):
        self.events.append((topic, data))
