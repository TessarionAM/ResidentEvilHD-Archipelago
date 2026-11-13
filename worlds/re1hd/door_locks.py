"""
Door lock randomiser (2026-11-12). Design: claude/door-lock-randomiser-design.md, decisions:
claude/door-lock-randomiser-decisions.md and -decisions-2.md.

Everything here works from door_table.py (THE door table, generated from the game) - the world,
the tracker / Key Map and the client all use the same functions, so there is one source of truth.

A seed's LAYOUT (stored in slot_data["door_locks"]):
    {door id: {"kind": "key" | "lockpick" | "one_sided" | "open",
               "sides": {"lo->hi": [key type, flag], "hi->lo": [key type, flag]}}}
  key type = the door record's +0x43 & 0x7F (KEY_ITEMS), 22 = locked from this side, 21 = opens
  it from this side, 0 = not locked. Both sides of a locked door share one unlock flag, so one
  key opens it from either side and it stays open (verified in-game, TessarionAM 11:14 / 11:28).
Key uses: every key's quantity = the number of doors it opens in the seed (verified: a key
loses one use per door and is discarded at 0).

Pure Python (no Archipelago imports), so the client can use it too.
"""
from collections import Counter
from typing import Dict, Iterable, List, Optional, Set, Tuple

from .data import BOX_ROOMS, DIRECT_ITEMS, DOORS, EVENT_NAMES, EVENTS, FINAL_REQUIRES, FINAL_ROOM, \
    GOAL_ROOM, MISSABLE, MISSABLE_POOL_ITEMS, PICKUPS, START
from .door_table import DOOR_TABLE, KEY_ITEMS, ONE_SIDED_LOCKED, ONE_SIDED_OPENER
from .game_data import ROOM_NUMBERS

DISABLED, MANSION_ONLY, REGIONAL, FULL = 0, 1, 2, 3
MODE_NAMES = {DISABLED: "disabled", MANSION_ONLY: "mansion_only", REGIONAL: "regional", FULL: "full"}
LOCKPICK = 1
AREA_KEYS = {"Mansion": [3, 4, 5, 6], "Residence": [7, 8, 20, 13], "Laboratory": [9]}
ALL_KEYS = [k for ks in AREA_KEYS.values() for k in ks]
KEY_NAMES = {t: KEY_ITEMS[t] for t in ALL_KEYS + [LOCKPICK]}
# share of locked doors that become one-sided / lock-pick doors (the vanilla mix: 5 and 4 of 30)
ONE_SIDED_SHARE, LOCKPICK_SHARE = 5 / 30, 4 / 30
BALANCE_RANGE = 3          # Mansion-only / Regional: max uses - min uses <= 3 (TessarionAM, 11:28)
WRONG_DOOR_FLAG = 255      # the Wrong Door trap's own unlock flag
ATTEMPTS = 60

# Most locked doors per mode = every door the mode can lock (2026-11-12 batch: even with all of
# them locked, a third of random layouts pass the fill check, and make_layout re-rolls up to
# ATTEMPTS times, so a completable layout is always found). See the Batch test in test_door_locks.
SAFE_MAX = {MANSION_ONLY: 42, REGIONAL: 65, FULL: 65}


class LayoutError(Exception):
    """The requested door locks can't be made into a completable seed (message says why)."""


# ------------------------------------------------------------------ door sets
def _area(d) -> str:
    return d["area"]


def mode_areas(mode: int) -> List[str]:
    return ["Mansion"] if mode == MANSION_ONLY else ["Mansion", "Residence", "Laboratory"]


def candidate_doors(mode: int) -> List[str]:
    """Doors the shuffle may lock or unlock in this mode (vanilla locks + open doors that can take one)."""
    areas = mode_areas(mode)
    return sorted(did for did, d in DOOR_TABLE.items() if (d["shuffle"] or d["new_lock"]) and _area(d) in areas)


def vanilla_locked(mode: int) -> List[str]:
    areas = mode_areas(mode)
    return sorted(did for did, d in DOOR_TABLE.items() if d["shuffle"] and _area(d) in areas)


def limits(mode: int) -> Tuple[int, int]:
    """(vanilla number of locked doors, maximum this mode supports)."""
    return len(vanilla_locked(mode)), min(SAFE_MAX[mode], len(candidate_doors(mode)))


def resolve_count(mode: int, value: int) -> int:
    """The option value -> a number of doors. Negative values are the named presets."""
    vanilla, top = limits(mode)
    presets = {-1: vanilla, -2: round(vanilla * 0.75), -3: round(vanilla * 1.25), -4: round(vanilla * 1.5)}
    n = presets.get(value, value)
    if n > top:
        raise LayoutError(
            f"locked_door_count {n} is more than door_lock_randomisation '{MODE_NAMES[mode]}' supports: at most "
            f"{top} doors can carry a lock there and still give a completable seed (vanilla: {vanilla}).")
    return max(0, n)


def _sides(did: str) -> Tuple[str, str]:
    lo, hi = DOOR_TABLE[did]["rooms"]
    return f"{lo:x}->{hi:x}", f"{hi:x}->{lo:x}"


def _vanilla_flag(did: str) -> int:
    d = DOOR_TABLE[did]
    flags = [f for side in d["sides"].values() if side for k, f in side if k & 0x7F and f]
    return flags[0] if flags else 0


def _fixed_uses() -> Counter:
    """Uses of each key on doors the shuffle never touches (e.g. the Sliding Trap Room's Helmet door)."""
    uses = Counter()
    for did, d in DOOR_TABLE.items():
        if d["shuffle"]:
            continue
        seen = set()
        for side in d["sides"].values():
            for k, f in side or []:
                t = k & 0x7F
                if t in KEY_NAMES and t != LOCKPICK and (t, f) not in seen:
                    seen.add((t, f))
                    uses[t] += 1
    return uses


# ------------------------------------------------------------------ building a layout
def make_layout(mode: int, count: int, rng, validate=None) -> Dict[str, dict]:
    """A random layout with `count` locked doors. validate(layout) -> None if completable, else a
    reason. Re-rolls up to ATTEMPTS times; raises LayoutError with the last reason if none works."""
    if mode == DISABLED:
        return {}
    cands = candidate_doors(mode)
    reason = "no attempt made"
    for _ in range(ATTEMPTS):
        layout = _random_layout(mode, count, cands, rng)
        reason = validate(layout) if validate else None
        if reason is None:
            return layout
    raise LayoutError(f"no completable door lock layout found in {ATTEMPTS} tries "
                      f"({MODE_NAMES[mode]}, {count} locked doors). Last problem: {reason}")


def _random_layout(mode: int, count: int, cands: List[str], rng) -> Dict[str, dict]:
    locked = rng.sample(cands, min(count, len(cands)))
    n_one = round(count * ONE_SIDED_SHARE)
    lockpick_ok = [d for d in locked if mode == FULL or _area(DOOR_TABLE[d]) == "Mansion"]
    rng.shuffle(lockpick_ok)
    n_pick = min(round(count * LOCKPICK_SHARE), len(lockpick_ok))
    pick = set(lockpick_ok[:n_pick])
    rest = [d for d in locked if d not in pick]
    rng.shuffle(rest)
    one = set(rest[:n_one])
    keyed = [d for d in rest if d not in one]

    used_flags = {f for d in DOOR_TABLE.values() for side in d["sides"].values() if side for _k, f in side}
    free = [f for f in range(254, 0, -1) if f not in used_flags and f != WRONG_DOOR_FLAG]

    def flag_for(did):
        f = _vanilla_flag(did)
        return f if f else free.pop(0)

    key_of = _assign_keys(mode, keyed, rng)
    # (one-sided doors are turned round afterwards if they cut rooms off: _repair_one_sided)
    layout = {}
    for did in cands:
        a, b = _sides(did)
        if did in pick:
            f = flag_for(did)
            layout[did] = {"kind": "lockpick", "sides": {a: [LOCKPICK, f], b: [LOCKPICK, f]}}
        elif did in one:
            f = flag_for(did)
            lockside, opener = (a, b) if rng.random() < 0.5 else (b, a)
            layout[did] = {"kind": "one_sided", "sides": {lockside: [ONE_SIDED_LOCKED, f], opener: [ONE_SIDED_OPENER, f]}}
        elif did in key_of:
            f = flag_for(did)
            layout[did] = {"kind": "key", "sides": {a: [key_of[did], f], b: [key_of[did], f]}}
        else:
            layout[did] = {"kind": "open", "sides": {a: [0, 0], b: [0, 0]}}
    _repair_one_sided(layout, rng)
    return layout


def _everything() -> Counter:
    """Every item / event any door or pickup asks for, once (= "has all items")."""
    names = {r for _a, _b, req, _o in DOORS for r in req} | {r for *_x, req in PICKUPS for r in req}
    names |= set(KEY_ITEMS.values()) | {name for _room, name, _req in EVENTS}
    names |= set(FINAL_REQUIRES)
    return Counter({n: 1 for n in names})


def _repair_one_sided(layout: Dict[str, dict], rng) -> None:
    """A one-sided door whose locked side faces the rooms you can reach (and whose other side you
    can't reach any other way) is turned round, so it opens from the side you arrive at. Repeats
    until nothing changes; whatever is still cut off makes check_layout reject the layout."""
    from .data import ROOMS
    every = _everything()
    for _ in range(len(layout)):
        rooms, _h, _b = reachable(effective_doors(layout), every, box_gate=False)
        if set(ROOMS) <= rooms:
            return
        flipped = False
        doors = [d for d, e in layout.items() if e["kind"] == "one_sided"]
        rng.shuffle(doors)
        for did in doors:
            sides = layout[did]["sides"]
            for w in DOOR_TABLE[did]["world"]:
                a, b = w[0], w[1]
                for x, y in ((a, b), (b, a)):
                    nx, ny = _world_dir(x, y)
                    here, there = f"{nx:x}->{ny:x}", f"{ny:x}->{nx:x}"
                    if x in rooms and y not in rooms and sides.get(here, [0])[0] == ONE_SIDED_LOCKED:
                        sides[here][0], sides[there][0] = ONE_SIDED_OPENER, ONE_SIDED_LOCKED
                        flipped = True
            if flipped:
                break
        if not flipped:
            return


def _assign_keys(mode: int, doors: List[str], rng) -> Dict[str, int]:
    """Key type for every key door. Full: any key, any amount (TessarionAM, 11:34). Mansion-only /
    Regional: the area's own keys, uses kept within BALANCE_RANGE of each other (TessarionAM, 11:28)."""
    out = {}
    if mode == FULL:
        for d in doors:
            out[d] = rng.choice(ALL_KEYS)
        return out
    fixed = _fixed_uses()
    for area in mode_areas(mode):
        keys = AREA_KEYS[area]
        uses = {k: fixed[k] for k in keys}
        area_doors = [d for d in doors if _area(DOOR_TABLE[d]) == area]
        rng.shuffle(area_doors)
        for d in area_doors:
            low = min(uses.values())
            k = rng.choice([k for k in keys if uses[k] < low + BALANCE_RANGE])
            uses[k] += 1
            out[d] = k
    return out


# ------------------------------------------------------------------ what the layout means
def key_uses(layout: Dict[str, dict]) -> Dict[str, int]:
    """Item name -> number of doors it opens in this seed (shuffled doors + fixed doors).
    Only keys that the shuffle touches are listed (the rest keep their vanilla quantity)."""
    if not layout:
        return {}
    uses = _fixed_uses()
    shuffled = set()
    for did, entry in layout.items():
        for t, f in {tuple(v) for v in entry["sides"].values()}:
            if t in KEY_NAMES and t != LOCKPICK:
                uses[t] += 1
                shuffled.add(t)
    # every key the mode can hand out is listed (a key with no doors gets 1 harmless use)
    for did in layout:
        for t in AREA_KEYS.get(_area(DOOR_TABLE[did]), []):
            shuffled.add(t)
    return {KEY_NAMES[t]: max(1, uses[t]) for t in sorted(shuffled)}


def _world_dir(a: str, b: str) -> Tuple[int, int]:
    return ROOM_NUMBERS[a], ROOM_NUMBERS[b]


def effective_doors(layout: Dict[str, dict]) -> List[tuple]:
    """data.DOORS with every door of the layout replaced by its per-direction requirement:
    (room A, room B, requirements, one_way). Non-key requirements of the world link (cranks,
    puzzle items...) are kept. A side marked 22 can't be used; 21 and 0 sides are free."""
    if not layout:
        return list(DOORS)
    replaced, out = set(), []
    by_link = {}
    for did in layout:
        for w in DOOR_TABLE[did]["world"]:
            by_link[(w[0], w[1])] = did
    for a, b, req, one_way in DOORS:
        did = by_link.get((a, b))
        if did is None:
            out.append((a, b, req, one_way))
            continue
        others = tuple(r for r in req if r not in KEY_ITEMS.values())
        sides = layout[did]["sides"]
        for x, y in ((a, b), (b, a)):
            nx, ny = _world_dir(x, y)
            t, _f = sides.get(f"{nx:x}->{ny:x}", [0, 0])
            if t == ONE_SIDED_LOCKED:
                continue
            need = others + ((KEY_ITEMS[t],) if t in KEY_ITEMS else ())
            out.append((x, y, need, True))
    return out


def unlock_flag_map(layout: Optional[Dict[str, dict]] = None) -> Dict[frozenset, Set[int]]:
    """{frozenset((room A, room B)): unlock flags of its locked sides} - this seed's flags where the
    layout changed the door, the game's own otherwise. The Key Map shows a door as unlocked (an
    ordinary door) once all its flags are set (bit n of flags + 0x31C)."""
    out: Dict[frozenset, Set[int]] = {}
    for did, e in DOOR_TABLE.items():
        if layout and did in layout:
            flags = {int(f) for t, f in layout[did]["sides"].values() if int(t) & 0x7F and int(f)}
        else:
            flags = {f for side in e["sides"].values() if side for k, f in side if k & 0x7F and f}
        for a, b, *_rest in e["world"]:
            if flags:
                out.setdefault(frozenset((a, b)), set()).update(flags)
    return out


def apply_to_tracker(layout: Dict[str, dict], shuffle: Optional[dict] = None) -> None:
    """Make the client's tracker, /inlogic and Key Map use this seed's doors (same functions the
    generator uses: effective_doors, and door_shuffle.connections when doors are shuffled - the
    Key Map keeps drawing the physical doors with their locks). Called once the client has the
    slot data."""
    from . import door_shuffle, logic_tracker, tracker
    doors = effective_doors(layout)
    logic_tracker.DOORS = door_shuffle.connections(shuffle or {}, doors)
    tracker.DOORS = doors
    req: Dict[frozenset, tuple] = {}
    for a, b, need, _one in doors:
        key = frozenset((a, b))
        req[key] = tuple(dict.fromkeys(req.get(key, ()) + tuple(need)))
    # a one-sided door (only one direction left) is shown as "opens from <room>"
    for a, b, need, one in doors:
        key = frozenset((a, b))
        if one and not any(x == b and y == a for x, y, _n, _o in doors):
            req[key] = req[key] + (f"opens from {a}",) if f"opens from {a}" not in req[key] else req[key]
    tracker._DOOR_REQ.clear()
    tracker._DOOR_REQ.update(req)
    tracker._UNLOCK = unlock_flag_map(layout)
    tracker.SHUFFLE = dict(shuffle or {})


# ------------------------------------------------------------------ validation (assumed fill)
def _ok(req, have: Counter, box: bool, box_gate: bool) -> bool:
    if any(have[r] <= 0 for r in req):
        return False
    if box_gate and req and any(r not in DIRECT_ITEMS and r not in EVENT_NAMES for r in req):
        return box
    return True


def reachable(doors, have: Counter, box_gate: bool) -> Tuple[Set[str], Counter, bool]:
    """(rooms, items incl. events, item box reached) with `have`, like the world's regions."""
    have = Counter(have)
    box = False
    while True:
        rooms, changed = {START}, True
        while changed:
            changed = False
            for a, b, req, one_way in doors:
                if a in rooms and b not in rooms and _ok(req, have, box, box_gate):
                    rooms.add(b)
                    changed = True
                elif not one_way and b in rooms and a not in rooms and _ok(req, have, box, box_gate):
                    rooms.add(a)
                    changed = True
        new_box = box or any(r in rooms for r in BOX_ROOMS)
        grew = False
        for room, name, req in EVENTS:
            if have[name] <= 0 and room in rooms and _ok(req, have, new_box, box_gate):
                have[name] += 1
                grew = True
        if not grew and new_box == box:
            return rooms, have, box
        box = new_box


def check_layout(layout, progression: List[str], locations: List[Tuple[str, str, tuple]],
                 goal_complete: bool, box_gate: bool, rng, start: Iterable[str] = (),
                 everything: bool = True, doors: Optional[List[tuple]] = None) -> Optional[str]:
    """None if the layout is completable, else a reason. Simulates Archipelago's assumed fill:
    each progression item is placed in a random location reachable with all the items not yet
    placed; then the goal must be reachable. `locations`: (name, room, requirements) of every
    location that can hold an item. Deterministic for a given rng state."""
    if doors is None:                    # door_shuffle passes its own connections
        doors = effective_doors(layout)
    base = Counter(start)
    every = base + Counter(progression)
    rooms, have, box = reachable(doors, every, box_gate)
    goal_room, goal_req = (FINAL_ROOM, FINAL_REQUIRES) if goal_complete else (GOAL_ROOM, ())
    if goal_room not in rooms or not _ok(goal_req, have, box, box_gate):
        return f"the goal ({goal_room}) can't be reached even with every item"
    if everything:
        # accessibility "full": every room (so every location) reachable once you have everything
        from .data import ROOMS
        cut = sorted(set(ROOMS) - rooms)
        if cut:
            return f"{', '.join(cut[:3])} can't be reached even with every item (a door locked from the wrong side)"
    pool = list(progression)
    rng.shuffle(pool)
    free = list(locations)
    placed: List[Tuple[Tuple[str, str, tuple], str]] = []      # (location, item)
    swaps = 0
    def sweep(state: Counter):
        """Like Archipelago's sweep: items already placed in reachable locations count too."""
        got = set()
        while True:
            rooms, have, box = reachable(doors, state, box_gate)
            new = [j for j, (loc, it) in enumerate(placed) if j not in got
                   and loc[1] in rooms and _ok(loc[2], have, box, box_gate)]
            if not new:
                return rooms, have, box
            for j in new:
                got.add(j)
                state = state + Counter([placed[j][1]] if placed[j][1] else [])

    while pool:
        item = pool.pop()
        rooms, have, box = sweep(base + Counter(pool))
        ok = [i for i, (_n, room, req) in enumerate(free) if room in rooms and _ok(req, have, box, box_gate)]
        if ok:
            i = rng.choice(ok)
            placed.append((free.pop(i), item))
            continue
        # like Archipelago's fill: swap with an item placed earlier (it goes back to the pool)
        done = False
        for j in range(len(placed) - 1, -1, -1):
            loc, other = placed[j]
            saved, placed[j] = placed[j], (loc, None)
            rooms2, have2, box2 = sweep(base + Counter(pool) + Counter([other]))
            placed[j] = saved
            if loc[1] in rooms2 and _ok(loc[2], have2, box2, box_gate):
                placed[j] = (loc, item)
                pool.insert(0, other)
                swaps += 1
                done = True
                break
        if not done or swaps > 200:
            return f"no reachable location left for {item} (a key behind its own doors?)"
    return None


def simple_progression() -> Tuple[List[str], List[Tuple[str, str, tuple]]]:
    """The progression items and locations of a default seed, for check_layout (the world passes
    its real ones)."""
    from .items import item_table
    from BaseClasses import ItemClassification as IC
    # missable checks hold junk, but their real item stays in the pool
    items = [it for _room, name, it, _req in PICKUPS if item_table[it].kind & IC.progression]
    items += [n for n in MISSABLE_POOL_ITEMS if item_table[n].kind & IC.progression]
    locs = [(name, room, tuple(req)) for room, name, _it, req in PICKUPS if name not in MISSABLE]
    return items, locs
