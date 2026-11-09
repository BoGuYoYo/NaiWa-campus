"""规则加载期校验与缓存失效。

覆盖三件事：
    * 选项的 `next_event_id` 指向不存在的事件时，在**加载期**报错（P0-1）；
    * 关系效果键白名单：未知 NPC 抛错且不产生“部分生效”（P0-3）；
    * `get_db` 按规则 JSON 的 mtime 失效，未改动时复用同一实例（P1-7）。

所有用例都在 tmp_path 的规则副本上操作，不改动 content/rules。
"""

from __future__ import annotations

import json
import os
import shutil
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from game.systems.content_db import (
    RULES_DIR,
    ContentDB,
    ContentError,
    get_db,
    reset_cache,
)
from game.systems.effects import apply


def _copy_rules(tmp_path: Path) -> Path:
    rules = tmp_path / "rules"
    shutil.copytree(RULES_DIR, rules)
    return rules


def _edit_json(path: Path, mutate: Callable[[Any], None]) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    mutate(data)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# P0-1 链式事件目标在加载期校验
# ---------------------------------------------------------------------------
def test_next_event_id_target_must_exist(tmp_path):
    """选项指向不存在的事件时，ContentDB 构造即失败，消息含来源事件与目标 ID。"""
    rules = _copy_rules(tmp_path)

    def mutate(data):
        for event in data:
            if event["id"] != "sem_1_club_fair":
                continue
            for choice in event["choices"]:
                if choice["id"] == "fair_lab":
                    choice["next_event_id"] = "rel_not_exists"

    _edit_json(rules / "events.json", mutate)

    with pytest.raises(ContentError) as excinfo:
        ContentDB(rules)
    message = str(excinfo.value)
    assert "sem_1_club_fair" in message
    assert "rel_not_exists" in message


def test_next_event_id_format_is_checked(tmp_path):
    """next_event_id 也必须是合法 ID，防止内容写错成文案或空串。"""
    rules = _copy_rules(tmp_path)

    def mutate(data):
        for event in data:
            if event["id"] != "sem_1_club_fair":
                continue
            for choice in event["choices"]:
                if choice["id"] == "fair_lab":
                    choice["next_event_id"] = "Bad-Id"

    _edit_json(rules / "events.json", mutate)

    with pytest.raises(ContentError, match="next_event_id 非法"):
        ContentDB(rules)


# ---------------------------------------------------------------------------
# P0-3 关系效果键白名单
# ---------------------------------------------------------------------------
def test_unknown_relationship_target_is_rejected(state):
    """未知 NPC 抛错，且整批效果一个都不落地（先全量校验再写入）。"""
    before = state.to_dict()
    with pytest.raises(ContentError, match="npc_unknown"):
        apply(state, {"rel.npc_unknown": 5, "mood": 5})
    assert state.to_dict() == before


def test_known_relationship_target_applies(state):
    assert apply(state, {"rel.npc_sumo": 5}) == {"rel.npc_sumo": 5}
    assert state.relationships["npc_sumo"] == 5


def test_non_integer_effect_value_is_rejected(state):
    before = state.to_dict()
    with pytest.raises(ContentError, match="必须是整数"):
        apply(state, {"mood": 1.5, "energy": 1})
    assert state.to_dict() == before


# ---------------------------------------------------------------------------
# P1-7 规则库缓存的失效边界
# ---------------------------------------------------------------------------
def test_get_db_reuses_instance_when_rules_unchanged(tmp_path):
    reset_cache()
    rules = _copy_rules(tmp_path)
    first = get_db(rules)
    assert get_db(rules) is first


def _set_daily_limit(data, value: int) -> None:
    for activity in data:
        if activity["id"] == "eat_canteen":
            activity["daily_limit"] = value


def test_get_db_rebuilds_after_rules_change(tmp_path):
    reset_cache()
    rules = _copy_rules(tmp_path)
    assert get_db(rules).activity("eat_canteen")["daily_limit"] == 2

    path = rules / "activities.json"
    _edit_json(path, lambda data: _set_daily_limit(data, 3))
    # 显式推进 mtime，规避文件系统时间粒度过粗导致“改了但戳没变”
    future = time.time_ns() + 1_000_000_000
    os.utime(path, ns=(future, future))

    refreshed = get_db(rules)
    assert refreshed.activity("eat_canteen")["daily_limit"] == 3


def test_get_db_rebuilds_when_only_an_older_file_changes(tmp_path):
    """改动落在“非最新”文件上时也必须失效（戳是序列而非最大值）。"""
    reset_cache()
    rules = _copy_rules(tmp_path)
    activities = rules / "activities.json"
    events = rules / "events.json"

    base = time.time_ns() - 10_000_000_000
    os.utime(activities, ns=(base, base))
    os.utime(events, ns=(base + 5_000_000_000, base + 5_000_000_000))
    assert get_db(rules).activity("eat_canteen")["daily_limit"] == 2

    _edit_json(activities, lambda data: _set_daily_limit(data, 3))
    # 新 mtime 仍早于 events.json：若实现只比较最大值，这里会命中旧缓存
    os.utime(activities, ns=(base + 1_000_000_000, base + 1_000_000_000))

    assert get_db(rules).activity("eat_canteen")["daily_limit"] == 3
