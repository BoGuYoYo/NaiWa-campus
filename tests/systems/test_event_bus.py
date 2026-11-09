"""EventBus 的行为契约（A 会复用该接口，B 只负责发出两个主题）。

锁住四件事：订阅顺序、emit 返回处理函数个数、退订只摘掉指定函数、
以及"派发中新增的订阅不会在同一轮被调用"（emit 取快照）。
"""

from __future__ import annotations

from game.core.event_bus import EventBus


def test_emit_returns_handler_count_and_passes_payload():
    bus = EventBus()
    seen: list[tuple[str, dict]] = []
    bus.subscribe("activity.done", lambda **data: seen.append(("a", data)))
    bus.subscribe("activity.done", lambda **data: seen.append(("b", data)))

    count = bus.emit("activity.done", activity_id="library_study")

    assert count == 2
    assert [name for name, _ in seen] == ["a", "b"]
    assert all(data["activity_id"] == "library_study" for _, data in seen)


def test_emit_without_subscriber_is_silent():
    assert EventBus().emit("scene.changed", scene="dorm") == 0


def test_unsubscribe_removes_only_that_handler():
    bus = EventBus()
    kept: list[int] = []
    dropped: list[int] = []

    def keep_fn(**kw):
        kept.append(1)

    def drop_fn(**kw):
        dropped.append(1)

    bus.subscribe("day.ended", keep_fn)
    bus.subscribe("day.ended", drop_fn)

    bus.unsubscribe("day.ended", drop_fn)

    assert bus.emit("day.ended") == 1
    assert kept == [1]
    assert dropped == []


def test_unsubscribe_unknown_handler_is_noop():
    bus = EventBus()
    bus.unsubscribe("game.graduated", lambda **kw: None)
    assert bus.emit("game.graduated") == 0


def test_clear_drops_every_subscription():
    bus = EventBus()
    bus.subscribe("activity.done", lambda **kw: None)
    bus.clear()
    assert bus.emit("activity.done") == 0


def test_handlers_added_during_emit_do_not_run_in_same_emit():
    """emit 先对处理函数列表取快照，回调里新增订阅不会在同一轮触发。"""
    bus = EventBus()
    late: list[int] = []

    def first(**kw):
        bus.subscribe("t", lambda **kw2: late.append(1))

    bus.subscribe("t", first)

    assert bus.emit("t") == 1
    assert late == []
    assert bus.emit("t") == 2
    assert late == [1]
