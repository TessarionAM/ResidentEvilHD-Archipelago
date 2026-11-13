"""
Steam version - DOOR SCANNER v2 (READ-ONLY). Research for the door lock randomiser.

Door records in memory (0x4C bytes each; every one starts with the door class 0x00C23408):
    +0x30  x, y, z   (floats)  where Jill arrives
    +0x40  stage     (byte)    where it leads
    +0x41  room      (byte)
    +0x42  cut       (byte)
    +0x43  KEY       (byte)    low 7 bits = the key item needed (0 = not locked)
    +0x44  FLAG      (int32)   which "already unlocked" flag the game checks
    +0x48  angle     (float)

v1 found records by the arrival position in BhdTool's rooms.json. That missed doors:
  * dead-end rooms (bathrooms, storerooms, Underground Statue Room...) have no rooms.json
    entries for their way out, so v1 scanned "0 doors" there;
  * 12 rooms.json rows aren't real doors (e.g. Room 001 -> Main Hall), so v1 said
    "record not found" for them.
v2 (2026-11-12) finds records by their door class instead, and checks them against the game's
own list of real doors (door\\doorinfo, saved as client/door_pairs.json: 274 from -> to pairs).
It keeps records the game points to (the live door lists), so leftovers from the room you just
left are ignored. Every room you enter adds its doors to the table. Nothing is written to the game.

Output: hd_door_scanner_output.txt (readable) and hd_door_scanner_doors.jsonl (data, appended).
"""
import json
import struct
import sys
import time
from pathlib import Path

from client import hd_versions as hv
from client.pc_process import ProcessConnection, ProcessError
from hd_inventory import sha256_of

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "hd_door_scanner_output.txt"
DOORS_OUT = HERE / "hd_door_scanner_doors.jsonl"
PAIRS = json.loads((HERE / "client" / "door_pairs.json").read_text(encoding="utf-8"))["doors"]
DOOR_CLASS = struct.pack("<I", 0x00C23408)   # first 4 bytes of every door record (Sept 2026 build)
NAMES = json.loads((HERE / "client" / "room_names.json").read_text(encoding="utf-8"))
SETTLE = 3.0                 # seconds after a room change before scanning
CHUNK = 4 * 1024 * 1024
MAX_HITS = 4096


def say(text):
    line = f"{time.strftime('%H:%M:%S')} {text}"
    print(line, flush=True)
    with OUTPUT.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def scan(conn, patterns):
    """4-byte-aligned addresses of matches of each pattern in the game's readable memory."""
    found = {p: [] for p in patterns}
    for base, size in conn.readable_regions(0x7FFF0000):
        off = 0
        while off < size:
            n = min(CHUNK + 12, size - off)
            try:
                data = conn.read_bytes(base + off, n)
            except ProcessError:
                break
            for p in patterns:
                hits = found[p]
                if len(hits) >= MAX_HITS:
                    continue
                i = data.find(p)
                while i != -1 and len(hits) < MAX_HITS:
                    if (base + off + i) % 4 == 0 and i < CHUNK:
                        hits.append(base + off + i)
                    i = data.find(p, i + 1)
            del data
            if patterns and all(len(found[p]) >= MAX_HITS for p in patterns):
                return found
            off += CHUNK
    return found


def find_records(conn, room: int, real):
    """[(address, 0x4C bytes)] of door records leading from `room` to one of its real doors.
    Prefers records the game points to (its live door lists)."""
    cands = []
    for a in scan(conn, [DOOR_CLASS])[DOOR_CLASS]:
        try:
            rec = conn.read_bytes(a, 0x4C)
        except ProcessError:
            continue
        if f"{rec[0x40]}{rec[0x41]:02x}" in real:
            cands.append((a, rec))
    if not cands:
        return []
    held = scan(conn, [struct.pack("<I", a) for a, _ in cands])
    live = [(a, r) for a, r in cands if held[struct.pack("<I", a)]]
    return live or cands


def main() -> int:
    OUTPUT.write_text(f"=== Door scanner v2 {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n", encoding="utf-8")
    try:
        conn = ProcessConnection("bhd.exe")          # read-only
        if not conn.connect():
            say("bhd.exe is not running.")
            return 1
        build = hv.find_build(sha256_of(conn.exe_path))
        if build is None or build.key not in hv.FLAGS_POINTER:
            say("This scanner only knows the Sept 2026 Steam build.")
            return 1
        say("READ-ONLY. Play normally; each room's doors are logged a few seconds after you enter.")
        ptr = hv.FLAGS_POINTER[build.key] - hv.DEFAULT_IMAGE_BASE + conn.module_base
        done, last_room, since, retries = set(), None, 0.0, 0
        while True:
            flags = struct.unpack("<I", conn.read_bytes(ptr, 4))[0]
            room = None
            if flags:
                stage, r = struct.unpack("<ii", conn.read_bytes(flags + hv.CURRENT_ROOM_OFFSET, 8))
                if 1 <= stage <= 6 and 0 <= r < 0x40:
                    room = stage * 0x100 + r
            if room != last_room:
                last_room, since, retries = room, time.time(), 0
            elif room is not None and room not in done and time.time() - since >= SETTLE:
                done.add(room)
                hexroom = f"{room:x}"
                real = PAIRS.get(hexroom, [])
                say(f"{NAMES.get(hexroom, hexroom)} ({room:#x}): {len(real)} real door(s) - scanning...")
                recs = find_records(conn, room, real)
                for dest in real:
                    mine = [(a, r) for a, r in recs if f"{r[0x40]}{r[0x41]:02x}" == dest]
                    if not mine:
                        say(f"   -> {NAMES.get(dest, dest)}: no record in memory (door not active yet?)")
                        continue
                    kinds = {}
                    for a, r in mine:
                        kinds.setdefault((r[0x43], r[0x44:0x48], r[0x30:0x3C]), []).append((a, r))
                    for (key, _f, _pos), group in kinds.items():
                        addr, rec = group[0]
                        flag = struct.unpack_from("<i", rec, 0x44)[0]
                        x, y, z = struct.unpack_from("<3f", rec, 0x30)
                        say(f"   -> {NAMES.get(dest, dest)}: KEY {key} (item {key & 0x7F}"
                            f"{', high bit set' if key & 0x80 else ''}), flag {flag}  [{len(group)} copies]"
                            f"  arrive ({x:.0f}, {y:.0f}, {z:.0f})")
                        with DOORS_OUT.open("a", encoding="utf-8") as f:
                            f.write(json.dumps({"t": round(time.time(), 1), "room": room, "dest": int(dest, 16),
                                                "key": key, "flag": flag, "address": addr, "copies": len(group),
                                                "record": rec.hex(), "scanner": 2}) + "\n")
                if real and not recs:
                    # nothing found (e.g. scanned at the title screen, which also says Main Hall):
                    # try this room again next time you enter it
                    # (2026-11-12: the Heliport, whose only door - the lift - isn't active, was
                    # rescanned every 3 s forever: now at most 2 retries per visit)
                    retries += 1
                    if retries <= 2:
                        done.discard(room)
                        say("   (nothing found - trying again in a moment)")
                    else:
                        done.discard(room)
                        since = float("inf")      # not again until you leave and come back
                        say("   (nothing found - this room's doors aren't active now; skipped until next visit)")
            time.sleep(0.5)
    except ProcessError as exc:
        say(f"ERROR: {exc}")
        return 1
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
