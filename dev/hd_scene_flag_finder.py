"""
Steam version - SCENE FLAG FINDER (READ-ONLY). Research for the Wrong Door trap (2026-11-12).

Goal: find the flag that says "Chris's cutscene in the Lab B3 Cell has been seen", so the Wrong
Door trap can hide the scene when it sends Jill to the Cell (and put the flag back afterwards).

How to use:
  1. Load a save from BEFORE you've seen Chris in the Cell. Go to the Laboratory B3 Cell Entrance.
  2. Run Tools\\run_hd_scene_flag_finder.bat. Stand in the Cell Entrance and press F9  (snapshot A).
  3. Walk into the Cell, watch Chris's scene, walk back out to the Cell Entrance. Press F9 (B).
  4. Walk into the Cell again (no scene this time), walk back out. Press F9 (C).
  5. Close the window and send hd_scene_flag_finder_output.txt.

Bits that turned ON between A and B and did NOT change between B and C are the candidates
(step 4 is the control: it shows what simply walking in and out changes). It only READS memory.
"""
import struct
import sys
import time
from pathlib import Path

from client import hd_versions as hv
from client.pc_process import ProcessConnection, ProcessError
from client.window_mode import key_held
from hd_inventory import sha256_of

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "hd_scene_flag_finder_output.txt"
VK_F9 = 0x78
BEFORE, AFTER = 0x100, 0x1000          # window around the flags structure
VISITED = (0x33C, 0x352)               # room-visited flags (known)
PICKUPS = (0x2C0, 0x33C)               # pickup flags (known)


def say(text):
    line = f"{time.strftime('%H:%M:%S')} {text}"
    print(line, flush=True)
    with OUTPUT.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def bits_changed(a: bytes, b: bytes):
    out = []
    for i, (x, y) in enumerate(zip(a, b)):
        d = x ^ y
        while d:
            bit = (d & -d).bit_length() - 1
            out.append((i - BEFORE, bit, (y >> bit) & 1))
            d &= d - 1
    return out


def label(off: int) -> str:
    if VISITED[0] <= off < VISITED[1]:
        return "  (room-visited flags)"
    if PICKUPS[0] <= off < PICKUPS[1]:
        return "  (pickup flags)"
    return ""


def main() -> int:
    OUTPUT.write_text(f"=== Scene flag finder {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n", encoding="utf-8")
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
        ptr = hv.FLAGS_POINTER[build.key] - hv.DEFAULT_IMAGE_BASE + conn.module_base
        snaps, was, room_was, last, muted = [], False, None, None, set()
        say("Ready. Stand in the Cell Entrance and press F9 for snapshot A.")
        while True:
            flags = struct.unpack("<I", conn.read_bytes(ptr, 4))[0]
            if flags:
                stage, r = struct.unpack("<ii", conn.read_bytes(flags + hv.CURRENT_ROOM_OFFSET, 8))
                room = stage * 0x100 + r
                if room != room_was:
                    say(f"Room: {room:#x}")
                    room_was = room
                data = conn.read_bytes(flags - BEFORE, BEFORE + AFTER)
                if last is not None and len(snaps) == 1:
                    # timeline between A and B: every bit that turns on, with the room it happened in
                    changes = bits_changed(last, data)
                    for off, bit, now in changes:
                        if not now:
                            muted.add((off, bit))      # turns off = a counter/timer, not a flag
                    new = [(o, b) for o, b, now in changes if now and (o, b) not in muted]
                    if len(new) > 40:
                        say(f"   {len(new)} bits turned on at once (room {room:#x}) - a load/screen change")
                    else:
                        for o, b in new:
                            say(f"   on: +{o:#x} bit {b}  (room {room:#x}){label(o)}")
                last = data
                down = key_held(VK_F9)
                if down and not was:
                    snaps.append(data)
                    name = "ABC"[len(snaps) - 1]
                    say(f"F9: snapshot {name} taken in room {room:#x}.")
                    if len(snaps) == 1:
                        say("Now walk into the Cell, watch the scene, come back out, press F9.")
                    elif len(snaps) == 2:
                        say("Now walk into the Cell again (no scene), come back out, press F9.")
                    else:
                        a, b, c = snaps
                        ab = {(o, bit): now for o, bit, now in bits_changed(a, b)}
                        bc = {(o, bit) for o, bit, _ in bits_changed(b, c)}
                        cands = sorted(k for k, now in ab.items() if now and k not in bc)
                        say(f"CANDIDATES (on after the scene, unchanged by the control walk): {len(cands)}")
                        for o, bit in cands:
                            say(f"   +{o:#x} bit {bit}{label(o)}")
                        say("Done - close the window and send hd_scene_flag_finder_output.txt.")
                        return 0
                was = down
            time.sleep(0.1)
    except ProcessError as exc:
        say(f"ERROR: {exc}")
        return 1
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
