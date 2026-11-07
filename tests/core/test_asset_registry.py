"""A 的 core 层单元测试：资源注册表（manifest 校验、缺失回退、许可检查）。"""

from __future__ import annotations

import json

import pytest

from game.core.asset_registry import AssetRegistry
from game.core.event_bus import TOPIC_ASSET_MISSING, EventBus

LICENSE_HEADER = ("license_id,asset_ids,author,source_url,license,commercial_ok,modified,"
                  "date_added,notes\n")


def make_manifest(tmp_path, assets):
    manifest = tmp_path / "assets" / "manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({"version": 1, "assets": assets}), encoding="utf-8")
    licenses = tmp_path / "assets" / "LICENSES.csv"
    licenses.write_text(
        LICENSE_HEADER
        + "LIC-0001,char_a,me,internal,own,yes,no,2026-01-05,placeholder\n"
        + "LIC-9999,bad,me,internal,own,no,no,2026-01-05,non commercial\n",
        encoding="utf-8",
    )
    return manifest


def sprite_entry(**overrides):
    entry = {
        "id": "char_a_walk",
        "type": "sprite_sheet",
        "path": "characters/a/walk.png",
        "frame_w": 48,
        "frame_h": 48,
        "cols": 4,
        "rows": 8,
        "fps": 8,
        "pivot": [24, 46],
        "row_order": ["s", "se", "e", "ne", "n", "nw", "w", "sw"],
        "license_id": "LIC-0001",
    }
    entry.update(overrides)
    return entry


def test_manifest_loads_and_indexes(tmp_path):
    manifest = make_manifest(tmp_path, [sprite_entry()])
    bus = EventBus()
    registry = AssetRegistry(manifest_path=manifest, licenses_path=manifest.parent / "LICENSES.csv", bus=bus)
    assert len(registry) == 1
    assert "char_a_walk" in registry
    entry = registry.get("char_a_walk")
    assert entry.cols == 4 and entry.rows == 8
    assert entry.row_for_facing("n") == 4
    assert entry.frame_uv(0, 0) == (0.0, 0.875, 0.25, 1.0)


def test_missing_file_is_reported_but_not_fatal(tmp_path):
    manifest = make_manifest(tmp_path, [sprite_entry()])
    registry = AssetRegistry(manifest_path=manifest, licenses_path=manifest.parent / "LICENSES.csv")
    assert registry.file_exists("char_a_walk") is False
    assert registry.missing_files() == [("char_a_walk", "characters/a/walk.png")]


def test_invalid_type_and_missing_sprite_fields_are_rejected(tmp_path):
    assets = [
        sprite_entry(id="bad_type", type="video"),
        sprite_entry(id="no_pivot", pivot=None),
        {**sprite_entry(id="no_pivot_key"), "pivot": None},
        sprite_entry(id="short"),
    ]
    assets[2].pop("pivot")
    assets[3].pop("cols")
    manifest = make_manifest(tmp_path, assets)
    registry = AssetRegistry(manifest_path=manifest, licenses_path=manifest.parent / "LICENSES.csv")
    assert "bad_type" not in registry
    assert "no_pivot" not in registry
    assert "no_pivot_key" not in registry
    assert "short" not in registry
    assert len(registry.manifest_errors) >= 4


def test_duplicate_id_is_rejected(tmp_path):
    manifest = make_manifest(tmp_path, [sprite_entry(), sprite_entry()])
    registry = AssetRegistry(manifest_path=manifest, licenses_path=manifest.parent / "LICENSES.csv")
    assert len(registry) == 1
    assert any("duplicate" in error for error in registry.manifest_errors)


def test_volume_out_of_range_rejected(tmp_path):
    manifest = make_manifest(tmp_path, [
        {"id": "bgm_a", "type": "music", "path": "audio/a.ogg", "loop": True, "volume": 3.5,
         "license_id": "LIC-0001"},
    ])
    registry = AssetRegistry(manifest_path=manifest, licenses_path=manifest.parent / "LICENSES.csv")
    assert "bgm_a" not in registry


def test_music_requires_loop_field(tmp_path):
    manifest = make_manifest(tmp_path, [
        {"id": "bgm_b", "type": "music", "path": "audio/b.ogg", "license_id": "LIC-0001"},
    ])
    registry = AssetRegistry(manifest_path=manifest, licenses_path=manifest.parent / "LICENSES.csv")
    assert "bgm_b" not in registry


def test_missing_manifest_is_logged_not_raised(tmp_path):
    registry = AssetRegistry(manifest_path=tmp_path / "nope.json",
                             licenses_path=tmp_path / "nope.csv")
    assert len(registry) == 0
    assert registry.manifest_errors


def test_release_blockers_flags_non_commercial(tmp_path):
    manifest = make_manifest(tmp_path, [
        sprite_entry(),
        {"id": "img_bad", "type": "image", "path": "ui/bad.png", "license_id": "LIC-9999"},
        {"id": "img_no_license", "type": "image", "path": "ui/c.png"},
    ])
    registry = AssetRegistry(manifest_path=manifest, licenses_path=manifest.parent / "LICENSES.csv")
    blockers = registry.release_blockers()
    assert any(blocker.startswith("img_bad") for blocker in blockers)
    assert any(blocker.startswith("img_no_license") for blocker in blockers)
    assert not any(blocker.startswith("char_a_walk") for blocker in blockers)


def test_mark_missing_emits_bus_event_and_dedupes(tmp_path):
    pytest.importorskip("panda3d")
    manifest = make_manifest(tmp_path, [sprite_entry()])
    bus = EventBus()
    events = []
    bus.subscribe(TOPIC_ASSET_MISSING, lambda **data: events.append(data))
    registry = AssetRegistry(manifest_path=manifest, licenses_path=manifest.parent / "LICENSES.csv", bus=bus)
    texture = registry.load_texture("char_a_walk")
    assert texture is not None  # 品红黑格占位图
    assert events and events[0]["asset_id"] == "char_a_walk"
    registry.load_texture("char_a_walk")
    assert len(events) == 1  # 同一原因只发一次
    assert registry.missing["char_a_walk"] == "file not found"


def test_sprite_fallback_reports_placeholder(tmp_path):
    pytest.importorskip("panda3d")
    manifest = make_manifest(tmp_path, [sprite_entry()])
    registry = AssetRegistry(manifest_path=manifest, licenses_path=manifest.parent / "LICENSES.csv")
    sheet = registry.load_sprite("char_a_walk")
    assert sheet.placeholder is True
    assert sheet.entry.frame_w == 48
    uv = sheet.frame_uv("s", 0)
    assert len(uv) == 4
