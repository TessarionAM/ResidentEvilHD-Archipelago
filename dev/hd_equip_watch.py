"""
Steam version - EQUIP WATCH (READ-ONLY). Finds where the game remembers which weapon
Jill is holding, for the random starting inventory (seed test: after we took the
Handgun away she still held one, with 0 bullets).

Watches the inventory structure (+0x00..+0x100 and +0x5000..+0x5200, as int32 values)
and prints every value that changes. Keys while playing (short beep confirms):
    Home      = I just EQUIPPED the Handgun
    Page Up   = I just EQUIPPED the Knife
    Page Down = I just equipped something else / unequipped (type a note later)
Do this a few times each, in the inventory screen. Nothing is written to the game.
Output: hd_equip_watch_output.txt
"""
import struct
import sys
import time
from pathlib import Path

from client import hd_versions as hv
from client.pc_process import ProcessConnection, ProcessError
from hd_event_recorder import beep
from hd_health_watch import Keys
from hd_inventory import inventory_struct_address, sha256_of

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "hd_equip_watch_output.txt"
RANGES = [(0x00, 0x100), (0x5000, 0x5200)]
# v2 (2026-11-11 evening): Jill's own object. The game's code reads her held weapon from
# Jill+0x15D0 (weapon type) and +0x15D4/+0x15D8 (handle of the weapon model), +0x15DC..0x15E4.
JILL_RANGE = (0x15C0, 0x1600)
KEYS = {0x24: "EQUIPPED HANDGUN", 0x21: "EQUIPPED KNIFE", 0x22: "OTHER equip/unequip"}


def say(text):
    line = f"{time.strftime('%H:%M:%S')} {text}"
    print(line, flush=True)
    with OUTPUT.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def snapshot(conn, inv):
    out = {}
    for a, b in RANGES:
        data = conn.read_bytes(inv + a, b - a)
        for i in range(0, b - a, 4):
            out[a + i] = struct.unpack_from("<i", data, i)[0]
    return out


def jill_object(conn, flags_ptr):
    """Jill's character object (verified path, claude/health-and-death.md), or 0."""
    u32 = lambda a: struct.unpack("<I", conn.read_bytes(a, 4))[0]
    mgr = u32(flags_ptr - hv.CHARACTER_MANAGER_BEFORE_FLAGS)
    if not mgr:
        return 0
    lo, hi = u32(mgr + 0x20), u32(mgr + 0x24)
    index = (hi >> 16) & 0xFFFF
    if index >= 0x40:
        return 0
    entry = mgr + 0x8B0 + index * 24
    return u32(entry) if u32(entry) and u32(entry + 4) == lo else 0


def jill_snapshot(conn, obj):
    a, b = JILL_RANGE
    data = conn.read_bytes(obj + a, b - a)
    return {a + i: struct.unpack_from("<i", data, i)[0] for i in range(0, b - a, 4)}


def main() -> int:
    OUTPUT.write_text(f"=== Equip watch {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n", encoding="utf-8")
    try:
        conn = ProcessConnection("bhd.exe")
        if not conn.connect():
            say("bhd.exe is not running.")
            return 1
        build = hv.find_build(sha256_of(conn.exe_path))
        if build is None:
            say("Unknown game build.")
            return 1
        say("READ-ONLY. Home = equipped Handgun, Page Up = equipped Knife, Page Down = other.")
        import hd_health_watch
        hd_health_watch.KEYS.clear()
        hd_health_watch.KEYS.update(KEYS)
        keys, last, jlast = Keys(), None, None
        flags_ptr = hv.FLAGS_POINTER[build.key] - hv.DEFAULT_IMAGE_BASE + conn.module_base
        while True:
            for label in keys.poll():
                say(f">>> {label}")
                beep()
            inv = inventory_struct_address(conn, build, 4)
            if not inv:
                last = None
                time.sleep(0.5)
                continue
            snap = snapshot(conn, inv)
            if last:
                for off, v in snap.items():
                    if v != last.get(off) and off not in (0x50F4,):
                        say(f"   +{off:#06x}: {last.get(off)} -> {v}")
            last = snap
            obj = jill_object(conn, flags_ptr)
            jsnap = jill_snapshot(conn, obj) if obj else None
            if jsnap and jlast:
                for off, v in jsnap.items():
                    if v != jlast.get(off):
                        say(f"   JILL+{off:#06x}: {jlast.get(off)} -> {v}")
            jlast = jsnap
            time.sleep(0.1)
    except ProcessError as exc:
        say(f"ERROR: {exc}")
        return 1
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
