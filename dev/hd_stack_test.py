"""
Steam version - STACK TEST: find the biggest stack the game allows for each ammo type.

While the game is running (keys work while the game window has focus):
    Ctrl+1  Handgun Bullets (15)     Ctrl+5  Incendiary Rounds (6)
    Ctrl+2  Shotgun Shells (6)       Ctrl+6  Magnum Rounds (6)
    Ctrl+3  Grenade Rounds (6)       Ctrl+7  Ink Ribbon (3)
    Ctrl+4  Acid Rounds (6)
    Ctrl+0  250 Handgun Bullets in ONE slot (what does the game do with an oversized stack?)

Each press puts ONE vanilla-pickup-sized stack in a NEW item box slot (never added onto an
existing stack), exactly like picking the item up in the world. To test: spawn several, take
them into the inventory one at a time and see where the game stops combining them. The
number it stops at is that type's maximum. Write it in stack_test_results.txt or tell Claude.

Every spawn is logged to hd_stack_test_log.txt. Writes ONLY to empty item box slots.
"""
import sys
import time
from pathlib import Path

from client import hd_versions as hv
from client.hd_delivery import DeliveryError, Journal, deliver_to_box
from hd_inventory import inventory_struct_address, is_32bit_process, sha256_of
from client.pc_process import ProcessConnection, ProcessError

LOG = Path(__file__).with_name("hd_stack_test_log.txt")
JOURNAL = Path(__file__).with_name("hd_stack_test_journal.jsonl")
VK_CONTROL = 0x11
# number key (virtual-key code) -> (item id, quantity, name)
SPAWNS = {
    0x31: (17, 15, "Handgun Bullets"),
    0x32: (18, 6, "Shotgun Shells"),
    0x33: (16, 6, "Grenade Rounds"),
    0x34: (19, 6, "Acid Rounds"),
    0x35: (20, 6, "Incendiary Rounds"),
    0x36: (25, 6, "Magnum Rounds"),
    0x37: (68, 3, "Ink Ribbon"),
    0x30: (17, 250, "Handgun Bullets (oversized test)"),
}


def say(text):
    line = f"{time.strftime('%H:%M:%S')}  {text}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def pressed(user32, down: set):
    """Number keys just pressed while Ctrl is held."""
    out = []
    ctrl = bool(user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)
    for vk in SPAWNS:
        is_down = ctrl and bool(user32.GetAsyncKeyState(vk) & 0x8000)
        if is_down and vk not in down:
            out.append(vk)
        (down.add if is_down else down.discard)(vk)
    return out


def main() -> int:
    import ctypes
    user32 = ctypes.windll.user32
    try:
        conn = ProcessConnection("bhd.exe", writable=True)
        if not conn.connect():
            print("bhd.exe is not running. Start the game first.")
            return 1
        ptr = 4 if is_32bit_process(conn) else 8
        build = hv.find_build(sha256_of(conn.exe_path))
        if build is None:
            print("Unsupported game version.")
            return 1
        say(f"Stack test ready ({build.description}).")
        print(__doc__.split("Every spawn")[0])
        down = set()
        while True:
            for vk in pressed(user32, down):
                item, qty, name = SPAWNS[vk]
                inv = inventory_struct_address(conn, build, ptr)
                try:
                    d = deliver_to_box(conn, inv, item, qty, Journal(JOURNAL), reason="stack test")
                except DeliveryError as exc:
                    say(f"NOT given ({name}): {exc}")
                    continue
                say(f"+{qty} {name} in item box slot {d.slot_number}")
            time.sleep(0.05)
    except ProcessError as exc:
        print(f"Lost the game: {exc}")
        return 1
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
