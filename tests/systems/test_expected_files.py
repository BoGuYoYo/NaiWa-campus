"""期望基线文件的有效性（防止基线腐烂）。

`strategies.json` 与 `random_3000.json` 是交付给 E 的回归基准，如果没人读取，
规格一变它们就会悄悄过期。这里把它们变成活断言。
"""

from __future__ import annotations

from game.systems import spec_data, spec_export


def test_strategies_baseline_matches_spec_data(expected_loader):
    """策略基线必须与 spec_data 完全一致（改策略却没重新导出会失败）。"""
    baseline = expected_loader("strategies.json")
    assert set(baseline) == set(spec_data.STRATEGY_NAMES)
    assert baseline == spec_export.build_strategies()


def test_random_baseline_covers_all_endings(expected_loader):
    """随机基线必须覆盖 6 个结局，且守住手册 B9 的设计意图。"""
    data = expected_loader("random_3000.json")
    ending_ids = {ending["id"] for ending in spec_data.ENDINGS}
    documented = data["documented"]
    measured = data["measured"]

    assert set(documented) == ending_ids
    assert set(measured) == ending_ids
    assert sum(documented.values()) == 3000
    assert sum(measured.values()) == 3000

    for ending_id, count in measured.items():
        if ending_id == "ending_balanced":
            continue
        assert count / 3000 <= data["invariants"]["specialist_rate_max"], ending_id
    assert measured["ending_balanced"] / 3000 >= data["invariants"]["balanced_rate_min"]
