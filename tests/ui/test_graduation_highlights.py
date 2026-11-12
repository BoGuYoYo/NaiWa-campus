"""毕业「四年回顾」文案守卫。

BUG：EndingService.highlights 产出的是「计数器×次数」「事件:选项」这类内部键，
GraduationScene 直接 get_raw() 渲染，玩家看到的是 `#class_count×3`、
`#sem_1_club_fair:fair_club`。这里钉住三件事：
1. 两种内部键都能翻成中文；
2. 解析不出来的条目返回空串（宁可不显示，也不印内部 ID）；
3. 真实一局产生的 highlights 全部可解析。
"""

from __future__ import annotations

import os

import pytest

from game.core.state import new_state
from game.systems.ending_service import EndingService
from game.ui.graduation_scene import GraduationScene
from game.ui.text_db import TextDB

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


@pytest.fixture(scope="module")
def text_db() -> TextDB:
    return TextDB.load(os.path.join(ROOT, "content"))


@pytest.fixture()
def scene(text_db) -> GraduationScene:
    obj = GraduationScene.__new__(GraduationScene)
    obj.text_db = text_db
    return obj


def test_counter_highlight_is_localized(scene):
    assert scene._highlight_line("class_count×3") == "上课 3 次"
    assert scene._highlight_line("library_count×12") == "泡图书馆 12 次"


def test_semester_choice_highlight_uses_choice_label(scene):
    assert scene._highlight_line("sem_1_club_fair:fair_club") == "跟李振兴去社团摊位"


def test_unknown_highlight_is_dropped_not_printed(scene):
    for entry in ("daily_sunset", "nope×2", "", None):
        line = scene._highlight_line(entry)
        assert line == ""
        assert not line.startswith("#")


def test_full_run_highlights_all_resolve(scene):
    state = new_state(seed=42)
    state.counters.update({"class_count": 9, "exercise_count": 4})
    state.event_log.append("sem_2_first_exam:cram")
    ending = EndingService().evaluate(state)
    resolved = [scene._highlight_line(h) for h in ending.highlights]
    assert resolved and all(resolved)
    assert not any(line.startswith("#") for line in resolved)
