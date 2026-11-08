"""A 维护：资源注册表（assets/manifest.json 的唯一读取方）。

规则：
* 代码里只能出现 asset_id，不得出现文件路径；
* 缺失资源返回品红黑格占位图（精灵/贴图）、无声音效（音频）、1 米灰色立方体（模型），
  同时写出 [ASSET] missing 日志并发出 asset.missing 主题；
* 本模块不在导入期依赖 panda3d，图形相关方法内部延迟导入，便于 core 测试与工具链复用。
"""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from .. import config
from .event_bus import TOPIC_ASSET_MISSING, EventBus

ALLOWED_TYPES = ("sprite_sheet", "image", "model", "sound", "music", "font")
SPRITE_REQUIRED = ("frame_w", "frame_h", "cols", "rows", "fps", "pivot")
TYPE_REQUIRED = {
    "sprite_sheet": SPRITE_REQUIRED,
    "image": (),
    "model": (),
    "sound": (),
    "music": ("loop",),
    "font": (),
}
DIRECTION_ORDER = ("s", "se", "e", "ne", "n", "nw", "w", "sw")


class AssetRegistryError(RuntimeError):
    pass


@dataclass
class AssetEntry:
    id: str
    type: str
    path: str = ""
    license_id: str | None = None
    frame_w: int = 0
    frame_h: int = 0
    cols: int = 1
    rows: int = 1
    fps: float = 0.0
    pivot: tuple[int, int] = (0, 0)
    row_order: list[str] = field(default_factory=list)
    loop: bool = False
    volume: float = 1.0
    raw: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    def frame_uv(self, row: int, col: int) -> tuple[float, float, float, float]:
        """返回 (u0, v0, u1, v1)；Panda3D 纹理原点在左下。"""
        if self.cols <= 0 or self.rows <= 0:
            return (0.0, 0.0, 1.0, 1.0)
        u0 = col / self.cols
        u1 = (col + 1) / self.cols
        v1 = 1.0 - row / self.rows
        v0 = 1.0 - (row + 1) / self.rows
        return (u0, v0, u1, v1)

    def row_for_facing(self, facing: str) -> int:
        order = self.row_order or list(DIRECTION_ORDER)
        try:
            return order.index(facing)
        except ValueError:
            return 0


@dataclass
class SpriteSheet:
    entry: AssetEntry
    texture: Any
    placeholder: bool = False

    @property
    def fps(self) -> float:
        return self.entry.fps or 8.0

    def frame_uv(self, facing: str, frame: int) -> tuple[float, float, float, float]:
        if self.placeholder:
            return (0.0, 0.0, 1.0, 1.0)  # 占位图整张显示，避免只截到棋盘一角
        row = self.entry.row_for_facing(facing)
        col = frame % max(1, self.entry.cols)
        return self.entry.frame_uv(row, col)


class AssetRegistry:
    def __init__(
        self,
        manifest_path: Path | str | None = None,
        licenses_path: Path | str | None = None,
        loader: Any | None = None,
        logger: logging.Logger | None = None,
        bus: EventBus | None = None,
    ) -> None:
        self.log = logger or logging.getLogger("naiwa.assets")
        self.bus = bus
        self.root = config.resource_root()
        self.manifest_path = Path(manifest_path) if manifest_path else self.root / "assets" / "manifest.json"
        self.licenses_path = (
            Path(licenses_path) if licenses_path else self.root / "assets" / "LICENSES.csv"
        )
        self.loader = loader  # Panda3D ShowBase（或测试替身），可为 None
        self.entries: dict[str, AssetEntry] = {}
        self.licenses: dict[str, dict[str, str]] = {}
        self.missing: dict[str, str] = {}
        self.version = 0
        self._texture_cache: dict[str, Any] = {}
        self._model_cache: dict[str, Any] = {}
        self._sound_cache: dict[str, Any] = {}
        self._font_cache: dict[str, Any] = {}
        self._placeholder_texture = None
        self._gray_cube = None
        self.manifest_errors: list[str] = []
        self.load_manifest()
        self.load_licenses()

    # ------------------------------------------------------------------ #
    # manifest
    # ------------------------------------------------------------------ #
    def load_manifest(self) -> None:
        self.entries.clear()
        self.manifest_errors.clear()
        if not self.manifest_path.exists():
            self.manifest_errors.append(f"manifest not found: {self.manifest_path}")
            self.log.error("[ASSET] manifest missing: %s", self.manifest_path)
            return
        try:
            raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            self.manifest_errors.append(f"manifest unreadable: {exc}")
            self.log.error("[ASSET] manifest unreadable: %s", exc)
            return

        self.version = int(raw.get("version", 0)) if isinstance(raw, dict) else 0
        items = raw.get("assets", []) if isinstance(raw, dict) else []
        if not isinstance(items, list):
            self.manifest_errors.append("manifest.assets 必须是数组")
            return
        for item in items:
            entry, error = self._parse_entry(item)
            if error:
                self.manifest_errors.append(error)
                self.log.error("[ASSET] manifest entry rejected: %s", error)
                continue
            if entry.id in self.entries:
                error = f"duplicate asset id {entry.id}"
                self.manifest_errors.append(error)
                self.log.error("[ASSET] %s", error)
                continue
            self.entries[entry.id] = entry

    def _parse_entry(self, item: Any) -> tuple[AssetEntry, str | None]:
        if not isinstance(item, dict):
            return AssetEntry(id="", type=""), "entry 不是对象"
        asset_id = str(item.get("id", "")).strip()
        asset_type = str(item.get("type", "")).strip()
        path = str(item.get("path", "")).strip()
        if not asset_id or not path:
            return AssetEntry(id=asset_id, type=asset_type), f"缺少 id 或 path: {item!r}"
        if asset_type not in ALLOWED_TYPES:
            return AssetEntry(id=asset_id, type=asset_type), f"{asset_id}: 非法 type {asset_type}"
        for key in TYPE_REQUIRED[asset_type]:
            if key not in item:
                return AssetEntry(id=asset_id, type=asset_type), f"{asset_id}: {asset_type} 缺少字段 {key}"
        if asset_type == "sprite_sheet":
            pivot = item.get("pivot", [0, 0])
            if not isinstance(pivot, (list, tuple)) or len(pivot) != 2:
                return AssetEntry(id=asset_id, type=asset_type), f"{asset_id}: pivot 必须是 [x, y]"
        volume = item.get("volume", 1.0)
        if not isinstance(volume, (int, float)) or not 0.0 <= float(volume) <= 1.0:
            return AssetEntry(id=asset_id, type=asset_type), f"{asset_id}: volume 必须在 0.0～1.0"
        tags = item.get("tags", [])
        entry = AssetEntry(
            id=asset_id,
            type=asset_type,
            path=path,
            license_id=item.get("license_id"),
            frame_w=int(item.get("frame_w", 0)),
            frame_h=int(item.get("frame_h", 0)),
            cols=int(item.get("cols", 1)),
            rows=int(item.get("rows", 1)),
            fps=float(item.get("fps", 0)),
            pivot=(int(item["pivot"][0]), int(item["pivot"][1])) if asset_type == "sprite_sheet" else (0, 0),
            row_order=list(item.get("row_order", list(DIRECTION_ORDER))),
            loop=bool(item.get("loop", False)),
            volume=float(volume),
            raw=dict(item),
            tags=[str(t) for t in tags] if isinstance(tags, list) else [],
        )
        return entry, None

    # ------------------------------------------------------------------ #
    # LICENSES.csv
    # ------------------------------------------------------------------ #
    def load_licenses(self) -> None:
        self.licenses.clear()
        if not self.licenses_path.exists():
            self.log.warning("[ASSET] LICENSES.csv not found: %s", self.licenses_path)
            return
        required = [
            "license_id",
            "asset_ids",
            "author",
            "source_url",
            "license",
            "commercial_ok",
            "modified",
            "date_added",
            "notes",
        ]
        try:
            with self.licenses_path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                if reader.fieldnames != required:
                    self.log.error("[ASSET] LICENSES.csv 表头必须固定为: %s", ",".join(required))
                for row in reader:
                    license_id = (row.get("license_id") or "").strip()
                    if not license_id:
                        continue
                    if (row.get("commercial_ok") or "").strip().lower() not in ("yes", "no"):
                        self.log.error("[ASSET] %s: commercial_ok 只能填 yes 或 no", license_id)
                    self.licenses[license_id] = {k: (v or "").strip() for k, v in row.items() if k}
        except OSError as exc:
            self.log.error("[ASSET] LICENSES.csv 读取失败: %s", exc)

    def license_for(self, asset_id: str) -> dict[str, str] | None:
        entry = self.entries.get(asset_id)
        if entry is None or not entry.license_id:
            return None
        return self.licenses.get(entry.license_id)

    def release_blockers(self) -> list[str]:
        """发布包中不得包含 commercial_ok=no 的资源；E 的构建脚本调用此检查。"""
        blockers: list[str] = []
        for asset_id, entry in self.entries.items():
            if not entry.license_id:
                blockers.append(f"{asset_id}: 未登记 license_id")
                continue
            record = self.licenses.get(entry.license_id)
            if record is None:
                blockers.append(f"{asset_id}: license_id {entry.license_id} 不在 LICENSES.csv")
            elif record.get("commercial_ok", "").lower() != "yes":
                blockers.append(f"{asset_id}: commercial_ok={record.get('commercial_ok')}")
        return blockers

    # ------------------------------------------------------------------ #
    # 查询
    # ------------------------------------------------------------------ #
    def get(self, asset_id: str) -> AssetEntry | None:
        return self.entries.get(asset_id)

    def __contains__(self, asset_id: object) -> bool:
        return asset_id in self.entries

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self) -> Iterator[AssetEntry]:
        return iter(self.entries.values())

    def resolve_path(self, asset_id: str) -> Path | None:
        entry = self.entries.get(asset_id)
        if entry is None:
            return None
        return self.root / "assets" / entry.path

    def file_exists(self, asset_id: str) -> bool:
        path = self.resolve_path(asset_id)
        return bool(path and path.exists())

    def verify_files(self) -> list[tuple[str, str, bool]]:
        """返回 (asset_id, 相对路径, 是否存在)；E 的 validate_assets 可复用。"""
        report: list[tuple[str, str, bool]] = []
        for entry in self.entries.values():
            report.append((entry.id, entry.path, (self.root / "assets" / entry.path).exists()))
        return report

    def missing_files(self) -> list[tuple[str, str]]:
        return [(aid, rel) for aid, rel, ok in self.verify_files() if not ok]

    # ------------------------------------------------------------------ #
    # 缺失回退
    # ------------------------------------------------------------------ #
    def _mark_missing(self, asset_id: str, reason: str = "not found") -> None:
        entry = self.entries.get(asset_id)
        path = entry.path if entry else "<unknown>"
        if self.missing.get(asset_id) == reason:
            return
        self.missing[asset_id] = reason
        self.log.error(
            "[ASSET] missing id=%s path=%s hint=检查 manifest 与文件名大小写", asset_id, path
        )
        if self.bus is not None:
            self.bus.emit(TOPIC_ASSET_MISSING, asset_id=asset_id, path=path)

    def placeholder_texture(self):
        """品红黑格占位图（48×48，6 像素格）。首次调用后缓存。"""
        if self._placeholder_texture is not None:
            return self._placeholder_texture
        from panda3d.core import PNMImage, SamplerState, Texture  # 延迟导入

        size = 48
        cell = 6
        image = PNMImage(size, size, 4)
        image.alphaFill(1.0)
        for y in range(size):
            for x in range(size):
                if ((x // cell) + (y // cell)) % 2 == 0:
                    image.setXel(x, y, 1.0, 0.0, 1.0)  # 品红
                else:
                    image.setXel(x, y, 0.0, 0.0, 0.0)
        texture = Texture("placeholder_missing")
        texture.load(image)
        texture.setMagfilter(SamplerState.FT_nearest)
        texture.setMinfilter(SamplerState.FT_nearest)
        self._placeholder_texture = texture
        return texture

    def gray_cube(self):
        """1 米灰色立方体，模型缺失时使用。"""
        if self._gray_cube is not None:
            return self._gray_cube
        from panda3d.core import CardMaker, NodePath  # 延迟导入

        root = NodePath("placeholder_model")
        maker = CardMaker("ph_face")
        maker.setFrame(-0.5, 0.5, -0.5, 0.5)
        faces = (
            ((0, 0, 0.5), 0), ((0, 0, -0.5), 180),
            ((0, -0.5, 0), 90), ((0, 0.5, 0), -90),
            ((0.5, 0, 0), 90), ((-0.5, 0, 0), -90),
        )
        for index, (pos, heading) in enumerate(faces):
            face = root.attachNewNode(maker.generate())
            face.setPos(*pos)
            if index >= 2:
                face.setHpr(heading, 0, 0)
                if index >= 4:
                    face.setHpr(0, 0, heading)
            face.setColorScale(0.5, 0.5, 0.5, 1.0)
        self._gray_cube = root
        return root

    def _entry_or_missing(self, asset_id: str, expected: tuple[str, ...]) -> AssetEntry | None:
        entry = self.entries.get(asset_id)
        if entry is None:
            self._mark_missing(asset_id, "not in manifest")
            return None
        if entry.type not in expected:
            self._mark_missing(asset_id, f"type {entry.type} != {expected}")
            return None
        path = self.root / "assets" / entry.path
        if not path.exists():
            self._mark_missing(asset_id, "file not found")
            return None
        return entry

    # ------------------------------------------------------------------ #
    # 图形资源（需要 panda3d）
    # ------------------------------------------------------------------ #
    @staticmethod
    def _filename(path: Path):
        """Panda3D 的 str 路径会按 model-path 解析且丢失非 ASCII 字符，必须走 fromOsSpecific。"""
        from panda3d.core import Filename

        return Filename.fromOsSpecific(str(path))

    def load_texture(self, asset_id: str):
        from panda3d.core import SamplerState, TexturePool

        entry = self._entry_or_missing(asset_id, ("image", "sprite_sheet"))
        if entry is None:
            return self.placeholder_texture()
        if asset_id in self._texture_cache:
            return self._texture_cache[asset_id]
        texture = TexturePool.loadTexture(self._filename(self.root / "assets" / entry.path))
        if texture is None or texture.getXSize() == 0:
            self._mark_missing(asset_id, "engine load failed")
            return self.placeholder_texture()
        texture.setMagfilter(SamplerState.FT_nearest)
        texture.setMinfilter(SamplerState.FT_nearest)
        texture.setWrapU(SamplerState.WM_clamp)
        texture.setWrapV(SamplerState.WM_clamp)
        texture.setKeepRamImage(False)
        self._texture_cache[asset_id] = texture
        return texture

    def load_sprite(self, asset_id: str) -> SpriteSheet:
        entry = self.entries.get(asset_id)
        texture = self.load_texture(asset_id)
        if entry is None or entry.type != "sprite_sheet":
            fallback = AssetEntry(id=asset_id, type="sprite_sheet", path="<missing>", frame_w=48,
                                  frame_h=48, cols=1, rows=1, fps=8.0, pivot=(24, 46))
            return SpriteSheet(entry=fallback, texture=texture, placeholder=True)
        return SpriteSheet(entry=entry, texture=texture, placeholder=asset_id in self.missing)

    def _render_root(self):
        if self.loader is not None and hasattr(self.loader, "render"):
            return self.loader.render
        return None

    def _spawn_gray_cube(self):
        root = self._render_root()
        cube = self.gray_cube()
        return cube.copyTo(root) if root is not None else cube

    def load_model(self, asset_id: str):
        entry = self._entry_or_missing(asset_id, ("model",))
        if entry is None:
            return self._spawn_gray_cube()
        if asset_id not in self._model_cache:
            render_root = self._render_root()
            if self.loader is None or render_root is None:
                self._mark_missing(asset_id, "no loader bound")
                return self._spawn_gray_cube()
            # ShowBase 1.10 不再有 loadModel 便捷方法，必须走 loader.Loader
            source = getattr(self.loader, "loader", self.loader)
            model = source.loadModel(self._filename(self.root / "assets" / entry.path))
            if model is None or model.isEmpty():
                self._mark_missing(asset_id, "engine load failed")
                return self._spawn_gray_cube()
            self._model_cache[asset_id] = model
        root = self._render_root()
        cached = self._model_cache[asset_id]
        return cached.copyTo(root) if root is not None else cached

    def load_sound(self, asset_id: str, positional: bool = False):
        entry = self._entry_or_missing(asset_id, ("sound", "music"))
        manager = None
        if self.loader is not None and hasattr(self.loader, "loader"):
            manager = self.loader.loader
        if entry is None or manager is None:
            return None
        if asset_id in self._sound_cache:
            return self._sound_cache[asset_id]
        try:
            sound = manager.loadSfx(self._filename(self.root / "assets" / entry.path))
        except Exception as exc:
            self.log.warning("[ASSET] loadSfx %s failed: %s", asset_id, exc)
            sound = None
        if sound is None:
            self._mark_missing(asset_id, "engine load failed")
            return None
        self._sound_cache[asset_id] = sound
        return sound

    def load_music(self, asset_id: str):
        return self.load_sound(asset_id)

    def load_font(self, asset_id: str):
        entry = self._entry_or_missing(asset_id, ("font",))
        if entry is None:
            return None
        if asset_id in self._font_cache:
            return self._font_cache[asset_id]
        from panda3d.core import TextFont

        font = TextFont()
        font.load(self._filename(self.root / "assets" / entry.path))
        if font.getNumPages() == 0 and not Path(self.root / "assets" / entry.path).exists():
            self._mark_missing(asset_id, "engine load failed")
            return None
        self._font_cache[asset_id] = font
        return font

    def clear_cache(self) -> None:
        self._texture_cache.clear()
        self._model_cache.clear()
        self._sound_cache.clear()
        self._font_cache.clear()
