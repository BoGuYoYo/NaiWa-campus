"""Regression tests for world math, collision, camera bounds, and layout fixes."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from game.systems import spec_data
from game.world.camera_controller import OUTDOOR_TARGET_MAX, OUTDOOR_TARGET_MIN, CameraRig
from game.world.collision import PLAYER_HALF, Rect, make_rect, move_and_collide


def test_move_and_collide_zero_delta_does_not_snap_other_axis():
    pos = SimpleNamespace(x=1.1, y=5.0)
    overlapping = [make_rect(0.0, 0.0, 2.0, 10.0)]
    # Even if pre-existing overlap were passed in rects directly:
    move_and_collide(pos, SimpleNamespace(x=0.0, y=1.0), overlapping)
    assert pos.x == 1.1
    assert pos.y == pytest.approx(6.0)

    # Zero-delta guard prevents axis push on an unmoving axis.
    pos2 = SimpleNamespace(x=1.0, y=5.0)
    move_and_collide(pos2, SimpleNamespace(x=0.0, y=0.0), [Rect(0.8, 4.8, 1.2, 5.2)])
    assert (pos2.x, pos2.y) == (1.0, 5.0)


def test_camera_rig_custom_clamp_bounds_prevent_double_clamp_deadzone():
    rig_default = CameraRig()
    assert (rig_default.clamp_min, rig_default.clamp_max) == (
        OUTDOOR_TARGET_MIN,
        OUTDOOR_TARGET_MAX,
    )

    custom_min = (12.5, 10.94)
    custom_max = (67.5, 49.06)
    rig = CameraRig(clamp_min=custom_min, clamp_max=custom_max)
    rig.set_outdoor((5.0, 5.0))
    assert rig.target == custom_min

    # Moving to edge doesn't let target linger in a clamped gap.
    rig.update((5.0, 5.0), 1.0)
    assert rig.target == custom_min


def test_play_games_rule_matches_dorm_location(map_data):
    db_acts = {a["id"]: a for a in spec_data.ACTIVITIES}
    assert db_acts["play_games"]["location"] == "loc_dorm"
    assert map_data.interactable("ia_game_pc").location_id == "loc_dorm"


def test_adjusted_interior_and_outdoor_layouts_are_clear(map_data):
    dorm_furn = {f.id: f.rect for f in map_data.interior("loc_dorm").furniture}
    assert dorm_furn["furn_wardrobe"].x1 <= 15.5  # inside west of 0.5m east wall

    lib_furn = {f.id: f.rect for f in map_data.interior("loc_library").furniture}
    assert lib_furn["furn_shelf_w"].x0 >= 0.5  # inside east of 0.5m west wall

    cls_furn = {f.id: f.rect for f in map_data.interior("loc_classroom").furniture}
    podium = cls_furn["furn_podium"]
    assert podium.x1 - podium.x0 == 2.0  # single podium width
    ia_desk = map_data.interactable("ia_class_desk")
    assert cls_furn["furn_desk_row_n"].y1 + PLAYER_HALF < ia_desk.y

    props = {p.id: p.rect for p in map_data.props}
    dorm_rect = next(b.rect for b in map_data.buildings if b.id == "loc_dorm")
    assert props["prop_tree_n1"].x0 > dorm_rect.x1
    assert props["prop_bin_dorm"].x1 < dorm_rect.x1
    assert props["prop_lamp_e2"].x0 > props["prop_flowerbed"].x1
    assert props["prop_lamp_n1"].y1 < props["prop_tree_w4"].y0
    assert props["prop_bin_canteen"].x1 < props["prop_tree_e3"].x0
