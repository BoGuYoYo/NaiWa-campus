"""game.core —— A 维护的公共接口层。"""

from __future__ import annotations

from .asset_registry import AssetEntry, AssetRegistry, SpriteSheet
from .audio import AudioManager
from .event_bus import EventBus
from .flow import GameFlow, Services, resolve_services
from .render_pipeline import LowResPipeline, Viewport, compute_viewport
from .results import (
    ActivityResult,
    ChoiceView,
    DayEndResult,
    EndingResult,
    EventResult,
    EventView,
    InteractionResult,
    PromptView,
    SaveError,
    SaveSummary,
)
from .save_manager import SaveLoadError, SaveManager
from .scene_manager import SceneManager
from .state import GameState, WorldPos, new_state

__all__ = [
    "AssetEntry",
    "AssetRegistry",
    "SpriteSheet",
    "AudioManager",
    "EventBus",
    "GameFlow",
    "Services",
    "resolve_services",
    "LowResPipeline",
    "Viewport",
    "compute_viewport",
    "ActivityResult",
    "ChoiceView",
    "DayEndResult",
    "EndingResult",
    "EventResult",
    "EventView",
    "InteractionResult",
    "PromptView",
    "SaveError",
    "SaveSummary",
    "SaveLoadError",
    "SaveManager",
    "SceneManager",
    "GameState",
    "WorldPos",
    "new_state",
]
