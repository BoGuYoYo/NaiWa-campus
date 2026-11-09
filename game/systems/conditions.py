"""条件 DSL（开发者 B，手册 B7）。

条件类型：
    stat      key, op, value   academic / stamina / social / interest
    mood      op, value
    energy    op, value
    counter   key, op, value   活动累计次数
    rel       key(npc_id), op, value
    flag      key              拥有旗标
    not_flag  key              不拥有旗标
    semester  op, value        semester_no 比较
    any       items: [条件…]   任一满足

conditions 数组本身表示“全部满足”。
"""

from __future__ import annotations

import operator
from typing import Any

from game.core.state import GameState
from game.systems.content_db import ALLOWED_OPS, ContentError

_OPS = {
    ">=": operator.ge,
    "<=": operator.le,
    "==": operator.eq,
    ">": operator.gt,
    "<": operator.lt,
}


def _compare(left: int, op: str, right: int) -> bool:
    fn = _OPS.get(op)
    if fn is None:
        raise ContentError(f"未知运算符：{op}")
    return fn(left, right)


def evaluate(state: GameState, cond: dict[str, Any]) -> bool:
    """判断单个条件。"""
    ctype = cond.get("type")
    if ctype == "stat":
        key = cond["key"]
        if key not in state.stats:
            raise ContentError(f"stat 条件引用了未知属性：{key}")
        return _compare(state.stats[key], cond["op"], int(cond["value"]))
    if ctype == "mood":
        return _compare(state.mood, cond["op"], int(cond["value"]))
    if ctype == "energy":
        return _compare(state.energy, cond["op"], int(cond["value"]))
    if ctype == "counter":
        return _compare(state.counters.get(cond["key"], 0), cond["op"], int(cond["value"]))
    if ctype == "rel":
        return _compare(state.relationships.get(cond["key"], 0), cond["op"],
                        int(cond["value"]))
    if ctype == "flag":
        return cond["key"] in state.flags
    if ctype == "not_flag":
        return cond["key"] not in state.flags
    if ctype == "semester":
        return _compare(state.semester_no, cond["op"], int(cond["value"]))
    if ctype == "any":
        return any(evaluate(state, item) for item in cond.get("items", []))
    raise ContentError(f"未知条件类型：{ctype}")


def evaluate_all(state: GameState, conds: list[dict[str, Any]] | None) -> bool:
    """判断条件数组（全部满足；空数组合法）。"""
    return all(evaluate(state, cond) for cond in (conds or []))


__all__ = ["ALLOWED_OPS", "evaluate", "evaluate_all"]
