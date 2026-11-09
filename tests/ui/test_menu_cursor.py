"""事件选项键盘逻辑测试（D-ST-04：锁定项不可选并显示原因）。"""

from __future__ import annotations

from game.ui.theme import MenuCursor


def make_cursor():
    return MenuCursor([
        ("a", True, None),
        ("b", True, None),
        ("c", False, "c"),   # 锁定，原因 -> evt.*.lock.c
    ])


def test_cursor_starts_on_first_enabled():
    cursor = make_cursor()
    assert cursor.items[cursor.index][0] == "a"


def test_move_down_skips_locked():
    cursor = make_cursor()
    cursor.move(1)  # a -> b
    assert cursor.items[cursor.index][0] == "b"
    cursor.move(1)  # b -> a（跳过锁定的 c）
    assert cursor.items[cursor.index][0] == "a"


def test_move_up_skips_locked():
    cursor = make_cursor()
    cursor.move(-1)  # a -> b（反向循环，跳过 c）
    assert cursor.items[cursor.index][0] == "b"


def test_confirm_current_choice():
    cursor = make_cursor()
    assert cursor.confirm() == ("a", None)
    cursor.move(1)
    assert cursor.confirm() == ("b", None)


def test_confirm_locked_returns_reason():
    """锁定项不可确认；循环移动会跳过它并给出原因通道（D-04）。"""
    cursor = make_cursor()
    cursor.move(1)          # a -> b（跳过锁定的 c）
    assert cursor.confirm() == ("b", None)
    assert cursor.lock_reason is None
    # 锁定项只能通过 lock_reason / 数字键探测，不可被光标停驻
    assert cursor.select_digit(3) == ("c", "c")


def test_digit_select_direct():
    cursor = make_cursor()
    assert cursor.select_digit(2) == ("b", None)


def test_digit_select_locked_invalid():
    """数字直接选择锁定项无效（D3 键盘规则）。"""
    cursor = make_cursor()
    assert cursor.select_digit(3) == ("c", "c")
    assert cursor.select_digit(9) is None


def test_all_locked_cursor_safe():
    cursor = MenuCursor([("x", False, "r"), ("y", False, None)])
    assert cursor.items[cursor.index][0] == "x"
    assert cursor.confirm() == ("x", "r")
