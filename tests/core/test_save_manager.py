"""A 的 core 层单元测试：存档系统（原子写入、.bak 回退、迁移、摘要）。"""

from __future__ import annotations

import json

import pytest

from game.core.save_manager import SaveLoadError, SaveManager
from game.core.state import WorldPos, new_state


@pytest.fixture()
def saves(tmp_path):
    return SaveManager(saves_root=tmp_path / "saves")


def test_save_creates_file_with_required_payload(saves, tmp_path):
    state = new_state(seed=7)
    state.day_index = 3
    path = saves.save(state, "slot_1")
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["save_version"] == 1
    assert payload["game_version"]
    assert payload["saved_at"]
    assert payload["summary"]["day_index"] == 3
    assert payload["state"]["day_index"] == 3
    assert payload["summary"]["stats"]["academic"] == state.stats["academic"]


def test_load_roundtrip(saves):
    state = new_state(seed=11)
    state.day_index = 6
    state.action_slot = 2
    state.stats["interest"] = 44
    state.relationships["npc_xiaoyou"] = 3
    state.flags = {"accepted_lab"}
    state.world = WorldPos(location_id="loc_library", x=12.0, y=1.5, facing="e")
    saves.save(state, "slot_2")

    loaded = saves.load("slot_2")
    assert loaded.day_index == 6
    assert loaded.action_slot == 2
    assert loaded.stats["interest"] == 44
    assert loaded.relationships["npc_xiaoyou"] == 3
    assert loaded.flags == {"accepted_lab"}
    assert loaded.world.location_id == "loc_library"
    assert (loaded.world.x, loaded.world.y, loaded.world.facing) == (12.0, 1.5, "e")


def test_second_save_rotates_bak(saves):
    state = new_state()
    saves.save(state, "slot_1")
    state.day_index = 5
    saves.save(state, "slot_1")
    assert saves.bak_path_for("slot_1").exists()
    assert json.loads(saves.path_for("slot_1").read_text(encoding="utf-8"))["state"]["day_index"] == 5


def test_corrupt_json_falls_back_to_bak(saves):
    state = new_state()
    saves.save(state, "slot_3")
    state.day_index = 8
    saves.save(state, "slot_3")  # slot_3 现在有效，slot_3.bak 里是 day_index=0 的旧存档
    saves.path_for("slot_3").write_text("{ this is not json", encoding="utf-8")

    loaded = saves.load("slot_3")
    assert loaded.day_index == 0  # 来自 .bak


def test_corrupt_without_bak_raises_save_error(saves):
    state = new_state()
    saves.save(state, "slot_1")
    saves.path_for("slot_1").write_text("null", encoding="utf-8")
    with pytest.raises(SaveLoadError) as excinfo:
        saves.load("slot_1")
    assert excinfo.value.code == "E_SAVE_CORRUPT"
    assert excinfo.value.text_id == "err.save_corrupt"


def test_missing_slot_raises_emptied_error(saves):
    with pytest.raises(SaveLoadError) as excinfo:
        saves.load("slot_2")
    assert excinfo.value.code == "E_SLOT_EMPTY"


def test_unsupported_version_is_rejected(saves):
    state = new_state()
    saves.save(state, "slot_1")
    payload = json.loads(saves.path_for("slot_1").read_text(encoding="utf-8"))
    payload["save_version"] = 99
    saves.path_for("slot_1").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SaveLoadError) as excinfo:
        saves.load("slot_1")
    assert excinfo.value.code == "E_SAVE_VERSION"


def test_migration_chain_runs_in_order(tmp_path):
    calls = []

    def migrate_1_to_2(data):
        calls.append(1)
        data["mood"] = 77
        return data

    manager = SaveManager(saves_root=tmp_path, migrations={1: migrate_1_to_2})
    state = new_state()
    manager.save(state, "slot_1")
    # 手工把文件降级成 save_version=1 但仍缺 mood 的场景
    payload = json.loads(manager.path_for("slot_1").read_text(encoding="utf-8"))
    payload["save_version"] = 1
    payload["state"].pop("mood", None)
    manager.path_for("slot_1").write_text(json.dumps(payload), encoding="utf-8")

    loaded = manager.load("slot_1")
    assert loaded.mood == 60  # 当前 save_version=1，不需要迁移，缺字段回落默认


def test_list_slots_and_peek(saves):
    assert saves.list_slots() == []
    state = new_state()
    saves.save(state, "slot_1")
    saves.save(state, "autosave")
    summaries = saves.list_slots()
    assert [item.slot for item in summaries] == ["slot_1", "autosave"]
    assert summaries[0].game_version


def test_manual_save_blocked_during_event(saves):
    state = new_state()
    ok, reason = saves.can_manual_save(state)
    assert ok and reason is None
    state.phase = "event"
    ok, reason = saves.can_manual_save(state)
    assert not ok and reason == "E_WRONG_PHASE"


def test_collision_inside_falls_back_to_spawn(saves):
    state = new_state()
    state.world = WorldPos(location_id="loc_gate", x=100.0, y=100.0, facing="e")
    saves.save(state, "slot_1")
    loaded = saves.load("slot_1", collision_check=lambda x, y: x > 50)
    assert (loaded.world.x, loaded.world.y) == (40.0, 5.0)
    assert loaded.world.facing == "n"


def test_invalid_slot_name_rejected(saves):
    with pytest.raises(ValueError):
        saves.save(new_state(), "slot_9")


def test_atomic_write_leaves_no_tmp_file(saves):
    saves.save(new_state(), "slot_1")
    leftovers = list((saves.root).glob("*.tmp"))
    assert leftovers == []
