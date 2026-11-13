"""Jill's position -> where she is on the Key Map (TessarionAM, 2026-11-12, v0.9.4). Pure Python.

The game gives each room its own coordinates (x, y = height, z). Some of its rooms are two rooms
on our map (one room number): Tea Room + Northern Corridor (0x103), Winding Corridor + Bathroom
(0x109), Graveyard + Crypt (0x10b), Large Art Room + Mirror Room (0x111); and some rooms span two
floor drawings (Main Hall 0x106, West Wing Inner Stairway 0x101). The room number can't tell
those apart; Jill's position can.

Calibration, from the game's own door data (no hand-placed numbers): every door has an arrival
spot in the room's coordinates (client/door_data.ARRIVALS, BhdTool's rooms.json) and a place on
our floor drawing (map_geometry snaps it onto its wall). Fitting the two (2026-11-12):
  - every floor: game x -> map x, game z -> map y, same direction, no rotation;
  - one scale per floor (Mansion 1F 48.3, 2F 48.5 game units per map cell);
  - one offset per room (each room has its own origin);
  - Jill appears about 30 units in front of the door (facing angle).
  Typical error 0.7 cells, worst 1.3 - well inside any room, so the room is never guessed; at a
  doorway the view keeps the room she was in until she's clearly past it (HYSTERESIS).
Height (y) picks the floor drawing: the floor whose door spots for this room are nearest in y.
"""
import math
from typing import Dict, List, Optional, Tuple

from .map_geometry import floor, logic_room
from .map_layout import FLOORS

FACING_OFFSET = 30.0      # game units between a door and where Jill appears in front of it
HYSTERESIS = 1.0          # cells: stay in the previous room until this far outside it
_MIN_OBS = 2


def _arrivals():
    from .client.door_data import ARRIVALS
    return ARRIVALS


def room_number(name: str) -> Optional[int]:
    """Game room number of a drawn room (None if unknown)."""
    from .game_data import ROOM_NUMBERS
    from .map_geometry import MAP_ONLY_NUMBERS
    if name in MAP_ONLY_NUMBERS:
        return MAP_ONLY_NUMBERS[name]
    return ROOM_NUMBERS.get(logic_room(name) or name)


def _door_point(x, z, angle):
    th = math.radians(angle)
    return x - FACING_OFFSET * math.sin(th), z - FACING_OFFSET * math.cos(th)


class Fit:
    """Per floor: scale (cells per game unit); per (floor, room number): offset and door heights."""

    def __init__(self):
        self.scale: Dict[int, float] = {}
        self.offset: Dict[Tuple[int, int], Tuple[float, float]] = {}
        self.levels: Dict[Tuple[int, int], List[float]] = {}
        self.residuals: List[float] = []
        arrivals = _arrivals()
        for fi in range(len(FLOORS)):
            f = floor(fi)
            obs = []
            for (_x, _y, _hz, a, b), (sx, sy, _h, _a, _b) in zip(f.doors, f.snapped):
                if not b:
                    continue
                for here, there in ((a, b), (b, a)):
                    r, s = room_number(here), room_number(there)
                    if r is None or s is None or r == s:
                        continue
                    spots = [e for e in arrivals.get(r, []) if e[0] == s and any(e[1:4])]
                    if len(spots) != 1:
                        continue
                    _src, x, y, z, ang, _cut = spots[0]
                    px, pz = _door_point(x, z, ang)
                    obs.append((r, px, y, pz, sx, sy))
            by_room: Dict[int, list] = {}
            for o in obs:
                by_room.setdefault(o[0], []).append(o)
            num = den = 0.0
            for os_ in by_room.values():
                if len(os_) < _MIN_OBS:
                    continue
                mx = sum(o[1] for o in os_) / len(os_)
                mz = sum(o[3] for o in os_) / len(os_)
                gx = sum(o[4] for o in os_) / len(os_)
                gy = sum(o[5] for o in os_) / len(os_)
                num += sum((o[1] - mx) * (o[4] - gx) + (o[3] - mz) * (o[5] - gy) for o in os_)
                den += sum((o[1] - mx) ** 2 + (o[3] - mz) ** 2 for o in os_)
            if den <= 0 or num <= 0:
                continue
            s = num / den
            self.scale[fi] = s
            for r, os_ in by_room.items():
                tx = sum(o[4] - s * o[1] for o in os_) / len(os_)
                ty = sum(o[5] - s * o[3] for o in os_) / len(os_)
                self.offset[(fi, r)] = (tx, ty)
                self.levels[(fi, r)] = [o[2] for o in os_]
                if len(os_) >= _MIN_OBS:
                    self.residuals += [math.hypot(o[4] - s * o[1] - tx, o[5] - s * o[3] - ty) for o in os_]

    def to_map(self, fi: int, number: int, x: float, z: float) -> Optional[Tuple[float, float]]:
        if fi not in self.scale or (fi, number) not in self.offset:
            return None
        s = self.scale[fi]
        tx, ty = self.offset[(fi, number)]
        return s * x + tx, s * z + ty


_FIT: Optional[Fit] = None


def fit() -> Fit:
    global _FIT
    if _FIT is None:
        _FIT = Fit()
    return _FIT


class Where:
    """Jill on the map: floor index, the drawn room(s) to light up, her map point (or None)."""

    def __init__(self, floor_index: int, rooms: List[str], point: Optional[Tuple[float, float]] = None):
        self.floor, self.rooms, self.point = floor_index, rooms, point

    def __repr__(self):
        return f"Where({FLOORS[self.floor][0]!r}, {self.rooms}, {self.point})"


def drawn_rooms(number: int) -> Dict[int, List[str]]:
    """{floor index: drawn rooms with this game room number}."""
    out: Dict[int, List[str]] = {}
    for fi in range(len(FLOORS)):
        for name in floor(fi).names:
            if room_number(name) == number:
                out.setdefault(fi, []).append(name)
    return out


def locate(number: Optional[int], pos: Optional[Tuple[float, float, float]] = None,
           previous: Optional[str] = None) -> Optional[Where]:
    """Where Jill is on the map, from the game's room number and (if known) her x, y, z.
    Without a position, every drawn room with that number lights up (the best the number alone
    can say)."""
    if number is None:
        return None
    rooms = drawn_rooms(number)
    if not rooms:
        return None
    if pos is None:
        fi = min(rooms)
        return Where(fi, rooms[fi])
    x, y, z = pos
    fl = fit()
    # floor: nearest door height for this room; a floor with no door data of its own (e.g. the
    # Crypt under the Graveyard) takes over when Jill is far from every known height
    known = {fi: min(abs(y - lv) for lv in fl.levels[(fi, number)]) for fi in rooms if (fi, number) in fl.levels}
    unknown = [fi for fi in rooms if fi not in known]
    if known:
        fi = min(known, key=known.get)
        if unknown and known[fi] > 150:
            fi = unknown[0]
    else:
        fi = min(rooms)
    names = rooms[fi]
    point = fl.to_map(fi, number, x, z)
    if len(names) == 1 or point is None:
        return Where(fi, names if len(names) == 1 else names, point)
    f = floor(fi)
    gx, gy = point
    if previous in names and _distance(f, previous, gx, gy) <= HYSTERESIS:
        return Where(fi, [previous], point)
    inside = f.room_at(gx, gy)
    if inside in names:
        return Where(fi, [inside], point)
    best = min(names, key=lambda n: _distance(f, n, gx, gy))
    return Where(fi, [best], point)


def _distance(f, name: str, gx: float, gy: float) -> float:
    """Distance in cells from the point to the nearest cell of the drawn room (0 inside)."""
    if f.room_at(gx, gy) == name:
        return 0.0
    best = 1e9
    for rx, ry, rw, rh in f.rects[name]:
        dx = max(rx - gx, 0, gx - (rx + rw))
        dy = max(ry - gy, 0, gy - (ry + rh))
        best = min(best, math.hypot(dx, dy))
    return best
