"""效果应用与裁剪（开发者 B，手册 B2 / B7）。

所有数值变化都经过这里：
    1. 先累计名义值，再逐项裁剪到合法范围；
    2. 属性、心情、关系裁剪到 0..100；
    3. 精力裁剪到 0..max_energy()，上限在体力落定之后计算（避免
       eat_canteen 这类“同时加体力与精力”的活动出现歧义）；
    4. 返回“实际变化量”，供 UI 显示与测试断言。

已知效果键：academic / stamina / social / interest / mood / energy / rel.<npc_id>
"""

from __future__ import annotations

from typing import Any

from game.core.state import STAT_KEYS, GameState
from game.systems.content_db import BASE_EFFECT_KEYS, ContentError

VALUE_MIN = 0
VALUE_MAX = 100


def _clamp(value: int, low: int, high: int) -> int:
    return low if value < low else min(value, high)


def validate_keys(effects: dict[str, Any], state: GameState | None = None) -> None:
    """校验效果键与取值；传入 state 时同时校验关系目标存在。

    所有校验都在写入之前完成，避免出现“部分效果已生效”的中间状态。
    """
    for key, value in effects.items():
        if not isinstance(value, int) or isinstance(value, bool):
            raise ContentError(f"效果键 {key} 的值必须是整数")
        if key.startswith("rel."):
            npc_id = key[4:]
            if state is not None and npc_id not in state.relationships:
                raise ContentError(f"未知 NPC：{npc_id}（效果键 {key}）")
            continue
        if key not in BASE_EFFECT_KEYS:
            raise ContentError(f"未知效果键：{key}")


def apply(state: GameState, effects: dict[str, Any]) -> dict[str, int]:
    """应用效果并返回实际变化量（可能为 0）。"""
    if not effects:
        return {}
    validate_keys(effects, state)
    deltas: dict[str, int] = {key: 0 for key in effects}

    # 1) 四项属性
    for key in STAT_KEYS:
        if key in effects:
            before = state.stats[key]
            state.stats[key] = _clamp(before + int(effects[key]), VALUE_MIN, VALUE_MAX)
            deltas[key] = state.stats[key] - before

    # 2) 心情
    if "mood" in effects:
        before = state.mood
        state.mood = _clamp(before + int(effects["mood"]), VALUE_MIN, VALUE_MAX)
        deltas["mood"] = state.mood - before

    # 3) 关系
    for key, value in effects.items():
        if not key.startswith("rel."):
            continue
        npc_id = key[4:]
        before = state.relationships.get(npc_id, 0)
        state.relationships[npc_id] = _clamp(before + int(value), VALUE_MIN, VALUE_MAX)
        deltas[key] = state.relationships[npc_id] - before

    # 4) 精力（上限依赖当前体力）
    if "energy" in effects:
        before = state.energy
        upper = state.max_energy()
        state.energy = _clamp(before + int(effects["energy"]), 0, upper)
        deltas["energy"] = state.energy - before

    return deltas


__all__ = ["apply", "validate_keys"]
