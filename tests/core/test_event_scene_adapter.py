"""回归覆盖真实 EventSceneAdapter 到 EventService 的玩家路径。"""

from __future__ import annotations

from types import SimpleNamespace

from game import config
from game.core.results import EventResult
from game.core.state import GameState
from game.core.world_scene import EventSceneAdapter
from game.systems.event_service import EventService
from game.ui.text_db import TextDB


class _FakeDialogue:
    def __init__(self) -> None:
        self.pages = []

    def show_page(self, page) -> None:
        self.pages.append(page)


class _FakeWidget:
    def __init__(self) -> None:
        self.dialogue = _FakeDialogue()
        self.loaded = []
        self.results = []
        self.hints = []

    def show_simple_pages(self, event_id, page_ids) -> None:
        self.loaded.append((event_id, page_ids))

    def load_event(self, view) -> None:
        self.loaded.append(view)

    def show_event_result(self, result) -> None:
        self.results.append(result)

    def _show_lock_hint(self, text) -> None:
        self.hints.append(text)


class _FakeText:
    def __init__(self) -> None:
        self.calls = []

    def has(self, text_id: str) -> bool:
        return text_id in {
            "evt.sem_1_club_fair.lock.fair_lab",
            "evt.sem_5_club_election.lock.tech_project",
        }

    def get_raw(self, text_id: str) -> str:
        return f"hint:{text_id}"

    def get(self, text_id: str, **kwargs) -> str:
        self.calls.append((text_id, dict(kwargs)))
        if text_id == "err.unknown_id":
            return f"内容缺失：{kwargs.get('id', '{id}')}"
        return f"text:{text_id}"


def _adapter(state: GameState):
    handled = []
    popped = []

    class _Flow:
        def require_state(self):
            return state

        def handle_event_result(self, result):
            handled.append(result)

    class _Scenes:
        def pop(self):
            popped.append(True)

    app = SimpleNamespace(
        flow=_Flow(),
        scenes=_Scenes(),
        services=SimpleNamespace(event=EventService()),
        text=_FakeText(),
    )
    adapter = EventSceneAdapter.__new__(EventSceneAdapter)
    adapter.app = app
    adapter.widget = _FakeWidget()
    adapter._pending_result = None
    adapter._inspect_only = False
    adapter._event_id = None
    return adapter, handled, popped


def test_real_adapter_builds_rule_aware_view_and_settles_event():
    state = GameState()
    adapter, handled, _ = _adapter(state)

    view = adapter._build_view("sem_1_club_fair")
    assert view.choices
    assert all(choice.enabled for choice in view.choices)

    adapter._choose("sem_1_club_fair", "fair_lab")

    assert state.stats["academic"] == 14
    assert state.relationships["npc_chenlang"] == 10
    assert "lab_visited" in state.flags
    assert state.event_log == ["sem_1_club_fair:fair_lab"]
    assert len(handled) == 0
    assert len(adapter.widget.results) == 1
    assert isinstance(adapter.widget.results[0], EventResult)


def test_adapter_uses_all_pages_from_real_textdb():
    adapter, _, _ = _adapter(GameState())
    adapter.app.text = TextDB.load(str(config.resource_root() / "content"))

    opening = adapter._build_view("story_opening")
    fair = adapter._build_view("sem_1_club_fair")

    assert opening.page_text_ids == [
        f"evt.story_opening.body.{i}" for i in range(1, 6)
    ]
    assert fair.page_text_ids == [
        f"evt.sem_1_club_fair.body.{i}" for i in range(1, 5)
    ]
    assert adapter.app.text.get_dialogue(fair.page_text_ids[1])["portrait"] == "portrait_npc_sumo_neutral"
    assert adapter.app.text.get_dialogue(fair.page_text_ids[2])["portrait"] == "portrait_npc_chenlang_neutral"
    assert adapter.app.text.get_dialogue(fair.page_text_ids[3])["portrait"] == "portrait_npc_xiaoyou_surprised"


def test_real_adapter_marks_locked_choices_disabled():
    state = GameState()
    state.day_index = 8
    adapter, _, _ = _adapter(state)

    view = adapter._build_view("sem_5_club_election")

    locked = next(choice for choice in view.choices if choice.choice_id == "tech_project")
    assert locked.enabled is False
    assert locked.lock_reason_id == "evt.sem_5_club_election.lock.tech_project"


def test_inspect_and_empty_finish_never_settle_event():
    state = GameState()
    adapter, handled, popped = _adapter(state)
    before = list(state.event_log)

    adapter.apply(text_id="insp.gate.body.1")
    adapter._finished("inspect")
    assert state.event_log == before
    assert handled == []
    assert len(popped) == 1

    adapter._inspect_only = False
    adapter._pending_result = None
    adapter._finished("sem_1_club_fair")
    assert state.event_log == before
    assert handled == []
    assert len(popped) == 2


def test_content_error_is_shown_without_bubbling():
    state = GameState()
    adapter, _, _ = _adapter(state)

    adapter._choose("sem_1_club_fair", "fair_lab")
    adapter._choose("sem_1_club_fair", "fair_club")

    assert adapter.widget.hints
    assert state.event_log == ["sem_1_club_fair:fair_lab"]


def test_unknown_event_error_formats_id_without_placeholder():
    state = GameState()
    adapter, _, _ = _adapter(state)

    adapter._choose("missing_event", "missing_choice")

    assert adapter.widget.hints == ["内容缺失：missing_event"]
    assert ("err.unknown_id", {"id": "missing_event"}) in adapter.app.text.calls
    assert "{" not in adapter.widget.hints[0]


def test_locked_error_uses_choice_locked_text():
    state = GameState()
    state.day_index = 8
    adapter, _, _ = _adapter(state)

    adapter._choose("sem_5_club_election", "tech_project")

    assert adapter.widget.hints == ["hint:evt.sem_5_club_election.lock.tech_project"]


def test_adapter_finish_forwards_real_result_once():
    state = GameState()
    adapter, handled, popped = _adapter(state)

    adapter._choose("sem_1_club_fair", "fair_lab")
    adapter._finished("sem_1_club_fair")

    assert len(handled) == 1
    assert isinstance(handled[0], EventResult)
    assert len(popped) == 1
    assert handled[0].choice_id == "fair_lab"
