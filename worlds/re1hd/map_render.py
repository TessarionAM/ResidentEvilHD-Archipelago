"""Key Map drawing as a list of simple shapes (TessarionAM, 2026-11-12). No Kivy here: the client's
Key Map tab (client/key_map_view.py) turns the shapes into Kivy instructions, and the tests /
preview tool turn the same shapes into a PNG, so what's tested is what's drawn.

v0.9.2 (TessarionAM: "a map, not a tracker"): no room badges; every wall exactly the same thickness
(everything is laid out on whole pixels); one-way doors dark green.
v0.9.3 (TessarionAM): ordinary doors - and locked doors once they're unlocked - are dark blue; a door
you can't open yet (no key, or it needs an item you haven't got) is fully red; a locked door you
hold the key for is in its key's colour; Jill's room glows from 25% darker to 50% brighter.
v0.9.4 (TessarionAM): doors that need an item are red until you have it, then ordinary; they're no
longer in the map key (the off-map ones aren't drawn anyway). Jill's room comes from her
position (map_position.py), not the room number alone.

Shapes, in whole pixels, origin top-left, y going down:
  ("rect", rgba, x, y, w, h)
  ("pulse", rgba, x, y, w, h)                     a rect that glows (Jill's room)
  ("ring_rect", rgba, x, y, w, h, width)          rectangle outline, width = full thickness
  ("text", rgba, text, size, x, y, bold)          x, y = top-left of the text
"""
import math
from typing import Callable, List, Optional, Tuple

from .map_geometry import DOOR_LEN, floor, logic_room
from .tracker import KEY_COLOURS, key_name, same_game_room

Measure = Callable[[str, int, bool], Tuple[float, float]]


def rgba(hexstr: str, a: float = 1.0):
    return (int(hexstr[0:2], 16) / 255, int(hexstr[2:4], 16) / 255, int(hexstr[4:6], 16) / 255, a)


BG = rgba("1c2026")
ROOM = rgba("4c5056")
WALL = rgba("0b0c0e")
ONE_WAY = rgba("1e7a3c")                  # dark green (TessarionAM)
CANT_OPEN = rgba("e02424")                # a door you can't open yet: fully red (TessarionAM)
HOLLOW = CANT_OPEN
ORDINARY = rgba("1f3fbf")                 # ordinary + unlocked doors: dark blue (TessarionAM)
TEXT, DIM = rgba("e8eaed"), rgba("9aa0a8")
PANEL, PANEL_EDGE = rgba("171a1e"), rgba("2c3036")
TIP, TIP_EDGE = rgba("0b0d10", 0.96), rgba("6b717a")
HOVER = rgba("ffffff")
FADE = 0.22                               # other doors while a key is highlighted
WALL_PX = 3                               # every wall line, every floor
DOOR_PX = WALL_PX + 6                     # locked doors: thicker than the wall they sit on
MIN_SCALE, MAX_SCALE = 2, 10              # pixels per cell
PULSE_LOW, PULSE_HIGH, PULSE_SECONDS = 0.75, 1.5, 2.0   # Jill's room: 25% darker .. 50% brighter, 2 s loop
# Boss Rush (TessarionAM, 2026-11-15): a small skull in each boss room while the boss is alive; it
# disappears once the boss is dead (TessarionAM, 19:15). Drawn from rects (pixel art), like
# everything else here.
SKULL_ALIVE, SKULL_DEAD, SKULL_EYES = rgba("f2ead8"), rgba("6b6f76"), rgba("0b0c0e")
SKULL = (".XXXXX.",
         "XXXXXXX",
         "X..X..X",
         "XXXXXXX",
         ".XX.XX.",
         ".X.X.X.")


def key_rgba(item: str):
    return rgba(KEY_COLOURS.get(item, "ffffff"))


def pulse_colour(base, t: float):
    """The glowing room colour t seconds into the loop: a smooth wave between 25% darker and 50%
    brighter than the normal room colour."""
    mid, amp = (PULSE_HIGH + PULSE_LOW) / 2, (PULSE_HIGH - PULSE_LOW) / 2
    k = mid + amp * math.sin(2 * math.pi * t / PULSE_SECONDS)
    return (min(1.0, base[0] * k), min(1.0, base[1] * k), min(1.0, base[2] * k), base[3])


class Scene:
    """The drawn floor: shapes, plus what hover tooltips need."""

    def __init__(self):
        self.ops: List[tuple] = []
        self.s = 1.0                 # pixels per grid cell (edges are rounded to whole pixels)
        self.ox = self.oy = 0        # pixel position of grid (0, 0)
        self.door_hits: List[Tuple[Tuple[int, int, int, int], dict]] = []
        self.legend_hits: List[Tuple[Tuple[float, float, float, float], str]] = []
        self.map_box = (0, 0, 0, 0)
        self.floor = None
        self.here: List[str] = []
        self.skulls: List[Tuple[str, str, bool]] = []     # (drawn room, boss, dead) - Boss Rush

    def to_grid(self, px, py):
        return (px - self.ox) / self.s, (py - self.oy) / self.s


# ------------------------------------------------------------------ pieces
def door_shapes(x, y, w, h, d, alpha=1.0):
    """Shapes of one locked door filling the whole-pixel box x, y, w, h."""
    a = lambda c: (c[0], c[1], c[2], c[3] * alpha)
    kind = d["kind"]
    if kind in ("open", "unlocked"):
        return [("rect", a(ORDINARY), x, y, w, h)]
    if not d["ok"] and kind in ("key", "item"):          # can't open it yet: fully red
        return [("rect", a(CANT_OPEN), x, y, w, h)]
    if kind == "item":                                  # you have the item: it opens like any door
        return [("rect", a(ORDINARY), x, y, w, h)]
    if kind == "key":
        return [("rect", a(key_rgba(d["key"])), x, y, w, h)]
    return [("rect", a(ONE_WAY), x, y, w, h)]          # one-way door


def _door_box(sc, d):
    """Whole-pixel box of a locked door centred on its wall line."""
    s = sc.s
    length = max(10, int(round(DOOR_LEN * s)))
    if d["hz"]:
        line = sc.oy + int(round(d["y"] * s))
        start = sc.ox + int(round(d["x"] * s)) - length // 2
        return start, line - WALL_PX // 2 - (DOOR_PX - WALL_PX) // 2, length, DOOR_PX
    line = sc.ox + int(round(d["x"] * s))
    start = sc.oy + int(round(d["y"] * s)) - length // 2
    return line - WALL_PX // 2 - (DOOR_PX - WALL_PX) // 2, start, DOOR_PX, length


# ------------------------------------------------------------------ the whole floor
def skull_shapes(cx: int, cy: int, px: int, dead: bool) -> List[tuple]:
    """A skull centred on cx, cy; px = size of one pixel-art cell."""
    w, h = len(SKULL[0]) * px, len(SKULL) * px
    x0, y0 = cx - w // 2, cy - h // 2
    ops = [("rect", SKULL_EYES, x0 - 1, y0 - 1, w + 2, h + 2)]          # dark outline
    bone = SKULL_DEAD if dead else SKULL_ALIVE
    for r, row in enumerate(SKULL):
        for c, ch in enumerate(row):
            ops.append(("rect", bone if ch == "X" else SKULL_EYES, x0 + c * px, y0 + r * px, px, px))
    return ops


def build(floor_index: int, state, width: float, height: float, current_room: Optional[str],
          measure: Measure, highlight: Optional[str] = None, here: Optional[List[str]] = None,
          bosses: Optional[dict] = None) -> Scene:
    """here: the drawn rooms Jill is in (from her position, map_position.locate). Without it,
    every drawn room with her game room's number glows. bosses: Boss Rush on - boss event name ->
    dead (the client's bosses_dead); None = no skulls."""
    _counts, doors, elsewhere = state
    f = floor(floor_index)
    sc = Scene()
    sc.floor = f
    ops = sc.ops
    width, height = int(width), int(height)
    ops.append(("rect", BG, 0, 0, width, height))
    if width < 60 or height < 60:
        return sc
    side = width >= 620
    if side:
        lw = int(min(270, max(220, width * 0.24)))
        map_box = (8, 8, width - lw - 24, height - 16)
        leg_box = (width - lw - 8, 8, lw, height - 16)
    else:
        lh = int(min(220, height * 0.42))
        map_box = (8, 8, width - 16, height - lh - 24)
        leg_box = (8, height - lh - 8, width - 16, lh)
    sc.map_box = map_box
    x0, y0, x1, y1 = f.bbox
    pad = 2
    gw, gh = (x1 - x0) + 2 * pad, (y1 - y0) + 2 * pad
    # any scale, but every edge lands on a whole pixel (rounded grid lines), so walls stay one width
    s = max(MIN_SCALE, min(MAX_SCALE, map_box[2] / gw, map_box[3] / gh))
    sc.s = s
    sc.ox = int(round(map_box[0] + (map_box[2] - gw * s) / 2 - (x0 - pad) * s))
    sc.oy = int(round(map_box[1] + (map_box[3] - gh * s) / 2 - (y0 - pad) * s))
    X = lambda gx: sc.ox + int(round(gx * s))
    Y = lambda gy: sc.oy + int(round(gy * s))

    # the client only knows the game's room number: every drawn room with that number glows
    # (Tea Room + Northern Corridor are one room, 0x103; Large Art + Mirror Room are 0x111)
    if here is None:
        group = same_game_room(current_room) if current_room else set()
        here = [n for n in f.names if n in group or logic_room(n) in group]
    else:
        here = [n for n in here if n in f.names]
    sc.here = here
    for name in f.names:
        kind = "pulse" if name in here else "rect"
        for rx, ry, rw, rh in f.rects[name]:
            ops.append((kind, ROOM, X(rx), Y(ry), X(rx + rw) - X(rx), Y(ry + rh) - Y(ry)))

    # doors on their walls (map_geometry moved the traced marks onto the wall)
    fdoors = []
    for d, (sx, sy, shz, _a, _b) in zip(doors[floor_index] if floor_index < len(doors) else [], f.snapped):
        d = dict(d, x=sx, y=sy, hz=shz)
        fdoors.append(d)

    # walls: one thickness everywhere
    t, h0 = WALL_PX, WALL_PX // 2
    # one-cell wall jogs right beside a door read as clutter: dropped
    near_door = [(d["x"] - DOOR_LEN / 2 - 1, d["y"] - 1.2, d["x"] + DOOR_LEN / 2 + 1, d["y"] + 1.2) if d["hz"] else
                 (d["x"] - 1.2, d["y"] - DOOR_LEN / 2 - 1, d["x"] + 1.2, d["y"] + DOOR_LEN / 2 + 1)
                 for d in fdoors]
    for wx0, wy0, wx1, wy1, _outer in f.walls:
        if (wx1 - wx0) + (wy1 - wy0) <= 1 and any(
                a0 <= min(wx0, wx1) and max(wx0, wx1) <= a1 and b0 <= min(wy0, wy1) and max(wy0, wy1) <= b1
                for a0, b0, a1, b1 in near_door):
            continue
        if wy0 == wy1:
            ops.append(("rect", WALL, X(wx0) - h0, Y(wy0) - h0, X(wx1) - X(wx0) + t, t))
        else:
            ops.append(("rect", WALL, X(wx0) - h0, Y(wy0) - h0, t, Y(wy1) - Y(wy0) + t))

    # doors on their walls: ordinary / unlocked ones first, locked ones on top
    for d in sorted(fdoors, key=lambda d: d["kind"] not in ("open", "unlocked")):
        bx, by, bw, bh = _door_box(sc, d)
        dim = highlight is not None and not _lit(d, highlight)
        ops.extend(door_shapes(bx, by, bw, bh, d, FADE if dim else 1.0))
        sc.door_hits.append(((bx - 3, by - 3, bw + 6, bh + 6), d))
    if bosses is not None:
        from .data import BOSSES
        px = max(2, int(round(s * 0.55)))
        for name, room, *_r in BOSSES:
            if bosses.get(name):
                continue                         # defeated: no skull
            for drawn in f.names:
                if drawn == room or logic_room(drawn) == room:
                    lx, ly = f.label_at[drawn]
                    ops.extend(skull_shapes(X(lx), Y(ly), px, bool(bosses.get(name))))
                    sc.skulls.append((drawn, name.replace(" Defeated", ""), bool(bosses.get(name))))
    _legend(sc, leg_box, fdoors, elsewhere, f, measure, highlight, sc.skulls)
    return sc


def _lit(d, highlight) -> bool:
    """Is this door lit up while the legend row `highlight` is hovered?"""
    if highlight == "cant":
        return d["kind"] in ("key", "item") and not d["ok"]
    return _legend_id(d) == highlight


def _legend_id(d) -> str:
    if d["kind"] == "unlocked" or (d["kind"] == "item" and d["ok"]):
        return "open"
    if d["kind"] == "key":
        return "key:" + d["key"]
    return d["kind"]


def _fit(text, size, maxw, measure, bold=False):
    if measure(text, size, bold)[0] <= maxw:
        return text
    while len(text) > 1 and measure(text + "...", size, bold)[0] > maxw:
        text = text[:-1]
    return text.rstrip() + "..."


def _legend(sc, box, fdoors, elsewhere, f, measure, highlight, skulls=()):
    ops = sc.ops
    bx, by, bw, bh = box
    ops.append(("rect", PANEL_EDGE, bx - 1, by - 1, bw + 2, bh + 2))
    ops.append(("rect", PANEL, bx, by, bw, bh))
    rows = [("title", "Map key"), ("head", "Rooms"), ("jill", "Jill is here (glows)")]
    for _drawn, boss, dead in skulls:
        rows.append(("skull", (f"{boss}: {'defeated' if dead else 'still alive'}", dead)))
    rows += [("head", "Doors"),
            ("door", ("open", dict(kind="open", ok=True), "ordinary / unlocked door"))]
    seen = {}
    for d in fdoors:
        seen.setdefault(_legend_id(d), d)
    if any(d["kind"] in ("key", "item") and not d["ok"] for d in fdoors):
        rows.append(("door", ("cant", dict(kind="key", key="", ok=False), "can't open yet")))
    for item in KEY_COLOURS:              # only keys whose doors show in their colour (you have it)
        lid = "key:" + item
        if lid in seen and seen[lid]["ok"]:
            rows.append(("door", (lid, dict(kind="key", key=item, ok=True), key_name(item))))
    if "one_sided" in seen:
        rows.append(("door", ("one_sided", dict(kind="one_sided", ok=True), "one-way door")))
    # doors not on the drawings (stairs, lifts, ladders) - key doors only (TessarionAM, v0.9.4: the
    # item ones aren't on the map and only made the key harder to read)
    far = [(a, b, d) for a, b, d in elsewhere
           if (a in f.names or b in f.names) and d["kind"] in ("key", "one_sided")]
    if far:
        rows.append(("head", "Stairs, lifts & ladders"))
        for a, b, d in far:
            rows.append(("door", (_legend_id(d), d, f"{a} - {b}")))
    rows.append(("hint", "Hover a room or door for details."))
    rows.append(("hint", "Hover a key here to light up its doors."))

    base = {"title": 28, "head": 24, "jill": 24, "open": 24, "door": 24, "hint": 18, "skull": 24}
    need = sum(base[k] for k, _ in rows) + 12
    k = max(0.62, min(1.0, (bh - 10) / need))
    fs = lambda n: max(9, int(round(n * k)))
    pad = 12
    sw_w = int(round(30 * k))
    sw_h = int(round(16 * k))
    tx = bx + pad + sw_w + 12
    maxw = bx + bw - pad - tx
    y = by + 8
    for n, (kind, p) in enumerate(rows):
        rh = int(round(base[kind] * k))
        nxt = int(round(base[rows[n + 1][0]] * k)) if kind == "head" and n + 1 < len(rows) else 0
        if y + rh + nxt > by + bh - 2:
            break
        sx, sy = bx + pad, y + (rh - sw_h) // 2
        label_y = lambda size: y + int((rh - size * 1.25) / 2)
        if kind == "title":
            ops.append(("text", TEXT, "Map key", fs(16), bx + pad, y + 3, True))
        elif kind == "head":
            ops.append(("text", DIM, p.upper(), fs(11), bx + pad, y + int(rh * 0.35), True))
        elif kind == "hint":
            ops.append(("text", DIM, _fit(p, fs(11), bw - 2 * pad, measure), fs(11), bx + pad, y + 2, False))
        elif kind == "jill":
            ops.append(("pulse", ROOM, sx, sy, sw_w, sw_h))
            ops.append(("ring_rect", WALL, sx, sy, sw_w, sw_h, 2))
            ops.append(("text", TEXT, p, fs(13), tx, label_y(fs(13)), False))
        elif kind == "skull":
            label, dead = p
            ops.extend(skull_shapes(sx + sw_w // 2, y + rh // 2, max(2, sw_h // 6), dead))
            ops.append(("text", DIM if dead else TEXT, _fit(label, fs(13), maxw, measure), fs(13),
                        tx, label_y(fs(13)), False))
        elif kind == "open":
            ops.append(("rect", ROOM, sx, sy, sw_w, sw_h))
            mid = sy + sw_h // 2 - WALL_PX // 2
            gap = sw_w // 3
            ops.append(("rect", WALL, sx, mid, gap, WALL_PX))
            ops.append(("rect", WALL, sx + sw_w - gap, mid, gap, WALL_PX))
            ops.append(("text", TEXT, p, fs(13), tx, label_y(fs(13)), False))
        elif kind == "door":
            lid, d, label = p
            dim = highlight is not None and lid != highlight
            if lid is not None and lid == highlight:
                ops.append(("rect", rgba("ffffff", 0.08), bx + 3, y, bw - 6, rh))
            dh = DOOR_PX + 1
            ops.extend(door_shapes(sx, y + (rh - dh) // 2, sw_w, dh, d, FADE if dim else 1.0))
            size = fs(13 if not label.count(" - ") else 12)
            ops.append(("text", DIM if dim else TEXT, _fit(label, size, maxw, measure), size,
                        tx, label_y(size), False))
            if lid is not None:
                sc.legend_hits.append(((bx, y, bw, rh), lid))
        y += rh


# ------------------------------------------------------------------ hover
def tooltip_lines(sc: Scene, px: float, py: float):
    """(lines, door dict or None, room name or None, legend id or None) for the mouse at px, py."""
    for (x, y, w, h), lid in sc.legend_hits:
        if x <= px <= x + w and y <= py <= y + h:
            return [], None, None, lid
    mx, my, mw, mh = sc.map_box
    if not (mx <= px <= mx + mw and my <= py <= my + mh):
        return [], None, None, None
    for (x, y, w, h), d in sc.door_hits:
        if x <= px <= x + w and y <= py <= y + h:
            return door_text(d), d, None, None
    gx, gy = sc.to_grid(px, py)
    room = sc.floor.room_at(gx, gy) if sc.floor else None
    if room is None:
        return [], None, None, None
    lines = [room]
    if room in sc.here:
        others = [n for n in sc.here if n != room]
        lines.append("Jill is here" if not others else
                     f"Jill is here or in the {' / '.join(others)} (one room to the game)")
    for drawn, boss, dead in sc.skulls:
        if drawn == room:
            lines.append(f"Boss Rush: {boss} - {'defeated' if dead else 'still alive'}")
    return lines, None, room, None


def door_text(d) -> List[str]:
    return _door_text(d) + list(d.get("leads", []))


def _door_text(d) -> List[str]:
    where = f"{d['a']} - {d['b']}" if d.get("b") else f"{d['a']} (to another floor or outside)"
    kind = d["kind"]
    if kind == "open":
        return ["Door", where]
    if kind == "unlocked":
        was = key_name(d["key"]) + " door" if d.get("was") == "key" and d.get("key") else \
            "one-way door" if d.get("was") == "one_sided" else "locked door"
        return ["Unlocked door", where, f"Was a {was} - you've opened it"]
    if kind == "key":
        k = key_name(d["key"])
        lines = [f"{k} door", where]
        others = [n for n in d.get("needs", []) if n != d["key"]]
        if others:              # e.g. the Courtyard Study: Helmet Key + the Broach (TessarionAM, 2026-11-13)
            lines.append("Also needs: " + ", ".join(key_name(n) for n in others))
        missing = d.get("missing")
        if missing is None:     # older state dicts
            missing = [] if d["ok"] else [d["key"]]
        if d["ok"]:
            lines.append("You have everything it needs" if others else "You have the key")
        else:
            lines.append("Can't open yet - you still need: " + ", ".join(key_name(n) for n in missing))
        return lines
    if kind == "item":
        need = ", ".join(key_name(n) for n in d["needs"])
        return ["Needs " + need, where, "You have it" if d["ok"] else "Can't open yet - you haven't got it"]
    return ["One-way door", where, "Opens from " + " / ".join(d["opens_from"]) + " only"]


def overlay(sc: Scene, px: float, py: float, width: float, height: float, measure: Measure):
    """Shapes drawn over the map for the mouse at px, py: a white frame round the hovered door and
    the tooltip box. Returns (shapes, legend id under the mouse or None)."""
    lines, d, _room, lid = tooltip_lines(sc, px, py)
    ops: List[tuple] = []
    if d is not None:
        (x, y, w, h), _d = next(hit for hit in sc.door_hits if hit[1] is d)
        ops.append(("ring_rect", HOVER, x, y, w, h, 2))
    if lines:
        size = 13
        sizes = [(ln, measure(ln, size + (1 if i == 0 else 0), i == 0)) for i, ln in enumerate(lines)]
        tw = int(max(m[0] for _l, m in sizes)) + 20
        th = int(sum(m[1] + 3 for _l, m in sizes)) + 14
        tx, ty = int(px) + 16, int(py) + 18
        if tx + tw > width - 4:
            tx = int(px) - tw - 12
        if ty + th > height - 4:
            ty = int(py) - th - 12
        tx, ty = max(4, tx), max(4, ty)
        ops.append(("rect", TIP_EDGE, tx - 1, ty - 1, tw + 2, th + 2))
        ops.append(("rect", TIP, tx, ty, tw, th))
        yy = ty + 7
        for i, (ln, (_w, h)) in enumerate(sizes):
            col = TEXT if i == 0 else DIM
            if d is not None and i == 0 and d["kind"] == "key":
                col = key_rgba(d["key"])
            elif d is not None and i == 0 and d["kind"] in ("open", "unlocked"):
                col = rgba("7d93ff")
            elif d is not None and i == 0 and d["kind"] == "one_sided":
                col = rgba("3fbf6a")
            ops.append(("text", col, ln, size + (1 if i == 0 else 0), tx + 10, int(yy), i == 0))
            yy += h + 3
    return ops, lid
