"""A 维护：公共结果对象（全员只读依赖）。

UI（D）只读这些对象渲染结果面板与事件界面；B 的服务返回它们；A 的 GameFlow 依据
day_finished / semester_event_id / graduated 推进流程。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .state import GameState


@dataclass
class ErrorInfo:
    """错误码与提示文本 ID 的固定映射（见文档“错误码与事件总线主题”表）。"""

    code: str
    text_id: str


ERROR_TEXT_IDS: dict[str, str] = {
    "E_NO_SLOT": "err.no_slot",
    "E_LOW_ENERGY": "err.low_energy",
    "E_DAILY_LIMIT": "err.daily_limit",
    "E_ALREADY_TALKED": "err.already_talked",
    "E_WRONG_PHASE": "err.wrong_phase",
    "E_UNKNOWN_ID": "err.unknown_id",
    "E_CHOICE_LOCKED": "err.choice_locked",
}


def error_text_id(code: str | None) -> str | None:
    if code is None:
        return None
    return ERROR_TEXT_IDS.get(code, "err.unknown_id")


@dataclass
class ActivityResult:
    ok: bool
    activity_id: str
    error_code: str | None
    deltas: dict[str, int] = field(default_factory=dict)
    added_flags: list[str] = field(default_factory=list)
    text_ids: list[str] = field(default_factory=list)
    triggered_event_id: str | None = None
    day_finished: bool = False

    @property
    def error_text_id(self) -> str | None:
        return error_text_id(self.error_code)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "activity_id": self.activity_id,
            "error_code": self.error_code,
            "deltas": dict(self.deltas),
            "added_flags": list(self.added_flags),
            "text_ids": list(self.text_ids),
            "triggered_event_id": self.triggered_event_id,
            "day_finished": self.day_finished,
        }


@dataclass
class DayEndResult:
    deltas: dict[str, int] = field(default_factory=dict)
    new_day_index: int = 0
    semester_event_id: str | None = None
    graduated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "deltas": dict(self.deltas),
            "new_day_index": self.new_day_index,
            "semester_event_id": self.semester_event_id,
            "graduated": self.graduated,
        }


@dataclass
class ChoiceView:
    choice_id: str
    text_id: str
    enabled: bool = True
    lock_reason_id: str | None = None


@dataclass
class EventView:
    event_id: str
    kind: str
    speaker: str | None
    page_text_ids: list[str] = field(default_factory=list)
    choices: list[ChoiceView] = field(default_factory=list)


@dataclass
class EventResult:
    event_id: str
    choice_id: str
    deltas: dict[str, int] = field(default_factory=dict)
    added_flags: list[str] = field(default_factory=list)
    result_text_ids: list[str] = field(default_factory=list)
    next_event_id: str | None = None


@dataclass
class EndingResult:
    ending_id: str
    matched: list[str] = field(default_factory=list)
    highlights: list[str] = field(default_factory=list)


@dataclass
class PromptView:
    interactable_id: str
    label_text_id: str
    enabled: bool = True
    reason_code: str | None = None
    cost_preview: dict[str, int] = field(default_factory=dict)

    @property
    def reason_text_id(self) -> str | None:
        return error_text_id(self.reason_code)


@dataclass
class InteractionResult:
    kind: str  # activity / npc / inspect / door / save / blocked
    payload: ActivityResult | str | None = None


@dataclass
class SaveSummary:
    """读档界面显示用，由 save_manager 从文件读取，不加载完整 GameState。"""

    slot: str
    saved_at: str
    game_version: str
    summary: dict[str, Any]

    @property
    def play_seconds(self) -> float:
        value = self.summary.get("play_seconds", 0.0)
        return float(value) if isinstance(value, (int, float)) else 0.0


@dataclass
class SaveError:
    code: str  # E_SAVE_CORRUPT / E_SAVE_IO / E_SAVE_VERSION / E_SLOT_EMPTY
    path: str
    detail: str = ""

    @property
    def text_id(self) -> str:
        return {
            "E_SAVE_CORRUPT": "err.save_corrupt",
            "E_SAVE_IO": "err.save_io",
            "E_SAVE_VERSION": "err.save_version",
            "E_SLOT_EMPTY": "err.slot_empty",
        }.get(self.code, "err.save_io")


def build_no_slot_result(activity_id: str) -> ActivityResult:
    return ActivityResult(ok=False, activity_id=activity_id, error_code="E_NO_SLOT")


def state_actions_left(state: GameState) -> int:
    return state.actions_left
