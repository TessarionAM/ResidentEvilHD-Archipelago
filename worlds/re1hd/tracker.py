"""
Tracker and key map text for the client window (TessarionAM, 2026-11-11). Pure functions (no Kivy), so
they're tested offline; RE1HDClient puts the text into two tabs: "Tracker" and "Key Map".
Kivy markup: [b]bold[/b], [color=rrggbb]...[/color].
"""
from collections import Counter
from typing import Dict, Iterable, List, Optional, Set

from .data import DOORS, EXTRA_CHECKS, PICKUPS
from .logic_tracker import closure, in_logic, reachable_rooms

# One colour per key, used in the Tracker tab and on the drawn Key Map. v0.9.2: TessarionAM picked the
# Mansion key colours; the rest are chosen to stay apart from them. Ordinary doors are gaps in the wall.
KEY_COLOURS: Dict[str, str] = {
    "Book of Curses": "ffe600",   # Sword Key - bright yellow (TessarionAM, v0.9.2)
    "Armor Key": "7cc8ff",        # light blue (TessarionAM)
    "Shield Key": "d9620b",       # dark orange (TessarionAM)
    "Helmet Key": "9b4dff",       # purple (TessarionAM)
    "Lock Pick": "ffb3d1",        # baby pink (TessarionAM)
    "Master Key": "ffffff",       # white
    "Power Key": "14b8a6",        # teal
    "001 Key": "a3e635",          # lime
    "003 Key": "a8743a",          # brown
    "Gallery Key": "e0218a",      # magenta
    "Control Room Key": "00e5ff", # cyan (v0.9.3: royal blue was too close to the dark blue ordinary doors)
}
KEY_NAMES: Dict[str, str] = {"Book of Curses": "Sword Key"}   # item name -> name players know
GREY, GREEN = "808080", "70d070"

_ROOM_OF: Dict[str, str] = {name: room for room, name, _i, _r in PICKUPS}
_ROOM_OF.update({name: room for _c, room, name, _r in EXTRA_CHECKS})


def drop_gone(active: Set[str], checked: Set[str], received: Iterable[str]) -> Set[str]:
    """Checks the game won't let you do any more once you hold an item (data.GONE_WHEN, e.g. the
    Cerberus' Collar once a Collar was received) leave the tracker - unless already done."""
    from .data import GONE_WHEN
    have = set(received)
    return {n for n in active if n in checked or GONE_WHEN.get(n) not in have}


def boss_lines(bosses: Optional[Dict[str, bool]]) -> List[str]:
    """Boss Rush (2026-11-15, TessarionAM): which bosses are dead and which are left.
    bosses = the client's bosses_dead (boss event name -> dead); None = Boss Rush is off."""
    if bosses is None:
        return []
    from .data import BOSSES
    dead = [name for name, *_r in BOSSES if bosses.get(name)]
    lines = [f"[b]Boss Rush: {len(dead)} of {len(BOSSES)} defeated[/b]"
             + ("" if bosses else f"   [color={GREY}](load your game to read them)[/color]")]
    for name, room, *_r in BOSSES:
        label = name.replace(" Defeated", "")
        if bosses.get(name):
            lines.append(f"[color={GREEN}]{label}: defeated[/color]")
        else:
            lines.append(f"{label}: left ({room})")
    return lines + [""]


def tracker_text(received: Iterable[str], active: Set[str], checked: Set[str], box_gate: bool,
                 bosses: Optional[Dict[str, bool]] = None) -> str:
    received = list(received)
    reachable = in_logic(received, active, checked, box_gate)
    lines = [f"[b]Checks you can do now: {len(reachable)}[/b]   "
             f"(done {len(checked)} of {len(active)})", ""]
    lines = boss_lines(bosses) + lines
    by_room: Dict[str, List[str]] = {}
    for name in reachable:
        by_room.setdefault(_ROOM_OF.get(name, "?"), []).append(name.split(" - ", 1)[-1])
    for room in sorted(by_room):
        lines.append(f"[b]{room}[/b]: " + ", ".join(by_room[room]))
    if not reachable:
        lines.append("Nothing in logic right now. If you think you're stuck, report it with your client log (see the README).")
    have = Counter(received)
    lines += ["", "[b]Keys[/b]"]
    for key, colour in KEY_COLOURS.items():
        mark = f"[color={GREEN}]have[/color]" if have[key] else f"[color={GREY}]not yet[/color]"
        lines.append(f"[color={colour}]{key}[/color]: {mark}")
    return "\n".join(lines)


def key_map_text(received: Iterable[str], box_gate: bool) -> str:
    """Every locked door, grouped by the key that opens it, coloured per key."""
    have = Counter(received)
    rooms = reachable_rooms(have, True, box_gate)
    by_key: Dict[str, List[str]] = {}
    for a, b, req, one_way in DOORS:
        for r in req:
            arrow = "->" if one_way else "<->"
            seen = a in rooms or b in rooms
            text = f"{a} {arrow} {b}"
            by_key.setdefault(r, []).append(text if seen else f"[color={GREY}]{text}[/color]")
    lines = ["[b]Locked doors by key[/b]  (grey = you haven't reached either side yet)", ""]
    for key in list(KEY_COLOURS) + sorted(k for k in by_key if k not in KEY_COLOURS):
        if key not in by_key:
            continue
        colour = KEY_COLOURS.get(key, "ffffff")
        status = "have" if have[key] else "not yet"
        lines.append(f"[b][color={colour}]{key}[/color][/b] ({status})")
        lines += [f"    {d}" for d in by_key[key]]
    return "\n".join(lines)


# ------------------------------------------------------------------ drawn key map
OPENS_FROM = "opens from "
_DOOR_REQ = {}
_PAIR_ENDS = None
SHUFFLE: dict = {}  # door randomiser layout (door_locks.apply_to_tracker); {} = doors as normal


def _shuffle_lines(pair, discovered) -> list:
    """Door randomiser: for each shuffled side of the door between this room pair, where it leads -
    only once Jill has been through it (no spoilers)."""
    targets = SHUFFLE.get("targets") or {}
    if not targets:
        return []
    from . import door_shuffle as ds
    global _PAIR_ENDS
    if _PAIR_ENDS is None:          # door sides by the room pair of their door (once)
        _PAIR_ENDS = {}
        for e in ds.ends():
            _PAIR_ENDS.setdefault(frozenset((ds.logic_room(e), ds.logic_room(ds.other_side(e)))), []).append(e)
    lines = []
    for e in _PAIR_ENDS.get(pair, []):
        here = ds.logic_room(e)
        if ds.key(e) not in targets:
            continue
        if ds.key(e) in (discovered or {}):
            lines.append(f"From {here}: leads to {ds.logic_room(ds.target(SHUFFLE, e))}")
        else:
            lines.append(f"From {here}: leads somewhere new (not used yet)")
    return lines
for _a, _b, _req, _one in DOORS:
    _DOOR_REQ.setdefault(frozenset((_a, _b)), tuple(_req))


def _needs(req):
    """The items a door needs (labels like "opens from <room>" aren't items)."""
    return [r for r in req if not r.startswith(OPENS_FROM)]


DONE, CAN_GET, LATER, EMPTY = "done", "can_get", "later", "empty"


def room_status(received: Iterable[str], active: Set[str], checked: Set[str], box_gate: bool) -> Dict[str, str]:
    """Per room: DONE (every check in it collected), CAN_GET (checks left that are in logic now),
    LATER (checks left, not in logic yet). Rooms with no checks this seed aren't listed (EMPTY)."""
    now = set(in_logic(received, active, checked, box_gate))
    out: Dict[str, str] = {}
    for name in active:
        room = _ROOM_OF.get(name)
        if room is None:
            continue
        if name in checked:
            out.setdefault(room, DONE)
        elif name in now:
            out[room] = CAN_GET
        elif out.get(room) != CAN_GET:
            out[room] = LATER
    return out


def floor_of(room: str) -> int:
    """Index of the first floor drawing that has this room (-1 if none)."""
    from .map_layout import FLOORS
    from .map_geometry import logic_room
    group = same_game_room(room) | {room}
    for i, (_t, _w, _h, rooms, _d) in enumerate(FLOORS):
        if any(r in group or logic_room(r) in group for r in rooms):
            return i
    return -1


# ------------------------------------------------------------------ drawn key map, v0.9.1
def key_name(item: str) -> str:
    return KEY_NAMES.get(item, item)


_UNLOCK = None     # frozenset(room pair) -> unlock flags; door_locks.apply_to_tracker sets this seed's


def unlock_flags() -> Dict[frozenset, Set[int]]:
    global _UNLOCK
    if _UNLOCK is None:
        from .door_locks import unlock_flag_map
        _UNLOCK = unlock_flag_map()
    return _UNLOCK


def same_game_room(room: str) -> Set[str]:
    """Our room names that are the same room in the game (one room number): the client only
    knows the number, e.g. Tea Room and Northern Corridor are both 0x103."""
    from .game_data import ROOM_NUMBERS
    nb = ROOM_NUMBERS.get(room)
    if nb is None:
        return {room} if room else set()
    return {name for name, n in ROOM_NUMBERS.items() if n == nb}


def map_state(received: Iterable[str], active: Set[str], checked: Set[str], box_gate: bool,
              unlocked: Iterable[int] = (), discovered=None):
    """Everything the drawn Key Map shows (map_render.py draws it).
    counts: logic room -> [can grab now, left but not in logic yet, collected].
    doors: per floor, a list of dicts: x, y, hz, a, b (drawn room names), kind ("key" / "item" /
      "one_sided" / "open"), key (item name for kind "key"), needs (items), ok (you have them all),
      opens_from (rooms a one-sided door opens from).
    elsewhere: locked doors that aren't on any floor drawing (stairs, lifts, ladders), as
      (room A, room B, door dict).
    unlocked: unlock flags set in the game (bit n of flags + 0x31C). A locked door whose flags are
      all set is shown as kind "unlocked" (drawn like an ordinary door)."""
    from .map_layout import FLOORS
    from .map_geometry import logic_room
    received = list(received)
    have, _rooms, _box = closure(received, active, box_gate, checked)
    now = set(in_logic(received, active, checked, box_gate))
    counts: Dict[str, List[int]] = {}
    for name in active:
        room = _ROOM_OF.get(name)
        if room is None:
            continue
        c = counts.setdefault(room, [0, 0, 0])
        c[2 if name in checked else 0 if name in now else 1] += 1

    unlocked = set(unlocked)
    flag_map = unlock_flags()

    def info(req, pair=None, **kw):
        keys = [r for r in req if r in KEY_COLOURS]
        needs = _needs(req)
        opens = [r[len(OPENS_FROM):] for r in req if r.startswith(OPENS_FROM)]
        kind = "key" if keys else "item" if needs else "one_sided" if opens else "open"
        flags = flag_map.get(pair) if pair is not None else None
        if kind != "open" and flags and flags <= unlocked:
            kw["was"] = kind
            kind = "unlocked"
        d = dict(kind=kind, key=keys[0] if keys else None, needs=needs, opens_from=opens,
                 ok=all(have[r] > 0 for r in needs), missing=[r for r in needs if have[r] <= 0])
        if pair is not None:
            leads = _shuffle_lines(pair, discovered)
            if leads:
                d["leads"] = leads
        d.update(kw)
        return d

    placed, doors = set(), []
    for _title, _w, _h, _rooms_f, fdoors in FLOORS:
        out = []
        for x, y, hz, a, b in fdoors:
            pair = frozenset((logic_room(a) or a, logic_room(b) or b))
            placed.add(pair)
            out.append(info(_DOOR_REQ.get(pair, ()), pair, x=x, y=y, hz=hz, a=a, b=b))
        doors.append(out)
    elsewhere = [(a, b, info(tuple(req), frozenset((a, b)), a=a, b=b)) for a, b, req, _one in DOORS
                 if req and frozenset((a, b)) not in placed]
    return counts, doors, elsewhere
