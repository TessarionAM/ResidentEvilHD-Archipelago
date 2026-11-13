"""
Door randomiser (entrance shuffle), 2026-11-12. Design: claude/door-randomiser-design.md.

TessarionAM's decisions: whole game (any door can lead to any area), doors + ladders + lifts, two modes:
  coupled   - door A leads to room X, and the door you arrive by in X leads back through A;
  decoupled - door A always leads to X this seed, but X's door goes somewhere else.

Model. A physical door joins game rooms a and b (door_table.DOOR_TABLE). Each side of it is an
END: (door id, room number). Going out through an end puts Jill in another room at the arrival
spot of the end it is matched with:
    coupled:   ends are paired; out through E -> arrive at F's spot; out through F -> at E's spot;
    decoupled: a permutation; out through E -> arrive at target(E)'s spot.
  Vanilla is every end paired with the other side of its own door.
Locks stay with the physical door side (the lock is in the door record of that room), so a
Sword Key door is still a Sword Key door - it just leads somewhere new. Works with the door lock
randomiser (requirements come from door_locks.effective_doors).

Not shuffled (kept vanilla):
  - doors the game's scripts open or use (kinds event / special / inactive / electronic);
  - doors inside one game room (Tea Room <-> Northern Corridor 103, Winding Corridor <-> Bathroom 109);
  - doors that aren't in the world's room graph (no logic link, e.g. the kitchen elevator, which the
    logic treats as one powered link);
  - the escape route after the self-destruct starts (Main Laboratory -> its entrance -> the lift ->
    Lab B1 -> Passage to Heliport -> Heliport Elevator -> Heliport), or the timer couldn't be beaten.

Pure Python (no Archipelago imports) so the client can use it too.

LAYOUT (slot_data["door_shuffle"]): {"mode": "coupled"|"decoupled",
    "targets": {"<door id>@<room hex>": ["<door id>", "<room hex>"]}}  - for every shuffled end,
    the end whose arrival spot Jill arrives at (in that end's room).
"""
from collections import Counter
from typing import Dict, List, Optional, Set, Tuple

from .data import START
from .door_table import DOOR_TABLE
from .game_data import ROOM_NUMBERS

OFF, COUPLED, DECOUPLED = 0, 1, 2
MODE_NAMES = {OFF: "off", COUPLED: "coupled", DECOUPLED: "decoupled"}
SHUFFLE_KINDS = {"open", "key", "one_sided", "lockpick"}
SHUFFLE_TYPES = {0, 1, 2, 3, 4}            # door / double door / ladder (3) / lift (4)
# the escape route (see above): Main Laboratory - entrance - lift - Lab B1 - passage - lift - Heliport
ESCAPE = {"513-514", "514-515", "500-501", "501-50d", "303-50d"}
# The Lisa passage (2026-11-13): Barry takes the cave lift up as soon as Jill enters it and the lift
# breaks, so the way in (Garbage Compactor Room door) and the way out (Lisa's door, opened with the
# Broken Flamethrower) stay where they are - the logic's flamethrower rule depends on them.
# The ceiling trap (TessarionAM, 2026-11-13): taking the Living Room's Shotgun pickup starts the Marble
# Room's ceiling. The game locks that room's exit and only lets Jill back into the Living Room (to put
# the gun back) - so a shuffled exit led into the Living Room, whose door then stayed locked, and Barry
# never came (log 16:47:39-16:47:52). Both Marble Room doors stay where they are.
STORY = {"316-317", "317-319", "109-115", "115-116"}
ATTEMPTS = 400
BUILD_GIVE_UP = 25     # failed builds (none succeeding) before these locks are given up on
CHECK_GIVE_UP = 60     # built layouts failing the logic check before these locks are given up on
PLAIN_LOW = 4          # coupled: plain open doors at or below this = only the best joins

End = Tuple[str, int]                      # (door id, room number)


class ShuffleError(Exception):
    """No completable door layout found (message says why)."""


# ------------------------------------------------------------------ ends
def shufflable(did: str) -> bool:
    d = DOOR_TABLE[did]
    if did in ESCAPE or did in STORY or d["kind"] not in SHUFFLE_KINDS or not d["world"]:
        return False
    if d.get("door_type", 0) not in SHUFFLE_TYPES:
        return False
    if d["kind"] == "open" and any(w[3] for w in d["world"]):
        # a one-way drop (the Secret Passage hole into B1, 2026-11-13): its lower end is only an
        # arrival spot, not a door locked from one side that opens later - keep it where it is
        return False
    a, b = d["world"][0][:2]
    return ROOM_NUMBERS.get(a) != ROOM_NUMBERS.get(b)


def ends() -> List[End]:
    out = []
    for did in sorted(DOOR_TABLE):
        if shufflable(did):
            lo, hi = DOOR_TABLE[did]["rooms"]
            out += [(did, lo), (did, hi)]
    return out


def logic_room(end: End) -> str:
    """Our (logic) room on that side of the door."""
    did, room = end
    a, b = DOOR_TABLE[did]["world"][0][:2]
    return a if ROOM_NUMBERS[a] == room else b


def other_side(end: End) -> End:
    did, room = end
    lo, hi = DOOR_TABLE[did]["rooms"]
    return did, hi if room == lo else lo


def key(end: End) -> str:
    return f"{end[0]}@{end[1]:x}"


def unkey(text: str) -> End:
    did, room = text.split("@")
    return did, int(room, 16)


# ------------------------------------------------------------------ layouts
def make_layout(mode: int, rng, validate=None, base_doors: Optional[List[tuple]] = None) -> Dict[str, object]:
    """A layout that passes validate(layout) (None = completable, else a reason). Re-rolls."""
    if mode == OFF:
        return {}
    reason = "no attempt made"
    built = 0
    for attempt in range(ATTEMPTS):
        try:
            layout = build_layout(mode, rng, base_doors)
        except ShuffleError as exc:          # this random build ran into a dead end: roll again
            reason = str(exc)
            if built == 0 and attempt + 1 >= BUILD_GIVE_UP:
                # 2026-11-13: some lock layouts can never be built (about a third with regional
                # locks); a buildable one succeeds within its first couple of tries. Stop early so
                # the caller re-rolls the locks instead of spending ~25 s on 400 hopeless builds.
                raise ShuffleError(f"no door layout can be built with these locks ({reason})")
            continue
        built += 1
        reason = validate(layout) if validate else None
        if reason is None:
            return layout
        if built >= CHECK_GIVE_UP:
            # 2026-11-13: some lock layouts build fine but never pass the logic check (seen: 380+
            # failures, ~50 s). Over 160 lock layouts that did pass, the slowest passed on its 21st
            # layout and most on their 1st-5th, so 60 failures means these locks won't work.
            raise ShuffleError(f"no completable door layout with these locks ({reason})")
    raise ShuffleError(f"no completable door layout found in {ATTEMPTS} tries ({MODE_NAMES[mode]}). "
                       f"Last problem: {reason}")


def pinned(need: Dict[End, Optional[tuple]]) -> Set[str]:
    """Doors kept where they are: a door whose need (in either direction) no other door shares
    can only be matched with itself (e.g. the one door a crank opens)."""
    count = Counter(need.values())
    out = set()
    for e, n in need.items():
        if n is not None and count[n] <= 2 and all(x[0] == e[0] for x, m in need.items() if m == n):
            out.add(e[0])
    return out


def _groups(base_doors: Optional[List[tuple]], keep: Set[str] = frozenset()):
    """Logic rooms joined by links the shuffle doesn't touch (internal doors, event doors, the
    escape route, non-door links like the Crypt's) form one group: reaching one reaches the rest.
    Returns (group of each logic room, ends of each group, the start's group)."""
    from .data import DOORS, ROOMS
    moved = {DOOR_TABLE[did]["world"][0][:2] for did, _r in ends() if did not in keep}
    parent = {r: r for r in ROOMS}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a, b, _req, one_way in (base_doors or DOORS):
        # only two-way links join rooms into one group (a one-way link doesn't let you back)
        if not one_way and (a, b) not in moved and (b, a) not in moved and a in parent and b in parent:
            parent[find(a)] = find(b)
    group = {r: find(r) for r in ROOMS}
    of: Dict[str, List[End]] = {}
    for e in ends():
        if e[0] not in keep:
            of.setdefault(group[logic_room(e)], []).append(e)
    return group, of, group[START]


def needs(base_doors: Optional[List[tuple]]) -> Dict[End, Optional[tuple]]:
    """What going out through each end needs (sorted tuple; () = nothing), or None if that side
    is locked from this side (can't be used)."""
    need: Dict[Tuple[str, str], tuple] = {}
    for a, b, req, one_way in (base_doors or []):
        need.setdefault((a, b), tuple(sorted(req)))
        if not one_way:
            need.setdefault((b, a), tuple(sorted(req)))
    return {e: (need.get((logic_room(e), logic_room(other_side(e)))) if base_doors else ()) for e in ends()}


def _covers(have: Optional[tuple], want: Optional[tuple]) -> bool:
    """Going out through a door that needs `have` means Jill has those - enough for `want`?"""
    return have is not None and want is not None and set(want) <= set(have)


def sealed_rooms(base_doors: Optional[List[tuple]], need, keep: Set[str]) -> Set[str]:
    """Doors of dead-end rooms whose every door is locked from the inside (a side locked from
    this side, e.g. Small Storeroom with full door locks). Shuffled, Jill could arrive there before
    the door was ever opened from outside and be trapped for good, so these doors stay where they
    are: then the only way in is through the door from its open side, which unlocks it, and she
    can always walk back out (connections() adds that way back).
    Only when nothing else leads into those rooms (no other link, no drop)."""
    from .data import DOORS
    out: Set[str] = set()
    while True:                             # chains: Room 001 is only left through its bathroom
        more = _sealed_once(base_doors, need, keep | out, DOORS)
        if not more:
            return out
        out |= more


def _sealed_once(base_doors, need, keep, DOORS) -> Set[str]:
    group, of, _start = _groups(base_doors, keep)
    out: Set[str] = set()
    for g, es in of.items():
        if any(need[e] is not None for e in es):
            continue
        if any(need[other_side(e)] is None for e in es):
            continue                        # locked from both sides: not this case
        rooms = {r for r, x in group.items() if x == g}
        dids = {e[0] for e in es}
        links = {tuple(DOOR_TABLE[d]["world"][0][:2]) for d in dids}
        links |= {(b, a) for a, b in links}
        into = [(a, b) for a, b, _r, one_way in (base_doors or DOORS)
                if (b in rooms and a not in rooms) or (not one_way and a in rooms and b not in rooms)]
        if all(l in links for l in into):
            out |= dids
    return out


def build_layout(mode: int, rng, base_doors: Optional[List[tuple]] = None) -> Dict[str, object]:
    """A layout with every room connected and no softlock built in (keys are then checked by the
    fill): see _coupled / _decoupled."""
    need = needs(base_doors)
    keep = pinned(need)
    sealed = sealed_rooms(base_doors, need, keep)
    group, of, start = _groups(base_doors, keep | sealed)
    if mode == COUPLED:
        targets = _coupled(of, start, need, rng)
    else:
        targets = _decoupled(of, start, need, rng)
    out = {"mode": MODE_NAMES[mode], "targets": targets}
    if sealed:
        out["sealed"] = sorted(sealed)
    return out


def _pair(targets, e, f):
    targets[key(e)], targets[key(f)] = [f[0], f"{f[1]:x}"], [e[0], f"{e[1]:x}"]


def _coupled(of, start, need, rng) -> Dict[str, List]:
    """Doors are paired only with doors that need the same to go through (a plain door with a plain
    door, a Sword Key side with a Sword Key side, a side locked from itself with another such side)
    - so Jill can always go back the way she came and coupled mode can't trap her.
    Grown from the start: an open door of the explored part is joined to a door of a group not yet
    joined (plain doors first), then the leftover doors pair at random within their kind."""
    targets: Dict[str, List] = {}
    open_ends = list(of.get(start, []))
    todo = [g for g in of if g != start]
    rng.shuffle(todo)
    plain = lambda es: sum(need[x] == () for x in es)
    while todo:
        kinds = {need[e] for e in open_ends if need[e] is not None}
        # every possible join: an open door of the explored part + a matching door of a new group
        moves = [(g, e, f) for g in todo for f in of[g] if need[f] in kinds
                 for e in open_ends if need[e] == need[f] and e[1] != f[1]]
        if not moves:
            raise ShuffleError("a room can't be joined: none of its doors matches an open door "
                               f"({', '.join(sorted(todo)[:3])}; open: {sorted(map(str, kinds))[:4]})")
        keyed = [m for m in moves if plain(of[m[0]]) == 0]
        gain = lambda m: plain(of[m[0]]) - (need[m[2]] == ()) - (need[m[1]] == ())
        if keyed:                    # rooms with only key doors: join while a matching door is open
            g, e, f = rng.choice(keyed)
        else:
            # 2026-11-13: plain doors are the budget that runs out. Joins that use up more plain
            # doors than they bring (dead ends) wait until nothing else is left, and when plain
            # doors run low only the joins that keep the most open are used.
            pool = [m for m in moves if gain(m) >= 0] or moves
            if plain(open_ends) <= PLAIN_LOW:
                best = max(gain(m) for m in pool)
                pool = [m for m in pool if gain(m) == best]
            g = rng.choice(sorted({m[0] for m in pool}))
            g_moves = [m for m in pool if m[0] == g]
            top = max(gain(m) for m in g_moves)      # join it by a key door when one matches
            g, e, f = rng.choice([m for m in g_moves if gain(m) == top])
        todo.remove(g)
        open_ends.remove(e)
        _pair(targets, e, f)
        open_ends += [x for x in of[g] if x != f]
    by_kind: Dict[Optional[tuple], List[End]] = {}
    for e in open_ends:
        by_kind.setdefault(need[e], []).append(e)
    for kind, es in by_kind.items():
        rng.shuffle(es)
        left = []
        while es:
            e = es.pop()
            j = next((i for i in range(len(es) - 1, -1, -1) if es[i][1] != e[1]), None)
            if j is None:
                left.append(e)               # only doors of its own room left
            else:
                _pair(targets, e, es.pop(j))
        for e in left:                       # odd ones out: lead where they always did
            o = other_side(e)
            targets[key(e)] = [o[0], f"{o[1]:x}"]
    return targets


def _decoupled(of, start, need, rng) -> Dict[str, List]:
    """Every end is arrived at exactly once. No softlock: a door only drops Jill into a group she
    can leave with what that door needed (a plain door never into a room whose only ways out need
    a key). Groups with a plain way out are chained in one loop of plain doors, so they all lead to
    each other with no items; groups that need a key to leave are only entered through doors that
    needed that key."""
    group_of = {e: g for g, es in of.items() for e in es}
    exits = {g: [need[e] for e in es if need[e] is not None] for g, es in of.items()}
    free_groups = [g for g in of if () in exits[g]]
    if start not in free_groups:
        raise ShuffleError("the start has no plain way out")
    rest = [g for g in free_groups if g != start]
    rng.shuffle(rest)
    loop = [start] + rest
    targets: Dict[str, List] = {}
    used_src, used_arr = set(), set()
    for i, g in enumerate(loop):
        nxt = loop[(i + 1) % len(loop)]
        src = rng.choice([e for e in of[g] if need[e] == ()])
        spots = [e for e in of[nxt] if e not in used_arr and e[1] != src[1]]
        if not spots:                        # e.g. Tea Room -> Northern Corridor: same game room
            raise ShuffleError("two neighbours in the loop share a game room")
        arr = rng.choice(spots)
        targets[key(src)] = [arr[0], f"{arr[1]:x}"]
        used_src.add(src)
        used_arr.add(arr)

    def can_enter(src: End, g) -> bool:
        return src[1] not in {e[1] for e in of[g]} and any(_covers(need[src], x) for x in exits[g])

    # rooms that need a key to leave: each is first led into from a door of a room Jill can
    # already reach (so nothing is only reachable from rooms that are themselves unreachable)
    reached = set(loop)
    pending = [g for g in of if g not in reached]
    rng.shuffle(pending)
    while pending:
        options, late = [], []
        for g in pending:
            spots = [a for a in of[g] if a not in used_arr]
            free = [e for r in reached for e in of[r] if e not in used_src and need[e] is not None]
            srcs = [e for e in free if can_enter(e, g)]
            if spots and srcs:
                options.append((g, srcs, spots))
            elif spots:
                # no door of the explored part needs the key this room's ways out need: any door
                # will do here, and the per-sphere softlock check decides whether Jill always has
                # that key by the time she can reach the door
                late.append((g, [e for e in free if e[1] not in {a[1] for a in spots}], spots))
        options = options or [o for o in late if o[1]]
        if not options:
            raise ShuffleError("a room needing a key to leave can't be reached from the explored part")
        g, srcs, spots = rng.choice(options)
        most = max(len(need[e]) for e in srcs)        # save plain doors for later
        src = rng.choice([e for e in srcs if len(need[e]) == most])
        arr = rng.choice(spots)
        targets[key(src)] = [arr[0], f"{arr[1]:x}"]
        used_src.add(src)
        used_arr.add(arr)
        reached.add(g)
        pending.remove(g)
    mine = [e for es in of.values() for e in es]
    sources = [e for e in mine if e not in used_src]
    arrivals = [e for e in mine if e not in used_arr]
    rng.shuffle(sources)
    rng.shuffle(arrivals)
    # hardest arrivals first: spots in groups that need a key to leave
    arrivals.sort(key=lambda a: () in exits[group_of[a]])
    blocked = [e for e in sources if need[e] is None]      # can't be gone through: any spot will do
    passable = [e for e in sources if need[e] is not None]
    for arr in arrivals:
        g = group_of[arr]
        cand = [e for e in passable if can_enter(e, g)]
        if not cand:
            cand = [e for e in blocked if e[1] != arr[1]]
            if not cand:
                raise ShuffleError("no door can lead into one of the rooms without trapping Jill")
            src = rng.choice(cand)
            blocked.remove(src)
        else:
            # keep plain doors for the plain groups: prefer the door needing the most
            most = max(len(need[e]) for e in cand)
            src = rng.choice([e for e in cand if len(need[e]) == most] if () not in exits[g] else cand)
            passable.remove(src)
        targets[key(src)] = [arr[0], f"{arr[1]:x}"]
    return targets


def target(layout, end: End) -> End:
    t = layout["targets"].get(key(end)) if layout else None
    return (t[0], int(t[1], 16)) if t else other_side(end)


# ------------------------------------------------------------------ logic
def connections(layout, base_doors: List[tuple]) -> List[tuple]:
    """The world's connections with this layout: (room A, room B, requirements, one_way).
    base_doors = door_locks.effective_doors(lock layout) (the vanilla doors with this seed's locks).
    Every shuffled end becomes a one-way link from its room to where it now leads, with the
    requirement of going out through that side of the door (a side locked from this side - 22,
    one-sided - has none, so it can't be used)."""
    if not layout:
        return list(base_doors)
    need: Dict[Tuple[str, str], tuple] = {}
    for a, b, req, one_way in base_doors:
        need.setdefault((a, b), tuple(req))
        if not one_way:
            need.setdefault((b, a), tuple(req))
    shuffled = [e for e in ends() if key(e) in layout["targets"]]
    moved = {DOOR_TABLE[did]["world"][0][:2] for did, _r in shuffled}
    moved |= {(b, a) for a, b in moved}
    out = [d for d in base_doors if (d[0], d[1]) not in moved]
    for e in shuffled:
        here, there = logic_room(e), logic_room(other_side(e))
        req = need.get((here, there))
        if req is None:
            continue                                   # locked from this side
        out.append((here, logic_room(target(layout, e)), req, True))
    return _ways_back(out)


def _ways_back(doors: List[tuple]) -> List[tuple]:
    """A door locked from the inside of a dead end (Small Storeroom, the Visual Data Room with
    some lock layouts) is unlocked by going in through it - and that's the only way in - so Jill
    can always walk back out. Only for doors that really are the one way into those rooms
    (repeated for chains, e.g. Room 001 and its bathroom)."""
    out = list(doors)
    links = {(a, b) for a, b, _r, _o in out}
    door_links = {tuple(w[:2]) for d in DOOR_TABLE.values() for w in d["world"]}
    door_links |= {(b, a) for a, b in door_links}
    changed = True
    while changed:
        changed = False
        for a, b, _req, one_way in list(out):
            if not one_way or (b, a) in links or (a, b) not in door_links:
                continue
            area, grow = {b}, True                 # b and the rooms it walks to and back from
            while grow:
                grow = False
                for x, y, _r, o in out:
                    for p, q in ((x, y), (y, x)) if not o else ():
                        if p in area and q not in area:
                            area.add(q)
                            grow = True
            into = {(x, y) for x, y, _r, o in out if y in area and x not in area}
            into |= {(y, x) for x, y, _r, o in out if not o and x in area and y not in area}
            if into == {(a, b)}:
                out.append((b, a, (), True))
                links.add((b, a))
                changed = True
    return out


def stuck_rooms(doors, have: Counter, box_gate: bool) -> List[str]:
    """Rooms Jill can reach with `have` but can't get back to the start from (a softlock), using
    the same rules as door_locks.reachable."""
    from .door_locks import _ok, reachable
    rooms, have2, box = reachable(doors, have, box_gate)
    back, changed = {START}, True
    while changed:                     # rooms from which START can be reached (reverse search)
        changed = False
        for a, b, req, one_way in doors:
            if b in back and a not in back and a in rooms and _ok(req, have2, box, box_gate):
                back.add(a)
                changed = True
            elif not one_way and a in back and b not in back and b in rooms and _ok(req, have2, box, box_gate):
                back.add(b)
                changed = True
    return sorted(rooms - back)


def check(layout, base_doors, progression, locations, goal_complete: bool, box_gate: bool, rng,
          start=(), everything: bool = True) -> Optional[str]:
    """None if the shuffled world is completable and has no softlock, else a reason.
    Completable: door_locks.check_layout (assumed fill) on the shuffled connections.
    No softlock: with the starting items, and again after each sphere of a fill (every location
    Jill can reach collected), every room she can reach leads back to the start."""
    from .door_locks import _ok, check_layout, reachable
    doors = connections(layout, base_doors)
    reason = check_layout({}, progression, locations, goal_complete, box_gate, rng, start,
                          everything=everything, doors=doors)
    if reason:
        return reason
    # spheres: collect everything reachable (progression items handed out in a fixed order
    # among reachable locations - the softlock rule must hold whatever the fill does, so the
    # state grows as slowly as a real seed's can: one sphere at a time)
    have = Counter(start)
    left = list(progression)
    free = list(locations)
    for _ in range(len(progression) + 2):
        stuck = stuck_rooms(doors, have, box_gate)
        if stuck:
            return f"softlock: {', '.join(stuck[:3])} has no way back with the items Jill can have then"
        rooms, have2, box = reachable(doors, have, box_gate)
        got = [loc for loc in free if loc[1] in rooms and _ok(loc[2], have2, box, box_gate)]
        if not got or not left:
            break
        n = min(len(got), len(left))
        rng.shuffle(left)
        for loc in got[:n]:
            free.remove(loc)
        have = have + Counter(left[:n])
        left = left[n:]
    return None
