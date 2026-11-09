"""事件视图与选择（开发者 B，手册 B5 / B7）。

本服务只产出规则字段与 text_id，不拼任何显示文案（文案归开发者 D）。
选项被锁时给出 lock_reason_id = evt.<event_id>.lock.<choice_id>。
"""

from __future__ import annotations

from game.core.results import ChoiceView, EventResult, EventView
from game.core.state import GameState
from game.systems import spec_data
from game.systems.conditions import evaluate_all
from game.systems.content_db import ContentDB, ContentError, get_db
from game.systems.effects import apply


class EventService:
    def __init__(self, db: ContentDB | None = None) -> None:
        self.db = db or get_db()

    def _require_event(self, event_id: str) -> dict:
        event = self.db.event(event_id)
        if event is None:
            raise ContentError(f"{spec_data.E_UNKNOWN_ID}: 事件 {event_id} 不存在")
        return event

    def get_view(self, state: GameState, event_id: str) -> EventView:
        event = self._require_event(event_id)
        choices: list[ChoiceView] = []
        for choice in event.get("choices", []):
            enabled = evaluate_all(state, choice.get("conditions", []))
            choices.append(
                ChoiceView(
                    choice_id=choice["id"],
                    text_id=f"evt.{event_id}.choice.{choice['id']}",
                    enabled=enabled,
                    lock_reason_id=None if enabled else f"evt.{event_id}.lock.{choice['id']}",
                )
            )
        return EventView(
            event_id=event_id,
            kind=event["kind"],
            speaker=event.get("speaker"),
            page_text_ids=list(event.get("pages", [])),
            choices=choices,
        )

    def choose(self, state: GameState, event_id: str, choice_id: str) -> EventResult:
        event = self._require_event(event_id)

        # 幂等保护：同一事件只能结算一次，避免 GameFlow 误调用导致属性重复叠加。
        # 放在最前面，保证被拒绝时不会留下任何副作用。
        prefix = f"{event_id}:"
        if any(entry.startswith(prefix) for entry in state.event_log):
            raise ContentError(f"事件 {event_id} 已经结算过，不能重复结算")

        choice = next((c for c in event.get("choices", []) if c["id"] == choice_id), None)
        if choice is None:
            raise ContentError(f"{spec_data.E_UNKNOWN_ID}: 事件 {event_id} 没有选项 {choice_id}")

        if not evaluate_all(state, choice.get("conditions", [])):
            raise ContentError(
                f"{spec_data.E_CHOICE_LOCKED}: 事件 {event_id} 的选项 {choice_id} 条件未满足"
            )

        # 链式事件的目标先校验，避免“效果已生效、事件却入队失败”的半完成状态
        next_event_id = choice.get("next_event_id")
        if next_event_id and self.db.event(next_event_id) is None:
            raise ContentError(
                f"{spec_data.E_UNKNOWN_ID}: {event_id} 的选项 {choice_id} "
                f"指向不存在的事件 {next_event_id}"
            )

        deltas = apply(state, choice.get("effects", {}))

        added_flags: list[str] = []
        for flag in choice.get("add_flags", []):
            if flag not in state.flags:
                state.flags.add(flag)
                added_flags.append(flag)
        for flag in choice.get("remove_flags", []):
            state.flags.discard(flag)

        state.event_log.append(f"{event_id}:{choice_id}")

        # 链式事件：选项可以指向下一个事件，由服务层统一入队，
        # 这样 A 的 GameFlow 与模拟器都只需要看 pending_event_id / phase。
        if next_event_id:
            state.pending_event_id = next_event_id
            state.phase = "event"
        else:
            state.pending_event_id = None
            if state.day_index >= spec_data.TOTAL_DAYS:
                state.phase = "graduation"
            else:
                state.phase = "campus"

        return EventResult(
            event_id=event_id,
            choice_id=choice_id,
            deltas=deltas,
            added_flags=added_flags,
            result_text_ids=[f"evt.{event_id}.result.{choice_id}"],
            next_event_id=next_event_id,
        )

    def first_available_choice(self, state: GameState, event_id: str) -> str:
        """按表中顺序返回第一个可用选项（模拟器与“默认选择”使用）。"""
        view = self.get_view(state, event_id)
        for choice in view.choices:
            if choice.enabled:
                return choice.choice_id
        raise ContentError(f"{event_id}: 没有任何可用选项")
