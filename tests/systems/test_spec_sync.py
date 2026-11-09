"""spec_data 与规则 JSON 的一致性 + JSON Schema 校验。

这一层守护“唯一数值源”与“运行期以 JSON 为准”两个约束：
改了 JSON 却没改 spec_data（或反之）会在这里失败，并指出是哪个文件。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from game.core import state as core_state
from game.systems import spec_data, spec_export

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RULES_DIR = PROJECT_ROOT / "content" / "rules"
SCHEMA_PATH = PROJECT_ROOT / "content" / "schema" / "rules.schema.json"

SCHEMA_BY_FILE = {
    "activities.json": "activities",
    "events.json": "events",
    "npcs.json": "npcs",
    "endings.json": "endings",
    "daily_events.json": "daily_events",
}


def _load(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def test_rules_match_spec_data():
    """五个 JSON 必须能由 spec_data 原样重新导出。"""
    problems = []
    for filename, payload in spec_export.build_rules().items():
        target = RULES_DIR / filename
        if not target.exists():
            problems.append(f"{filename} 缺失")
            continue
        expected = json.loads(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        if _load(target) != expected:
            problems.append(
                f"{filename} 与 spec_data 不一致：若是有意修改内容，请先改 "
                f"game/systems/spec_data.py 再运行 python -m game.systems.spec_export；"
                f"直接导出会覆盖当前 JSON 修改"
            )
    assert not problems, "；".join(problems)


@pytest.mark.parametrize("filename,definition", sorted(SCHEMA_BY_FILE.items()))
def test_rules_pass_schema(filename: str, definition: str):
    if not SCHEMA_PATH.exists():
        # 正式 JSON Schema 归 E；A 合入 B 时只搬了规则内容，没搬 B 的临时 schema。
        # E 的 schema 落库后这条会自动开始生效。
        pytest.skip(f"{SCHEMA_PATH.name} 尚未落库（E 负责）")
    schema_root = _load(SCHEMA_PATH)
    schema = {"$schema": schema_root["$schema"],
              "$ref": f"#/$defs/{definition}",
              "$defs": schema_root["$defs"]}
    Draft202012Validator(schema).validate(_load(RULES_DIR / filename))


def test_daily_event_order_is_frozen():
    """B-T12 依赖数组顺序，禁止重排。"""
    daily = _load(RULES_DIR / "daily_events.json")
    assert [e["id"] for e in daily][-1] == "daily_old_friend"
    assert len(daily) == 12


def test_constants_have_single_source():
    """NPC_IDS / STAT_KEYS 只在 game.core.state 定义，systems 层引用而非复制。"""
    from game.systems import content_db

    assert spec_data.NPC_IDS is core_state.NPC_IDS
    assert content_db.STAT_KEYS is core_state.STAT_KEYS
    # NPC 列表的 id 顺序与核心常量一致，避免两处漂移
    assert tuple(n["id"] for n in spec_data.NPCS) == core_state.NPC_IDS


def test_unit_expect_is_executable_spec(expected_loader):
    """23 条用例以 v2 结构存放（执行细节由 test_unit_cases.py 校验）。"""
    spec = expected_loader("unit_expect.json")
    assert spec["version"] == 2
    assert [case["id"] for case in spec["cases"]] == [
        f"B-T{n:02d}" for n in range(1, 24)
    ]
