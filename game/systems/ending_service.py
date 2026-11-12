"""结局判定（开发者 B，手册 B8）。

毕业时调用一次：按 priorities 从上到下检查，第一个全部满足的结局生效，
ending_balanced 无条件兜底。highlights 取累计次数最多的 3 个计数器，
加上 event_log 中全部学期事件的选择，供毕业界面展示。
"""

from __future__ import annotations

from game.core.results import EndingResult
from game.core.state import GameState
from game.systems.conditions import evaluate_all
from game.systems.content_db import ContentDB, get_db


class EndingService:
    def __init__(self, db: ContentDB | None = None) -> None:
        self.db = db or get_db()

    def evaluate(self, state: GameState) -> EndingResult:
        endings = sorted(self.db.endings, key=lambda e: int(e.get("priority", 999)))
        for ending in endings:
            if evaluate_all(state, ending.get("conditions", [])):
                return EndingResult(
                    ending_id=ending["id"],
                    matched=list(ending.get("matched", [])),
                    highlights=self._highlights(state),
                )
        # 内容层面已经保证 ending_balanced 存在，这里只是兜底
        return EndingResult(ending_id="ending_balanced", matched=[], highlights=[])

    @staticmethod
    def _highlights(state: GameState) -> list[str]:
        counters = sorted(state.counters.items(), key=lambda kv: (-kv[1], kv[0]))
        top = [f"{name}×{count}" for name, count in counters[:3]]
        # event_log 里同时存在「事件 id」（开播时登记）与「id:choice」（结算后登记），
        # 两行都会渲染成回顾条目 —— 同一个事件在结局回顾里出现两次。
        # 这里只取已结算的那条，并按事件 id 去重（保留最后一次选择）。
        settled: dict[str, str] = {}
        for entry in state.event_log:
            if not entry.startswith("sem_") or ":" not in entry:
                continue
            event_id, _, _choice_id = entry.partition(":")
            settled[event_id] = entry
        return top + list(settled.values())
