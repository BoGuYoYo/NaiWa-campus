"""结局回顾用边界用例。

B-T13（兜底结局）、B-T14（优先级）与六个结局的正向用例见
tests/expected/unit_expect.json 与 test_content_coverage.py。
"""

from __future__ import annotations


def test_highlights_contains_top_counters_and_semester_choices(state, endings):
    state.counters.update({"library_count": 12, "class_count": 9, "walk_count": 4,
                           "rest_count": 1})
    state.event_log.extend(["sem_1_club_fair:fair_lab", "daily_sunset",
                            "sem_2_first_exam:cram"])
    result = endings.evaluate(state)
    assert result.highlights[:3] == ["library_count×12", "class_count×9", "walk_count×4"]
    assert "sem_1_club_fair:fair_lab" in result.highlights
    assert "sem_2_first_exam:cram" in result.highlights
    assert "daily_sunset" not in result.highlights


def test_highlights_empty_for_new_game(state, endings):
    assert endings.evaluate(state).highlights == []
