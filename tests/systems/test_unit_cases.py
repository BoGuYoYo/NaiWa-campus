"""B-T01～B-T20 的数据驱动执行器（B-ST-01）。

规格唯一来源是 tests/expected/unit_expect.json：
    setup   —— 按点号路径给 GameState 打补丁
    ops     —— start / talk / end_day / can_start / view / evaluate
    expect  —— 断言 state 上的路径
    expect_result —— 断言最近一次服务返回值的路径
    state_unchanged —— 本 stage 前后 to_dict() 必须完全一致（B-T16 用）
    triggered_sequence —— 累计的 triggered_event_id 序列（B-T12 用）
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

from game.core.state import GameState

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = PROJECT_ROOT / "tests" / "expected" / "unit_expect.json"


def load_spec() -> dict[str, Any]:
    with SPEC_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


SPEC = load_spec()
CASE_KIND = [case for case in SPEC["cases"] if case["kind"] == "case"]


def case_by_id(case_id: str) -> dict[str, Any]:
    for case in SPEC["cases"]:
        if case["id"] == case_id:
            return case
    raise KeyError(case_id)


# ---------------------------------------------------------------------------
# 路径读写
# ---------------------------------------------------------------------------
_DICT_FIELDS = {
    "stats": "stats",
    "relationships": "relationships",
    "counters": "counters",
    "today_counts": "today_counts",
}


def set_path(state: GameState, path: str, value: Any) -> None:
    if path == "flags":
        state.flags = set(value)
        return
    if path == "talked_today":
        state.talked_today = set(value)
        return
    if path == "event_log":
        state.event_log = list(value)
        return
    head, _, tail = path.partition(".")
    if tail and head in _DICT_FIELDS:
        getattr(state, _DICT_FIELDS[head])[tail] = int(value)
        return
    if not hasattr(state, path):
        raise AttributeError(f"unit_expect 的 setup 路径非法：{path}")
    setattr(state, path, value)


def get_path(state: GameState, path: str) -> Any:
    if path == "max_energy":
        return state.max_energy()
    if path == "flags":
        return sorted(state.flags)
    if path == "talked_today":
        return sorted(state.talked_today)
    head, _, tail = path.partition(".")
    if tail and head in _DICT_FIELDS:
        return getattr(state, _DICT_FIELDS[head]).get(tail, 0)
    if not hasattr(state, path):
        raise AttributeError(f"unit_expect 的 expect 路径非法：{path}")
    return getattr(state, path)


def dig(payload: Any, path: str) -> Any:
    """按点号路径取值；每一段先判断当前节点是 dict 还是 list。

    支持列表下标（如 `text_ids.0`、`choices.-1`），便于在规格里精确断言单个元素。
    """
    node: Any = payload
    walked: list[str] = []
    for part in path.split("."):
        prefix = ".".join(walked) or "<root>"
        walked.append(part)
        if isinstance(node, dict):
            if part not in node:
                raise KeyError(f"返回值中没有路径 {path}（已走到 {prefix}，当前键：{sorted(node)}）")
            node = node[part]
        elif isinstance(node, list):
            if not part.lstrip("-").isdigit():
                raise KeyError(f"返回值路径 {path}：{prefix} 是列表，需要数字下标而不是 {part!r}")
            index = int(part)
            if not -len(node) <= index < len(node):
                raise KeyError(f"返回值路径 {path}：{prefix} 下标 {index} 越界（长度 {len(node)}）")
            node = node[index]
        else:
            raise KeyError(
                f"返回值路径 {path}：{prefix} 是 {type(node).__name__}，无法继续取 {part!r}"
            )
    return node


# ---------------------------------------------------------------------------
# 执行
# ---------------------------------------------------------------------------
def run_op(op: list[str], state: GameState, services: dict[str, Any]) -> dict[str, Any] | None:
    name = op[0]
    if name == "start":
        return asdict(services["activity"].start(state, op[1]))
    if name == "talk":
        return asdict(services["relationship"].talk(state, op[1]))
    if name == "end_day":
        return asdict(services["calendar"].end_day(state))
    if name == "can_start":
        ok, code = services["activity"].can_start(state, op[1])
        return {"ok": ok, "error_code": code}
    if name == "evaluate":
        return asdict(services["endings"].evaluate(state))
    if name == "view":
        view = services["events"].get_view(state, op[1])
        choice = next((c for c in view.choices if c.choice_id == op[2]), None)
        if choice is None:
            raise AssertionError(f"{op[1]} 没有选项 {op[2]}")
        return {"enabled": choice.enabled, "lock_reason_id": choice.lock_reason_id}
    raise ValueError(f"未知 op：{name}")


@pytest.mark.parametrize("case", CASE_KIND, ids=[c["id"] for c in CASE_KIND])
def test_unit_case(case, state, activity, calendar, relationship, events, endings):
    services = {
        "activity": activity,
        "calendar": calendar,
        "relationship": relationship,
        "events": events,
        "endings": endings,
    }
    for path, value in case.get("setup", {}).items():
        set_path(state, path, value)

    triggered: list[str | None] = []
    for index, stage in enumerate(case["stages"]):
        where = f"{case['id']} stage{index + 1}"
        snapshot = state.to_dict() if stage.get("state_unchanged") else None
        last_result: dict[str, Any] | None = None

        for op in stage.get("ops", []):
            last_result = run_op(op, state, services)
            if last_result and "triggered_event_id" in last_result:
                triggered.append(last_result["triggered_event_id"])

        if stage.get("state_unchanged"):
            assert state.to_dict() == snapshot, f"{where} 状态被意外修改"

        for path, expected in stage.get("expect", {}).items():
            actual = get_path(state, path)
            assert actual == expected, f"{where} {path}：期望 {expected!r}，实际 {actual!r}"

        for path, expected in stage.get("expect_result", {}).items():
            assert last_result is not None, f"{where} 没有可断言的返回值"
            actual = dig(last_result, path)
            assert actual == expected, f"{where} 返回值 {path}：期望 {expected!r}，实际 {actual!r}"

        if "triggered_sequence" in stage:
            assert triggered == stage["triggered_sequence"], (
                f"{where} 触发序列：期望 {stage['triggered_sequence']!r}，实际 {triggered!r}"
            )


def test_dig_supports_list_index():
    """路径解析支持列表下标与负数下标，越界/非数字给出可读错误。"""
    payload = {"text_ids": ["a", "b"], "nested": [{"ok": True}]}
    assert dig(payload, "text_ids.0") == "a"
    assert dig(payload, "text_ids.-1") == "b"
    assert dig(payload, "nested.0.ok") is True

    with pytest.raises(KeyError, match="下标 2 越界"):
        dig(payload, "text_ids.2")
    with pytest.raises(KeyError, match="需要数字下标"):
        dig(payload, "text_ids.first")
    with pytest.raises(KeyError, match="没有路径"):
        dig(payload, "missing")


def test_spec_covers_23_cases():
    """规格必须覆盖 B-T01～B-T23，且 kind 合法。"""
    ids = [case["id"] for case in SPEC["cases"]]
    assert ids == [f"B-T{n:02d}" for n in range(1, 24)]
    kinds = {case["kind"] for case in SPEC["cases"]}
    assert kinds == {"case", "batch", "resume", "fuzz"}
