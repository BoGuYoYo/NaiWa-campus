"""随机数入口（开发者 B）。

规则：随机数只能由字符串种子派生，禁止使用全局 random 模块的函数。
这样存档、读档后继续运行的结果与不中断完全一致（B-T22 的硬性要求）。

已用文档 B6 校验：seed 42 第 0 天三个时段的 r 分别为
0.976379 / 0.941113 / 0.247446，第三段触发 daily_old_friend。
"""

from __future__ import annotations

import random


def derive_rng(seed: int, *parts: object) -> random.Random:
    """按 "seed:part1:part2:..." 派生独立随机流。"""
    key = ":".join([str(seed), *(str(p) for p in parts)])
    return random.Random(key)


def walk_rng(seed: int, day_index: int, action_slot: int) -> random.Random:
    """校园闲逛的日常事件掷骰（action_slot 为本次行动之前的时段序号）。"""
    return derive_rng(seed, day_index, action_slot, "walk")


def random_strategy_rng(seed: int, day_index: int, action_slot: int) -> random.Random:
    """随机策略选动作用的独立随机流。"""
    return derive_rng(seed, day_index, action_slot, "random")


def event_choice_rng(seed: int, event_id: str) -> random.Random:
    """随机策略选择事件选项时使用。"""
    return derive_rng(seed, event_id, "choice")
