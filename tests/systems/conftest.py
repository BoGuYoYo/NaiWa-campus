"""任务 B 独立测试夹具。

原则：只依赖 game.core（最小 A 层）与 game.systems，不导入 panda3d、
game.ui、game.world；不启动任何窗口。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from game.core.state import GameState
from game.systems.activity_service import ActivityService
from game.systems.calendar_service import CalendarService
from game.systems.content_db import get_db
from game.systems.ending_service import EndingService
from game.systems.event_service import EventService
from game.systems.relationship_service import RelationshipService

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
EXPECTED = PROJECT_ROOT / "tests" / "expected"


@pytest.fixture()
def state() -> GameState:
    """按手册 B2 初始值构造的新游戏状态。"""
    return GameState()


@pytest.fixture()
def activity() -> ActivityService:
    return ActivityService()


@pytest.fixture()
def calendar() -> CalendarService:
    return CalendarService()


@pytest.fixture()
def relationship() -> RelationshipService:
    return RelationshipService()


@pytest.fixture()
def events() -> EventService:
    return EventService()


@pytest.fixture()
def endings() -> EndingService:
    return EndingService()


@pytest.fixture(scope="session")
def db():
    return get_db()


def load_expected(name: str) -> Any:
    with (EXPECTED / name).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_fixture(name: str) -> Any:
    with (FIXTURES / name).open("r", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="session")
def expected_loader():
    """用例里按文件名读取 tests/expected/*.json。"""
    return load_expected


@pytest.fixture(scope="session")
def fixture_loader():
    """用例里按文件名读取 tests/systems/fixtures/*.json。"""
    return load_fixture
