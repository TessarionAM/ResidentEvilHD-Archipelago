"""
Steam version - DOOR SHUFFLE LAB (testing helper, 2026-11-12). WRITES to the game (memory only).

Research for the door randomiser (TessarionAM: whole game, stairs / ladders / lifts too). The Wrong
Door trap proved ordinary door -> ordinary door works, also across areas. This lab tests the
transitions nobody has tried yet:
  A. arriving at a LADDER (e.g. coming out at the top/bottom of the Crypt or Caves ladder)
  B. arriving at a LIFT / elevator
  C. leaving by a LADDER or LIFT that has been pointed somewhere else
  D. arriving in another area at an ordinary door (done before - a control)

How to use (on a SPARE save - it can take you to places out of story order):
  1. Run Tools\\run_hd_door_shuffle_lab.bat, load the save, stand in any room.
  2. Wait for "Ready" (a few seconds the first time).
  3. Press F10. The tool says where every exit of this room now leads (it picks the next test
     that hasn't been done yet). If the room has a ladder or lift, USE IT - that also tests C.
  4. Walk through. On arrival it says OK. The exits there now lead back to where you came from:
     go back through one (if this room has a ladder / lift, use that).
  5. Repeat F10 until it says "ALL TESTS DONE". If the game crashes, just write down which
     exit you used and send the output file - the last lines say what was being tried.
  6. Send hd_door_shuffle_lab_output.txt.

Locks are never touched. Doors that are locked stay locked (use another exit).
"""
import json
import math
import random
import struct
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
from client import wrong_door as wdm                   # noqa: E402  (the world's client code)
from client.door_data import ARRIVALS                  # noqa: E402
from client import hd_versions as hv                   # noqa: E402
from client.pc_process import ProcessConnection, ProcessError   # noqa: E402
from client.window_mode import key_held                # noqa: E402
from hd_inventory import sha256_of                     # noqa: E402

OUTPUT = HERE / "hd_door_shuffle_lab_output.txt"
NAMES = json.loads((HERE / "client" / "room_names.json").read_text(encoding="utf-8"))
_TYPES = json.loads((HERE / "client" / "doorinfo_pairs.json").read_text(encoding="utf-8"))["doors"]
TYPE = {(int(e["src"], 16), int(e["dest"], 16)): e["door_type"] for e in _TYPES}
KIND = {0: "door", 1: "door", 2: "double door", 3: "LADDER", 4: "LIFT"}
VK_F10 = 0x79
AVOID = {0x303, 0x501, 0x50D}          # Heliport, its passage and elevator: the ending
TESTS = ["lift departure", "lift departure"]
# v3 (2026-11-13): run 2 proved leaving by a redirected LADDER (Lab Entrance, Aqua Ring Entry). Lifts were
# never left by (Falls Area lift needs the battery, the kitchen lift had no power), so v3 only sends Jill
# to Jessica's Tomb, at its lift (needs nothing - TessarionAM rode it in run 1), and she leaves by that lift.
# Also fixed: the exits were listed after they'd been redirected, so ladders/lifts showed as "door".
LIFT_ROOM = 0x315
# v2 (2026-11-12 17:3x): run 1 proved arriving at ladders / lifts / another area; the way back (leaving
# by a redirected ladder or lift) never armed - fixed (home_spot).


def say(text=""):
    line = f"{time.strftime('%H:%M:%S')} {text}" if text else ""
    print(line, flush=True)
    with OUTPUT.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def name(room: int) -> str:
    return f"{NAMES.get(f'{room:x}', '?')} ({room:x})"


def ends():
    """Every place Jill can arrive: (room, the room its door leads to), with the door's kind."""
    out = []
    for room, spots in ARRIVALS.items():
        if room in AVOID:
            continue
        for src, x, y, z, ang, cut in spots:
            if (x, y, z) == (0, 0, 0) or src in AVOID:
                continue
            out.append((room, src, TYPE.get((room, src), 0)))
    return out


def pick(test: str, here: int, rng):
    stage = here >> 8
    pool = ends()
    if test == "lift departure":
        cand = [e for e in pool if e[0] == LIFT_ROOM and e[2] == 4 and e[0] != here]
    elif test == "ladder arrival":
        cand = [e for e in pool if e[2] == 3 and e[0] != here]
    elif test == "lift arrival":
        cand = [e for e in pool if e[2] == 4 and e[0] != here]
    else:
        cand = [e for e in pool if e[2] in (0, 1, 2) and e[0] >> 8 != stage]
    return rng.choice(cand) if cand else None


def spot(room: int, came_from: int):
    for src, x, y, z, ang, cut in ARRIVALS.get(room, []):
        if src == came_from:
            return x, y, z, math.radians(ang), cut
    return None


def home_spot(room: int):
    """Any usable arrival spot in `room` (the way back): v2 fix - v1 looked for the target room's
    neighbour in the wrong room, found none and changed no exit (lab run 17:24)."""
    for src, x, y, z, _ang, _cut in ARRIVALS.get(room, []):
        if (x, y, z) != (0, 0, 0) and src not in AVOID:
            return src
    return None


def point_all(w, conn, pid, room: int, target: int, came_from: int) -> int:
    """Every real exit of `room` -> arrive in `target` at its door to `came_from`. Returns how many."""
    arr = spot(target, came_from)
    game = w._game(conn, pid)
    if arr is None or not game:
        return 0
    x, y, z, ang, cut = arr
    n = 0
    for rec, dest in w._live(conn, game):
        if dest == target:
            continue
        if not w._patch_info(conn, pid, room, dest, target):
            continue
        conn.write_bytes(rec + 0x30, struct.pack("<fff", x, y, z))
        conn.write_bytes(rec + 0x40, bytes([target >> 8, target & 0xFF, cut & 0xFF]))
        conn.write_bytes(rec + 0x48, struct.pack("<f", ang))
        n += 1
    return n


def exits(w, conn, pid, room: int):
    game = w._game(conn, pid)
    if not game:
        return []
    return [(dest, KIND.get(TYPE.get((room, dest), 0), "door")) for _rec, dest in w._live(conn, game)]


def main() -> int:
    OUTPUT.write_text(f"=== Door shuffle lab {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n", encoding="utf-8")
    print(__doc__)
    rng = random.Random()
    try:
        conn = ProcessConnection("bhd.exe", writable=True)
        if not conn.connect():
            say("bhd.exe is not running.")
            return 1
        build = hv.find_build(sha256_of(conn.exe_path))
        if build is None or build.key not in hv.FLAGS_POINTER:
            say("This tool only knows the Sept 2026 Steam build.")
            return 1
        pid = getattr(conn, "pid", None)
        ptr = hv.FLAGS_POINTER[build.key] - hv.DEFAULT_IMAGE_BASE + conn.module_base
        w = wdm.WrongDoor({}, lambda: None)
        w.warm_up(conn, pid)
        say("Finding the game's door data (a few seconds)...")
        while not w.ready(conn, pid):
            time.sleep(0.5)
            w.warm_up(conn, pid)
        say(f"Ready. {len(w.info)} door animation entries. Stand in a room and press F10.")
        room, was, todo, results = None, False, list(TESTS), []
        trip = None          # {"from", "to", "test", "back": bool, "at"}
        while True:
            flags = struct.unpack("<I", conn.read_bytes(ptr, 4))[0]
            now = None
            if flags:
                st, r = struct.unpack("<ii", conn.read_bytes(flags + hv.CURRENT_ROOM_OFFSET, 8))
                if 1 <= st <= 6 and 0 <= r < 0x40:
                    now = st * 0x100 + r
            if now is not None and now != room:
                prev, room = room, now
                say(f"Room: {name(room)}")
                if trip and prev == trip["from"]:
                    ok = room == trip["to"]
                    results.append((trip["test"] + (" (way back)" if trip["back"] else ""), ok,
                                    trip["from"], trip["to"]))
                    say(f"  {'OK' if ok else 'ARRIVED SOMEWHERE ELSE'}: {trip['test']}"
                        f"{' (way back)' if trip['back'] else ''} -> {name(room)}")
                    time.sleep(wdm.SETTLE)
                    w._put_back_info(conn, pid)
                    if ok and not trip["back"]:
                        # way back: every exit here leads to where she came from
                        back_spot = home_spot(trip["from"])
                        here = exits(w, conn, pid, room)      # before redirecting: the real kinds
                        n = point_all(w, conn, pid, room, trip["from"], back_spot) if back_spot is not None else 0
                        say(f"  Way back armed on {n} exit(s): " + ", ".join(f"{k} to {name(d)}" for d, k in here))
                        if any(k in ("LADDER", "LIFT") for _d, k in here):
                            say("  -> Take the LIFT back (that's the test) - not the door.")
                        if n:
                            trip = {"from": room, "to": trip["from"], "came_from": back_spot,
                                    "test": "leave by " + ("ladder/lift" if any(k in ("LADDER", "LIFT") for _d, k in here)
                                                           else "door"), "back": True}
                        else:
                            say("  Couldn't arm the way back here - press F10 for the next test.")
                            trip = None
                    else:
                        trip = None
                        left = len(todo)
                        say("  Press F10 for the next test." if left else "  ALL TESTS DONE - send the output file.")
                elif trip:
                    say("  (not through a lab exit - the doors here are normal)")
                    trip = None
            down = key_held(VK_F10)
            if down and not was and room is not None and trip is None:
                if not todo:
                    say("All tests done already. Close the window and send hd_door_shuffle_lab_output.txt.")
                else:
                    test = todo[0]
                    target = pick(test, room, rng)
                    if target is None:
                        say(f"No target found for '{test}' - skipping it.")
                        todo.pop(0)
                    else:
                        troom, tfrom, ttype = target
                        here = exits(w, conn, pid, room)
                        n = point_all(w, conn, pid, room, troom, tfrom)
                        if not n:
                            say("  Couldn't change the exits here - try another room.")
                        else:
                            todo.pop(0)
                            trip = {"from": room, "to": troom, "came_from": tfrom, "test": test, "back": False}
                            say(f"TEST '{test}': all {n} exit(s) of {name(room)} now lead to {name(troom)}, "
                                f"arriving at its {KIND.get(ttype, 'door')} (the one to {name(tfrom)}).")
                            say("  Exits here: " + ", ".join(f"{k} to {name(d)}" for d, k in here))
                            if any(k in ("LADDER", "LIFT") for _d, k in here):
                                say("  -> This room has a ladder/lift: use THAT (tests leaving by it).")
            was = down
            time.sleep(0.1)
    except ProcessError as exc:
        say(f"ERROR: {exc}")
        return 1
    except KeyboardInterrupt:
        say("Stopped.")
        return 0
    finally:
        try:
            say("Results: " + "; ".join(f"{t}: {'OK' if ok else 'FAIL'} ({a:x}->{b:x})" for t, ok, a, b in results))
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
