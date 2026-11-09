"""条件 DSL 逐类型行为（手册 B7）。

内容用例只会走到"真实内容里出现过的条件"，这里补齐没被内容覆盖到的分支：
energy / not_flag / semester / any（含嵌套），以及三类错误：未知运算符、
未知属性、未知条件类型。
"""

from __future__ import annotations

import pytest

from game.systems import conditions
from game.systems.content_db import ContentError


def test_empty_condition_list_is_true(state):
    """空数组与 None 都表示"无条件"，恒真。"""
    assert conditions.evaluate_all(state, []) is True
    assert conditions.evaluate_all(state, None) is True


def test_all_conditions_must_pass(state):
    state.stats["academic"] = 50
    assert conditions.evaluate_all(state, [
        {"type": "stat", "key": "academic", "op": ">=", "value": 40},
        {"type": "mood", "op": "==", "value": state.mood},
    ]) is True
    assert conditions.evaluate_all(state, [
        {"type": "stat", "key": "academic", "op": ">=", "value": 40},
        {"type": "stat", "key": "academic", "op": ">", "value": 50},
    ]) is False


@pytest.mark.parametrize("op,expected", [
    (">=", True), (">", False), ("<=", True), ("<", False), ("==", True),
])
def test_energy_conditions(state, op, expected):
    """energy 分支与其余数值条件共用比较器，五个运算符都要成立。"""
    state.energy = 40
    assert conditions.evaluate(state, {"type": "energy", "op": op, "value": 40}) is expected


def test_flag_and_not_flag(state):
    state.flags.add("accepted_lab")
    assert conditions.evaluate(state, {"type": "flag", "key": "accepted_lab"}) is True
    assert conditions.evaluate(state, {"type": "not_flag", "key": "accepted_lab"}) is False
    assert conditions.evaluate(state, {"type": "not_flag", "key": "held_exhibition"}) is True


def test_semester_condition_uses_derived_semester_no(state):
    """semester 条件比较的是 day_index 派生的 semester_no，而不是 day_index 本身。"""
    state.day_index = 6
    assert state.semester_no == 4
    assert conditions.evaluate(state, {"type": "semester", "op": ">=", "value": 4}) is True
    assert conditions.evaluate(state, {"type": "semester", "op": ">=", "value": 5}) is False


def test_counter_and_rel_default_to_zero(state):
    assert conditions.evaluate(
        state, {"type": "counter", "key": "library_count", "op": "==", "value": 0}
    ) is True
    assert conditions.evaluate(
        state, {"type": "rel", "key": "npc_sumo", "op": "<", "value": 1}
    ) is True


def test_any_is_disjunction_and_supports_nesting(state):
    state.stats["academic"] = 5
    state.flags.discard("accepted_lab")
    assert conditions.evaluate(state, {"type": "any", "items": [
        {"type": "stat", "key": "academic", "op": ">=", "value": 50},
        {"type": "any", "items": [{"type": "flag", "key": "never_happens"}]},
        {"type": "stat", "key": "academic", "op": "==", "value": 5},
    ]}) is True


def test_any_with_no_matching_item_is_false(state):
    state.stats["academic"] = 5
    assert conditions.evaluate(state, {"type": "any", "items": [
        {"type": "stat", "key": "academic", "op": ">=", "value": 50},
    ]}) is False


def test_unknown_operator_is_rejected(state):
    with pytest.raises(ContentError, match="未知运算符"):
        conditions.evaluate(state, {"type": "mood", "op": "!=", "value": 50})


def test_unknown_stat_key_is_rejected(state):
    with pytest.raises(ContentError, match="未知属性"):
        conditions.evaluate(state, {"type": "stat", "key": "luck", "op": ">=", "value": 1})


def test_unknown_condition_type_is_rejected(state):
    with pytest.raises(ContentError, match="未知条件类型"):
        conditions.evaluate(state, {"type": "weather"})
