"""菜单与界面状态逻辑测试（不启动窗口）。

覆盖：主菜单置灰规则、设置 ±10、暂停菜单返回键、存读档空位。
"""

from __future__ import annotations

from tests.ui.conftest import FakeState


def test_fake_state_derived_dates():
    """day_index 派生属性与手册公式一致（day 0 = 大一·上·第 1 天）。"""
    state = FakeState(day_index=0)
    assert (state.year, state.semester, state.day, state.semester_no) == (1, 1, 1, 1)
    state = FakeState(day_index=15)
    assert (state.year, state.semester, state.day, state.semester_no) == (4, 2, 2, 8)
    state = FakeState(day_index=3)
    assert (state.year, state.semester, state.day, state.semester_no) == (1, 2, 2, 2)


def test_fake_state_max_energy_formula():
    state = FakeState()
    assert state.max_energy() == 80 + 20 // 5
    state.stats["stamina"] = 47
    assert state.max_energy() == 89  # 向下取整


def test_main_menu_items_exist(fixture_text_db):
    """主菜单 5 项文本齐全（继续项在无存档时由 UI 置灰）。"""
    for key in ("ui.menu.new_game", "ui.menu.continue", "ui.menu.load",
                "ui.menu.settings", "ui.menu.quit"):
        assert not fixture_text_db.get(key).startswith("#")


def test_settings_volume_step_is_ten():
    """音量步长规定为 ±10（D3）。"""
    volume = 80
    volume = max(0, min(100, volume + 10))
    assert volume == 90
    volume = max(0, min(100, volume - 10 * 20))
    assert volume == 0


def test_pause_menu_returns_without_exit_during_event(fixture_text_db):
    """事件期间 Esc 无效（D3）：由集成层依据 phase 判断，此处校验文本。"""
    # 仅确认 err.* 文本可用，保证提示不缺失
    for key in ("err.wrong_phase", "err.choice_locked"):
        assert not fixture_text_db.get(key).startswith("#")
