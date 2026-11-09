"""适配层装配烟测：每个 `*SceneAdapter` 都真的走一遍 `on_enter` → `on_exit`。

为什么需要这支用例（BUG-3 的成因形态）：`test_event_scene_adapter.py` 用
`EventSceneAdapter.__new__()` 直接注入 `app`/`widget`，**绕过了 `on_enter`**，
因此它只证明"方法逻辑对"，不证明"适配层被正确装配"。BUG-3（教程横幅从不显示）
恰恰不是方法算错，而是**没人调用 / 忘了接线**。

本用例用假 app + 记录型假 widget，但走**真实装配入口** `on_enter`：
- 断言 `on_enter` 不抛异常；
- 断言绑定了至少一个按键（需要输入的覆盖层）；
- 断言 `on_exit()` 之后**每个绑定都被收回**、widget 被 destroy（无残留订阅/泄漏）。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from game.core import world_scene as ws
from game.core.state import GameState
from game.systems.event_service import EventService


class _RecText:
    """记录调用、按真 TextDB 语义格式化，且永不返回 None。"""

    def has(self, text_id: str) -> bool:
        return True

    def get_raw(self, text_id: str) -> str:
        return f"raw:{text_id}"

    def get(self, text_id: str, **fmt) -> str:
        return f"text:{text_id}"

    def get_dialogue(self, text_id: str):
        return {"speaker": None, "portrait": None, "lines": ["线"] * 3}


class _RecDialogue:
    def __init__(self) -> None:
        self.pages: list = []

    def show_page(self, page) -> None:
        self.pages.append(page)


class _RecWidget:
    """尽量宽容的记录型 widget：任何未定义属性都返回一个无害的可调用对象。"""

    def __init__(self) -> None:
        object.__setattr__(self, "calls", [])
        object.__setattr__(self, "dialogue", _RecDialogue())
        object.__setattr__(self, "destroyed", False)
        object.__setattr__(self, "handlers", {})

    def __getattr__(self, name):
        record = self.__dict__["calls"]

        def _record(*args, **kwargs):
            record.append((name, args, kwargs))
            return None

        return _record

    def show(self) -> None:
        self.calls.append(("show", (), {}))

    def destroy(self) -> None:
        object.__setattr__(self, "destroyed", True)

    def tick(self, dt) -> None:
        self.calls.append(("tick", (dt,), {}))


class _RecInput:
    """记录 bind/unbind，用来断言"绑了就必须收回"。"""

    def __init__(self) -> None:
        self.binds: list[tuple[object, str]] = []
        self.unbinds: list[object] = []

    def bind(self, owner, event, handler) -> None:
        self.binds.append((owner, event))

    def unbind(self, owner) -> None:
        self.unbinds.append(owner)
        self.binds = [(o, e) for (o, e) in self.binds if o is not owner]


def _fake_app(state: GameState):
    class _Flow:
        def require_state(self):
            return state

        def activity_log_today(self):
            return []

        def finish_graduation(self):
            return None

        def back_to_main_menu(self):
            return None

        def set_paused(self, paused):
            return None

        @property
        def state(self):
            return state

    class _Saves:
        def list_slots(self):
            return []

        def can_manual_save(self, state):
            return True, None

        def path_for(self, slot):
            return f"/tmp/{slot}.json"

    return SimpleNamespace(
        flow=_Flow(),
        scenes=SimpleNamespace(pop=lambda: None, push=lambda *a, **k: None,
                               change=lambda *a, **k: None),
        services=SimpleNamespace(event=EventService(), activity=None, relationship=None),
        saves=_Saves(),
        text=_RecText(),
        registry=None,
        input=_RecInput(),
        ui_root=None,
        ui_transform=None,
        settings=SimpleNamespace(),
        audio=SimpleNamespace(),
        quit_game=lambda *a, **k: None,
    )


# (适配器, on_enter 的最小 kwargs)
_CASES = [
    (ws.MainMenuSceneAdapter, {}),
    (ws.EventSceneAdapter, {"event_id": "sem_1_club_fair"}),
    (ws.ResultPanelSceneAdapter, {}),
    (ws.DaySummarySceneAdapter, {}),
    (ws.TabPanelSceneAdapter, {}),
    (ws.PauseMenuSceneAdapter, {}),
    (ws.SettingsMenuSceneAdapter, {}),
    (ws.SaveMenuSceneAdapter, {}),
    (ws.GraduationSceneAdapter, {}),
]


@pytest.mark.parametrize("adapter_cls,kwargs", _CASES, ids=[c.__name__ for c, _ in _CASES])
def test_adapter_enters_and_exits_cleanly(adapter_cls, kwargs) -> None:
    state = GameState()

    class _Adapter(adapter_cls):  # type: ignore[misc, valid-type]
        def _make_widget(self):
            return _RecWidget()

    app = _fake_app(state)
    adapter = _Adapter(app)

    adapter.on_enter(**kwargs)  # 真实装配入口

    assert adapter.widget is not None, "on_enter 没有建出 widget"
    assert app.input.binds, f"{adapter_cls.__name__} 一个按键都没绑（忘记接线？）"

    owner = adapter
    bound_events = {event for (o, event) in app.input.binds if o is owner}
    assert bound_events, "绑定没有记到适配层自己名下（InputRouter 归属丢了）"

    adapter.on_exit()

    assert owner in app.input.unbinds, "on_exit 没有归还绑定"
    leftover = [e for (o, e) in app.input.binds if o is owner]
    assert leftover == [], f"on_exit 之后仍有残留绑定：{leftover}"
    assert adapter.widget is None, "on_exit 之后 widget 没有被释放"
