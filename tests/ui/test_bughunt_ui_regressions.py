"""A 的 bug 猎杀回归测试（界面 / 场景适配层）。

对应 reports/review/bughunt_fix.md 里 H5~H8、M1、M9 与"事件交互"几条。
全部不启动窗口：控件用 __new__ 或假 widget 装配，只验证状态机。
"""

from __future__ import annotations

import pytest

from game.core.world_scene import (
    DaySummarySceneAdapter,
    PauseMenuSceneAdapter,
    SaveMenuSceneAdapter,
    WorldSceneBase,
)
from game.ui.event_scene import EventScene
from game.ui.graduation_scene import GraduationScene, PAGES


# --------------------------------------------------------------------------- #
# 假件
# --------------------------------------------------------------------------- #
class FakeInput:
    def bind(self, _owner, _event, _handler):
        pass

    def unbind(self, _owner):
        pass


class FakeWidget:
    def __init__(self, visible=True):
        self.visible = visible
        self.handlers = {}

    def show(self):
        self.visible = True

    def hide(self):
        self.visible = False

    def destroy(self):
        self.visible = False

    def move(self, _direction):
        pass

    def confirm(self):
        pass

    def cancel(self):
        pass

    def open(self, *_args, **_kwargs):
        pass


class FakeScenes:
    def __init__(self, base_scene=None, overlays=None, transitioning=False):
        self.base_scene = base_scene
        self.overlays = list(overlays or [])
        self._transitioning = transitioning
        self.popped = []
        self.pushed = []

    def is_transitioning(self):
        return self._transitioning

    def push(self, scene_id, **kwargs):
        self.pushed.append((scene_id, kwargs))
        self.overlays.append((scene_id, FakeWidgetScene(FakeWidget())))

    def pop(self):
        if self.overlays:
            return self.overlays.pop()[0]
        return None

    def pop_all(self):
        popped = [sid for sid, _ in self.overlays]
        self.overlays.clear()
        return popped


class FakeWidgetScene:
    def __init__(self, widget):
        self.widget = widget


class FakeApp:
    def __init__(self, scenes):
        self.scenes = scenes
        self.input = FakeInput()
        self.audio = None
        self.flow = None
        self.saves = None


# --------------------------------------------------------------------------- #
# H7：毕业最后一页连按两下不能崩
# --------------------------------------------------------------------------- #
def test_graduation_last_page_double_press_calls_back_once():
    scene = GraduationScene.__new__(GraduationScene)
    scene._page = len(PAGES) - 1
    scene._closed = False
    scene._render = lambda: None
    scene.hide = lambda: None
    calls = []
    scene.on_back_to_menu = lambda: calls.append(True)

    scene.on_space()
    scene.on_space()      # 黑场期间的第二下
    scene.on_space()

    assert calls == [True]


# --------------------------------------------------------------------------- #
# H5 / H6：暂停菜单与子面板
# --------------------------------------------------------------------------- #
def test_pause_menu_resume_pops_the_overlay_and_unpauses():
    flows = []

    class FakeFlow:
        paused = True

        def set_paused(self, value):
            self.paused = bool(value)
            flows.append(self.paused)

    app = FakeApp(FakeScenes())
    app.flow = FakeFlow()
    adapter = PauseMenuSceneAdapter(app)
    adapter.widget = FakeWidget()
    adapter.widget.confirm = lambda: "ui.menu.resume"
    app.scenes.overlays.append(("PauseMenu", adapter))

    adapter._confirm()

    assert app.scenes.overlays == [], "「继续」必须把暂停菜单从场景栈里摘掉"
    assert app.flow.paused is False
    assert flows == [False]


def test_save_menu_restores_the_pause_menu_behind_it():
    pause = FakeWidgetScene(FakeWidget())
    app = FakeApp(FakeScenes(base_scene=FakeWidgetScene(FakeWidget()), overlays=[("PauseMenu", pause)]))
    adapter = SaveMenuSceneAdapter(app)
    widget = FakeWidget(visible=False)
    adapter._make_widget = lambda: widget
    app.scenes.overlays.append(("SaveMenu", adapter))

    adapter.on_enter()
    assert pause.widget.visible is False      # 打开存档界面时藏起暂停菜单

    app.scenes.overlays.pop()
    adapter.on_exit()
    assert pause.widget.visible is True, "从暂停菜单存档/读档返回后必须看得见暂停菜单"


# --------------------------------------------------------------------------- #
# H8：黑场期间 Tab / Esc 不能开面板
# --------------------------------------------------------------------------- #
class _WorldStub(WorldSceneBase):
    scene_id = "campus"

    def __init__(self, app):
        self.app = app
        self._state = type("S", (), {"phase": "campus"})()
        self.tutorial = type("T", (), {"notify": staticmethod(lambda *_a, **_k: None)})()

    def build_scene(self, parent):        # pragma: no cover - 不会被调用
        raise NotImplementedError

    def _apply_scene_camera(self):        # pragma: no cover
        pass

    def _update_scene_camera(self, dt, force):   # pragma: no cover
        pass


def test_tab_and_escape_are_ignored_while_the_screen_fades():
    app = FakeApp(FakeScenes(transitioning=True))
    app.flow = type("F", (), {"set_paused": lambda self, v: None})()
    scene = _WorldStub(app)

    scene._on_tab()
    scene._on_escape()

    assert app.scenes.pushed == [], "黑场期间不能 push 任何覆盖层"


def test_tab_still_works_after_the_fade():
    app = FakeApp(FakeScenes(transitioning=False))
    app.flow = type("F", (), {"set_paused": lambda self, v: None})()
    scene = _WorldStub(app)

    scene._on_tab()
    assert [sid for sid, _ in app.scenes.pushed] == ["TabPanel"]


# --------------------------------------------------------------------------- #
# M：日结算标题的天数
# --------------------------------------------------------------------------- #
class _SummaryWidget(FakeWidget):
    def __init__(self):
        super().__init__()
        self.shown = None

    def move(self, _direction):
        pass

    def confirm(self):
        pass

    def show_summary(self, result, day, action_names):
        self.shown = (day, list(action_names))


def test_day_summary_label_uses_the_finished_day_not_the_modulo_day():
    app = FakeApp(FakeScenes())
    app.flow = type("F", (), {
        "state": type("S", (), {"day_index": 2, "day": 1})(),
        "activity_log_today": lambda self: [],
    })()
    adapter = DaySummarySceneAdapter(app)
    widget = _SummaryWidget()
    adapter._make_widget = lambda: widget

    adapter.on_enter(result=type("R", (), {"new_day_index": 2})())
    assert widget.shown[0] == 2, "第 2 天结束必须显示「第 2 天」，不是永远第 1 天"

    adapter.widget = widget
    adapter.apply(result=type("R", (), {"new_day_index": config_total_days_last()})())
    assert widget.shown[0] == 2    # 第 16 天结束 = 第 4 学年下学期第 2 天


def config_total_days_last() -> int:
    from game import config

    return config.TOTAL_DAYS


# --------------------------------------------------------------------------- #
# 事件：结果页打字机 / 鼠标点击 / 文本速度
# --------------------------------------------------------------------------- #
class _Dialogue:
    def __init__(self, revealed=0, total=12, advance_result=True):
        self._revealed_chars = revealed
        self._total_chars = total
        self._advance = advance_result
        self.advance_calls = 0
        self._cps = 40.0

    def advance(self):
        self.advance_calls += 1
        return self._advance

    def set_text_speed(self, name):
        from game.ui import theme

        self._cps = theme.chars_per_second(name)


class _Cursor:
    """最小 MenuCursor 替身：两个可用选项，index/lock_reason 齐备。"""

    def __init__(self):
        self.items = [("a", True, None), ("b", True, None)]
        self.index = 0
        self.lock_reason = None
        self.confirm_calls = 0

    def move(self, _direction):
        pass

    def confirm(self):
        self.confirm_calls += 1
        return ("continue", None)


def _event_scene(revealed=0, total=12) -> EventScene:
    scene = EventScene.__new__(EventScene)
    scene.root = FakeWidget()
    scene._pages = [{"lines": ["最后一页"]}]
    scene._page_index = 0
    scene._cursor = _Cursor()
    scene._choice_stage = False
    scene._showing_result = False
    scene.dialogue = _Dialogue(revealed=revealed, total=total, advance_result=revealed < total)
    scene.panel = type("P", (), {"is_shown": lambda self: True, "hide": lambda self: None,
                                 "show": lambda self: None})()
    scene.page_hint = FakeWidget()
    scene.choice_labels = []
    scene.lock_hint = FakeWidget()
    scene.lock_hint.set_text = lambda _t: None
    scene.text_db = type("T", (), {
        "get": staticmethod(lambda _k, **_kw: "hint"),
        "has": staticmethod(lambda _k: False),
        "get_raw": staticmethod(lambda _k: "hint"),
    })()
    scene.selected = []
    scene._event_id = "story_opening"
    scene.on_choose = lambda _e, choice: scene.selected.append(choice)
    scene.on_finished = lambda _eid: scene.selected.append("finished")
    return scene


def test_result_page_typewriter_is_finished_before_it_closes():
    scene = _event_scene()
    scene._showing_result = True
    scene.on_finished = lambda _eid: scene.selected.append("finished")

    scene.on_space()

    assert scene.dialogue.advance_calls == 1
    assert scene.selected == [], "结果页还在逐字显示时，第一下按键只应该补全文字"

    scene.dialogue._advance = False
    scene.on_space()
    assert scene.selected == ["finished"]


def test_click_does_not_pick_a_choice():
    scene = _event_scene()
    scene._choice_stage = True

    scene.on_click()

    assert scene._cursor.confirm_calls == 0, "选项摊开后点画面任何位置都不能替玩家选"
    assert scene.selected == []


def test_click_still_advances_normal_dialogue():
    scene = _event_scene(revealed=12, total=12)
    scene.dialogue._advance = False   # 本页已整页显示

    scene.on_click()

    # 点击等价于 Space：读完最后一页 → 展开选项，不替玩家选
    assert scene._choice_stage is True
    assert scene._cursor.confirm_calls == 0


def test_text_speed_setting_reaches_the_typewriter():
    from game.ui import theme

    scene = _event_scene()
    scene.set_text_speed("slow")
    slow = scene.dialogue._cps
    scene.set_text_speed("fast")
    assert slow == theme.chars_per_second("slow")
    assert scene.dialogue._cps == theme.chars_per_second("fast")
    assert scene.dialogue._cps > slow


# --------------------------------------------------------------------------- #
# 风险项：唯一选项被锁 / 教程横幅一直不消失
# --------------------------------------------------------------------------- #
def test_single_locked_choice_does_not_confirm_and_can_be_left():
    scene = _event_scene()
    scene._cursor.items = [("only", False, "evt.x.lock.only")]
    scene._cursor.index = 0

    scene._open_choices()
    assert scene._cursor.confirm_calls == 0, "唯一选项被锁时不能替玩家确认"

    scene._choice_stage = True
    scene.dialogue._advance = False        # 打字机已结束
    scene.on_escape()
    assert scene.selected == ["finished"], "全锁事件必须允许 Esc 离开，不能永久卡在选项页"


def test_tutorial_banner_times_out_instead_of_hanging():
    from game.ui import theme
    from game.ui.tutorial import TutorialController

    class _State:
        def __init__(self):
            self.tutorial_done = set()
            self.day_index = 0

    class _Text:
        def get(self, key, **_kw):
            return key

    controller = TutorialController(_State(), _Text())
    controller.notify("enter_campus")
    assert controller.active_step == "tut.move"

    controller.notify("tick", dt=theme.TUTORIAL_STEP_TIMEOUT_SECONDS + 1.0)
    assert controller.active_step is None, "教程横幅必须能自己消失，不能永久占位"
