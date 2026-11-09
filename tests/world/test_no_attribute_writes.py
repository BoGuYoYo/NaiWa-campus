"""独立通过条件：game/world/ 中不存在任何属性字段的写入。

规格（独立测试用例）："C 独立通过：tests/world 全部通过；world 中不存在属性写入"。
本测试对 game/world/*.py 做静态扫描，禁止对 academic / stamina / social /
interest / mood / energy 赋值（读取向的 energy 比较不受影响）。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WORLD_DIR = Path(__file__).resolve().parents[2] / "game" / "world"
FORBIDDEN = ("academic", "stamina", "social", "interest", "mood", "energy")

_NAMES = "|".join(FORBIDDEN)
# 形如 state.energy = / state.mood += / obj.interest -=
_ATTR_ASSIGN = re.compile(rf"\.(?:{_NAMES})\s*(?:\+|-|\*|/)?=(?!=)")
# 形如 setattr(state, "mood", ...)
_SETATTR = re.compile(rf"setattr\s*\([^,]+,\s*['\"](?:{_NAMES})['\"]")


def _world_files() -> list[Path]:
    return sorted(WORLD_DIR.glob("*.py"))


def test_world_module_files_exist():
    assert _world_files(), f"未找到 game/world 下的模块：{WORLD_DIR}"


@pytest.mark.parametrize("path", _world_files(), ids=lambda p: p.name)
def test_no_attribute_writes(path: Path):
    text = path.read_text(encoding="utf-8")
    hits = [m.group(0) for m in _ATTR_ASSIGN.finditer(text)]
    hits += [m.group(0) for m in _SETATTR.finditer(text)]
    assert not hits, f"{path.name} 出现属性写入：{hits}"


def test_world_files_are_scanned():
    """确保扫描确实覆盖了全部 world 模块（防止 glob 失效导致空通过）。"""
    names = {p.name for p in _world_files()}
    for expected in ("collision.py", "map_data.py", "camera_controller.py", "player_controller.py"):
        assert expected in names
