"""
Steam version - DOOR SCANNER TOUR (testing helper, 2026-11-12). WRITES to the game (memory only).

Takes you round every room the door scanner hasn't logged yet. Run it AT THE SAME TIME as the
door scanner (Tools\\run_hd_door_scanner.bat, v2), which logs each room you arrive in.

  F9  = every door in your room now leads to the CLOSEST room still missing from the scanner's
        table. Walk through any door that isn't locked. Wait ~4 s in the new room (the scanner
        logs it), then F9 again for the next one.
  F10 = skip the room it picked (e.g. a boss room you'd rather not enter): the doors switch to the
        next room straight away.

Boss / big-event rooms (Attic, Heliport, Enrico Room, Aqua Ring Water Tank, Main Laboratory...)
come LAST, and the tool warns you before going there. Use a spare save and don't save during the
tour: arriving early in later areas marks rooms as visited in that save.

Uses the Wrong Door method (verified 2026-11-12): the door animation table is changed first, then
the game's live door list. Locks are never touched; everything is put back after each trip.
Output: hd_scanner_tour_output.txt.
"""
import json
import struct
import sys
import time
from collections import deque

import hd_wrong_door_test as wd
from client import hd_versions as hv
from client.pc_process import ProcessConnection, ProcessError
from client.window_mode import key_held
from hd_inventory import sha256_of

wd.OUTPUT = wd.HERE / "hd_scanner_tour_output.txt"
say, name = wd.say, wd.name
SCANNED = wd.HERE / "hd_door_scanner_doors.jsonl"
PAIRS = {int(k, 16): [int(d, 16) for d in v] for k, v in wd.PAIRS.items()}
# boss / big-event rooms: visited last, with a warning
RISKY = {0x210: "Yawn (Attic)", 0x303: "Heliport (story)", 0x30A: "Enrico + Hunter",
         0x412: "Neptune (Aqua Ring)", 0x513: "Tyrant (Main Lab)", 0x514: "Main Lab area",
         0x515: "Main Lab elevator", 0x40C: "Plant 42", 0x30C: "Black Tiger", 0x216: "Yawn (Library)"}


def arrival(target: int):
    """Arrival in `target` through a REAL door (rooms.json also has a few rows that aren't doors)."""
    real_from = [f"{s:x}" for s, ds in PAIRS.items() if target in ds]
    doors = wd.ROOMS.get(f"{target:x}", {}).get("doors", [])
    real = [d for d in doors if d["targetRoomNb"] in real_from]
    if not real:
        return None
    return wd.arrival(target, int(real[0]["targetRoomNb"], 16))


def missing_rooms():
    """Rooms that still have a real door the scanner hasn't logged."""
    found = set()
    if SCANNED.exists():
        for line in SCANNED.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                found.add((r["room"], r["dest"]))
            except (ValueError, KeyError):
                continue
    return {s for s, ds in PAIRS.items() if any((s, d) not in found for d in ds)}


def distances(start: int):
    graph = {}
    for s, ds in PAIRS.items():
        for d in ds:
            graph.setdefault(s, set()).add(d)
            graph.setdefault(d, set()).add(s)
    dist, q = {start: 0}, deque([start])
    while q:
        r = q.popleft()
        for n in graph.get(r, ()):
            if n not in dist:
                dist[n] = dist[r] + 1
                q.append(n)
    return dist


def next_target(room: int, done: set):
    todo = [r for r in missing_rooms() - done if r != room and arrival(r)]
    if not todo:
        return None, 0
    dist = distances(room)
    todo.sort(key=lambda r: (r in RISKY, dist.get(r, 999), r))
    return todo[0], len(todo)


def find_info(conn):
    """(src, dest) -> doorinfo entry addresses, found once (class of the Main Hall -> Dining Room entry)."""
    vt = None
    for h in wd.search(conn, [struct.pack("<4i", 1, 6, 1, 5)])[struct.pack("<4i", 1, 6, 1, 5)]:
        if conn.read_bytes(h - 0x1C + 8, 2) == b"do":
            vt = conn.read_bytes(h - 0x1C, 4)
            break
    info = {}
    if vt is None:
        return info
    for e in wd.search(conn, [vt])[vt]:
        raw = conn.read_bytes(e, 0x2C)
        if raw[8:10] == b"do":
            ss, sr, ds, dr = struct.unpack_from("<4i", raw, 0x1C)
            info.setdefault((ss * 0x100 + sr, ds * 0x100 + dr), []).append(e)
    return info


def point_doors(conn, game, info, room, target, saved):
    """Doorinfo first, then the live records. Returns how many doors now lead to target."""
    arr = arrival(target)
    n = 0
    for rec, dest in wd.live_records(conn, game):
        if dest == target:
            n += 1
            continue
        entries = [e for e in info.get((room, dest), [])]
        if not entries:
            continue                      # no animation entry: leave this door alone
        for e in entries:
            if e not in {s[0] for s in saved}:
                saved.append((e, conn.read_bytes(e + 0x24, 8)))
            conn.write_bytes(e + 0x24, struct.pack("<ii", target >> 8, target & 0xFF))
        wd.redirect(conn, [(rec, dest)], target, arr)
        n += 1
    return n


def main() -> int:
    wd.OUTPUT.write_text(f"=== Door scanner tour {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n", encoding="utf-8")
    print(__doc__)
    try:
        conn = ProcessConnection("bhd.exe", writable=True)
        if not conn.connect():
            say("bhd.exe is not running.")
            return 1
        build = hv.find_build(sha256_of(conn.exe_path))
        if build is None or build.key not in hv.FLAGS_POINTER:
            say("This tool only knows the Sept 2026 Steam build.")
            return 1
        ptr = hv.FLAGS_POINTER[build.key] - hv.DEFAULT_IMAGE_BASE + conn.module_base
        say(f"{len(missing_rooms())} rooms still missing from the scanner's table. Make sure the door "
            "scanner is running too. Press F9 to go to the closest one.")
        game, info = None, None
        room, target, armed, saved, done = None, None, False, [], set()
        f9_was = f10_was = False
        while True:
            flags = struct.unpack("<I", conn.read_bytes(ptr, 4))[0]
            now_room = None
            if flags:
                stage, r = struct.unpack("<ii", conn.read_bytes(flags + hv.CURRENT_ROOM_OFFSET, 8))
                if 1 <= stage <= 6 and 0 <= r < 0x40:
                    now_room = stage * 0x100 + r
            if now_room is not None and now_room != room:
                room = now_room
                say(f"Room: {name(room)}")
                if armed:
                    time.sleep(1.5)
                    for e, orig in saved:
                        conn.write_bytes(e + 0x24, orig)
                    saved, armed = [], False
                    if room == target:
                        done.add(room)
                        left = len(missing_rooms() - done)
                        say(f"  Arrived. Wait ~4 s for the scanner to log this room, then F9 "
                            f"({left} room(s) left after this one).")
                    else:
                        say("  Arrived somewhere else - press F9 to try again.")
            if armed and room is not None and game:
                point_doors(conn, game, info, room, target, saved)      # keep them pointed (cheap)
            f9, f10 = key_held(wd.VK_F9), key_held(wd.VK_F10)
            skip = f10 and not f10_was and target is not None and (armed or room != target)
            if skip:
                done.add(target)
                say(f"F10: skipping {name(target)}.")
                for e, orig in saved:          # the doors here get pointed at the next room below
                    conn.write_bytes(e + 0x24, orig)
                saved, armed, target = [], False, None
            if (skip or (f9 and not f9_was)) and room is not None and not armed:
                if game is None or info is None:
                    say("Finding the game's door data (once, ~10-20 s - stand still)...")
                    game = wd.find_game(conn)
                    info = find_info(conn) if game else {}
                    say(f"  game object {game:#x}, door animation table {sum(map(len, info.values()))} entries."
                        if game and info else "  door data NOT found - send me hd_scanner_tour_output.txt.")
                if game and info:
                    target, left = next_target(room, done)
                    if target is None:
                        say("All rooms done! Close this window and send hd_door_scanner_output.txt.")
                    else:
                        warn = f"  WARNING: {RISKY[target]} - F10 to skip it." if target in RISKY else ""
                        n = point_doors(conn, game, info, room, target, saved)
                        if n:
                            armed = True
                            say(f"Next room: {name(target)} ({left} left). {n} door(s) here lead there now"
                                f" - walk through one that isn't locked.{warn}")
                        else:
                            say("No door here can be changed - walk to a neighbouring room and press F9 again.")
            f9_was, f10_was = f9, f10
            time.sleep(0.1)
    except ProcessError as exc:
        say(f"ERROR: {exc}")
        return 1
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
