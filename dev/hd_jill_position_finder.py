"""
Steam version - JILL POSITION FINDER (READ-ONLY). Research for the Key Map (2026-11-12).

Goal: find where the game keeps Jill's position (x, y, z), and a pointer path to it that works
in every room, so the Key Map can show exactly which part of a room she's in. The game uses one
room number for some pairs of map rooms (Tea Room + Northern Corridor 0x103, Winding Corridor +
Bathroom 0x109, Graveyard + Crypt 0x10b, Large Art + Mirror Room 0x111), so the room number alone
can't tell them apart.

How it works: when Jill comes through a door she appears at a spot the game's door data gives
(client/door_data.py ARRIVALS, from BhdTool's rooms.json). The tool looks for that spot in memory
right after each door, keeps the places that follow Jill when she walks, then looks for pointer
paths from bhd.exe to them and keeps the paths that are right in every room.

How to use:
  1. Load any save in the Mansion. Run Tools\\run_hd_jill_position_finder.bat.
  2. Walk through a door. When the new room appears, DON'T TOUCH THE CONTROLLER until the tool
     says "walk around" (a few seconds while it searches memory).
  3. Walk around the room for about 10 seconds, the way the tool says, then stand still.
  4. Go through a door into a DIFFERENT room and again don't touch anything until it says so.
     Repeat until the tool says "DONE" (usually 3-4 rooms).
  5. Close the window and send hd_jill_position_finder_output.txt.

It only READS memory.
"""
import re
import struct
import sys
import time
from pathlib import Path

from client import hd_versions as hv
from client.pc_process import ProcessConnection, ProcessError
from hd_inventory import sha256_of

HERE = Path(__file__).resolve().parent
from client.door_data import ARRIVALS     # noqa: E402  (the world's own door data)
OUTPUT = HERE / "hd_jill_position_finder_output.txt"
TOL = 2.0                  # game units: Jill can settle a little after the door
CHUNK = 1 << 20
MAX_STRUCT = 0x2000        # pointer -> position: offsets up to this
ROOMS_NEEDED = 3           # rooms a pointer path must be right in


def say(text=""):
    line = f"{time.strftime('%H:%M:%S')} {text}" if text else ""
    print(line, flush=True)
    with OUTPUT.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def f2u(v: float) -> int:
    return struct.unpack("<I", struct.pack("<f", v))[0]


def top_bytes(lo: float, hi: float):
    """All (byte2, byte3) little-endian top halves of floats between lo and hi (same sign)."""
    a, b = sorted((f2u(lo), f2u(hi)))
    return {((u >> 16) & 0xFF, u >> 24) for u in range(a & 0xFFFF0000, b + 1, 0x10000)}


def float_regex(v: float) -> re.Pattern:
    lo, hi = v - TOL, v + TOL
    if lo < 0 < hi:
        raise ValueError("too close to 0")
    alts = b"|".join(re.escape(bytes([b2, b3])) for b2, b3 in sorted(top_bytes(lo, hi)))
    return re.compile(b"(?s)..(?:" + alts + b")")


def regions(conn):
    for start, size in conn.readable_regions():
        yield start, size


def read_chunks(conn, start, size):
    off = 0
    while off < size:
        n = min(CHUNK, size - off)
        try:
            yield start + off, conn.read_bytes(start + off, n)
        except ProcessError:
            pass
        off += n


def find_spot(conn, x, y, z):
    """Addresses A where float(A) ~ x and float(A+4 or A+8) ~ z (and something ~ y between)."""
    big, other, first_is_x = (x, z, True) if abs(x) >= abs(z) else (z, x, False)
    pat = float_regex(big)
    out = []
    for start, size in regions(conn):
        for base, data in read_chunks(conn, start, size):
            for m in pat.finditer(data):
                o = m.start()
                if o % 4 or o + 12 > len(data):
                    continue
                v = struct.unpack_from("<f", data, o)[0]
                if abs(v - big) > TOL:
                    continue
                if first_is_x:
                    for step in (8, 4):
                        if o + step + 4 <= len(data) and abs(struct.unpack_from("<f", data, o + step)[0] - other) <= TOL:
                            out.append((base + o, step))
                else:            # we found z; x sits 8 or 4 bytes before
                    for step in (8, 4):
                        if o - step >= 0 and abs(struct.unpack_from("<f", data, o - step)[0] - other) <= TOL:
                            out.append((base + o - step, step))
    return out


def read_xz(conn, addr, step):
    try:
        x, = struct.unpack("<f", conn.read_bytes(addr, 4))
        z, = struct.unpack("<f", conn.read_bytes(addr + step, 4))
        y, = struct.unpack("<f", conn.read_bytes(addr + 4, 4)) if step == 8 else (float("nan"),)
        return x, y, z
    except ProcessError:
        return None


def pointer_holders(conn, targets, only=None, max_off=MAX_STRUCT):
    """{address (4-aligned): [(target, offset)]} for every dword P with 0 <= target - P < max_off.
    only=(lo, hi): search just that address range (bhd.exe's own memory)."""
    import bisect
    targets = sorted(set(targets))
    tops = set()
    for t in targets:
        tops |= set(range(max(0, t - max_off + 1) >> 16, (t >> 16) + 1))
    pat = re.compile(b"(?s)..(?:" + b"|".join(re.escape(struct.pack("<H", top)) for top in sorted(tops)) + b")")
    found = {}
    lo_hi = only or (0, 1 << 32)
    for start, size in regions(conn):
        if start + size <= lo_hi[0] or start >= lo_hi[1]:
            continue
        for base, data in read_chunks(conn, start, size):
            for m in pat.finditer(data):
                o = m.start()
                if o % 4:
                    continue
                p = struct.unpack_from("<I", data, o)[0]
                i = bisect.bisect_left(targets, p)
                while i < len(targets) and targets[i] - p < max_off:
                    found.setdefault(base + o, []).append((targets[i], targets[i] - p))
                    i += 1
    return found


def resolve(conn, chain):
    """chain = (static address, [offsets...]) -> final address or None."""
    static, offs = chain
    try:
        a = struct.unpack("<I", conn.read_bytes(static, 4))[0]
        for o in offs[:-1]:
            a = struct.unpack("<I", conn.read_bytes(a + o, 4))[0]
        return a + offs[-1]
    except ProcessError:
        return None


def main() -> int:
    OUTPUT.write_text(f"=== Jill position finder {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n", encoding="utf-8")
    print(__doc__)
    try:
        conn = ProcessConnection("bhd.exe")
        if not conn.connect():
            say("bhd.exe is not running.")
            return 1
        build = hv.find_build(sha256_of(conn.exe_path))
        if build is None or build.key not in hv.FLAGS_POINTER:
            say("This tool only knows the Sept 2026 Steam build.")
            return 1
        mod = (conn.module_base, conn.module_base + conn.module_size)
        flags_ptr = hv.FLAGS_POINTER[build.key] - hv.DEFAULT_IMAGE_BASE + conn.module_base

        def room():
            flags = struct.unpack("<I", conn.read_bytes(flags_ptr, 4))[0]
            if not flags:
                return None
            stage, r = struct.unpack("<ii", conn.read_bytes(flags + hv.CURRENT_ROOM_OFFSET, 8))
            return stage * 0x100 + r if 1 <= stage <= 6 and 0 <= r < 0x100 else None

        say(f"bhd.exe base {conn.module_base:#x}. READ-ONLY.")
        say("Walk through a door. Then DON'T TOUCH THE CONTROLLER until I say so.")
        chains = None               # pointer paths still right in every room so far
        rooms_ok = 0
        last = room()
        while True:
            time.sleep(0.1)
            now = room()
            if now is None or now == last:
                continue
            came_from, last = last, now
            spots = [a for a in ARRIVALS.get(now, []) if came_from is None or a[0] == came_from]
            if not spots:
                say(f"Room {now:#x}: no door data for coming from {came_from or 0:#x} - try another door.")
                continue
            time.sleep(1.0)          # let the room finish loading
            say(f"Room {now:#x} (from {came_from:#x}). Searching memory - don't move...")
            hits = []
            for _src, x, y, z, _ang, _cut in spots:
                try:
                    hits += [(a, step, (x, y, z)) for a, step in find_spot(conn, x, y, z)]
                except ValueError:
                    say("  this door's spot is too close to 0 to search - try another door.")
            say(f"  {len(hits)} places hold the arrival spot.")
            if chains is not None:
                good = []
                for ch in chains:
                    a = resolve(conn, ch[0])
                    v = read_xz(conn, a, ch[1]) if a else None
                    if v and any(abs(v[0] - s[1]) <= TOL and abs(v[2] - s[3]) <= TOL for s in spots):
                        good.append(ch)
                say(f"  pointer paths still right here: {len(good)} of {len(chains)}")
                chains = good
                rooms_ok += 1
                if not chains:
                    say("  None left - starting over from this room.")
                    chains = None
                elif rooms_ok >= ROOMS_NEEDED - 1:
                    report(conn, chains)
                    return 0
                else:
                    say("  Good. Go through a door into another room (don't touch anything after).")
                    continue
            if not hits:
                say("  Nothing found. Go through another door.")
                continue
            say("WALK AROUND now for about 10 seconds - all over the room - then stand still.")
            start_vals = {(a, s): read_xz(conn, a, s) for a, s, _ in hits}
            moved = set()
            t_end = time.time() + 12
            while time.time() < t_end:
                for key, v0 in start_vals.items():
                    v = read_xz(conn, *key)
                    if v and v0 and (abs(v[0] - v0[0]) > 20 or abs(v[2] - v0[2]) > 20):
                        moved.add(key)
                time.sleep(0.2)
            say(f"  {len(moved)} of them followed Jill. Now STAND STILL...")
            time.sleep(2.0)
            a1 = {k: read_xz(conn, *k) for k in moved}
            time.sleep(1.0)
            still = [k for k in moved if a1[k] and read_xz(conn, *k) == a1[k]]
            say(f"  {len(still)} stay put when she stands still.")
            for a, s in still[:20]:
                v = read_xz(conn, a, s)
                say(f"    0x{a:08X} (z at +{s}): x {v[0]:.1f} y {v[1]:.1f} z {v[2]:.1f}")
            if not still:
                say("  Nothing followed her. Go through another door and try again.")
                continue
            say("  Looking for pointer paths to them (can take a minute)...")
            targets = [a for a, _s in still[:40]]
            step_of = dict(still)
            found = []
            level1 = pointer_holders(conn, targets, mod)            # bhd.exe -> position
            for holder, lst in level1.items():
                for t, off in lst:
                    found.append(((holder, [off]), step_of[t]))
            heap = pointer_holders(conn, targets, None, 0x1000)       # object -> position
            heap = {h: v for h, v in heap.items() if not (mod[0] <= h < mod[1])}
            say(f"  {len(level1)} direct paths, {len(heap)} objects pointing near her position.")
            if heap:
                keep = sorted(heap, key=lambda h: min(o for _t, o in heap[h]))[:5000]
                level2 = pointer_holders(conn, keep, mod, 0x1000)    # bhd.exe -> object
                for holder, lst in level2.items():
                    for h, off1 in lst:
                        for t, off2 in heap[h]:
                            found.append(((holder, [off1, off2]), step_of[t]))
            say(f"  {len(found)} pointer paths. Now go through a door into ANOTHER room and don't touch anything.")
            chains, rooms_ok = found, 0
            if not chains:
                say("  No pointer paths found - keep the output file anyway.")
    except ProcessError as exc:
        say(f"ERROR: {exc}")
        return 1
    except KeyboardInterrupt:
        say("Stopped.")
        return 0


def report(conn, chains):
    say("")
    say("DONE. Pointer paths that were right in every room:")
    chains = sorted(chains, key=lambda c: (len(c[0][1]), c[0][1]))
    for (static, offs), step in chains[:40]:
        a = resolve(conn, (static, offs))
        v = read_xz(conn, a, step) if a else None
        rel = static - conn.module_base + hv.DEFAULT_IMAGE_BASE
        path = " -> ".join(f"+{o:#x}" for o in offs)
        say(f"  [bhd.exe {rel:#010x}] {path}  (z at +{step}) now x {v[0]:.1f} y {v[1]:.1f} z {v[2]:.1f}" if v
            else f"  [bhd.exe {rel:#010x}] {path}")
    say("Close the window and keep hd_jill_position_finder_output.txt.")


if __name__ == "__main__":
    sys.exit(main())
