"""
"What can I reach right now?" - the world's logic, evaluated without a MultiWorld, so the
client can answer /inlogic while you play (TessarionAM, 2026-11-11: "is my seed unbeatable?").

Same rules as __init__.py: doors and pickups need ALL their listed items; with received items
going to the item box, any requirement on an item that isn't handed straight to Jill also needs
an item box to have been reached; pickups that aren't checks in this seed give their normal
item. tests/test_logic.py checks this matches the generator's own logic.
"""
from collections import Counter
from typing import Iterable, List, Optional, Set, Tuple

from .data import (BOX_ROOMS, DIRECT_ITEMS, DOORS, EITHER_ROOM, EVENT_NAMES, EVENT_SPOT_CHECK, EVENTS,
                   EXTRA_CHECKS, PICKUPS, START)


def _ok(requires: Tuple[str, ...], have: Counter, box: bool, box_gate: bool) -> bool:
    if any(have[r] <= 0 for r in requires):
        return False
    if box_gate and requires and any(r not in DIRECT_ITEMS and r not in EVENT_NAMES for r in requires):
        return box
    return True


ORIGIN = START      # the seed's start room (random_start_room); the client sets it from slot data


def reachable_rooms(have: Counter, box: bool, box_gate: bool) -> Set[str]:
    rooms, changed = {ORIGIN}, True
    while changed:
        changed = False
        for a, b, req, one_way in DOORS:
            if not _ok(tuple(req), have, box, box_gate):
                continue
            if a in rooms and b not in rooms:
                rooms.add(b)
                changed = True
            elif not one_way and b in rooms and a not in rooms:
                rooms.add(a)
                changed = True
    return rooms


def closure(received: Iterable[str], active: Set[str], box_gate: bool = True, checked: Optional[Set[str]] = None):
    """(items you have incl. events and vanilla pickups on the way, rooms you can reach, box reached).
    With `checked` (the live tracker): a "spot" event (EVENT_SPOT_CHECK) whose pickup is a check
    only counts once that check is really collected - e.g. Barry's East Wing Storeroom items only
    appear after the Armor Key is taken from its spot (seed test 5)."""
    have = Counter(received)
    taken: Set[str] = set()
    box = False
    while True:
        rooms = reachable_rooms(have, box, box_gate)
        new_box = box or any(r in rooms for r in BOX_ROOMS)
        grew = False
        for room, name, req in EVENTS:
            spot = EVENT_SPOT_CHECK.get(name)
            if checked is not None and spot in active and spot not in checked:
                continue
            if have[name] <= 0 and room in rooms and _ok(tuple(req), have, new_box, box_gate):
                have[name] += 1
                grew = True
        for room, name, item, req in PICKUPS:
            if name not in active and name not in taken and room in rooms and _ok(tuple(req), have, new_box, box_gate):
                taken.add(name)
                have[item] += 1
                grew = True
        if not grew and new_box == box:
            return have, rooms, box
        box = new_box


def in_logic(received: Iterable[str], active: Set[str], checked: Set[str],
             box_gate: bool = True, live: bool = True) -> List[str]:
    """Location names that are checks in this seed (active), not yet checked, and reachable
    with the received items (starting items included) - plus the normal items of pickups that
    aren't checks, which you pick up on the way. live=False: the generator's view (spot events
    count as soon as they're reachable) - used by the test that compares the two."""
    have, rooms, box = closure(received, active, box_gate, checked if live else None)
    out = []
    for room, name, item, req in PICKUPS:
        if name in active and name not in checked and room in rooms and _ok(tuple(req), have, box, box_gate):
            out.append(name)
    for category, room, name, req in EXTRA_CHECKS:
        here = any(r in rooms for r in EITHER_ROOM.get(name, (room,)))
        if name in active and name not in checked and here and _ok(tuple(req), have, box, box_gate):
            out.append(name)
    return out
