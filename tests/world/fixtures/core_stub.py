"""A 的 game/core/results.py 尚未交付时，安装同签名的替身模块。

pytest（tests/world/conftest.py）与独立命令（tests/standalone_c.py）共用本函数，
保证 C 的模块在缺少 A 的公共接口时也能独立运行；A 交付后自动改用真实实现。
"""

from __future__ import annotations

import dataclasses
import sys
import types
from pathlib import Path


def install_core_results_stub(project_root: Path | str) -> bool:
    """缺少 game.core.results 时安装替身，返回是否安装了替身。"""
    try:
        import game.core.results  # noqa: F401

        return False
    except ModuleNotFoundError:
        pass

    root = Path(project_root)
    game = sys.modules.get("game")
    if game is None:
        game = types.ModuleType("game")
        game.__path__ = [str(root / "game")]
        sys.modules["game"] = game

    core = types.ModuleType("game.core")
    core.__path__ = []
    results = types.ModuleType("game.core.results")

    @dataclasses.dataclass
    class PromptView:
        interactable_id: str
        label_text_id: str
        enabled: bool
        reason_code: str | None = None
        cost_preview: dict = dataclasses.field(default_factory=dict)

    @dataclasses.dataclass
    class InteractionResult:
        kind: str
        payload: object = None

    results.PromptView = PromptView
    results.InteractionResult = InteractionResult
    core.results = results
    game.core = core
    sys.modules["game.core"] = core
    sys.modules["game.core.results"] = results
    return True
