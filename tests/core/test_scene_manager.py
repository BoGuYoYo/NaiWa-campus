"""A 的 core 层单元测试：事件总线与场景管理器（不依赖 panda3d）。"""

from __future__ import annotations

import pytest

from game.core.event_bus import (
    TOPIC_ACTIVITY_DONE,
    TOPIC_SCENE_CHANGED,
    EventBus,
)
from game.core.scene_manager import SceneManager


class DummyScene:
    def __init__(self, scene_id, **kwargs):
        self.scene_id = scene_id
        self.kwargs = kwargs
        self.entered = False
        self.exited = False
        self.updates = 0.0

    def on_enter(self, **kwargs):
        self.entered = True
        self.kwargs.update(kwargs)

    def on_exit(self):
        self.exited = True

    def on_update(self, dt):
        self.updates += dt


def make_manager(factory_calls=None, fade=0.25):
    created = factory_calls if factory_calls is not None else []

    def factory(scene_id, kwargs):
        scene = DummyScene(scene_id, **kwargs)
        created.append(scene)
        return scene

    return SceneManager(app=None, factory=factory, bus=EventBus(), fade_seconds=fade), created


# --------------------------------------------------------------------------- #
# EventBus
# --------------------------------------------------------------------------- #
def test_subscribe_emit_and_unsubscribe():
    bus = EventBus()
    seen = []
    handler = lambda **data: seen.append(data)  # noqa: E731
    bus.subscribe(TOPIC_ACTIVITY_DONE, handler)
    assert bus.handler_count(TOPIC_ACTIVITY_DONE) == 1
    bus.emit(TOPIC_ACTIVITY_DONE, result="r")
    assert seen == [{"result": "r"}]
    bus.unsubscribe(TOPIC_ACTIVITY_DONE, handler)
    bus.emit(TOPIC_ACTIVITY_DONE, result="r2")
    assert len(seen) == 1


def test_handler_exception_is_isolated():
    bus = EventBus()
    calls = []

    def boom(**data):
        raise RuntimeError("handler failed")

    bus.subscribe(TOPIC_ACTIVITY_DONE, boom)
    bus.subscribe(TOPIC_ACTIVITY_DONE, lambda **data: calls.append(data))
    bus.emit(TOPIC_ACTIVITY_DONE, result=1)
    assert calls == [{"result": 1}]
    assert len(bus.errors) == 1
    assert bus.errors[0][0] == TOPIC_ACTIVITY_DONE


def test_emit_records_history():
    bus = EventBus()
    bus.emit("custom.topic", a=1)
    assert bus.emitted[-1][0] == "custom.topic"


# --------------------------------------------------------------------------- #
# SceneManager
# --------------------------------------------------------------------------- #
def test_start_enters_scene_and_fades_in():
    manager, created = make_manager()
    manager.start("MainMenu")
    assert created[0].entered
    assert manager.current_id == "MainMenu"
    assert manager.input_locked  # 淡入期间锁定
    manager.update(0.3)
    assert not manager.input_locked
    assert manager.fade_alpha == pytest.approx(0.0)


def test_change_waits_for_fade_out_then_swaps():
    manager, created = make_manager()
    manager.start("MainMenu")
    manager.update(0.3)

    manager.change("CampusScene", spawn="loc_gate")
    assert manager.is_transitioning()
    assert manager.fade_alpha == pytest.approx(0.0)
    manager.update(0.1)
    assert created[-1].scene_id == "MainMenu"  # 还没换
    manager.update(0.2)
    assert created[-1].scene_id == "CampusScene"
    assert created[-1].kwargs["spawn"] == "loc_gate"
    assert created[0].exited
    manager.update(0.3)
    assert not manager.is_transitioning()


def test_first_change_skips_fade_out():
    manager, created = make_manager()
    manager.change("CampusScene")
    assert created and created[0].scene_id == "CampusScene"
    assert created[0].entered


def test_overlays_lock_input_and_pop_in_order():
    manager, _created = make_manager()
    manager.start("CampusScene")
    manager.update(0.3)
    assert not manager.input_locked

    manager.push("TabPanel")
    assert manager.input_locked
    manager.push("PauseMenu")
    assert manager.top_overlay_id == "PauseMenu"
    assert manager.pop() == "PauseMenu"
    assert manager.top_overlay_id == "TabPanel"
    assert manager.pop() == "TabPanel"
    assert not manager.input_locked
    assert manager.pop() is None


def test_pop_all_clears_overlays():
    manager, _ = make_manager()
    manager.start("CampusScene")
    manager.push("TabPanel")
    manager.push("PauseMenu")
    assert manager.pop_all() == ["PauseMenu", "TabPanel"]
    assert manager.overlays == []


def test_scene_changed_event_emitted():
    bus = EventBus()
    seen = []
    bus.subscribe(TOPIC_SCENE_CHANGED, lambda **data: seen.append(data))
    manager = SceneManager(app=None, factory=lambda sid, kw: DummyScene(sid, **kw), bus=bus)
    manager.start("MainMenu")
    manager.update(0.3)
    manager.change("CampusScene")
    manager.update(0.3)
    assert seen[-1]["new"] == "CampusScene"
    assert seen[-1]["old"] == "MainMenu"


def test_update_scenes_forwards_dt():
    manager, created = make_manager()
    manager.start("CampusScene")
    manager.update_scenes(0.05)
    assert created[0].updates == pytest.approx(0.05)


def test_pending_change_is_replaced_by_later_request():
    manager, created = make_manager()
    manager.start("MainMenu")
    manager.update(0.3)
    manager.change("CampusScene")
    count = len(created)
    manager.change("GraduationScene", ending="ending_kaoyan")
    manager.update(0.3)
    assert len(created) == count + 1
    assert created[-1].scene_id == "GraduationScene"


# --------------------------------------------------------------------------- #
# on_ready：新场景就绪（淡入结束）后才允许 push 覆盖层
# --------------------------------------------------------------------------- #
def test_on_ready_runs_after_fade_in():
    manager, created = make_manager()
    manager.start("MainMenu")
    manager.update(0.3)
    seen = []
    manager.change("CampusScene", on_ready=lambda: seen.append(manager.base_id))

    manager.update(0.1)
    assert seen == []  # 还在淡出
    manager.update(0.2)
    assert seen == []  # 场景换了，但淡入还没结束
    manager.update(0.3)
    assert seen == ["CampusScene"]
    assert created[-1].scene_id == "CampusScene"


def test_on_ready_runs_once_only():
    manager, _created = make_manager()
    manager.start("CampusScene")
    manager.update(0.3)
    seen = []
    manager.change("MainMenu", on_ready=lambda: seen.append(1))
    for _ in range(10):
        manager.update(0.1)
    assert seen == [1]


def test_on_ready_runs_immediately_without_fade():
    manager, _created = make_manager(fade=0.0)
    manager.start("MainMenu")
    seen = []
    manager.change("CampusScene", on_ready=lambda: seen.append(manager.base_id))
    assert seen == ["CampusScene"]


def test_on_ready_exception_is_contained():
    manager, _created = make_manager()

    def boom():
        raise RuntimeError("overlay failed")

    manager.start("MainMenu", on_ready=boom)  # 不应把构造/main loop 带崩
    manager.update(0.3)
    assert manager.current_id == "MainMenu"
