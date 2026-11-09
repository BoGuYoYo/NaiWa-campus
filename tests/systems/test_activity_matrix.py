"""九个活动的接口矩阵（B-ST-05）。

对 spec_data.ACTIVITY_IDS 全量参数化，逐项验证：
    can_start 只读 / preview 名义值 / start 生效 / 精力边界 / 每日上限数据契约
"""

from __future__ import annotations

import pytest

from game.systems import spec_data

ACTIVITY_IDS = spec_data.ACTIVITY_IDS
NEGATIVE_COST_IDS = [act["id"] for act in spec_data.ACTIVITIES
                     if int(act["effects"].get("energy", 0)) < 0]


@pytest.mark.parametrize("activity_id", ACTIVITY_IDS)
def test_can_start_is_read_only(state, activity, activity_id):
    """满精力新游戏下 9 个活动都可执行，且前置检查不修改状态。"""
    before = state.to_dict()
    assert activity.can_start(state, activity_id) == (True, None)
    assert state.to_dict() == before


@pytest.mark.parametrize("activity_id", ACTIVITY_IDS)
def test_preview_returns_nominal_effects(state, activity, db, activity_id):
    """preview 返回该活动的名义变化，且不修改状态。"""
    before = state.to_dict()
    expected = {k: int(v) for k, v in db.activity(activity_id)["effects"].items()}
    if db.activity(activity_id).get("halve_academic_on_low_mood") and state.mood < 30:
        expected["academic"] //= 2
    assert activity.preview(state, activity_id) == expected
    assert state.to_dict() == before


@pytest.mark.parametrize("activity_id", ACTIVITY_IDS)
def test_start_applies_counters_slot_and_text(state, activity, db, activity_id):
    """start 后计数器/当日计数/时段/文案/增量键都正确。"""
    row = db.activity(activity_id)
    counter = row["counter"]
    effects = row["effects"]

    result = activity.start(state, activity_id)

    assert result.ok is True
    assert result.error_code is None
    assert state.counters[counter] == 1
    assert state.today_counts[activity_id] == 1
    assert state.action_slot == 1
    assert result.text_ids == [f"act.{activity_id}.result.1"]
    assert set(result.deltas) <= set(effects), result.deltas
    assert result.day_finished is False


@pytest.mark.parametrize("activity_id", NEGATIVE_COST_IDS)
def test_energy_boundary(state, activity, db, activity_id):
    """负消耗活动：差 1 点精力被拒，刚好够时成功。"""
    cost = -int(db.activity(activity_id)["effects"]["energy"])
    state.energy = cost - 1
    assert activity.can_start(state, activity_id) == (False, "E_LOW_ENERGY")

    state.energy = cost
    assert activity.can_start(state, activity_id) == (True, None)
    assert activity.start(state, activity_id).ok is True


def test_daily_limit_contract(db):
    """每日次数上限只存在于食堂，且为 2 次。"""
    limits = {act["id"]: act.get("daily_limit") for act in db.activities}
    assert limits.pop("eat_canteen") == 2
    assert all(value is None for value in limits.values()), limits


def test_preview_reflects_low_mood_halving(state, activity):
    """心情低迷时，上课与图书馆的预览学业收益减半。"""
    state.mood = 29
    assert activity.preview(state, "attend_class")["academic"] == 2
    assert activity.preview(state, "library_study")["academic"] == 2
    state.mood = 30
    assert activity.preview(state, "attend_class")["academic"] == 4
    assert activity.preview(state, "library_study")["academic"] == 5


def test_start_unknown_activity_returns_error_without_side_effects(state, activity):
    """未知活动 id：start 返回 E_UNKNOWN_ID 而不是断言/空引用，且状态不变。"""
    before = state.to_dict()
    result = activity.start(state, "no_such_activity")
    assert result.ok is False
    assert result.error_code == spec_data.E_UNKNOWN_ID
    assert state.to_dict() == before
