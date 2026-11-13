"""随机策略不变式（B-T23）。

局数与阈值取自 tests/expected/unit_expect.json 的 B-T23 规格。
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from game.core.state import GameState
from game.sim import simulator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SPEC = json.loads((PROJECT_ROOT / "tests" / "expected" / "unit_expect.json")
                  .read_text(encoding="utf-8"))
FUZZ = next(case for case in SPEC["cases"] if case["id"] == "B-T23")
RUNS = FUZZ["runs"]
SPECIALIST_MAX = FUZZ["invariants"]["specialist_rate_max"]
MEDIOCRE_MIN = FUZZ["invariants"]["mediocre_rate_min"]


@pytest.mark.slow
def test_b_t23_random_no_violation():
    """B-T23：随机游玩无异常、字段不越界、每局都有结局。"""
    counter: Counter[str] = Counter()
    for seed in range(RUNS):
        report = simulator.run("random", seed)
        final = report["final"]

        assert final["day_index"] == 16, seed
        assert report["ending_id"], seed
        assert 0 <= final["mood"] <= 100, seed
        for key, value in final["stats"].items():
            assert 0 <= value <= 100, (seed, key, value)
        # 上限直接取引擎实现，避免测试复制公式后“自洽地错”
        assert 0 <= final["energy"] <= GameState.from_dict(final).max_energy(), seed
        for npc, value in final["relationships"].items():
            assert 0 <= value <= 100, (seed, npc, value)
        assert len(report["actions"]) == 48, seed

        counter[report["ending_id"]] += 1

    for ending_id, count in counter.items():
        if ending_id == "ending_mediocre":
            continue
        assert count / RUNS <= SPECIALIST_MAX, (ending_id, count)
    assert counter["ending_mediocre"] / RUNS >= MEDIOCRE_MIN, counter
