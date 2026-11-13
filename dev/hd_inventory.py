"""
Steam version (Resident Evil HD Remaster) - Milestone 1 + 2:
find the running game, identify the exact build, and show Jill's inventory live.

Run with run_hd_inventory.bat while the game is running and you're in-game.
Everything printed is also saved to hd_inventory_output.txt for Claude.
It only READS memory.
"""

import ctypes
import hashlib
import logging
import struct
import sys
import time
from pathlib import Path

from client import hd_versions as hv
from client.hd_items import item_name
from client.pc_process import ProcessConnection, ProcessError, kernel32

OUTPUT = Path("hd_inventory_output.txt")


def say(*parts):
    line = " ".join(str(p) for p in parts)
    print(line)
    with OUTPUT.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def is_32bit_process(conn: ProcessConnection) -> bool:
    wow64 = ctypes.c_int(0)
    if not kernel32.IsWow64Process(conn.handle, ctypes.byref(wow64)):
        raise ProcessError("Could not tell whether the game is 32- or 64-bit")
    return bool(wow64.value)


def inventory_struct_address(conn: ProcessConnection, build: hv.HDBuild, ptr_size: int) -> int:
    """Address of the inventory structure (0 on the title screen, before a game is loaded)."""
    ptr_addr = build.inventory_pointer - hv.DEFAULT_IMAGE_BASE + conn.module_base
    return int.from_bytes(conn.read_bytes(ptr_addr, ptr_size), "little")


def _slots(data: bytes):
    return [struct.unpack_from("<ii", data, i * 8) for i in range(len(data) // 8)]


def read_inventory(conn: ProcessConnection, build: hv.HDBuild, ptr_size: int):
    """Returns a list of (item_id, quantity) for the 8 slots, or None if no inventory yet."""
    inv = inventory_struct_address(conn, build, ptr_size)
    if inv == 0:
        return None
    return _slots(conn.read_bytes(inv + hv.INVENTORY_SLOTS_OFFSET,
                                  hv.INVENTORY_SLOT_COUNT * hv.INVENTORY_SLOT_SIZE))


def read_item_box(conn: ProcessConnection, build: hv.HDBuild, ptr_size: int):
    """Returns (hidden_slots, box_entries) or None if no game is loaded.
    hidden_slots: the 2 entries between inventory and box (Jill's Lock Pick lives in the first).
    box_entries: (slot number 1-256 as shown in-game, item_id, quantity) for every non-empty slot."""
    inv = inventory_struct_address(conn, build, ptr_size)
    if inv == 0:
        return None
    hidden = _slots(conn.read_bytes(inv + hv.HIDDEN_SLOTS_OFFSET, hv.HIDDEN_SLOT_COUNT * hv.INVENTORY_SLOT_SIZE))
    data = conn.read_bytes(inv + hv.ITEM_BOX_OFFSET, hv.ITEM_BOX_SLOTS * hv.INVENTORY_SLOT_SIZE)
    box = [(i + 1, iid, qty) for i, (iid, qty) in enumerate(_slots(data)) if (iid, qty) != (0, 0)]
    return hidden, box


def show(slots):
    for i, (item_id, qty) in enumerate(slots):
        if item_id == 0:
            say(f"  Slot {i}: (empty)")
        else:
            say(f"  Slot {i}: {item_name(item_id):<32} x{qty:<4} (id {item_id})")


def main() -> int:
    watch = "--watch" in sys.argv
    logging.basicConfig(level=logging.DEBUG if "--debug" in sys.argv else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    OUTPUT.write_text(f"=== HD inventory run {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n", encoding="utf-8")

    try:
        conn = ProcessConnection("bhd.exe")
        if not conn.connect():
            say("bhd.exe is not running. Start Resident Evil HD Remaster first.")
            return 1
        say(f"Game file   : {conn.exe_path}")
        say(f"Load address: 0x{conn.module_base:08X}"
            + ("" if conn.module_base == hv.DEFAULT_IMAGE_BASE else "  (not the default 0x00400000 - corrected)"))
        bits32 = is_32bit_process(conn)
        say(f"Process     : {'32-bit' if bits32 else '64-bit'}")
        ptr_size = 4 if bits32 else 8

        digest = sha256_of(conn.exe_path)
        say(f"SHA-256     : {digest}")
        build = hv.find_build(digest)
        if build is None:
            say("UNKNOWN BUILD - this bhd.exe isn't in our list. Please report it with this output.")
            return 1
        say(f"Detected    : {build.description}")
        say("")

        show_box = "--box" in sys.argv
        last, last_box = "unset", "unset"
        while True:
            try:
                slots = read_inventory(conn, build, ptr_size)
                box = read_item_box(conn, build, ptr_size) if show_box else None
            except ProcessError as exc:
                say(f"ERROR reading inventory: {exc}")
                if not watch or not conn.is_connected():
                    return 1
                slots, box = "error", "error"
            if slots != last:
                say(time.strftime("%H:%M:%S"), "Inventory:")
                if slots is None:
                    say("  (no inventory yet - load a save or start a new game)")
                elif slots != "error":
                    show(slots)
                say("")
                last = slots
            if show_box and box != last_box:
                say(time.strftime("%H:%M:%S"), "Item box (non-empty slots, numbered 1-256 like in-game):")
                if box is None:
                    say("  (no game loaded)")
                elif box != "error":
                    hidden, entries = box
                    for n, (iid, qty) in enumerate(hidden, 1):
                        if (iid, qty) != (0, 0):
                            say(f"  Hidden slot {n}: {item_name(iid):<26} x{qty:<4} (id {iid})")
                    say(f"  {len(entries)} of {hv.ITEM_BOX_SLOTS} box slots in use")
                    for n, iid, qty in entries:
                        say(f"  Box {n:>3}: {item_name(iid):<32} x{qty:<4} (id {iid})")
                say("")
                last_box = box
            if not watch:
                return 0
            time.sleep(0.5)
    except ProcessError as exc:
        say(f"ERROR: {exc}")
        return 1
    except KeyboardInterrupt:
        say("Stopped.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
