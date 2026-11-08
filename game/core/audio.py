"""A 维护：音频（音乐切换、音效、音量设置生效）。

无音频设备（例如 --offscreen 或 CI）时自动降级为静默模式，不抛异常、不阻塞流程。
"""

from __future__ import annotations

import logging
from typing import Any

from .. import config
from .asset_registry import AssetRegistry

SFX_IDS = (
    "sfx_ui_move",
    "sfx_ui_confirm",
    "sfx_ui_cancel",
    "sfx_interact",
    "sfx_stat_up",
    "sfx_stat_down",
    "sfx_footstep_ground",
    "sfx_footstep_floor",
    "sfx_door",
    "sfx_day_end",
    "sfx_semester_end",
    "sfx_ending",
)

MUSIC_IDS = ("bgm_title", "bgm_campus_day", "bgm_event", "bgm_graduation")


class AudioManager:
    def __init__(
        self,
        registry: AssetRegistry,
        settings: config.Settings,
        logger: logging.Logger | None = None,
        enabled: bool = True,
    ) -> None:
        self.registry = registry
        self.settings = settings
        self.log = logger or logging.getLogger("naiwa.audio")
        self.enabled = enabled
        self.current_music: str | None = None
        self._music_obj: Any = None
        self._sfx_objects: dict[str, Any] = {}
        self.missing_audio: set[str] = set()

    # ------------------------------------------------------------------ #
    def _bgm_volume(self, base: float) -> float:
        return max(0.0, min(1.0, self.settings.effective_bgm_volume() * base))

    def _sfx_volume(self, base: float) -> float:
        return max(0.0, min(1.0, self.settings.effective_sfx_volume() * base))

    def apply_settings(self) -> None:
        if self._music_obj is not None:
            entry = self.registry.get(self.current_music or "")
            base = entry.volume if entry else 1.0
            try:
                self._music_obj.setVolume(self._bgm_volume(base))
            except Exception as exc:  # 音频对象可能已释放
                self.log.warning("[AUDIO] setVolume failed: %s", exc)

    # ------------------------------------------------------------------ #
    def play_music(self, asset_id: str | None, fade: float = 0.0) -> None:
        if asset_id == self.current_music:
            return
        self.stop_music()
        self.current_music = asset_id
        if not self.enabled or asset_id is None:
            return
        try:
            sound = self.registry.load_music(asset_id)
        except Exception as exc:
            self.log.warning("[AUDIO] load %s failed: %s", asset_id, exc)
            sound = None
        if sound is None:
            self.missing_audio.add(asset_id)
            return
        entry = self.registry.get(asset_id)
        try:
            sound.setLoop(bool(entry.loop) if entry else True)
            sound.setVolume(self._bgm_volume(entry.volume if entry else 1.0))
            sound.play()
        except Exception as exc:
            self.log.warning("[AUDIO] play %s failed: %s", asset_id, exc)
            return
        self._music_obj = sound
        self.log.info("[AUDIO] music -> %s", asset_id)

    def stop_music(self) -> None:
        if self._music_obj is not None:
            try:
                self._music_obj.stop()
            except Exception:
                pass
        self._music_obj = None
        self.current_music = None

    def stop_all(self) -> None:
        """停止音乐与全部音效，并把管理器置为静默（退出流程调用）。"""
        self.stop_music()
        for sound in self._sfx_objects.values():
            try:
                sound.stop()
            except Exception:
                pass
        self._sfx_objects.clear()
        if self.enabled:
            self.log.info("[AUDIO] stopped all sounds")
        self.enabled = False

    def play_sfx(self, asset_id: str, volume: float = 1.0) -> None:
        if not self.enabled:
            return
        sound = self._sfx_objects.get(asset_id)
        if sound is None:
            try:
                sound = self.registry.load_sound(asset_id)
            except Exception as exc:
                self.log.warning("[AUDIO] load %s failed: %s", asset_id, exc)
                sound = None
            if sound is None:
                self.missing_audio.add(asset_id)
                return
            self._sfx_objects[asset_id] = sound
        try:
            sound.setVolume(self._sfx_volume(volume))
            sound.play()
        except Exception as exc:
            self.log.warning("[AUDIO] play %s failed: %s", asset_id, exc)

    # 事件总线订阅 ------------------------------------------------------ #
    def on_scene_changed(self, old: str, new: str, **_: Any) -> None:
        if new in ("CampusScene", "InteriorScene"):
            self.play_music("bgm_campus_day")
        elif new == "MainMenu":
            self.play_music("bgm_title")
        elif new in ("EventScene",):
            self.play_music("bgm_event")
        elif new in ("GraduationScene",):
            self.play_music("bgm_graduation")

    def on_day_ended(self, result: Any = None, **_: Any) -> None:
        self.play_sfx("sfx_day_end")

    def on_graduated(self, ending: Any = None, **_: Any) -> None:
        self.play_sfx("sfx_ending")
