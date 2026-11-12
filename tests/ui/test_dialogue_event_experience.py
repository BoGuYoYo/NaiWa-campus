"""Gameplay regressions for dialogue portraits, page counts, and choice presentation."""

from __future__ import annotations

from types import SimpleNamespace

from game.ui.dialogue_box import DialogueBox, _resolve_portrait_id
from game.ui.event_scene import EventScene


class _Node:
    def __init__(self) -> None:
        self.visible = True
        self.texture = None
        self.color = None

    def show(self) -> None:
        self.visible = True

    def hide(self) -> None:
        self.visible = False

    def clear_texture(self) -> None:
        self.texture = None

    def set_texture(self, texture) -> None:
        self.texture = texture

    def set_color(self, *color) -> None:
        self.color = color

    def remove_node(self) -> None:
        self.visible = False


class _Label(_Node):
    def __init__(self) -> None:
        super().__init__()
        self.text = ""

    def set_text(self, text) -> None:
        self.text = text


class _Body:
    def __init__(self) -> None:
        self._x = 108
        self._y = 188
        self._line_height = 18
        self.labels = []
        self.lines = []

    def set_lines(self, lines) -> None:
        self.lines = list(lines)


class _Transform:
    def to_aspect2d(self, x, y):
        return float(x), float(y)


class _Text:
    def get(self, text_id, **kwargs):
        return text_id

    def get_raw(self, text_id):
        return text_id

    def has(self, text_id):
        return False


class _Assets:
    def __init__(self, texture=None):
        self.requested = []
        self.texture = texture

    def load_texture(self, asset_id):
        self.requested.append(asset_id)
        return self.texture


def _dialogue(assets=None):
    box = DialogueBox.__new__(DialogueBox)
    box.text_db = _Text()
    box.transform = _Transform()
    box.assets = assets
    box.root = _Node()
    box.visible = False
    box.portrait = _Node()
    box.name_label = _Label()
    box.body = _Body()
    box.continue_mark = _Node()
    box._full_lines = []
    box._revealed_chars = 0
    box._total_chars = 0
    box._cps = 0
    box._typing_done_callback = None
    return box


def test_portrait_id_resolution_covers_all_fallback_states():
    assert _resolve_portrait_id({"speaker": None, "portrait": None}) == "portrait_naiwan_neutral"
    assert _resolve_portrait_id({"speaker": "npc_sumo", "portrait": None}) == "portrait_npc_sumo_neutral"
    assert _resolve_portrait_id({"speaker": "npc_sumo", "portrait": "portrait_npc_sumo_happy"}) == "portrait_npc_sumo_happy"


def test_pure_narration_uses_protagonist_neutral_portrait():
    box = _dialogue(_Assets(texture="naiwan-neutral"))

    box.show_page({"speaker": None, "portrait": None, "lines": ["叙述"]})

    assert box.assets.requested == ["portrait_naiwan_neutral"]
    assert box.portrait.visible is True
    assert box.portrait.texture == "naiwan-neutral"
    assert box.portrait.color == (1, 1, 1, 1)
    assert box.body._x == 108


def test_speaker_without_portrait_uses_neutral_fallback():
    box = _dialogue(_Assets(texture="loaded-texture"))

    box.show_page({"speaker": "npc_sumo", "portrait": None, "lines": ["你好"]})

    assert box.assets.requested == ["portrait_npc_sumo_neutral"]
    assert box.portrait.visible is True
    assert box.portrait.texture == "loaded-texture"
    # 与旁白那条对齐：成功路径必须把颜色复位成白色。
    # 若有人把复位逻辑挪进"仅旁白"分支，这条会红——它守的是"所有成功路径都复位"。
    assert box.portrait.color == (1, 1, 1, 1)
    assert box.body._x == 108


def test_requested_portrait_load_failure_keeps_diagnostic_placeholder(caplog):
    box = _dialogue(_Assets(texture=None))

    box.show_page({"speaker": "npc_sumo", "portrait": "portrait_npc_sumo_happy", "lines": ["你好"]})

    assert box.portrait.visible is True
    assert box.portrait.texture is None
    assert "asset.missing asset_id=portrait_npc_sumo_happy" in caplog.text
    # 灰块是"加载失败"的**唯一**诊断信号：成功分支必须复位成白色，
    # 失败分支必须显式涂成 #4A5578。两条都要断言，否则语义会静默漂移。
    from game.ui import theme as _theme

    assert box.portrait.color == _theme.hex_to_rgba("#4A5578")


def test_dialogue_page_indicator_only_shows_for_multi_page_event():
    box = DialogueBox.__new__(DialogueBox)
    box.page_label = _Label()

    box.set_page_indicator(5, 5)
    assert box.page_label.visible is True
    assert box.page_label.text == "5/5"

    box.set_page_indicator(1, 1)
    assert box.page_label.visible is False


class _Panel(_Node):
    def is_shown(self):
        return self.visible


class _ChoiceCursor:
    def __init__(self, count):
        self.items = [(f"choice_{i}", True, None) for i in range(count)]
        self.index = 0
        self.lock_reason = None
        self.confirm_calls = 0

    def confirm(self):
        self.confirm_calls += 1
        return (self.items[0][0], None)


class _EventDialogue:
    def __init__(self):
        self.pages = []
        self.continue_mark = _Node()

    def show_page(self, page):
        self.pages.append(page)

    def set_page_indicator(self, current, total):
        pass

    def advance(self):
        return False



def _event_scene(choice_count):
    scene = EventScene.__new__(EventScene)
    scene._pages = [{"lines": ["last page"]}]
    scene._page_index = 0
    scene._cursor = _ChoiceCursor(choice_count)
    scene._choice_stage = False
    scene._showing_result = False
    scene.dialogue = _EventDialogue()
    scene.panel = _Panel()
    scene.page_hint = _Node()
    scene.choice_labels = [_Label() for _ in range(choice_count)]
    scene.on_choose = lambda _event, choice: scene.selected.append(choice)
    scene._event_id = "story_opening"
    scene.selected = []
    scene.lock_hint = _Label()
    scene.text_db = _Text()
    return scene


def test_single_continue_choice_hides_panel_but_space_still_selects():
    scene = _event_scene(1)

    scene._show_current_page()
    # 最后一页只显示正文 + 翻页提示；再按一次 Space 才算"继续"
    assert scene._choice_stage is False
    assert scene.panel.visible is False
    assert scene.choice_labels[0].visible is False
    assert scene.page_hint.visible is True

    scene.on_space()

    assert scene._cursor.confirm_calls == 1
    assert scene.selected == ["choice_0"]


def test_multiple_choices_keep_choice_panel():
    scene = _event_scene(2)

    scene._show_current_page()
    # 旧版最后一页就把面板摊开，玩家"读完这页"按一下 Space 就替自己选了第一项
    assert scene._choice_stage is False
    assert scene.panel.visible is False
    assert not any(label.visible for label in scene.choice_labels)

    scene.on_space()

    assert scene._choice_stage is True
    assert scene.panel.visible is True
    assert all(label.visible for label in scene.choice_labels)
