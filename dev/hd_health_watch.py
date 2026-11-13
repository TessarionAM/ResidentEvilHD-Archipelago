"""
Steam version - HEALTH WATCH (READ-ONLY). Finds Jill's character data and shows her
health live, and records every change inside her data so Claude can find the
poison flag (for the poison trap) and a clean "Jill died" signal (for Death Link).

How it finds Jill (worked out from the game's own code, see claude/health-and-death.md):
    manager = [bhd.exe+0x00CF2E84]
    index   = [manager+0x24] >> 16           (checked: below 0x40)
    entry   = manager + 0x8B0 + index * 24
    jill    = [entry]   if [entry+4] == [manager+0x20]
    health  = int32 at jill+0x13BC, max health = int32 at jill+0x13C0 (max is a guess)
None of that is trusted until you see the numbers behave in-game - that's this test.

Keys while playing (short beep confirms):
    Home    = I just got POISONED
    Page Up = poison just CURED (blue herb / serum)
    Page Down = anything else worth noting
Health changes (hurt, healed, died) are recorded automatically - no key needed.

Output: hd_health_watch_output.txt and hd_health_watch_events.jsonl. Close the window to stop.
"""
import json
import struct
import sys
import time
from pathlib import Path

from client import hd_versions as hv
from client.pc_process import ProcessConnection, ProcessError
from hd_event_recorder import NoiseFilter, bit_changes, beep
from hd_inventory import is_32bit_process, sha256_of

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "hd_health_watch_output.txt"
EVENTS = HERE / "hd_health_watch_events.jsonl"

CHARACTER_MANAGER_POINTER = 0x00CF2E84     # build 6699874012183562949 (from code at 0x48AE3B)
HANDLE_LO, HANDLE_HI = 0x20, 0x24
TABLE, ENTRY_SIZE, TABLE_SLOTS = 0x8B0, 24, 0x40
HEALTH, MAX_HEALTH = 0x13BC, 0x13C0
OBJECT_SPAN = 0x2000                        # bytes of Jill's data watched for changes

KEYS = {0x24: "POISONED", 0x21: "POISON CURED", 0x22: "note"}


def say(text, show=True):
    line = f"{time.strftime('%H:%M:%S')} {text}"
    if show:
        print(line, flush=True)
    with OUTPUT.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def record(**event):
    event.setdefault("t", round(time.time(), 2))
    with EVENTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def u32(conn, addr):
    return struct.unpack("<I", conn.read_bytes(addr, 4))[0]


def find_jill(conn, module_base):
    """(address of Jill's data or 0, explanation)."""
    mgr = u32(conn, CHARACTER_MANAGER_POINTER - hv.DEFAULT_IMAGE_BASE + module_base)
    if not mgr:
        return 0, "manager pointer is 0 (title screen / loading?)"
    lo, hi = u32(conn, mgr + HANDLE_LO), u32(conn, mgr + HANDLE_HI)
    index = (hi >> 16) & 0xFFFF
    if index >= TABLE_SLOTS:
        return 0, f"index {index:#x} out of range (manager {mgr:#x}, handle {lo:#x}/{hi:#x})"
    entry = mgr + TABLE + index * ENTRY_SIZE
    obj, check = u32(conn, entry), u32(conn, entry + 4)
    if not obj or check != lo:
        return 0, f"table entry doesn't match (obj {obj:#x}, check {check:#x} vs {lo:#x})"
    return obj, f"manager {mgr:#x}, index {index}, Jill's data at {obj:#x}"


class Keys:
    def __init__(self):
        self.down = set()
        try:
            import ctypes
            self.user32 = ctypes.windll.user32
        except (ImportError, AttributeError):
            self.user32 = None

    def poll(self):
        out = []
        for vk, label in KEYS.items():
            d = bool(self.user32 and self.user32.GetAsyncKeyState(vk) & 0x8000)
            if d and vk not in self.down:
                out.append(label)
            (self.down.add if d else self.down.discard)(vk)
        return out


def main() -> int:
    OUTPUT.write_text(f"=== Health watch {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n", encoding="utf-8")
    record(event="start")
    try:
        conn = ProcessConnection("bhd.exe")            # read-only
        if not conn.connect():
            say("bhd.exe is not running.")
            return 1
        build = hv.find_build(sha256_of(conn.exe_path))
        if build is None or build.key not in hv.FLAGS_POINTER:
            say("This finder only knows the Sept 2026 Steam build.")
            return 1
        if not is_32bit_process(conn):
            say("Unexpected 64-bit game process.")
            return 1
        say("READ-ONLY. Home = poisoned, Page Up = poison cured, Page Down = note. Health is automatic.")
        keys, noise = Keys(), NoiseFilter()
        last_obj, last_hp, last_data = None, None, None
        while True:
            now = time.time()
            for label in keys.poll():
                say(f">>> {label}")
                record(event="label", text=label)
                beep()
            try:
                obj, why = find_jill(conn, conn.module_base)
            except ProcessError as exc:
                if not conn.is_connected():
                    raise
                obj, why = 0, f"couldn't read the character table ({exc})"
            if obj != last_obj:
                say(f"Jill: {why}")
                record(event="jill", obj=obj, why=why)
                last_obj, last_hp, last_data = obj, None, None
            if not obj:
                time.sleep(0.5)
                continue
            try:
                hp, mx = struct.unpack("<ii", conn.read_bytes(obj + HEALTH, 8))
                data = conn.read_bytes(obj, OBJECT_SPAN)
            except ProcessError:
                if not conn.is_connected():
                    raise
                last_obj = None
                time.sleep(0.5)
                continue
            if (hp, mx) != last_hp:
                say(f"HEALTH {hp} / {mx}" + ("   <-- 0 or below: DEAD?" if hp <= 0 else ""))
                record(event="health", hp=hp, max=mx)
                last_hp = (hp, mx)
            if last_data is not None:
                changes = bit_changes(last_data, data, 0)
                if changes:
                    kept, _ = noise.keep(changes, now)
                    if kept:
                        record(event="bits", bits=[[o, b, v] for o, b, v in kept])
            last_data = data
            time.sleep(0.1)
    except ProcessError as exc:
        say(f"ERROR: {exc}")
        return 1
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
