"""交谈与关系事件（开发者 B，手册 B4）。

每名 NPC 每天限 1 次交谈：占 1 个时段，精力 -5、心情 +2、社交 +2、关系 +6；
要求精力 ≥ 5。交谈后按阶段顺序检查关系事件，满足条件时再加 5 点关系、
写入 <npc_id>_stage<n> 旗标并返回 triggered_event_id，每次交谈最多触发 1 段。
"""

from __future__ import annotations

from game.core.results import ActivityResult
from game.core.state import GameState
from game.systems import spec_data
from game.systems.content_db import ContentDB, get_db
from game.systems.effects import apply


class RelationshipService:
    def __init__(self, db: ContentDB | None = None) -> None:
        self.db = db or get_db()

    def can_talk(self, state: GameState, npc_id: str) -> tuple[bool, str | None]:
        if state.phase != "campus":
            return False, spec_data.E_WRONG_PHASE
        if state.action_slot >= spec_data.SLOTS_PER_DAY:
            return False, spec_data.E_NO_SLOT
        if self.db.npc(npc_id) is None:
            return False, spec_data.E_UNKNOWN_ID
        if npc_id in state.talked_today:
            return False, spec_data.E_ALREADY_TALKED
        if state.energy < spec_data.TALK_REQUIRED_ENERGY:
            return False, spec_data.E_LOW_ENERGY
        return True, None

    def check_stage(self, state: GameState, npc_id: str) -> tuple[str | None, list[str], dict[str, int]]:
        """检查并登记该 NPC 的下一段关系事件：返回 (event_id|None, added_flags, deltas)。

        这段逻辑以前只写在 talk() 里，于是"关系阈值"只在交谈这一个入口被检查：
        靠社团/活动/事件涨上去的关系永远不会触发关系事件。抽出来后
        GameFlow 可以在任意活动结算后调用，语义与交谈完全一致。
        """
        added_flags: list[str] = []
        triggered: str | None = None
        deltas: dict[str, int] = {}
        relation = state.relationships.get(npc_id, 0)
        for stage in spec_data.REL_STAGES:
            stage_flag = f"{npc_id}_stage{stage['stage']}"
            if stage_flag in state.flags:
                continue
            require = stage["require_flag"]
            require = require.format(npc_id=npc_id) if require else None
            if require and require not in state.flags:
                continue
            if relation < int(stage["threshold"]):
                continue
            if state.semester_no < int(stage["min_semester"]):
                continue
            state.flags.add(stage_flag)
            added_flags.append(stage_flag)
            bonus = apply(state, {f"rel.{npc_id}": spec_data.REL_EVENT_BONUS})
            deltas[f"rel.{npc_id}"] = bonus[f"rel.{npc_id}"]
            triggered = f"rel_{npc_id}_{stage['stage']}"
            break
        return triggered, added_flags, deltas

    def talk(self, state: GameState, npc_id: str) -> ActivityResult:
        ok, code = self.can_talk(state, npc_id)
        if not ok:
            return ActivityResult(ok=False, activity_id=f"talk.{npc_id}", error_code=code)

        effects = dict(spec_data.TALK_EFFECTS)
        effects[f"rel.{npc_id}"] = spec_data.TALK_RELATION_GAIN
        deltas = apply(state, effects)
        state.talked_today.add(npc_id)
        state.action_slot += 1

        triggered, added_flags, bonus = self.check_stage(state, npc_id)
        if triggered:
            deltas[f"rel.{npc_id}"] = deltas.get(f"rel.{npc_id}", 0) + bonus[f"rel.{npc_id}"]

        return ActivityResult(
            ok=True,
            activity_id=f"talk.{npc_id}",
            error_code=None,
            deltas=deltas,
            added_flags=added_flags,
            text_ids=[f"talk.{npc_id}.result.1"],
            triggered_event_id=triggered,
            day_finished=state.action_slot >= spec_data.SLOTS_PER_DAY,
        )
