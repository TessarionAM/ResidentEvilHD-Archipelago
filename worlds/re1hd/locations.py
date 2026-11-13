"""
Locations (checks) for Resident Evil HD Remaster, built from data.PICKUPS.

Location IDs: BASE_ID + position in data.PICKUPS. Before the first public
release we may reorder freely; after release, only APPEND new pickups.
"""

from typing import Dict, NamedTuple, Tuple

from BaseClasses import Location

from .data import EXTRA_CHECKS, PICKUPS

BASE_ID = 1_302_100_000
EXTRA_BASE_ID = BASE_ID + 10_000      # maps, and later typewriters / story / bosses / puzzles


class RE1HDLocation(Location):
    game = "Resident Evil HD Remaster"


class LocationData(NamedTuple):
    code: int
    room: str
    vanilla_item: str
    requires: Tuple[str, ...]


location_table: Dict[str, LocationData] = {
    name: LocationData(BASE_ID + i, room, item, tuple(req))
    for i, (room, name, item, req) in enumerate(PICKUPS)
}



class ExtraData(NamedTuple):
    code: int
    room: str
    category: str
    requires: Tuple[str, ...]


# Checks that don't give an inventory item (EXTRA_CHECKS in data.py).
extra_location_table: Dict[str, ExtraData] = {
    name: ExtraData(EXTRA_BASE_ID + i, room, category, tuple(req))
    for i, (category, room, name, req) in enumerate(EXTRA_CHECKS)
}

all_location_ids: Dict[str, int] = {**{n: d.code for n, d in location_table.items()},
                                    **{n: d.code for n, d in extra_location_table.items()}}

location_name_groups = {}
for _name, _data in location_table.items():
    location_name_groups.setdefault(_data.room, set()).add(_name)
for _name, _data in extra_location_table.items():
    location_name_groups.setdefault(_data.room, set()).add(_name)
    location_name_groups.setdefault({"map": "Maps", "room": "Room Entries"}.get(_data.category, _data.category),
                                    set()).add(_name)
