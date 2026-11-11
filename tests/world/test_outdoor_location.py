"""回归：进出建筑 / 读室内存档后，地点必须回到室外区域。

BUG-25：出口点不在任何登记区域内时，``WorldPos.location_id`` 会保留成建筑 id，
``trigger_zone.scene_of()`` 于是判成室内，户外交互点全部显示「内容缺失」。
"""

from __future__ import annotations

from types import SimpleNamespace

from game.core.flow import GameFlow
from game.core.state import WorldPos, new_state


def _flow(map_data) -> GameFlow:
    return GameFlow(SimpleNamespace(map_data=map_data), scenes=None, saves=None, bus=None)


def test_every_exit_point_maps_to_an_outdoor_location(map_data):
    for building in map_data.buildings:
        exit_x, exit_y, _facing = map_data.exit_point(building.id)
        location = map_data.outdoor_location_at(exit_x, exit_y)
        assert not map_data.has_interior(location), f"{building.id} 出口地点仍是室内：{location}"


def test_indoor_save_reloads_at_the_door_outside(map_data):
    state = new_state(7)
    state.world = WorldPos(location_id="loc_dorm", x=208.0, y=1.6, facing="n")

    _flow(map_data)._restore_outdoor_after_indoor_save(state)

    exit_x, exit_y, facing = map_data.exit_point("loc_dorm")
    assert (state.world.x, state.world.y) == (exit_x, exit_y)
    assert state.world.facing == facing
    assert not map_data.has_interior(state.world.location_id)


def test_outdoor_save_keeps_its_position(map_data):
    state = new_state(7)
    state.world = WorldPos(location_id="loc_plaza", x=40.0, y=30.0, facing="s")

    _flow(map_data)._restore_outdoor_after_indoor_save(state)

    assert (state.world.x, state.world.y) == (40.0, 30.0)
    assert state.world.location_id == "loc_plaza"
