"""
Builds worlds/re1hd/door_table.py - the ONE door table for the door lock randomiser (design:
claude/door-lock-randomiser-design.md). Run from the project folder:  python Tools/build_door_table.py

Inputs (all read from the Steam game, nothing guessed):
  client/doorinfo_pairs.json     the game's door animation table (every real door + its door type)
  client/door_locks_scanned.json the door scanner: each door record's KEY byte and unlock FLAG
  worlds/re1hd data (ROOM_NUMBERS, DOORS) to name the rooms the way the world does
"""
import json
import pprint
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent      # dev/ (research data in dev/client)
ROOT = HERE.parent                                   # repository root (worlds/re1hd)
sys.path.insert(0, str(ROOT / "worlds"))
sys.path.insert(0, str(ROOT / "worlds" / "re1hd"))

import importlib.util


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# data.py / game_data.py are plain data modules (game_data imports .data for FILE_CHECKS)
pkg = ROOT / "worlds" / "re1hd"
sys.modules.setdefault("re1hd_build", type(sys)("re1hd_build"))
data = _load("re1hd_build.data", pkg / "data.py")
sys.modules["re1hd_build.data"] = data
gd_src = (pkg / "game_data.py").read_text(encoding="utf-8").replace("from .data import", "from re1hd_build.data import")
game_data = type(sys)("re1hd_build.game_data")
exec(compile(gd_src, str(pkg / "game_data.py"), "exec"), game_data.__dict__)

SAVE_ROOMS = {0x100, 0x105, 0x118, 0x307, 0x314, 0x316, 0x31A, 0x403, 0x40A, 0x502, 0x50E}   # client/autosave.py
# Boss / scripted rooms (TessarionAM, 2026-11-12, decision 2): their doors keep their vanilla lock.
SCRIPTED_ROOMS = {0x210: "Attic (Yawn)", 0x216: "Library (Yawn)", 0x40C: "Plant 42 Room", 0x412: "Aqua Ring Water Tank",
                  0x30C: "Spider Room", 0x513: "Main Laboratory (Tyrant)", 0x303: "Heliport", 0x30A: "Enrico Room",
                  0x200: "Kitchen Elevator", 0x20C: "Sliding Trap Room", 0x203: "Outside Balcony (Forest)"}
# TessarionAM (2026-11-12 11:28): the Attic and Library key doors may be shuffled after all (their lock
# changes; no NEW lock is ever added to a scripted room's doors).
SHUFFLE_ANYWAY = {0x210, 0x216}
AREAS = {1: "Mansion", 2: "Mansion", 3: "Courtyard", 4: "Residence", 5: "Laboratory"}
REAL_DOOR_TYPES = {0, 1, 2}           # doorinfo: 0/1 single door, 2 double door; 3 ladder, 4 lift
KEY_TYPES = {1: "lockpick", 3: "key", 4: "key", 5: "key", 6: "key", 7: "key", 8: "key", 9: "key", 13: "key", 20: "key"}


def main():
    info = json.loads((HERE / "client" / "doorinfo_pairs.json").read_text(encoding="utf-8"))["doors"]
    scanned = json.loads((HERE / "client" / "door_locks_scanned.json").read_text(encoding="utf-8"))
    door_type = {}
    for d in info:
        door_type.setdefault((int(d["src"], 16), int(d["dest"], 16)), (d["door_type"], d["model"]))
    sides = {}
    for k, recs in scanned.items():
        s, d = (int(x, 16) for x in k.split("->"))
        if (s, d) not in door_type:
            continue                                   # not a real door (rooms.json extras)
        clean = sorted({(r["key"], r["flag"]) for r in recs if 0 <= r["flag"] < 256})
        sides[(s, d)] = clean
    # stale records: the same (key, flag) as a record of ANOTHER door of the same room (seen once:
    # Entry Corridor -> Rec Room carried the Room 001 door's 135 / 27) - drop them
    for (s, d), recs in sides.items():
        others = {r for (s2, d2), rr in sides.items() if s2 == s and d2 != d for r in rr if r[1]}
        sides[(s, d)] = [r for r in recs if not (r[1] and r in others)] or recs

    num_to_world = defaultdict(list)
    for name, nb in game_data.ROOM_NUMBERS.items():
        num_to_world[nb].append(name)
    world_links = defaultdict(list)
    for a, b, req, one_way in data.DOORS:
        na, nb = game_data.ROOM_NUMBERS.get(a), game_data.ROOM_NUMBERS.get(b)
        if na is not None and nb is not None:
            world_links[frozenset((na, nb)) if na != nb else frozenset((na,))].append(
                (a, b, list(req), one_way))

    table = {}
    for (s, d) in sorted(door_type):
        lo, hi = min(s, d), max(s, d)
        did = f"{lo:x}-{hi:x}"
        if did in table:
            continue
        ab, ba = sides.get((lo, hi)), sides.get((hi, lo))
        types = {k & 0x7F for side in (ab or [], ba or []) for k, _f in side if k & 0x7F}
        flags = {f for side in (ab or [], ba or []) for _k, f in side if f}
        dt = door_type.get((lo, hi), door_type.get((hi, lo)))[0]
        if ab is None and ba is None:
            kind = "inactive"
        elif types & {10, 19}:
            kind = "electronic"
        elif types & {11, 12}:
            kind = "special"
        elif types & set(KEY_TYPES):
            kind = "lockpick" if types & set(KEY_TYPES) == {1} else "key"
        elif types and types <= {21, 22}:
            kind = "one_sided"
        elif flags:
            kind = "event"
        else:
            kind = "open"
        area = AREAS.get(lo >> 8, "?")
        if AREAS.get(hi >> 8) != area:
            area = f"{area}/{AREAS.get(hi >> 8)}"
        world = world_links.get(frozenset((lo, hi)) if lo != hi else frozenset((lo,)), [])
        scripted = [SCRIPTED_ROOMS[r] for r in (lo, hi) if r in SCRIPTED_ROOMS]
        scripted_shuffle = [SCRIPTED_ROOMS[r] for r in (lo, hi) if r in SCRIPTED_ROOMS and r not in SHUFFLE_ANYWAY]
        why_not = []
        if "Courtyard" in area:
            why_not.append("Courtyard (no keys of its own: decision 1)")
        if "/" in area:
            why_not.append("crosses two areas")
        if scripted_shuffle:
            why_not.append("scripted room: " + ", ".join(scripted_shuffle))
        if not world:
            why_not.append("not in the world's room graph")
        if dt not in REAL_DOOR_TYPES:
            why_not.append("ladder / lift")
        if lo == hi:
            why_not.append("door inside one game room")
        shuffle = kind in ("key", "lockpick", "one_sided") and not why_not
        new_lock = (kind == "open" and not why_not and not scripted and bool(ab) and bool(ba)
                    and not ({lo, hi} & SAVE_ROOMS))
        table[did] = {
            "rooms": (lo, hi), "area": area, "door_type": dt, "kind": kind,
            "sides": {f"{lo:x}->{hi:x}": ab, f"{hi:x}->{lo:x}": ba},
            "world": world, "shuffle": shuffle, "new_lock": new_lock,
            "why_not": "; ".join(why_not) if kind != "open" or why_not else "",
        }

    out = ROOT / "worlds" / "re1hd" / "door_table.py"
    counts = defaultdict(int)
    for t in table.values():
        counts[(t["kind"], t["shuffle"] or t["new_lock"])] += 1
    with out.open("w", encoding="utf-8") as f:
        f.write('"""\nTHE door table (generated by Tools/build_door_table.py on 2026-11-12 - do not edit by hand).\n'
                "One entry per physical door, id = 'lowroom-highroom' (game room numbers, hex).\n"
                "  sides: 'from->to': [(KEY byte, unlock flag), ...] read from the game (None = no record:\n"
                "         the door isn't active until an event). KEY & 0x7F = key type (KEY_ITEMS).\n"
                "  kind:  open / key / lockpick / one_sided (22 = locked side, 21 = opening side, shared flag) /\n"
                "         electronic (Master Key + type 19) / special (Emblem, Closet) / event / inactive\n"
                "  shuffle:  the lock randomiser may change this door's lock\n"
                "  new_lock: an open door that may be given a lock (both sides, new unlock flag)\n"
                "  world:    the matching link(s) in data.DOORS (room A, room B, requirements, one_way)\n"
                '"""\n\n')
        f.write("# key type (door record +0x43 & 0x7F) -> the item the world uses for it (table at 0xC2FF20)\n")
        f.write("KEY_ITEMS = " + pprint.pformat({1: "Lock Pick", 3: "Book of Curses", 4: "Armor Key", 5: "Shield Key",
                                                6: "Helmet Key", 7: "001 Key", 8: "003 Key", 9: "Power Key",
                                                10: "Master Key", 13: "Control Room Key", 20: "Gallery Key"}) + "\n")
        f.write("ONE_SIDED_LOCKED, ONE_SIDED_OPENER, ELECTRONIC = 22, 21, 19\n\n")
        f.write("DOOR_TABLE = " + pprint.pformat(table, width=110, sort_dicts=True) + "\n")
    print(f"wrote {out} with {len(table)} doors")
    for k, v in sorted(counts.items()):
        print(f"  {k[0]:11s} {'eligible' if k[1] else 'fixed   '}: {v}")


if __name__ == "__main__":
    main()
