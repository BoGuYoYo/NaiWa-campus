"""内容正向覆盖：24 个学期选项、12 个日常事件、6 个结局与 5 类内容错误。

期望值用测试内独立实现的裁剪逻辑计算，不复用 game.systems.effects，
避免“用被测实现证明被测实现”。
"""

from __future__ import annotations

import json
import shutil

import pytest

from game.systems import rng as rng_mod
from game.systems.content_db import RULES_DIR, ContentDB, ContentError, get_db

STAT_KEYS = ("academic", "stamina", "social", "interest")


# ---------------------------------------------------------------------------
# 期望值计算（独立实现）
# ---------------------------------------------------------------------------
def _clamp(value: int, low: int, high: int) -> int:
    return low if value < low else min(value, high)


def _expected_deltas(before: dict, effects: dict) -> dict[str, int]:
    stats = dict(before["stats"])
    mood = before["mood"]
    energy = before["energy"]
    relationships = dict(before["relationships"])
    deltas = {key: 0 for key in effects}

    for key in STAT_KEYS:  # 属性先落定，energy 的上限依赖体力
        if key in effects:
            new = _clamp(stats[key] + int(effects[key]), 0, 100)
            deltas[key] = new - stats[key]
            stats[key] = new

    if "mood" in effects:
        new = _clamp(mood + int(effects["mood"]), 0, 100)
        deltas["mood"] = new - mood
        mood = new

    for key, value in effects.items():
        if key.startswith("rel."):
            npc = key[4:]
            new = _clamp(relationships.get(npc, 0) + int(value), 0, 100)
            deltas[key] = new - relationships.get(npc, 0)
            relationships[npc] = new

    if "energy" in effects:
        upper = 80 + stats["stamina"] // 5
        new = _clamp(energy + int(effects["energy"]), 0, upper)
        deltas["energy"] = new - energy

    return deltas


def _target(cond: dict) -> int:
    value = int(cond["value"])
    return {">=": value, ">": value + 1, "<=": value, "<": value - 1, "==": value}[cond["op"]]


def _satisfy(state, conditions: list[dict]) -> None:
    for cond in conditions:
        ctype = cond["type"]
        if ctype == "any":
            _satisfy(state, [cond["items"][0]])
        elif ctype == "stat":
            state.stats[cond["key"]] = _target(cond)
        elif ctype == "counter":
            state.counters[cond["key"]] = _target(cond)
        elif ctype == "rel":
            state.relationships[cond["key"]] = _target(cond)
        elif ctype == "mood":
            state.mood = _target(cond)
        elif ctype == "energy":
            state.energy = min(_target(cond), state.max_energy())
        elif ctype == "semester":
            state.day_index = max(state.day_index, (int(cond["value"]) - 1) * 2)
        elif ctype == "flag":
            state.flags.add(cond["key"])
        elif ctype == "not_flag":
            state.flags.discard(cond["key"])
        else:  # pragma: no cover - 内容校验会先拦下
            raise AssertionError(f"未知条件类型 {ctype}")


# ---------------------------------------------------------------------------
# 24 个学期选项
# ---------------------------------------------------------------------------
def _semester_choices(db) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for event in db.events:
        if event["kind"] != "semester":
            continue
        for choice in event["choices"]:
            pairs.append((event["id"], choice["id"]))
    return pairs


CHOICES = _semester_choices(get_db())


@pytest.mark.parametrize("event_id,choice_id", CHOICES, ids=[f"{e}:{c}" for e, c in CHOICES])
def test_every_semester_choice_applies_declared_effects(state, events, db,
                                                       event_id, choice_id):
    event = db.event(event_id)
    choice = next(c for c in event["choices"] if c["id"] == choice_id)
    _satisfy(state, choice["conditions"])
    before = state.to_dict()

    result = events.choose(state, event_id, choice_id)

    assert result.deltas == _expected_deltas(before, choice["effects"])
    for flag in choice.get("add_flags", []):
        assert flag in state.flags
    for flag in choice.get("remove_flags", []):
        assert flag not in state.flags
    assert state.event_log[-1] == f"{event_id}:{choice_id}"
    if choice.get("next_event_id"):
        assert state.phase == "event"
        assert state.pending_event_id == choice["next_event_id"]
    else:
        assert state.phase == "campus"
        assert state.pending_event_id is None


def test_semester_choice_count_is_24(db):
    assert len(CHOICES) == 24


# ---------------------------------------------------------------------------
# 12 个日常事件
# ---------------------------------------------------------------------------
class _StubRng:
    """固定掷骰结果：必定触发，且指定选中的下标。"""

    def __init__(self, index: int) -> None:
        self.index = index

    def random(self) -> float:
        return 0.0

    def choice(self, seq):
        return seq[self.index]


@pytest.mark.parametrize("index", range(12))
def test_every_daily_event_applies(state, activity, db, monkeypatch, index):
    monkeypatch.setattr(rng_mod, "walk_rng", lambda *a, **k: _StubRng(index))
    row = db.daily_events[index]
    walk_effects = dict(db.activity("campus_walk")["effects"])

    combined = dict(walk_effects)
    for key, value in row["effects"].items():
        combined[key] = combined.get(key, 0) + value

    before = state.to_dict()
    result = activity.start(state, "campus_walk")

    assert result.triggered_event_id == row["id"]
    assert state.event_log[-1] == row["id"]
    assert result.deltas == _expected_deltas(before, combined)


# ---------------------------------------------------------------------------
# 6 个结局
# ---------------------------------------------------------------------------
ENDING_SETUPS = {
    "ending_academic": {
        "stats.academic": 70, "counters.library_count": 10, "flags": ["accepted_lab"],
    },
    "ending_club_leader": {
        "stats.social": 60, "counters.club_count": 10,
        "relationships.npc_sumo": 60, "flags": ["ran_for_president"],
    },
    "ending_creator": {
        "stats.interest": 60, "counters.create_count": 8, "flags": ["held_exhibition"],
    },
    "ending_digital": {
        "stats.interest": 60, "counters.games_count": 10, "flags": ["joined_game_jam"],
    },
    "ending_vibrant": {
        "stats.stamina": 55, "stats.social": 40, "mood": 70, "counters.exercise_count": 10,
    },
    "ending_balanced": {},
}


def _apply_setup(state, setup: dict) -> None:
    for path, value in setup.items():
        if path == "flags":
            state.flags.update(value)
            continue
        head, _, tail = path.partition(".")
        if tail:
            getattr(state, head)[tail] = value
        else:
            setattr(state, path, value)


@pytest.mark.parametrize("ending_id", list(ENDING_SETUPS), ids=list(ENDING_SETUPS))
def test_each_ending_is_reachable(state, endings, ending_id):
    _apply_setup(state, ENDING_SETUPS[ending_id])
    assert endings.evaluate(state).ending_id == ending_id


def test_creator_has_priority_over_digital(state, endings):
    """creator（优先级 3）与 digital（4）同时满足时取 creator。"""
    _apply_setup(state, {
        "stats.interest": 60,
        "counters.create_count": 8, "counters.games_count": 10,
        "flags": ["held_exhibition", "joined_game_jam"],
    })
    assert endings.evaluate(state).ending_id == "ending_creator"


# ---------------------------------------------------------------------------
# 内容错误路径
# ---------------------------------------------------------------------------
def _broken_db(tmp_path, mutate) -> ContentDB:
    rules = tmp_path / "rules"
    shutil.copytree(RULES_DIR, rules)
    path = rules / "events.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    mutate(data)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return ContentDB(rules)


def _event(data, event_id: str) -> dict:
    return next(evt for evt in data if evt["id"] == event_id)


def test_unknown_effect_key_is_rejected(tmp_path):
    def mutate(data):
        _event(data, "sem_1_club_fair")["choices"][0]["effects"]["luck"] = 3

    with pytest.raises(ContentError, match="未知效果键 luck"):
        _broken_db(tmp_path, mutate)


def test_unknown_condition_type_is_rejected(tmp_path):
    def mutate(data):
        _event(data, "sem_1_club_fair")["choices"][1]["conditions"] = [{"type": "weather"}]

    with pytest.raises(ContentError, match="未知条件类型 weather"):
        _broken_db(tmp_path, mutate)


def test_empty_any_items_is_rejected(tmp_path):
    def mutate(data):
        _event(data, "sem_1_club_fair")["choices"][1]["conditions"] = [
            {"type": "any", "items": []}
        ]

    with pytest.raises(ContentError, match="any 条件必须提供非空 items"):
        _broken_db(tmp_path, mutate)


def test_invalid_event_kind_is_rejected(tmp_path):
    def mutate(data):
        _event(data, "sem_1_club_fair")["kind"] = "boss"

    with pytest.raises(ContentError, match="kind 非法"):
        _broken_db(tmp_path, mutate)


def test_semester_event_without_free_choice_is_rejected(tmp_path):
    def mutate(data):
        for choice in _event(data, "sem_2_first_exam")["choices"]:
            choice["conditions"] = [{"type": "flag", "key": "never_happens"}]

    with pytest.raises(ContentError, match="无条件选项"):
        _broken_db(tmp_path, mutate)


def test_invalid_id_is_rejected(tmp_path):
    def mutate(data):
        _event(data, "sem_1_club_fair")["id"] = "Bad-ID"

    with pytest.raises(ContentError, match="ID 不符合"):
        _broken_db(tmp_path, mutate)


def test_non_object_effects_is_rejected(tmp_path):
    def mutate(data):
        _event(data, "sem_1_club_fair")["choices"][0]["effects"] = 5

    with pytest.raises(ContentError, match="effects 必须是对象"):
        _broken_db(tmp_path, mutate)


def test_condition_without_type_is_rejected(tmp_path):
    def mutate(data):
        _event(data, "sem_1_club_fair")["choices"][1]["conditions"] = [
            {"op": ">=", "value": 1}
        ]

    with pytest.raises(ContentError, match="条件缺少 type"):
        _broken_db(tmp_path, mutate)


def test_undefined_counter_is_rejected(tmp_path):
    def mutate(data):
        _event(data, "sem_1_club_fair")["choices"][1]["conditions"] = [
            {"type": "counter", "key": "no_such_counter", "op": ">=", "value": 1}
        ]

    with pytest.raises(ContentError, match="未定义的计数器"):
        _broken_db(tmp_path, mutate)


def test_unknown_npc_in_condition_is_rejected(tmp_path):
    def mutate(data):
        _event(data, "sem_1_club_fair")["choices"][1]["conditions"] = [
            {"type": "rel", "key": "npc_nobody", "op": ">=", "value": 1}
        ]

    with pytest.raises(ContentError, match="不存在的 NPC"):
        _broken_db(tmp_path, mutate)


def test_invalid_operator_is_rejected(tmp_path):
    def mutate(data):
        _event(data, "sem_1_club_fair")["choices"][1]["conditions"] = [
            {"type": "mood", "op": "!=", "value": 50}
        ]

    with pytest.raises(ContentError, match="运算符非法"):
        _broken_db(tmp_path, mutate)
