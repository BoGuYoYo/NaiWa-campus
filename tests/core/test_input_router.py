"""A 的 core 层单元测试：按键绑定路由（不依赖 panda3d）。

回归的是整合期两个真实故障：
1. 主菜单点"新游戏"→ 淡出期间先把开场事件对话框 push 上来，
   主菜单 on_exit 的 ignore() 把对话框的 Space/Enter 一起清掉（对话框按不动、Esc 失效）；
2. 主菜单 → 设置 → 返回，子面板退场时 ignore() 掉上下键与确认键，主菜单变死界面。
"""

from __future__ import annotations

from game.core.input_router import InputRouter


class FakeMessenger:
    """最小的 accept/ignore 替身：只记录当前生效的绑定。"""

    def __init__(self) -> None:
        self.active: dict[str, object] = {}
        self.accept_calls: list[tuple[str, object]] = []
        self.ignore_calls: list[str] = []

    def accept(self, event, handler):
        self.active[event] = handler
        self.accept_calls.append((event, handler))

    def ignore(self, event):
        self.active.pop(event, None)
        self.ignore_calls.append(event)

    def send(self, event):
        handler = self.active.get(event)
        if handler is not None:
            handler()


def make_router() -> tuple[InputRouter, FakeMessenger]:
    messenger = FakeMessenger()
    return InputRouter(messenger.accept, messenger.ignore), messenger


def test_bind_activates_handler():
    router, messenger = make_router()
    calls = []
    router.bind("menu", "enter", lambda: calls.append("menu"))
    messenger.send("enter")
    assert calls == ["menu"]
    assert router.owner_of("enter") == "menu"


def test_later_binding_wins_like_accept():
    router, messenger = make_router()
    calls = []
    router.bind("menu", "enter", lambda: calls.append("menu"))
    router.bind("dialog", "enter", lambda: calls.append("dialog"))
    messenger.send("enter")
    assert calls == ["dialog"]


def test_unbind_restores_previous_owner_instead_of_dropping_the_key():
    """核心回归：对话框退场后，按键回到下层场景，而不是彻底失效。"""
    router, messenger = make_router()
    calls = []
    router.bind("campus", "escape", lambda: calls.append("pause"))
    router.bind("pause", "escape", lambda: calls.append("resume"))

    assert router.unbind("pause") == ["escape"]
    messenger.send("escape")
    assert calls == ["pause"]
    assert router.owner_of("escape") == "campus"


def test_old_scene_exit_does_not_steal_newer_overlay_bindings():
    """核心回归：旧场景 on_exit 晚于新覆盖层 on_enter 执行时，新绑定必须还在。"""
    router, messenger = make_router()
    calls = []
    router.bind("menu", "space", lambda: calls.append("menu"))
    router.bind("menu", "enter", lambda: calls.append("menu"))

    # 覆盖层先绑（对话框），主菜单随后才退场
    router.bind("dialog", "space", lambda: calls.append("dialog"))
    router.bind("dialog", "enter", lambda: calls.append("dialog"))
    router.unbind("menu")

    assert router.is_bound("space") and router.is_bound("enter")
    messenger.send("space")
    messenger.send("enter")
    assert calls == ["dialog", "dialog"]


def test_unbind_last_owner_ignores_the_event():
    router, messenger = make_router()
    router.bind("dialog", "space", lambda: None)
    router.unbind("dialog")
    assert not router.is_bound("space")
    assert "space" in messenger.ignore_calls


def test_unbind_specific_events_only():
    router, messenger = make_router()
    handler = lambda: None  # noqa: E731
    router.bind("menu", "enter", handler)
    router.bind("menu", "escape", handler)
    router.bind("menu", "space", handler)

    assert router.unbind("menu", events=["enter"]) == ["enter"]
    assert not router.is_bound("enter")
    assert router.is_bound("escape")
    assert router.is_bound("space")


def test_unbind_unknown_owner_is_a_noop():
    router, messenger = make_router()
    router.bind("menu", "enter", lambda: None)
    assert router.unbind("something_else") == []
    assert router.is_bound("enter")
    assert messenger.ignore_calls == []


def test_bind_many_and_clear():
    router, messenger = make_router()
    router.bind_many("pause", [("w", lambda: None), ("s", lambda: None)])
    assert router.events == ["s", "w"]
    assert router.depth("w") == 1
    router.clear()
    assert router.events == []
    assert sorted(messenger.ignore_calls) == ["s", "w"]


def test_empty_event_or_handler_is_ignored():
    router, messenger = make_router()
    router.bind("menu", "", lambda: None)
    router.bind("menu", "enter", None)
    assert router.events == []
    assert messenger.accept_calls == []
