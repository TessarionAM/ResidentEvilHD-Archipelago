"""Cleaned-up floor shapes for the Key Map (TessarionAM, 2026-11-12, v0.9.1). Pure Python, no Kivy.

map_layout.py holds the shapes as traced from evilresource.com at 1/3 scale. The tracing left
1-2 cell gaps where the source map had wall lines and door markers, so rooms looked cut off from
each other ("not connected") and doors had black slits beside them. clean_floor() fills those
gaps once per floor and works out everything the drawing needs:
  - owner grid (which room each cell belongs to),
  - fill rectangles per room,
  - wall segments (between two rooms, or a room and outside),
  - a label point per room (the cell deepest inside it, for the status badge),
  - the content bounding box (so the drawing can zoom to what's actually there),
  - every door moved onto the wall between its two rooms (v0.9.2: traced door marks sat
    beside the walls in places).
"""
from typing import Dict, List, Optional, Tuple

from .map_layout import FLOORS

DOOR_LEN = 2.2         # door length in cells (doors are kept inside their wall run)
SNAP_RANGE = 5.0       # a traced door moves onto a wall of its rooms within this many cells
SAME_ROOM_GAP = 4      # a gap this wide (cells) with the same room on both sides is filled
TWO_ROOM_GAP = 2       # a gap this wide between two different rooms is filled (split between them)

# Map-only names -> the room our logic uses (None = no checks there, always grey).
LOGIC_ROOM: Dict[str, Optional[str]] = {
    "Large Art Room": "Large Art & Mirror Rooms",
    "Mirror Room": "Large Art & Mirror Rooms",
    "Secret Passage (1F)": None,
    "Hidden Wardrobe": None,
    "Aqua Ring Exit": None,
    "Residence Medical Room": None,
    "Room 003 Bathroom": None,
    "Surgeon's Room": None,
}
# Game room numbers of map-only rooms (BhdTool's rooms.json), so Jill can be shown in them.
MAP_ONLY_NUMBERS: Dict[str, int] = {
    "Hidden Wardrobe": 0x11C,
    "Residence Medical Room": 0x409,
    "Room 003 Bathroom": 0x40B,
}
# Rooms that share one logic room: only this one carries the status badge.
BADGE_HOLDER = {"Large Art & Mirror Rooms": "Large Art Room"}


def logic_room(name: str) -> Optional[str]:
    """The logic room a drawn room belongs to (None if it has no checks of its own)."""
    return LOGIC_ROOM.get(name, name) if name else None


class Floor:
    def __init__(self, index: int):
        title, w, h, rooms, doors = FLOORS[index]
        self.index, self.title, self.w, self.h = index, title, w, h
        self.names: List[str] = list(rooms)
        self.doors = doors
        grid = [[-1] * w for _ in range(h)]
        for i, rects in enumerate(rooms.values()):
            for x, y, rw, rh in rects:
                for yy in range(y, y + rh):
                    for xx in range(x, x + rw):
                        grid[yy][xx] = i
        _fill_gaps(grid, w, h)
        _fill_gaps(grid, w, h)            # a second pass closes corners the first one opened up
        _smooth(grid, w, h)               # one-cell bumps and notches made walls look jagged
        _straighten(grid, w, h)           # 1-deep notches up to 3 long (wall jogs beside doors)
        self.grid = grid
        self.rects = {n: _rects_of(grid, i, w, h) for i, n in enumerate(self.names)}
        self.walls = _walls(grid, w, h)
        self.label_at = {n: _deepest(grid, i, w, h) for i, n in enumerate(self.names)}
        self.snapped = [_snap_door(grid, w, h, self.names, d) for d in doors]
        xs = [x for y in range(h) for x in range(w) if grid[y][x] >= 0]
        ys = [y for y in range(h) for x in range(w) if grid[y][x] >= 0]
        self.bbox = (min(xs), min(ys), max(xs) + 1, max(ys) + 1)

    def room_at(self, gx: float, gy: float) -> Optional[str]:
        x, y = int(gx), int(gy)
        if 0 <= x < self.w and 0 <= y < self.h and gx >= 0 and gy >= 0 and self.grid[y][x] >= 0:
            return self.names[self.grid[y][x]]
        return None

    def outline_of(self, name: str) -> List[Tuple[int, int, int, int]]:
        """Boundary segments of one room (for the 'Jill is here' highlight)."""
        i = self.names.index(name)
        return _walls(self.grid, self.w, self.h, only=i)


def _snap_door(grid, w, h, names, door):
    """Move a traced door onto the wall between its two rooms (or onto its room's edge when the
    other side is another floor / outside), centred inside that stretch of wall. Returns
    (x, y, horizontal, a, b) in grid units: a horizontal door sits on the line y, a vertical one on x."""
    x, y, _hz, a, b = door
    ia = names.index(a) if a in names else None
    ib = names.index(b) if b in names else None
    if ia is None:
        return door
    own = lambda xx, yy: grid[yy][xx] if 0 <= xx < w and 0 <= yy < h else -1

    def ok(p, q):
        if ib is not None:
            return {p, q} == {ia, ib}
        return ia in (p, q) and -1 in (p, q)        # to another floor / outside: an outer wall

    best = None
    for strict in (True, False):
        for yy in range(max(0, int(y - SNAP_RANGE)), min(h, int(y + SNAP_RANGE) + 2)):
            for xx in range(max(0, int(x - SNAP_RANGE)), min(w, int(x + SNAP_RANGE) + 2)):
                # horizontal edge on line yy, cell column xx; vertical edge on line xx, cell row yy
                for horiz, p, q, mx, my in ((True, own(xx, yy - 1), own(xx, yy), xx + 0.5, yy),
                                            (False, own(xx - 1, yy), own(xx, yy), xx, yy + 0.5)):
                    good = ok(p, q) if strict else (ia in (p, q) and p != q)
                    if not good:
                        continue
                    dist = (mx - x) ** 2 + (my - y) ** 2
                    if dist <= SNAP_RANGE ** 2 and (best is None or dist < best[0]):
                        best = (dist, horiz, xx, yy, frozenset((p, q)))
        if best is not None:
            break
    if best is None:
        return door
    _d, horiz, ex, ey, pair = best
    if horiz:
        lo = hi = ex
        while lo - 1 >= 0 and frozenset((own(lo - 1, ey - 1), own(lo - 1, ey))) == pair:
            lo -= 1
        while hi + 1 < w and frozenset((own(hi + 1, ey - 1), own(hi + 1, ey))) == pair:
            hi += 1
        cx = _clamp(x, lo + DOOR_LEN / 2, hi + 1 - DOOR_LEN / 2)
        return (cx, float(ey), 1, a, b)
    lo = hi = ey
    while lo - 1 >= 0 and frozenset((own(ex - 1, lo - 1), own(ex, lo - 1))) == pair:
        lo -= 1
    while hi + 1 < h and frozenset((own(ex - 1, hi + 1), own(ex, hi + 1))) == pair:
        hi += 1
    cy = _clamp(y, lo + DOOR_LEN / 2, hi + 1 - DOOR_LEN / 2)
    return (float(ex), cy, 0, a, b)


def _clamp(v, lo, hi):
    if lo > hi:
        return (lo + hi) / 2
    return min(max(v, lo), hi)


def _fill_gaps(grid, w, h):
    snap = [row[:] for row in grid]
    for y in range(h):
        for x in range(w):
            if snap[y][x] >= 0:
                continue
            best = None
            for dx, dy in ((1, 0), (0, 1)):
                a, da = _scan(snap, w, h, x, y, -dx, -dy)
                b, db = _scan(snap, w, h, x, y, dx, dy)
                if a < 0 or b < 0:
                    continue
                gap = da + db - 1
                if (a == b and gap <= SAME_ROOM_GAP) or (a != b and gap <= TWO_ROOM_GAP):
                    pick = a if da <= db else b
                    if best is None or gap < best[0]:
                        best = (gap, pick)
            if best is not None:
                grid[y][x] = best[1]


def _smooth(grid, w, h, passes=2):
    """A cell whose neighbours on 3 or 4 sides all belong to one other owner (another room, or
    outside) joins that owner: removes one-cell bumps and fills one-cell notches. Room cells are
    only taken away in the first pass, so nothing gets eaten away bit by bit."""
    for n in range(passes):
        snap = [row[:] for row in grid]
        for y in range(h):
            for x in range(w):
                me = snap[y][x]
                if me >= 0 and n > 0:
                    continue
                nb = [snap[y + dy][x + dx] if 0 <= x + dx < w and 0 <= y + dy < h else -1
                      for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))]
                for o in set(nb):
                    if o != me and nb.count(o) >= 3:
                        grid[y][x] = o
                        break


def _straighten(grid, w, h, max_len=3, rounds=4):
    """Straighten walls: a run of up to max_len cells of one owner, one cell deep, with another
    owner B just before and after it along the run and B all along one side, is a notch in B's
    wall - those cells join B. (Seed test 6: the Dark Corridor / Winding Corridor wall jogged by
    one cell right where the door is, leaving short stray wall lines.)"""
    for _ in range(rounds):
        snap = [row[:] for row in grid]
        own = lambda x, y: snap[y][x] if 0 <= x < w and 0 <= y < h else -1
        changed = False
        for vertical in (True, False):
            outer, inner = (w, h) if vertical else (h, w)
            for o in range(outer):
                at = (lambda i, o=o: own(o, i)) if vertical else (lambda i, o=o: own(i, o))
                side = (lambda i, d, o=o: own(o + d, i)) if vertical else (lambda i, d, o=o: own(i, o + d))
                i = 0
                while i < inner:
                    a, i0 = at(i), i
                    while i < inner and at(i) == a:
                        i += 1
                    i1 = i - 1
                    if i1 - i0 + 1 > max_len:
                        continue
                    b = at(i0 - 1)
                    if b == a or b != at(i1 + 1):
                        continue
                    if any(all(side(k, d) == b for k in range(i0, i1 + 1)) for d in (1, -1)):
                        for k in range(i0, i1 + 1):
                            x, y = (o, k) if vertical else (k, o)
                            if grid[y][x] != b:
                                grid[y][x] = b
                                changed = True
        if not changed:
            return


def _scan(g, w, h, x, y, dx, dy):
    for d in range(1, SAME_ROOM_GAP + 2):
        xx, yy = x + dx * d, y + dy * d
        if not (0 <= xx < w and 0 <= yy < h):
            return -1, d
        if g[yy][xx] >= 0:
            return g[yy][xx], d
    return -1, SAME_ROOM_GAP + 2


def _rects_of(grid, i, w, h):
    """Cells of room i as rectangles: runs per row, merged downwards while they match."""
    open_runs, out = {}, []
    for y in range(h + 1):
        runs = set()
        if y < h:
            x = 0
            while x < w:
                if grid[y][x] == i:
                    s = x
                    while x < w and grid[y][x] == i:
                        x += 1
                    runs.add((s, x - s))
                else:
                    x += 1
        for run in list(open_runs):
            if run not in runs:
                y0 = open_runs.pop(run)
                out.append((run[0], y0, run[1], y - y0))
        for run in runs:
            open_runs.setdefault(run, y)
    return out


def _walls(grid, w, h, only=None):
    """Segments (x0, y0, x1, y1, outer) wherever two cells of different owners meet; outer = one
    side is outside. With only=i, just the boundary of room i."""
    own = lambda x, y: grid[y][x] if 0 <= x < w and 0 <= y < h else -1
    segs = []
    for y in range(h + 1):
        start = None
        for x in range(w + 1):
            a, b = own(x, y - 1), own(x, y)
            wall = x < w and a != b and (only is None or only in (a, b))
            kind = (a < 0 or b < 0) if wall else None
            if start is not None and kind != start[1]:
                segs.append((start[0], y, x, y, start[1]))
                start = None
            if wall and start is None:
                start = (x, kind)
    for x in range(w + 1):
        start = None
        for y in range(h + 1):
            a, b = own(x - 1, y), own(x, y)
            wall = y < h and a != b and (only is None or only in (a, b))
            kind = (a < 0 or b < 0) if wall else None
            if start is not None and kind != start[1]:
                segs.append((x, start[0], x, y, start[1]))
                start = None
            if wall and start is None:
                start = (y, kind)
    return segs


def _deepest(grid, i, w, h):
    """The cell of room i furthest from its edge (a breadth-first distance map), as a centre point."""
    from collections import deque
    dist, q = {}, deque()
    cells = [(x, y) for y in range(h) for x in range(w) if grid[y][x] == i]
    for x, y in cells:
        if any(not (0 <= x + dx < w and 0 <= y + dy < h) or grid[y + dy][x + dx] != i
               for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
            dist[(x, y)] = 0
            q.append((x, y))
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (x + dx, y + dy)
            if n not in dist and 0 <= n[0] < w and 0 <= n[1] < h and grid[n[1]][n[0]] == i:
                dist[n] = dist[(x, y)] + 1
                q.append(n)
    if not dist:
        return (0.0, 0.0)
    best = max(dist.values())
    top = [c for c in cells if dist[c] == best]
    cx = sum(c[0] for c in top) / len(top)
    cy = sum(c[1] for c in top) / len(top)
    x, y = min(top, key=lambda c: (c[0] - cx) ** 2 + (c[1] - cy) ** 2)
    return (x + 0.5, y + 0.5)


_CACHE: Dict[int, Floor] = {}


def floor(index: int) -> Floor:
    if index not in _CACHE:
        _CACHE[index] = Floor(index)
    return _CACHE[index]
