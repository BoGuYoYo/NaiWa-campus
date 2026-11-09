"""tests/ui 独立夹具（D 隔离规则）：

- 不读正式文本 → 文本库使用 tests/ui/fixtures/strings.json；
- 不依赖其他岗位未完成的代码 → GameState 使用本文件的 FakeState；
- 不启动 Panda3D 窗口（本包所有测试均标记 not gui）。
"""

from __future__ import annotations

import json
import os

import pytest

from game.ui.text_db import TextDB

HERE = os.path.dirname(__file__)
FIXTURES = os.path.join(HERE, "fixtures")
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))


def load_fixture(name: str):
    with open(os.path.join(FIXTURES, name), "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def project_root() -> str:
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def fixture_strings() -> dict:
    return load_fixture("strings.json")


@pytest.fixture(scope="session")
def fixture_events() -> dict:
    return load_fixture("events.json")


@pytest.fixture(scope="session")
def fixture_results() -> dict:
    return load_fixture("results.json")


@pytest.fixture(scope="session")
def fixture_assets() -> dict:
    return load_fixture("assets.json")


@pytest.fixture()
def fixture_text_db(fixture_strings, fixture_events) -> TextDB:
    dialogues = {}
    for event in fixture_events.values():
        if isinstance(event, dict):
            dialogues.update(event.get("fixture_text", {}))
    return TextDB(fixture_strings, dialogues)


class FakeState:
    """最小 GameState 替身：只包含教程 / 面板需要的字段。"""

    def __init__(self, **kw) -> None:
        self.day_index = kw.get("day_index", 0)
        self.action_slot = kw.get("action_slot", 0)
        self.stats = kw.get("stats", {
            "academic": 10, "stamina": 20, "social": 10, "interest": 10,
        })
        self.mood = kw.get("mood", 60)
        self.energy = kw.get("energy", 84)
        self.relationships = kw.get("relationships", {})
        self.tutorial_done = kw.get("tutorial_done", set())

    @property
    def year(self) -> int:
        return self.day_index // 4 + 1

    @property
    def semester(self) -> int:
        return (self.day_index // 2) % 2 + 1

    @property
    def day(self) -> int:
        return self.day_index % 2 + 1

    @property
    def semester_no(self) -> int:
        return self.day_index // 2 + 1

    def max_energy(self) -> int:
        return 80 + self.stats.get("stamina", 0) // 5


@pytest.fixture()
def fake_state() -> FakeState:
    return FakeState()
