"""夹具与正式文本的自检测试。

- 夹具结构符合独立契约（事件 3 选项 1 锁定、结果固定 deltas）；
- 正式 strings.json / dialogues.json 通过 TextDB.validate()（D-07 的
  基础部分：无缺失引用结构、无超长行、无非法 ID）。
"""

from __future__ import annotations

import json
import os

from game.ui.text_db import TextDB


def test_event_fixture_has_three_choices_one_locked(fixture_events):
    event = fixture_events["event_fixture_01"]
    choices = event["choices"]
    assert len(choices) == 3
    locked = [c for c in choices if not c["enabled"]]
    assert len(locked) == 1
    assert locked[0]["lock_reason_id"] == "c"


def test_result_fixture_fixed_deltas(fixture_results):
    result = fixture_results["result_library"]
    assert result["deltas"] == {"academic": 5, "energy": -20}
    assert result["text_ids"] == ["ui.test.act.result.1"]
    blocked = fixture_results["result_blocked"]
    assert blocked["error_code"] == "E_LOW_ENERGY"


def test_assets_fixture_all_flat_colors(fixture_assets):
    for asset_id, spec in fixture_assets["assets"].items():
        assert spec["kind"] == "flat_color", asset_id


def test_fixture_text_db_resolves_fixture_pages(fixture_text_db, fixture_events):
    event = fixture_events["event_fixture_01"]
    for page_id in event["page_text_ids"]:
        page = fixture_text_db.get_dialogue(page_id)
        assert page is not None
        assert page["lines"]


def test_official_strings_pass_validation(project_root):
    """正式文本零问题（行 ≤26、页 ≤4 行、选项 ≤12 字等）。"""
    base = os.path.join(project_root, "content", "text", "zh_CN")
    with open(os.path.join(base, "strings.json"), "r", encoding="utf-8") as f:
        strings = json.load(f)
    with open(os.path.join(base, "dialogues.json"), "r", encoding="utf-8") as f:
        dialogues = json.load(f)
    problems = TextDB(strings, dialogues).validate()
    assert problems == []


def test_official_content_covers_required_ids(project_root):
    """交付内容覆盖：9 活动、8 学期事件、9 关系事件、12 日常、6 结局。"""
    base = os.path.join(project_root, "content", "text", "zh_CN")
    with open(os.path.join(base, "strings.json"), "r", encoding="utf-8") as f:
        strings = json.load(f)

    activities = {k.split(".")[1] for k in strings if k.startswith("act.") and k.endswith(".name")}
    assert len(activities) == 9

    semester_events = {k.split(".")[1] for k in strings if k.startswith("evt.sem_") and k.endswith(".title")}
    assert len(semester_events) == 8

    rel_events = {k.split(".")[1] for k in strings if k.startswith("evt.rel_") and k.endswith(".title")}
    assert len(rel_events) == 9

    daily = {k.split(".")[1] for k in strings if k.startswith("daily.") and k.endswith(".title")}
    assert len(daily) == 12

    endings = {k.split(".")[1] for k in strings if k.startswith("ending.") and k.endswith(".title")}
    assert len(endings) == 5

    npc = {k.split(".")[1] for k in strings if k.startswith("npc.") and k.endswith(".name")}
    assert npc == {"sumo", "chenlang", "xiaoyou"}

    for err_id in ("err.no_slot", "err.low_energy", "err.daily_limit", "err.already_talked",
                   "err.wrong_phase", "err.unknown_id", "err.choice_locked"):
        assert err_id in strings, err_id


def test_official_dialogues_cover_all_events(project_root):
    """开场 5 页 + 8 学期事件 + 9 关系事件均有分页正文。"""
    base = os.path.join(project_root, "content", "text", "zh_CN")
    with open(os.path.join(base, "dialogues.json"), "r", encoding="utf-8") as f:
        dialogues = json.load(f)

    opening_pages = [k for k in dialogues if k.startswith("evt.story_opening.body.")]
    assert len(opening_pages) == 5

    for n in range(1, 9):
        pages = [k for k in dialogues if k.startswith(f"evt.sem_{n}_") ]
        assert pages, f"sem_{n} 缺少分页"

    for npc in ("sumo", "chenlang", "xiaoyou"):
        for i in (1, 2, 3):
            pages = [k for k in dialogues if k.startswith(f"evt.rel_npc_{npc}_{i}.body.")]
            assert len(pages) >= 3, f"rel_npc_{npc}_{i} 需要 3~5 页"
