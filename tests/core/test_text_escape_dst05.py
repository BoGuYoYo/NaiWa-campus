"""D-ST-05 守卫：玩家可见文案里绝不能出现未格式化的 ``{placeholder}``。

背景：`TextDB.get()` 仅在文本含 ``{`` 时走 ``str.format(**fmt)``，参数缺失会
``KeyError`` → 记 error 日志后**原样返回**（`text_db.py:108-119`）。所以任何
"少传一个参数"的调用点在实机上都会把 ``内容缺失：{id}`` 直接显示给玩家。

这类缺陷之前被 `tests/core/test_event_scene_adapter.py` 的假 text 掩盖过：
它的假 `get()` 把 kwargs 丢掉，因此"少传参数"永远测不出来。本文件的假 text
**按真 TextDB 的语义执行 format**，并且 `has()` 一律返回 False，强制覆盖
``err.unknown_id`` 这条分支。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import game.config as config
from game.core.state import GameState
from game.core.world_scene import EventSceneAdapter
from game.systems.event_service import EventService
from game.ui.text_db import TextDB

# 真实 TextDB 里带占位符的错误文案（新增/修改后必须同步这张表）
_TEMPLATED_ERRORS = {
    "err.unknown_id": "内容缺失：{id}",
    "err.choice_locked": "这个选项暂时无法选择",
}


class _StrictText:
    """按 TextDB.get 的真实语义工作；记录调用参数以便断言。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def has(self, text_id: str) -> bool:  # 强制走 err.* 兜底分支
        return False

    def get_raw(self, text_id: str) -> str:
        return f"#{text_id}"

    def get(self, text_id: str, **fmt) -> str:
        self.calls.append((text_id, dict(fmt)))
        raw = _TEMPLATED_ERRORS.get(text_id, f"#{text_id}")
        try:
            return raw.format(**fmt)
        except (KeyError, IndexError, ValueError):
            return raw  # 与 TextDB.get 的失败路径一致：原样漏出 {placeholder}


class _FakeWidget:
    def __init__(self) -> None:
        self.hints: list[str] = []

    def _show_lock_hint(self, text: str) -> None:
        self.hints.append(text)


def _adapter(text, state: GameState | None = None):
    state = state or GameState()

    class _Flow:
        def require_state(self):
            return state

    app = SimpleNamespace(
        flow=_Flow(),
        scenes=SimpleNamespace(pop=lambda: None),
        services=SimpleNamespace(event=EventService()),
        text=text,
    )
    adapter = EventSceneAdapter.__new__(EventSceneAdapter)
    adapter.app = app
    adapter.widget = _FakeWidget()
    adapter._pending_result = None
    adapter._inspect_only = False
    adapter._event_id = None
    return adapter


@pytest.mark.parametrize("error_text", ["E_UNKNOWN_ID: sem_x", "E_SOMETHING_ELSE"])
def test_unknown_content_error_hint_never_leaks_placeholder(error_text: str) -> None:
    text = _StrictText()
    adapter = _adapter(text)

    adapter._show_content_error("sem_1_club_fair", "fair_lab", RuntimeError(error_text))

    assert adapter.widget.hints, "锁定提示没有传给控件"
    hint = adapter.widget.hints[-1]
    assert "{" not in hint and "}" not in hint, f"占位符漏到界面：{hint!r}"
    # 必须把 event_id 作为 id= 传进去（少传就会留下 {id}）
    assert any(name == "err.unknown_id" and fmt.get("id") for name, fmt in text.calls), text.calls


def test_real_textdb_requires_id_for_unknown_id() -> None:
    """真实数据也钉一遍：不传 id 时原文含 {id}，传了才是可用文案。"""
    db = TextDB.load(str(config.resource_root() / "content"))
    if not db.has("err.unknown_id"):  # 文案被删/改名时提示同步本文件
        pytest.fail("err.unknown_id 不存在：请同步 _TEMPLATED_ERRORS")

    raw = db.get("err.unknown_id")
    assert "{id}" in raw, f"err.unknown_id 的模板变了：{raw!r}"
    assert "{" not in db.get("err.unknown_id", id="sem_1_club_fair")
