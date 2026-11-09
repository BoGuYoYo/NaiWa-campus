"""规则文件的损坏形态：加载器必须给出"哪个文件、什么问题"的人话报错。

覆盖的是"手抖改坏规则"的真实形态——JSON 截断、编码损坏、顶层结构错、
字段类型错乱、缺文件——而不是语义错误（那些见 test_content_coverage.py）。
每条用例断言 ContentError 且消息里带文件名，防止退化成运行期裸抛
JSONDecodeError / AttributeError。
"""

from __future__ import annotations

import json
import shutil

import pytest

from game.systems.content_db import RULE_FILES, RULES_DIR, ContentDB, ContentError


def _rules_dir(tmp_path):
    rules = tmp_path / "rules"
    rules.mkdir()
    for filename in RULE_FILES.values():
        shutil.copy2(RULES_DIR / filename, rules / filename)
    return rules


def _edit_json(path, mutate):
    data = json.loads(path.read_text(encoding="utf-8"))
    mutate(data)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def test_valid_copy_loads(tmp_path):
    """正向对照：复制目录本身必须能加载，排除 helper 的问题。"""
    db = ContentDB(_rules_dir(tmp_path))
    assert db.activity("eat_canteen") is not None


def test_truncated_json_names_file(tmp_path):
    rules = _rules_dir(tmp_path)
    path = rules / "activities.json"
    text = path.read_text(encoding="utf-8")
    path.write_text(text[: len(text) // 2], encoding="utf-8")

    with pytest.raises(ContentError, match=r"activities\.json.*JSON 解析失败"):
        ContentDB(rules)


def test_invalid_utf8_names_file(tmp_path):
    rules = _rules_dir(tmp_path)
    (rules / "npcs.json").write_bytes(b'[{"id": "npc_sumo", "name": "\xff\xfe"}]')

    with pytest.raises(ContentError, match=r"npcs\.json.*不是有效的 UTF-8"):
        ContentDB(rules)


def test_top_level_object_is_rejected(tmp_path):
    rules = _rules_dir(tmp_path)
    (rules / "npcs.json").write_text('{"id": "npc_sumo"}', encoding="utf-8")

    with pytest.raises(ContentError, match=r"npcs\.json.*顶层必须是 JSON 数组"):
        ContentDB(rules)


def test_non_object_element_is_rejected(tmp_path):
    rules = _rules_dir(tmp_path)

    def mutate(data):
        data[1] = "npc_sumo"

    _edit_json(rules / "npcs.json", mutate)
    with pytest.raises(ContentError, match=r"npcs\.json.*第 1 项必须是对象"):
        ContentDB(rules)


def test_missing_file_names_the_file(tmp_path):
    rules = _rules_dir(tmp_path)
    (rules / "npcs.json").unlink()

    with pytest.raises(ContentError, match=r"缺少规则文件.*npcs\.json"):
        ContentDB(rules)


def test_conditions_as_string_is_rejected(tmp_path):
    rules = _rules_dir(tmp_path)

    def mutate(data):
        _event(data, "sem_1_club_fair")["choices"][1]["conditions"] = "none"

    _edit_json(rules / "events.json", mutate)
    with pytest.raises(ContentError, match=r"events\.json.*conditions 必须是数组"):
        ContentDB(rules)


def test_effect_value_as_string_is_rejected(tmp_path):
    rules = _rules_dir(tmp_path)

    def mutate(data):
        _event(data, "sem_1_club_fair")["choices"][0]["effects"] = {"academic": "5"}

    _edit_json(rules / "events.json", mutate)
    with pytest.raises(ContentError, match=r"events\.json.*值必须是整数"):
        ContentDB(rules)


def test_condition_value_as_string_is_rejected(tmp_path):
    rules = _rules_dir(tmp_path)

    def mutate(data):
        _event(data, "sem_1_club_fair")["choices"][1]["conditions"] = [
            {"type": "mood", "op": ">=", "value": "50"}
        ]

    _edit_json(rules / "events.json", mutate)
    with pytest.raises(ContentError, match=r"events\.json.*value 必须是整数"):
        ContentDB(rules)


def _event(data, event_id):
    for event in data:
        if event["id"] == event_id:
            return event
    raise AssertionError(f"fixtures 里没有 {event_id}")
