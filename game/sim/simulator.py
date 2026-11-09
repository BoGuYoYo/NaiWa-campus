"""无界面模拟器主循环（开发者 B，手册 B11）。

一次 run() 跑完 16 天：选动作 → 执行 → 处理触发事件 → 日结算 → 学期事件，
最后调用结局判定。输出结构与手册 B11 的 JSON 一致。
"""

from __future__ import annotations

import time
from typing import Any

from game.core.results import ActivityResult
from game.core.state import GameState
from game.sim.strategies import BaseStrategy, Services, build_strategy
from game.systems import spec_data
from game.systems.content_db import ContentDB

MAX_ITERATIONS = 4000  # 48 次行动 + 16 次日结算 + 若干事件，留足余量


def run(strategy: BaseStrategy | str, seed: int = 42, *,
        save_resume: bool = False, db: ContentDB | None = None) -> dict[str, Any]:
    """跑一个完整周目，返回可用于比对的报告字典。"""
    started = time.perf_counter()
    if isinstance(strategy, str):
        strategy = build_strategy(strategy, seed)

    services = Services(db)
    state = GameState(seed=seed)
    actions: list[list[str]] = []
    min_end_energy: int | None = None
    resumed = False

    for _ in range(MAX_ITERATIONS):
        # 学期事件 / 关系事件：必须先结算才能继续
        if state.phase == "event" and state.pending_event_id:
            event_id = state.pending_event_id
            view = services.events.get_view(state, event_id)
            choice_id = strategy.choose_event_option(state, view, services)
            services.events.choose(state, event_id, choice_id)
            # 选项可能链到下一个事件（next_event_id 由 choose 入队）
            if state.phase == "event" and state.pending_event_id:
                continue
            if state.day_index >= spec_data.TOTAL_DAYS:
                break
            continue

        if state.day_index >= spec_data.TOTAL_DAYS:
            break

        # 当天行动用完 -> 日结算
        if state.action_slot >= spec_data.SLOTS_PER_DAY:
            if min_end_energy is None or state.energy < min_end_energy:
                min_end_energy = state.energy
            services.calendar.end_day(state)
            if save_resume and not resumed and state.day_index == 7:
                state = GameState.from_dict(state.to_dict())
                resumed = True
            continue

        day_before, slot_before = state.day_index, state.action_slot
        kind, ident = strategy.next_action(state, services)
        if kind == "talk":
            result: ActivityResult = services.relationships.talk(state, ident)
            action_id = f"talk.{ident}"
        else:
            result = services.activities.start(state, ident)
            action_id = ident
        actions.append([f"d{day_before}s{slot_before}", action_id])

        if not result.ok:  # 策略层已过滤，正常不会发生
            raise RuntimeError(
                f"{strategy.name} 在 d{day_before}s{slot_before} 执行 {ident} 失败："
                f"{result.error_code}"
            )

        # 关系事件需要玩家选择；日常事件已在活动内立即结算
        triggered = result.triggered_event_id
        if triggered and not triggered.startswith("daily_"):
            view = services.events.get_view(state, triggered)
            choice_id = strategy.choose_event_option(state, view, services)
            services.events.choose(state, triggered, choice_id)
    else:  # pragma: no cover - 逻辑错误时才会触发
        raise RuntimeError("模拟器超过最大迭代次数，可能存在死循环")

    # 收尾校验：让 200 种子回归与 3000 局模糊测试顺带验证引擎从不产生越界状态
    state.validate()

    ending = services.endings.evaluate(state)
    state.ending_id = ending.ending_id
    state.phase = "finished"

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return {
        "seed": seed,
        "strategy": strategy.name,
        "ending_id": ending.ending_id,
        "matched": list(ending.matched),
        "highlights": list(ending.highlights),
        "final": state.to_dict(),
        "event_log": list(state.event_log),
        "actions": actions,
        "min_end_energy": min_end_energy,
        "elapsed_ms": elapsed_ms,
    }
