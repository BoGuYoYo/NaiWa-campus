"""spec_export 的两条 CLI 路径：只比对（--check）与真正写盘。

写盘用例把 RULES_DIR/EXPECTED_DIR 都指向 tmp_path，绝不改动仓库内的
content/rules 与 tests/expected。
"""

from __future__ import annotations

import json

from game.systems import spec_export
from game.systems.content_db import ContentDB, get_db

RULE_FILES = ("activities.json", "events.json", "npcs.json", "endings.json",
              "daily_events.json")


def test_check_passes_on_repository_rules(capsys):
    assert spec_export.main(["--check"]) == 0
    assert "一致" in capsys.readouterr().out


def test_check_reports_mismatch(tmp_path, capsys):
    rules = tmp_path / "rules"
    rules.mkdir()
    (rules / "activities.json").write_text("[]\n", encoding="utf-8")

    assert spec_export.main(["--check", "--rules-dir", str(rules)]) == 1

    out = capsys.readouterr().out
    assert "不一致" in out
    assert "activities.json" in out


def test_write_outputs_rules_and_strategies(tmp_path, monkeypatch, capsys):
    rules = tmp_path / "rules"
    expected = tmp_path / "expected"
    monkeypatch.setattr(spec_export, "EXPECTED_DIR", expected)

    assert spec_export.main(["--rules-dir", str(rules)]) == 0

    for name in RULE_FILES:
        payload = json.loads((rules / name).read_text(encoding="utf-8"))
        assert isinstance(payload, list)
        assert payload

    strategies = json.loads((expected / "strategies.json").read_text(encoding="utf-8"))
    assert set(strategies) == set(spec_export.spec_data.STRATEGIES)
    # prefs 的键必须是字符串，否则与基线文件比对时会因 int 键而失配
    assert all(isinstance(key, str) for cfg in strategies.values() for key in cfg["prefs"])

    assert "已导出 5 个规则文件" in capsys.readouterr().out


def test_exported_rules_are_loadable(tmp_path, monkeypatch):
    """导出的文件必须能被 ContentDB 直接加载：导出格式与加载契约一致。"""
    rules = tmp_path / "rules"
    monkeypatch.setattr(spec_export, "EXPECTED_DIR", tmp_path / "expected")

    assert spec_export.main(["--rules-dir", str(rules)]) == 0

    reloaded = ContentDB(rules)
    assert set(reloaded.events_by_id) == set(get_db().events_by_id)
