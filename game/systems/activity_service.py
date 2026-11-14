"""九种校园活动（开发者 B，手册 B3）。

执行顺序严格为：
    计算收益（含心情减半）→ 一次性 apply 并裁剪 → counters/today_counts +1
    → 检查旗标规则 → action_slot +1 → 校园闲逛掷日常事件 → 组装结果

can_start() 必须保持只读：B-T16 会断言被拒绝时 state 完全不变。
"""

from __future__ import annotations

from typing import Any

from game.core.results import ActivityResult
from game.core.state import GameState
from game.systems import rng as rng_mod
from game.systems import spec_data
from game.systems.content_db import ContentDB, get_db
from game.systems.effects import apply


class ActivityService:
    def __init__(self, db: ContentDB | None = None) -> None:
        self.db = db or get_db()

    # ---- 前置检查 -------------------------------------------------------
    def can_start(self, state: GameState, activity_id: str) -> tuple[bool, str | None]:
        if state.phase != "campus":
            return False, spec_data.E_WRONG_PHASE
        if state.action_slot >= spec_data.SLOTS_PER_DAY:
            return False, spec_data.E_NO_SLOT
        activity = self.db.activity(activity_id)
        if activity is None:
            return False, spec_data.E_UNKNOWN_ID
        cost = -int(activity.get("effects", {}).get("energy", 0))
        if cost > 0 and state.energy < cost:
            return False, spec_data.E_LOW_ENERGY
        limit = activity.get("daily_limit")
        if limit is not None and state.today_counts.get(activity_id, 0) >= int(limit):
            return False, spec_data.E_DAILY_LIMIT
        return True, None

    # ---- 预览 -----------------------------------------------------------
    def _nominal_effects(self, state: GameState, activity: dict[str, Any]) -> dict[str, int]:
        effects = {k: int(v) for k, v in activity.get("effects", {}).items()}
        # Relationship gains from activities unlock after the player has met
        # that NPC through the dedicated talk interaction.
        for key in list(effects):
            if key.startswith("rel."):
                npc_id = key[4:]
                if spec_data.met_npc_flag(npc_id) not in state.flags:
                    del effects[key]
        halve = (activity.get("halve_academic_on_low_mood") is True
                 and state.mood < spec_data.LOW_MOOD_THRESHOLD)
        if halve and "academic" in effects:
            effects["academic"] = int(effects["academic"]) // 2
        return effects

    def preview(self, state: GameState, activity_id: str) -> dict[str, int]:
        """返回名义变化量，不修改 state。"""
        activity = self.db.activity(activity_id)
        if activity is None:
            return {}
        return self._nominal_effects(state, activity)

    # ---- 执行 -----------------------------------------------------------
    def start(self, state: GameState, activity_id: str) -> ActivityResult:
        ok, code = self.can_start(state, activity_id)
        if not ok:
            return ActivityResult(ok=False, activity_id=activity_id, error_code=code)

        activity = self.db.activity(activity_id)
        if activity is None:  # can_start 已保证；此处兜底，保证 python -O 下行为一致
            return ActivityResult(ok=False, activity_id=activity_id,
                                  error_code=spec_data.E_UNKNOWN_ID)
        slot_before = state.action_slot

        # 1) 计算收益并一次性应用
        deltas = apply(state, self._nominal_effects(state, activity))

        # 2) 计数器
        counter = activity.get("counter")
        if counter:
            state.counters[counter] = state.counters.get(counter, 0) + 1
        state.today_counts[activity_id] = state.today_counts.get(activity_id, 0) + 1

        # 3) 旗标规则
        added_flags: list[str] = []
        flag_rule = activity.get("flag_when_counter")
        if flag_rule:
            value = state.counters.get(flag_rule["counter"], 0)
            if value >= int(flag_rule["at_least"]) and flag_rule["flag"] not in state.flags:
                state.flags.add(flag_rule["flag"])
                added_flags.append(flag_rule["flag"])

        late_rule = activity.get("late_flag_on_daily_count")
        if (late_rule
                and state.today_counts.get(activity_id, 0) == int(late_rule["count"])
                and late_rule["flag"] not in state.flags):
            state.flags.add(late_rule["flag"])
            added_flags.append(late_rule["flag"])

        # 4) 消耗时段
        state.action_slot += 1

        # 5) 校园闲逛的日常事件
        triggered_event_id: str | None = None
        if activity.get("random_daily_event"):
            triggered_event_id = self._roll_daily_event(state, slot_before)
            if triggered_event_id:
                # 日常事件立即结算，并记入 event_log
                event = next((e for e in self.db.daily_events if e["id"] == triggered_event_id), None)
                if event is not None:
                    for key, value in apply(state, event.get("effects", {})).items():
                        deltas[key] = deltas.get(key, 0) + value

        # 6) 结果文案：3 条轮换，不使用随机数
        text_ids: list[str] = []
        if counter:
            n = (state.counters[counter] - 1) % 3 + 1
            text_ids.append(f"act.{activity_id}.result.{n}")

        return ActivityResult(
            ok=True,
            activity_id=activity_id,
            error_code=None,
            deltas=deltas,
            added_flags=added_flags,
            text_ids=text_ids,
            triggered_event_id=triggered_event_id,
            day_finished=state.action_slot >= spec_data.SLOTS_PER_DAY,
        )

    def _roll_daily_event(self, state: GameState, slot_before: int) -> str | None:
        rng = rng_mod.walk_rng(state.seed, state.day_index, slot_before)
        if rng.random() >= spec_data.DAILY_EVENT_CHANCE:
            return None
        candidates = self.db.daily_events
        if not candidates:  # pragma: no cover - 内容缺失时才会触发
            return None
        event = rng.choice(candidates)
        state.event_log.append(event["id"])
        return event["id"]
