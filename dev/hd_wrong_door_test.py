"""
Steam version - WRONG DOOR TEST v7 (research for the Wrong Door fun trap). WRITES to the game.

History:
  v1 (07:53) rewrote door records found by position: no effect (wrong copies).
  v2 (07:57) changed the "next room" value (flags -0x404) while a door opened: crash
     ("Failed open file ...r10a.epv"). Never touch -0x404 again.
  v3 (08:04) found the live door lists and sent every door to the Dark Corridor: crash.
  v4 (08:10) sent every door to a room NEXT to yours (Art Room): worked both ways.
  v5 (08:35) also patched the door animation table, but Jill still went to the Dining Room:
     the memory search found 18 door records, yet only 2 of them were in the game's live list -
     the rest were leftovers from earlier visits to the Main Hall (you'd walked in and out).
  v6 reads the live door list directly instead of guessing: the game object (class "Game",
     vtable 0xC21854) holds it at +0x1B0 (+0xE0 = list, +0xD4 = count) - the exact list the door
     check at 0x47D6E0 walks. While armed it re-checks that list every 0.1 s and re-applies the
     change if the game rebuilt it.
  v6 (08:39) read the live list correctly (9 doors) but the game closed within 10 s of the
     change, before Jill used a door, and the doorinfo search then found nothing (game gone).
     Likely cause: for a few seconds the doors pointed at the Dark Corridor while the door
     animation table had no Main Hall -> Dark Corridor entry yet. v7 patches the table FIRST,
     then the doors, and no longer touches the lock byte (+0x43). It also logs whether the game
     is still running for 10 s after the change, so we know exactly when a crash happens.

What v5 tests (Claude's research, 2026-11-12):
  * Every room's .arc is self-contained, and the game loads the destination's .arc from the
    door record itself - it does NOT preload the rooms next door. So far rooms should load.
  * But the door animation comes from a table, door\\doorinfo (in ingamecommon.arc): 274 entries,
    one per (from room -> to room) pair, giving the door model, motion, sound and camera.
    Main Hall -> Dark Corridor has no entry, so v3's door had no door model -> likely the crash.
  * v5 also edits that table (in memory) for the doors it changes: the entry for
    "this room -> real destination" gets the decoy as its destination, so the game plays the
    real door's own animation and then loads the decoy. Everything is put back afterwards.

How to use:
  1. Load a save, stand in a Mansion 1F room (the Main Hall is good). Run
     Tools\run_hd_wrong_door_test.bat.
  2. Press F9  = far room in the same building (Dark Corridor; Roofed Passage if you are next to it).
     Press F10 = themed far room in another area: the Lab B3 Cell ("Wesker caught you!").
     WAIT until it says "Walk through any door" (scanning takes a few seconds).
  3. Walk through any door that isn't locked. Then walk through any door there to come back.
  4. Close the window and send hd_wrong_door_test_output.txt (and a photo if it crashes).
"""
import json
import math
import struct
import sys
import time
from pathlib import Path

from client import hd_versions as hv
from client.pc_process import ProcessConnection, ProcessError
from client.window_mode import key_held
from hd_inventory import sha256_of

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "hd_wrong_door_test_output.txt"
ROOMS = json.loads((HERE / "client" / "bhdtool_rooms.json").read_text(encoding="utf-8"))
PAIRS = json.loads((HERE / "client" / "door_pairs.json").read_text(encoding="utf-8"))["doors"]
NAMES = json.loads((HERE / "client" / "room_names.json").read_text(encoding="utf-8"))
VK_F9 = 0x78
VK_F10 = 0x79
FAR_DECOYS = [0x10A, 0x11A]               # Dark Corridor, Roofed Passage
THEMED = 0x512                            # Laboratory B3 - Cell
INFO_OFFSETS = (0x1C, 0x20, 0x24, 0x28)    # doorinfo entry: src stage, src room, dest stage, dest room
DOOR_VTABLE = 0x00C23408                   # first 4 bytes of every door record (Sept 2026 build)
CHUNK = 4 * 1024 * 1024
MAX_HITS = 4096


def say(text):
    line = f"{time.strftime('%H:%M:%S')} {text}"
    print(line, flush=True)
    with OUTPUT.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def name(room: int) -> str:
    return NAMES.get(f"{room:x}", f"{room:#x}")


def arrival(room: int, came_from=None):
    doors = ROOMS.get(f"{room:x}", {}).get("doors", [])
    pick = [d for d in doors if came_from is not None and d["targetRoomNb"] == f"{came_from:x}"] or doors
    d = pick[0]
    return d["x"], d["y"], d["z"], math.radians(d["angle"]), d["cut"]


def doors_out_of(room: int):
    """Destinations of the doors in `room` (from rooms.json)."""
    return {int(dest, 16) for dest, data in ROOMS.items()
            for d in data["doors"] if d["targetRoomNb"] == f"{room:x}"}


def search(conn, patterns, aligned=True):
    """{pattern: [addresses]} over the game's readable memory."""
    found = {p: [] for p in patterns}
    for base, size in conn.readable_regions(0x7FFF0000):
        off = 0
        while off < size:
            n = min(CHUNK, size - off)
            try:
                data = conn.read_bytes(base + off, n)
            except ProcessError:
                break
            for p in patterns:
                hits = found[p]
                i = data.find(p)
                while i != -1 and len(hits) < MAX_HITS:
                    if not aligned or (base + off + i) % 4 == 0:
                        hits.append(base + off + i)
                    i = data.find(p, i + 1)
            off += CHUNK
    return found


def find_door_records(conn, room: int):
    """[(address, destination)] of every door record (by class) leading out of `room`."""
    dests = doors_out_of(room)
    hits = search(conn, [struct.pack("<I", DOOR_VTABLE)])[struct.pack("<I", DOOR_VTABLE)]
    out = []
    for a in hits:
        try:
            rec = conn.read_bytes(a, 0x4C)
        except ProcessError:
            continue
        dest = rec[0x40] * 0x100 + rec[0x41]
        if dest in dests and 1 <= rec[0x40] <= 6:
            out.append((a, dest))
    return out, len(hits)


def redirect(conn, records, target: int, arr):
    x, y, z, ang, cut = arr
    for addr, _dest in records:
        conn.write_bytes(addr + 0x30, struct.pack("<fff", x, y, z))
        conn.write_bytes(addr + 0x40, bytes([target >> 8, target & 0xFF, cut & 0xFF]))
        conn.write_bytes(addr + 0x48, struct.pack("<f", ang))


def report(conn, records, room):
    say(f"  {len(records)} door records out of {name(room)}:")
    for a, d in records:
        rec = conn.read_bytes(a, 0x4C)
        x, y, z = struct.unpack_from("<3f", rec, 0x30)
        say(f"    {a:#010x} -> {name(d)}  arrive ({x:.1f}, {y:.4f}, {z:.1f})  key {rec[0x43]}")
    held = search(conn, [struct.pack("<I", a) for a, _ in records])
    live = [(a, d, held[struct.pack("<I", a)]) for a, d in records if held[struct.pack("<I", a)]]
    say(f"  records the game points to (live list candidates): {len(live)}")
    for a, d, holders in live:
        say(f"    {a:#010x} -> {name(d)} pointed to from {[hex(h) for h in holders[:4]]}")


def split(room: int):
    return room >> 8, room & 0xFF


def info_pattern(src: int, dest: int) -> bytes:
    return struct.pack("<4i", *split(src), *split(dest))


def find_info(conn, pairs):
    """{(src, dest): [entry addresses]} of door\\doorinfo entries in memory (model name at +0x8)."""
    pats = {pair: info_pattern(*pair) for pair in pairs}
    hits = search(conn, list(set(pats.values())))
    out = {}
    for pair, pat in pats.items():
        good = []
        for h in hits[pat]:
            entry = h - 0x1C
            try:
                model = conn.read_bytes(entry + 0x8, 8)
            except ProcessError:
                continue
            if model[:2] == b"do":
                good.append(entry)
        out[pair] = good
    return out


def patch_info(conn, room: int, records, target: int):
    """Point this room's doorinfo entries (room -> each real destination) at `target`.
    Returns [(entry, original 8 bytes)] for put_back."""
    pairs = sorted({(room, d) for _a, d in records if d != target})
    found = find_info(conn, pairs + [(room, target)])
    if found.get((room, target)):
        say(f"  doorinfo already has {name(room)} -> {name(target)} ({len(found[(room, target)])} entries).")
    saved = []
    for pair in pairs:
        entries = found.get(pair, [])
        model = conn.read_bytes(entries[0] + 0x8, 8).split(b"\0")[0].decode("ascii", "replace") if entries else "-"
        say(f"  doorinfo {name(pair[0])} -> {name(pair[1])}: {len(entries)} entr{'y' if len(entries) == 1 else 'ies'} (door model {model})")
        for e in entries:
            saved.append((e, conn.read_bytes(e + 0x24, 8)))
            conn.write_bytes(e + 0x24, struct.pack("<ii", *split(target)))
    say(f"  doorinfo entries now leading to {name(target)}: {len(saved)}")
    return saved


def put_back(conn, saved):
    for e, orig in saved:
        try:
            conn.write_bytes(e + 0x24, orig)
        except ProcessError:
            pass
    if saved:
        say(f"  put back {len(saved)} doorinfo entries.")


GAME_VTABLE = 0x00C21854                   # class "Game" (owns the room scene and its door list)
DOOR_LIST = 0x1B0                          # Game+0x50 scene, +0x160 trigger list
LIST_COUNT, LIST_ARRAY = 0xD4, 0xE0


def find_game(conn):
    """Address of the Game object (one per session)."""
    for a in search(conn, [struct.pack("<I", GAME_VTABLE)])[struct.pack("<I", GAME_VTABLE)]:
        try:
            count, arr = struct.unpack("<I", conn.read_bytes(a + DOOR_LIST + LIST_COUNT, 4))[0], \
                struct.unpack("<I", conn.read_bytes(a + DOOR_LIST + LIST_ARRAY, 4))[0]
        except ProcessError:
            continue
        if count <= 64 and (count == 0 or arr > 0x10000):
            return a
    return None


def live_records(conn, game):
    """[(address, destination)] straight from the game's live door list."""
    base = game + DOOR_LIST
    count = struct.unpack("<I", conn.read_bytes(base + LIST_COUNT, 4))[0]
    arr = struct.unpack("<I", conn.read_bytes(base + LIST_ARRAY, 4))[0]
    if not arr or count > 64:
        return []
    out = []
    for p in struct.unpack(f"<{count}I", conn.read_bytes(arr, 4 * count)):
        if not p:
            continue
        rec = conn.read_bytes(p, 0x4C)
        if struct.unpack_from("<I", rec, 0)[0] != DOOR_VTABLE:
            continue
        out.append((p, rec[0x40] * 0x100 + rec[0x41]))
    return out


def heartbeat(conn, ptr, seconds=10):
    """Log once a second whether the game is still alive after a change."""
    for i in range(seconds):
        time.sleep(1.0)
        try:
            conn.read_bytes(ptr, 4)
        except ProcessError:
            say(f"  !! the game stopped {i + 1} s after the change (before any door was used)")
            raise
    say(f"  game still fine {seconds} s after the change.")


def show(records, title):
    say(f"  {title}: {len(records)}")
    for a, d in records:
        say(f"    {a:#010x} -> {name(d)}")


def main() -> int:
    OUTPUT.write_text(f"=== Wrong door test v7 {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n", encoding="utf-8")
    print(__doc__)
    try:
        conn = ProcessConnection("bhd.exe", writable=True)
        if not conn.connect():
            say("bhd.exe is not running.")
            return 1
        build = hv.find_build(sha256_of(conn.exe_path))
        if build is None or build.key not in hv.FLAGS_POINTER:
            say("This test only knows the Sept 2026 Steam build.")
            return 1
        ptr = hv.FLAGS_POINTER[build.key] - hv.DEFAULT_IMAGE_BASE + conn.module_base
        room = prev = None
        state, home, home_from, decoy = "idle", None, None, None
        f9_was = False
        say("Ready. Press F9 (Dark Corridor) or F10 (Lab Cell), wait for 'Walk through any door', then use a door.")
        saved_home, saved_decoy, back_from = [], [], None
        f10_was = False
        game = None
        arr_home = arr_armed = None
        reapplied = 0
        while True:
            flags = struct.unpack("<I", conn.read_bytes(ptr, 4))[0]
            now_room = None
            if flags:
                stage, r = struct.unpack("<ii", conn.read_bytes(flags + hv.CURRENT_ROOM_OFFSET, 8))
                if 1 <= stage <= 6 and 0 <= r < 0x40:
                    now_room = stage * 0x100 + r
            if now_room != room and now_room is not None:
                prev, room = room, now_room
                say(f"Room: {name(room)}")
                if state == "armed":
                    time.sleep(2.0)
                    put_back(conn, saved_home)
                    saved_home = []
                    if room == decoy:
                        say("  ARRIVED IN THE FAR DECOY - it worked! Setting this room's doors to lead back...")
                        recs = live_records(conn, game)
                        show(recs, "live door list here")
                        arr_home = arrival(home, back_from)
                        saved_decoy = patch_info(conn, room, recs, home)
                        redirect(conn, recs, home, arr_home)
                        heartbeat(conn, ptr)
                        say(f"  {len(recs)} records now lead back to {name(home)}. Walk through any door.")
                        state = "in_decoy"
                    else:
                        say("  arrived somewhere else - the change didn't take.")
                        state = "idle"
                elif state == "in_decoy":
                    time.sleep(2.0)
                    put_back(conn, saved_decoy)
                    saved_decoy = []
                    say("  back home - " + ("correct!" if room == home else "NOT the home room."))
                    state = "idle"
            if state in ("armed", "in_decoy") and game is not None and room is not None:
                want = decoy if state == "armed" else home
                try:
                    live = live_records(conn, game)
                except ProcessError:
                    live = []
                here = home if state == "armed" else decoy
                if room == here:
                    real = {int(x, 16) for x in PAIRS.get(f"{here:x}", [])}
                    stale = [(a, d) for a, d in live if d != want and d in real]
                else:
                    stale = []
                if stale:
                    reapplied += 1
                    if reapplied <= 5:
                        say(f"  the door list changed back ({len(stale)} records) - applying again")
                    redirect(conn, stale, want, arr_armed if state == "armed" else arr_home)
            f9 = key_held(VK_F9)
            f10 = key_held(VK_F10)
            pressed = (f9 and not f9_was) or (f10 and not f10_was)
            if pressed and room is not None and state == "idle":
                key = "F9" if f9 else "F10"
                if game is None:
                    say(f"{key}: finding the game's door list (once, a few seconds - stand still)...")
                    game = find_game(conn)
                    say(f"  Game object: {game:#010x}" if game else "  Game object NOT found - send me this file.")
                if game is None:
                    f9_was, f10_was = f9, f10
                    continue
                recs = live_records(conn, game)
                show(recs, f"{key}: live door list for {name(room)}")
                unlocked = [(a, d) for a, d in recs if not conn.read_bytes(a + 0x43, 1)[0] & 0x7F]
                if f9:
                    near = {d for _a, d in recs}
                    choices = [d for d in FAR_DECOYS if d != room and d not in near]
                    decoy = choices[0] if choices else None
                else:
                    decoy = THEMED if room != THEMED else None
                if not recs or decoy is None:
                    say("  nothing to do here (no doors found, or the decoy is next door) - try another room.")
                else:
                    home, home_from = room, prev
                    back_from = (unlocked or recs)[0][1]
                    arr_armed = arrival(decoy, room)
                    saved_home = patch_info(conn, room, recs, decoy)
                    if not saved_home:
                        say("  no door animation entries found - NOT changing the doors (it would crash).")
                        f9_was, f10_was = f9, f10
                        continue
                    redirect(conn, recs, decoy, arr_armed)
                    say("  doors changed. Stand still for a moment...")
                    heartbeat(conn, ptr)
                    say(f"  All {len(recs)} door records now lead to {name(decoy)} (far away).")
                    say("  Walk through any door that isn't locked.")
                    reapplied = 0
                    state = "armed"
            f9_was, f10_was = f9, f10
            time.sleep(0.1)
    except ProcessError as exc:
        say(f"ERROR: {exc}")
        return 1
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
