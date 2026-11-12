"""A 维护：存档系统（原子写入 + .bak 回退 + 版本迁移）。

文件：user_dir/saves/<slot>.json，槽位 slot_1 / slot_2 / slot_3 / autosave。
写入：先写 <slot>.json.tmp，flush + fsync 后 os.replace；上一份改名为 <slot>.json.bak。
读取：JSON 解析失败或 save_version 不支持时回退 .bak；仍失败返回 SaveError。
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .. import config
from .results import SaveError, SaveSummary
from .state import GameState, WorldPos

MIN_SUPPORTED_SAVE_VERSION = 1
DEFAULT_SPAWN_BY_LOCATION: dict[str, tuple[float, float]] = {
    "loc_gate": (40.0, 5.0),
}

Migration = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass
class SaveManagerConfig:
    write_bak: bool = True
    use_fsync: bool = True


class SaveManager:
    def __init__(
        self,
        saves_root: Path | str | None = None,
        logger: logging.Logger | None = None,
        config_: SaveManagerConfig | None = None,
        migrations: dict[int, Migration] | None = None,
    ) -> None:
        self.log = logger or logging.getLogger("naiwa.save")
        self.root = Path(saves_root) if saves_root else config.saves_dir()
        self.root.mkdir(parents=True, exist_ok=True)
        self.cfg = config_ or SaveManagerConfig()
        self.migrations = migrations or {}
        self.last_error: SaveError | None = None

    # ------------------------------------------------------------------ #
    def path_for(self, slot: str) -> Path:
        self._validate_slot(slot)
        return self.root / f"{slot}.json"

    def bak_path_for(self, slot: str) -> Path:
        return self.path_for(slot).with_suffix(".json.bak")

    def _validate_slot(self, slot: str) -> None:
        if slot not in config.SLOT_IDS:
            raise ValueError(f"unknown save slot: {slot!r}")

    def exists(self, slot: str) -> bool:
        return self.path_for(slot).exists()

    # ------------------------------------------------------------------ #
    def can_manual_save(self, state: GameState) -> tuple[bool, str | None]:
        """手动存档只在宿舍书桌或暂停菜单中进行；事件进行中禁止存档。"""
        if state.phase in ("event", "graduation", "finished"):
            return False, "E_WRONG_PHASE"
        return True, None

    # ------------------------------------------------------------------ #
    def save(
        self,
        state: GameState,
        slot: str,
        reason: str | None = None,
        summary_extra: dict[str, Any] | None = None,
    ) -> Path:
        self._validate_slot(slot)
        payload = {
            # 版本号必须写当前格式版本：以前写 state.save_version（默认 1），
            # 一旦 SAVE_VERSION 升到 2，新写的档会被自己的版本检查判成"不支持"。
            "save_version": int(config.SAVE_VERSION),
            "saved_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "game_version": config.GAME_VERSION,
            "reason": reason or "manual",
            "summary": self._build_summary(state, summary_extra),
            "state": state.to_dict(),
        }
        target = self.path_for(slot)
        tmp = target.parent / (target.name + ".tmp")
        bak = self.bak_path_for(slot)

        text = json.dumps(payload, ensure_ascii=False, indent=2)
        with tmp.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            if self.cfg.use_fsync:
                os.fsync(handle.fileno())

        if self.cfg.write_bak and target.exists():
            try:
                if bak.exists():
                    bak.unlink()
                target.replace(bak)
            except OSError as exc:
                self.log.warning("[SAVE] cannot rotate %s -> %s: %s", target.name, bak.name, exc)

        os.replace(tmp, target)
        if self.cfg.use_fsync:
            self._fsync_dir(target.parent)
        self.log.info("[SAVE] wrote %s (reason=%s, day=%d slot=%d)",
                      target.name, payload["reason"], state.day_index, state.action_slot)
        return target

    def _fsync_dir(self, directory: Path) -> None:
        """Windows 不支持对目录 fsync，失败即忽略；POSIX 上保证目录项落盘。"""
        try:
            fd = os.open(directory, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(fd)
        except OSError:
            pass
        finally:
            os.close(fd)

    def _build_summary(self, state: GameState, extra: dict[str, Any] | None) -> dict[str, Any]:
        summary = state.summary()
        if extra:
            summary.update(extra)
        return summary

    # ------------------------------------------------------------------ #
    def load(self, slot: str, collision_check: Callable[[float, float], bool] | None = None) -> GameState:
        self._validate_slot(slot)
        target = self.path_for(slot)
        bak = self.bak_path_for(slot)
        first_error: SaveError | None = None

        for candidate in (target, bak):
            if not candidate.exists():
                continue
            state, error = self._read_state(candidate, slot)
            if state is not None:
                if candidate != target:
                    self.log.warning("[SAVE] %s 损坏，已回退到 %s", target.name, candidate.name)
                self._apply_load_position(state, collision_check)
                return state
            first_error = first_error or error

        if first_error is None:
            first_error = SaveError(
                code="E_SLOT_EMPTY" if not target.exists() else "E_SAVE_CORRUPT",
                path=str(target),
                detail="no save file",
            )
        self.last_error = first_error
        self.log.error("[SAVE] load %s failed: %s (%s)", slot, first_error.code, first_error.detail)
        raise SaveLoadError(first_error)

    def _read_state(self, path: Path, slot: str) -> tuple[GameState | None, SaveError | None]:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return None, SaveError("E_SAVE_CORRUPT", str(path), f"json: {exc}")
        if not isinstance(raw, dict):
            return None, SaveError("E_SAVE_CORRUPT", str(path), "root is not an object")
        version = raw.get("save_version", 0)
        if not isinstance(version, int) or version < MIN_SUPPORTED_SAVE_VERSION:
            return None, SaveError("E_SAVE_VERSION", str(path), f"save_version={version!r}")
        if version > config.SAVE_VERSION:
            return None, SaveError("E_SAVE_VERSION", str(path),
                                   f"save_version {version} > 当前 {config.SAVE_VERSION}")
        state_payload = raw.get("state")
        if not isinstance(state_payload, dict):
            return None, SaveError("E_SAVE_CORRUPT", str(path), "state missing")

        try:
            state_payload = self._migrate(version, state_payload)
            state = GameState.from_dict(state_payload)
        except Exception as exc:
            return None, SaveError("E_SAVE_CORRUPT", str(path), f"state: {exc}")
        return state, None

    def _migrate(self, version: int, payload: dict[str, Any]) -> dict[str, Any]:
        current = int(version)
        data = dict(payload)
        while current < config.SAVE_VERSION:
            migration = self.migrations.get(current)
            if migration is None:
                raise ValueError(f"no migration from save_version {current}")
            data = migration(data)
            current += 1
            data["save_version"] = current
        if current > config.SAVE_VERSION:
            raise ValueError(f"save_version {current} is newer than {config.SAVE_VERSION}")
        data.setdefault("save_version", current)
        return data

    def _apply_load_position(
        self, state: GameState, collision_check: Callable[[float, float], bool] | None
    ) -> None:
        """读档后恢复世界位置；若坐标位于碰撞体内，退回该地点默认出生点并写日志。"""
        inside = False
        if collision_check is not None:
            try:
                inside = bool(collision_check(state.world.x, state.world.y))
            except Exception as exc:
                self.log.warning("[SAVE] collision_check failed: %s", exc)
        if not inside:
            return
        spawn = DEFAULT_SPAWN_BY_LOCATION.get(state.world.location_id, (40.0, 5.0))
        self.log.warning(
            "[SAVE] saved position (%.2f, %.2f) inside collision, falling back to spawn %s %s",
            state.world.x, state.world.y, state.world.location_id, spawn,
        )
        state.world = WorldPos(location_id=state.world.location_id, x=spawn[0], y=spawn[1],
                               facing="n")

    # ------------------------------------------------------------------ #
    def peek(self, slot: str) -> SaveSummary | None:
        """只读摘要，不构建完整状态，用于读档界面。

        主文件损坏时回退 .bak —— 否则存档列表显示「空」、实际却能读出来。
        """
        self._validate_slot(slot)
        target = self.path_for(slot)
        bak = self.bak_path_for(slot)
        for candidate in (target, bak):
            if not candidate.exists():
                continue
            raw = self._read_summary_payload(candidate)
            if raw is None:
                continue
            if candidate != target:
                self.log.warning("[SAVE] %s 损坏，摘要回退到 %s", target.name, candidate.name)
            summary = raw.get("summary")
            return SaveSummary(
                slot=slot,
                saved_at=str(raw.get("saved_at", "")),
                game_version=str(raw.get("game_version", "")),
                summary=summary if isinstance(summary, dict) else {},
            )
        return None

    @staticmethod
    def _read_summary_payload(path: Path) -> dict[str, Any] | None:
        """解析存档顶层对象；损坏或形态不对返回 None。"""
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(raw, dict):
            return None
        return raw

    def list_slots(self) -> list[SaveSummary]:
        result: list[SaveSummary] = []
        for slot in config.SLOT_IDS:
            info = self.peek(slot)
            if info is not None:
                result.append(info)
        return result

    def delete(self, slot: str) -> None:
        path = self.path_for(slot)
        bak = self.bak_path_for(slot)
        for target in (path, bak):
            try:
                if target.exists():
                    target.unlink()
            except OSError as exc:
                self.log.warning("[SAVE] delete %s failed: %s", target, exc)


class SaveLoadError(Exception):
    def __init__(self, error: SaveError) -> None:
        super().__init__(f"{error.code}: {error.detail}")
        self.error = error

    @property
    def code(self) -> str:
        return self.error.code

    @property
    def text_id(self) -> str:
        return self.error.text_id
