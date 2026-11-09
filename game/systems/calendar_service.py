"""时间模型与日结算（开发者 B，手册 B1）。"""

from __future__ import annotations

from game.core.results import DayEndResult
from game.core.state import GameState
from game.systems import spec_data
from game.systems.content_db import ContentDB, get_db
from game.systems.effects import apply


class CalendarService:
    def __init__(self, db: ContentDB | None = None) -> None:
        self.db = db or get_db()

    def semester_event_id(self, semester_no: int) -> str | None:
        return self.db.semester_event_by_no.get(semester_no)

    def end_day(self, state: GameState) -> DayEndResult:
        """执行八步日结算并推进日期（会修改 state）。

        只允许在 campus 阶段、毕业之前调用。事件未结算就再次结算会让日期空转并
        覆盖 pending_event_id，因此这里显式抛错，而不是静默推进。
        """
        if state.phase != "campus" or state.day_index >= spec_data.TOTAL_DAYS:
            raise RuntimeError(
                "end_day 只能在 campus 阶段、毕业之前调用："
                f"当前 phase={state.phase}，day_index={state.day_index}，"
                f"pending_event_id={state.pending_event_id}；请先结算待展示事件"
            )

        deltas: dict[str, int] = {}

        # 1) 精力过低，心情下降
        if state.energy < spec_data.LOW_ENERGY_THRESHOLD:
            for key, value in apply(state, {"mood": -spec_data.LOW_ENERGY_MOOD_PENALTY}).items():
                deltas[key] = deltas.get(key, 0) + value

        # 2) 熬夜旗标在当日结算时消耗
        late = spec_data.LATE_NIGHT_FLAG in state.flags
        state.flags.discard(spec_data.LATE_NIGHT_FLAG)

        # 3) 恢复精力
        recovery = spec_data.DAILY_ENERGY_RECOVERY
        if late:
            recovery -= spec_data.LATE_NIGHT_RECOVERY_PENALTY
        for key, value in apply(state, {"energy": recovery}).items():
            deltas[key] = deltas.get(key, 0) + value

        # 4) 清空当日计数与交谈记录
        state.today_counts.clear()
        state.talked_today.clear()
        state.action_slot = 0

        # 5) 推进日期
        finished = state.day_index
        state.day_index = finished + 1

        # 6) 每学期第 2 天结束时触发学期事件
        semester_event_id: str | None = None
        if finished % 2 == 1:
            semester_event_id = self.semester_event_id(finished // 2 + 1)
            state.pending_event_id = semester_event_id
            state.phase = "event"

        # 7) 第 16 天结束 -> 先放第 8 学期事件，事件结束后再毕业
        graduated = finished == spec_data.TOTAL_DAYS - 1

        return DayEndResult(
            deltas=deltas,
            new_day_index=state.day_index,
            semester_event_id=semester_event_id,
            graduated=graduated,
        )
