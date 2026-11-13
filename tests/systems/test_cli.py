"""模拟器命令行契约（手册 B11 的退出码与输出结构）。

所有输出写入 tmp_path，不污染 reports/。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from game.sim.__main__ import main
from game.systems import spec_data

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _run(*args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-m", "game.sim", *args],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        env=env,
        check=False,  # 退出码由用例自己断言（0/1/2 都是契约的一部分）
    )


@pytest.mark.slow
def test_expect_hit_returns_zero(tmp_path):
    out = tmp_path / "academic_42.json"
    result = _run("--strategy", "kaoyan", "--seed", "42",
                  "--expect", "ending_kaoyan", "--out", str(out))
    assert result.returncode == 0, result.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["ending_id"] == "ending_kaoyan"
    assert payload["seed"] == 42
    assert payload["strategy"] == "kaoyan"


@pytest.mark.slow
def test_expect_mismatch_returns_one(tmp_path):
    out = tmp_path / "mismatch.json"
    result = _run("--strategy", "kaoyan", "--seed", "42",
                  "--expect", "ending_tech_master", "--out", str(out))
    assert result.returncode == 1
    assert "结局不符" in result.stdout


@pytest.mark.slow
def test_unknown_strategy_returns_two():
    result = _run("--strategy", "no_such_strategy", "--seed", "42")
    assert result.returncode == 2
    assert "运行异常" in result.stderr


@pytest.mark.slow
def test_batch_all_strategies(tmp_path):
    out = tmp_path / "batch.json"
    result = _run("--strategy", "all", "--seeds", "0-1", "--summary", "--out", str(out))
    assert result.returncode == 0, result.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["mode"] == "batch"
    assert set(payload["distribution"]) == set(spec_data.STRATEGY_NAMES)
    assert payload["mismatches"] == []
    for name in spec_data.STRATEGY_NAMES:
        assert name in result.stdout


@pytest.mark.slow
def test_random_mode_outputs_distribution(tmp_path):
    out = tmp_path / "fuzz.json"
    result = _run("--random", "2", "--out", str(out))
    assert result.returncode == 0, result.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["mode"] == "random"
    assert payload["total"] == 2
    assert sum(payload["distribution"].values()) == 2
    assert len(payload["runs"]) == 2


# ---------------------------------------------------------------------------
# 直调 main()：子进程用例覆盖真实进程行为，这里补进程内路径，
# 一是毫秒级反馈，二是让 __main__.py 的行覆盖率可被统计（子进程不计入）。
# ---------------------------------------------------------------------------
def test_main_direct_call_single_strategy(tmp_path, capsys):
    out = tmp_path / "one.json"
    assert main(["--strategy", "mediocre", "--seed", "42", "--summary",
                 "--out", str(out)]) == 0

    payload = json.loads(out.read_text(encoding="utf-8"))
    # 单策略时直接输出一局的报告，不带 mode 包装
    assert payload["ending_id"] == "ending_mediocre"
    assert payload["strategy"] == "mediocre"
    assert "mediocre seed=42" in capsys.readouterr().out


def test_main_direct_call_expect_mismatch(capsys):
    assert main(["--strategy", "kaoyan", "--seed", "42",
                 "--expect", "ending_tech_master"]) == 1
    assert "结局不符" in capsys.readouterr().out


def test_main_direct_call_batch(tmp_path, capsys):
    out = tmp_path / "batch.json"
    assert main(["--strategy", "tech_master", "--seeds", "0-1", "--summary",
                 "--out", str(out)]) == 0

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["mode"] == "batch"
    assert payload["mismatches"] == []
    assert "tech_master" in capsys.readouterr().out


def test_main_direct_call_random(tmp_path, capsys):
    out = tmp_path / "fuzz.json"
    assert main(["--random", "2", "--summary", "--out", str(out)]) == 0

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["total"] == 2
    assert "随机策略 2 局" in capsys.readouterr().out


def test_main_direct_call_returns_two_on_error(capsys):
    assert main(["--strategy", "no_such_strategy", "--seed", "42"]) == 2
    assert "运行异常" in capsys.readouterr().err
