"""任务 C 的独立测试夹具入口。

- 把仓库根目录与 tests/world 加入 sys.path，使 game.world.* 与 fixtures.* 可直接导入。
- A 的 game/core/results.py 尚未交付时，用同签名的替身占位；A 交付后自动使用真实实现。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
CONTENT_ROOT = ROOT / "content"

for _path in (str(ROOT), str(HERE)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from fixtures.core_stub import install_core_results_stub  # noqa: E402

install_core_results_stub(ROOT)

import pytest  # noqa: E402

from game.world.map_data import MapData  # noqa: E402

FIXTURES = HERE / "fixtures"


def pytest_configure(config) -> None:
    config.addinivalue_line("markers", "gui: 需要 Panda3D 图形上下文（离屏）的测试")


@pytest.fixture(scope="session")
def map_data() -> MapData:
    """正式地图数据（content/world/）。"""
    return MapData.from_content_root(CONTENT_ROOT)


@pytest.fixture(scope="session")
def test_map_data() -> MapData:
    """独立测试用的小地图，不依赖正式地图与模型。"""
    return MapData.from_files(FIXTURES / "test_map.json", FIXTURES / "test_interactables.json")
