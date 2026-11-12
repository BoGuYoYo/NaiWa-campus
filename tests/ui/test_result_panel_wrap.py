"""结果面板折行守卫（BUG：交谈文本过长时崩溃）。

`ResultPanel._wrap_line()` 曾经把不存在的 `self._measure` 传给
`theme.wrap_cjk()`，只有在文本超过面板宽度时才会执行到那一行 ——
所以短文案的活动结果一直正常，和李振兴聊天（一句长台词）必崩：
`AttributeError: 'ResultPanel' object has no attribute '_measure'`。
"""

from __future__ import annotations

from panda3d.core import TextNode

from game.ui.result_panel import ResultPanel


def _panel() -> ResultPanel:
    panel = ResultPanel.__new__(ResultPanel)
    panel._measure_node = TextNode("result_measure")
    return panel


def test_wrap_line_handles_long_text_without_crashing():
    panel = _panel()
    long_text = "M" * 200  # 用拉丁字符：不依赖中文字体也能量出宽度

    lines = panel._wrap_line(long_text)

    assert len(lines) > 1
    assert "".join(lines) == long_text
    assert all(line for line in lines)


def test_wrap_line_keeps_short_text_on_one_line():
    panel = _panel()

    assert panel._wrap_line("短句") == ["短句"]
