"""固定策略回归与存档续跑（B-T21、B-T22）。

参数（策略名、种子区间）统一取自 tests/expected/unit_expect.json，
避免规格与用例两处维护。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from game.core.state import GameState
from game.sim import simulator
from game.systems import spec_data

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SPEC = json.loads((PROJECT_ROOT / "tests" / "expected" / "unit_expect.json")
                  .read_text(encoding="utf-8"))
CASES = {case["id"]: case for case in SPEC["cases"]}
BATCH = CASES["B-T21"]
RESUME = CASES["B-T22"]
STRATEGIES = BATCH["strategies"]
SEED_FROM = BATCH["seeds"]["from"]
SEED_TO = BATCH["seeds"]["to"]


def test_case_parameters_match_project():
    """规格里的策略名必须与工程定义一致，否则批量回归会悄悄少跑。"""
    assert sorted(STRATEGIES) == sorted(spec_data.STRATEGY_NAMES)
    assert RESUME["strategies"] == STRATEGIES
    assert SEED_FROM <= SEED_TO


@pytest.mark.slow
@pytest.mark.parametrize("name", STRATEGIES)
def test_b_t21_six_strategies_hit_expected_ending(name):
    """B-T21：5 套策略在 seed 0～199 下全部命中预期结局。"""
    expected = spec_data.STRATEGIES[name]["expected_ending"]
    failures = []
    for seed in range(SEED_FROM, SEED_TO + 1):
        report = simulator.run(name, seed)
        if report["ending_id"] != expected:
            failures.append((seed, report["ending_id"]))
    assert not failures, f"{name} 未命中：{failures[:5]}"


def test_seed42_snapshot_matches_expected(expected_loader):
    """seed 42 的终局数值必须与文档 B9 表一致。"""
    expected = expected_loader("smoke_seed42.json")
    for name, snapshot in expected.items():
        report = simulator.run(name, 42)
        final = report["final"]
        assert report["ending_id"] == snapshot["ending_id"], name
        for key, value in snapshot["stats"].items():
            assert final["stats"][key] == value, (name, key, final["stats"][key], value)
        assert final["mood"] == snapshot["mood"], name
        for npc, value in snapshot["relationships"].items():
            assert final["relationships"][npc] == value, (name, npc)
        assert report["min_end_energy"] == snapshot["min_end_energy"], name


@pytest.mark.parametrize("name", STRATEGIES)
def test_b_t22_save_resume_is_deterministic(name):
    """B-T22：第 7 天存档续跑，最终状态与不中断运行完全一致。"""
    seed = RESUME["seed"]
    plain = simulator.run(name, seed)
    resumed = simulator.run(name, seed, save_resume=True)
    assert resumed["final"] == plain["final"]
    assert resumed["actions"] == plain["actions"]


def test_save_fixture_roundtrip(fixture_loader):
    """存档夹具只做 dict 序列化，不依赖存档管理器。"""
    payload = fixture_loader("save_day_7.json")
    state = GameState.from_dict(payload)
    assert state.to_dict() == payload
    assert state.day_index == 7


def test_new_game_fixture_matches_defaults(fixture_loader):
    payload = fixture_loader("new_game.json")
    state = GameState.from_dict(payload)
    assert state.to_dict() == GameState().to_dict()


def test_report_shape():
    """模拟器输出结构符合手册 B11。"""
    report = simulator.run("kaoyan", 42)
    assert json.dumps(report, ensure_ascii=False)
    for key in ("seed", "strategy", "ending_id", "final", "event_log", "actions",
                "min_end_energy", "elapsed_ms"):
        assert key in report
    assert report["actions"][0][0] == "d0s0"
    assert len(report["actions"]) == 48
