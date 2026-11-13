"""
Steam version - EVENT RECORDER: one session (read-only apart from the F8 ammo helper) that captures what the
game changes when you kill enemies, defeat a boss, use a typewriter, read /
pick up a file, finish a puzzle or reach a story moment. Claude uses the log to
find where each of those is remembered, so they can become checks.

What it records (with timestamps):
  * the current room (named, from BhdTool's room list)
  * inventory gains / losses, dagger + battery counts, "just picked up" value
  * EVERY bit that changes in the flags structure, -0x1000..+0x1000
    (bits that keep flipping - timers, counters - are muted automatically)
  * big bursts (doors, cutscenes, loads) are summarised on screen but kept
    in full in the .jsonl file

Labels without leaving the game: press one key right after doing something
(a short beep confirms):
    Insert = enemy killed      Home = typewriter used     Page Up   = file / document
    Delete = puzzle solved     End  = story moment / boss Page Down = health change (hurt / poisoned / cured / died)
    F8     = put 6 shotgun shells in the ITEM BOX (testing helper; the ONLY write)
You can still type a note + Enter in this window. The window itself stays quiet
(rooms and labels only); every detail goes to the log files.

Output: hd_event_recorder_output.txt (readable) and
        hd_event_recorder_events.jsonl (everything, for Claude).
Run with run_hd_event_recorder.bat. Close the window to stop.
"""
import json
import struct
import sys
import threading
import time
from collections import deque
from pathlib import Path

from client import hd_versions as hv
from client.hd_delivery import DeliveryError, Journal, deliver_to_box
from client.hd_items import item_name
from client.hd_pickups import GUARDED_SLOTS, SLOT, parse_slots
from client.pc_process import ProcessConnection, ProcessError
from client.pickup_mapper import inventory_gains
from hd_inventory import inventory_struct_address, is_32bit_process, sha256_of

OUTPUT = Path("hd_event_recorder_output.txt")
EVENTS = Path("hd_event_recorder_events.jsonl")
NAMES = json.loads((Path(__file__).resolve().parent / "client" / "room_names.json").read_text(encoding="utf-8"))
SPAN = 0x1000             # flags structure window: -SPAN .. +SPAN
BURST = 40                # more changed bits than this in one poll = door / cutscene / load
NOISY_FLIPS = 4           # a bit that flips this often ...
NOISY_WINDOW = 3.0        # ... within this many seconds is muted (timer / counter)


def say(*parts, show=True):
    """Write to the log file; also show in the window only if show=True (keeps it readable)."""
    line = time.strftime("%H:%M:%S ") + " ".join(str(p) for p in parts)
    if show:
        print(line)
    with OUTPUT.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


# Hotkeys (Windows virtual-key codes) -> label. Read with GetAsyncKeyState, so they
AMMO_LABEL = "give 6 shotgun shells"   # F8: testing helper, puts ammo in the ITEM BOX
AMMO_ITEM, AMMO_QTY = 18, 6   # 6 = the size of a vanilla shell pickup (seen in the Graveyard)
AMMO_JOURNAL = Path(__file__).with_name("hd_event_recorder_ammo_journal.jsonl")
# work while the game window has focus. None of these keys are used by the game.
HOTKEYS = {0x2D: "enemy killed", 0x24: "typewriter used", 0x21: "file / document",
           0x2E: "puzzle solved", 0x23: "story moment / boss", 0x22: "health change (hurt / poisoned / cured / died)",
           0x77: AMMO_LABEL}


class Hotkeys:
    def __init__(self):
        self.down = set()
        try:
            import ctypes
            self.user32 = ctypes.windll.user32
        except (ImportError, AttributeError):
            self.user32 = None          # not on Windows (tests)

    def poll(self, state=None):
        """Labels for keys that were just pressed. `state` (vk -> bool) is for tests."""
        pressed = []
        for vk, label in HOTKEYS.items():
            if state is not None:
                is_down = state.get(vk, False)
            elif self.user32 is not None:
                is_down = bool(self.user32.GetAsyncKeyState(vk) & 0x8000)
            else:
                is_down = False
            if is_down and vk not in self.down:
                pressed.append(label)
            (self.down.add if is_down else self.down.discard)(vk)
        return pressed


def beep():
    try:
        import winsound
        winsound.Beep(880, 80)
    except (ImportError, RuntimeError):
        pass


def record(**event):
    event.setdefault("t", round(time.time(), 2))
    with EVENTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def room_label(number):
    if number is None:
        return "(loading)"
    return NAMES.get(f"{number:x}", f"unlisted room {number:#x}")


def bit_changes(old: bytes, new: bytes, start: int):
    """[(offset, bit, new value)] for every bit that differs."""
    out = []
    for i, (a, b) in enumerate(zip(old, new)):
        x = a ^ b
        while x:
            bit = (x & -x).bit_length() - 1
            out.append((start + i, bit, (b >> bit) & 1))
            x &= x - 1
    return out


class NoiseFilter:
    """Mutes bits that flip repeatedly in a short time (timers, counters, positions)."""

    def __init__(self, flips=NOISY_FLIPS, window=NOISY_WINDOW):
        self.flips, self.window = flips, window
        self.history = {}
        self.muted = set()

    def keep(self, changes, now):
        """Returns (kept changes, newly muted keys)."""
        kept, newly = [], []
        for off, bit, val in changes:
            key = (off, bit)
            if key in self.muted:
                continue
            h = self.history.setdefault(key, deque())
            h.append(now)
            while h and now - h[0] > self.window:
                h.popleft()
            if len(h) >= self.flips:
                self.muted.add(key)
                newly.append(key)
                continue
            kept.append((off, bit, val))
        return kept, newly


def label_reader():
    while True:
        try:
            text = input().strip()
        except EOFError:
            return
        if text:
            say(f">>> LABEL: {text}")
            record(event="label", text=text)


def give_ammo(conn, inv):
    """Testing helper: AMMO_QTY of AMMO_ITEM (now shotgun shells) into the first empty item-box slot (same tested
    code as AP deliveries). Logged as a 'cheat_ammo' event so the analysis never mistakes
    this ammo for a pickup."""
    try:
        d = deliver_to_box(conn, inv, AMMO_ITEM, AMMO_QTY, Journal(AMMO_JOURNAL), reason="F8 test ammo")
    except DeliveryError as exc:
        say(f"F8 ammo NOT given: {exc}")
        record(event="cheat_ammo_failed", why=str(exc))
        return
    say(f">>> +{AMMO_QTY} SHOTGUN SHELLS in item box slot {d.slot_number}")
    record(event="cheat_ammo", item=AMMO_ITEM, qty=AMMO_QTY, slot=d.slot_number)
    beep(); beep()


def main() -> int:
    OUTPUT.write_text(f"=== Event recorder {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n", encoding="utf-8")
    record(event="start")
    try:
        conn = ProcessConnection("bhd.exe", writable=True)   # writes ONLY for F8 ammo
        if not conn.connect():
            say("bhd.exe is not running.")
            return 1
        ptr = 4 if is_32bit_process(conn) else 8
        build = hv.find_build(sha256_of(conn.exe_path))
        if build is None or build.key not in hv.FLAGS_POINTER:
            say("Unsupported game version.")
            return 1
        flags_ptr = hv.FLAGS_POINTER[build.key] - hv.DEFAULT_IMAGE_BASE + conn.module_base
        say(f"Detected {build.description}. Recording (read-only except F8 ammo).")
        say("Press right after doing something:  Insert = enemy killed   Home = typewriter   "
            "Page Up = file")
        say("                                    Delete = puzzle   End = story / boss   Page Down = health change")
        say("F8 = put 6 shotgun shells in the ITEM BOX (testing helper)")
        say("(This window only shows rooms and labels; all details go to the log files.)")
        threading.Thread(target=label_reader, daemon=True).start()
        keys = Hotkeys()

        noise = NoiseFilter()
        last = {"zone": None, "slots": None, "def": None, "picked": None, "room": None}
        while True:
            now = time.time()
            inv = inventory_struct_address(conn, build, ptr)
            for label in keys.poll():
                if label == AMMO_LABEL:
                    give_ammo(conn, inv)
                    continue
                say(f">>> {label.upper()}")
                record(event="label", text=label, source="key")
                beep()
            flags = int.from_bytes(conn.read_bytes(flags_ptr, ptr), "little")
            if inv == 0 or flags == 0:
                if last["zone"] is not None:
                    say("(no game loaded - waiting)")
                    record(event="no_game")
                last = dict.fromkeys(last)
                time.sleep(0.5)
                continue

            stage, room = struct.unpack("<ii", conn.read_bytes(flags + hv.CURRENT_ROOM_OFFSET, 8))
            number = stage * 0x100 + room if 1 <= stage <= 6 and 0 <= room < 0x100 else None
            if number is not None and number != last["room"]:
                say(f"ROOM: {room_label(number)} ({number:#x})")
                record(event="room", room=number)
                last["room"] = number

            slots = parse_slots(conn.read_bytes(inv + hv.INVENTORY_SLOTS_OFFSET, GUARDED_SLOTS * SLOT.size))
            if last["slots"] is not None and slots != last["slots"]:
                gained = inventory_gains(last["slots"], slots)
                lost = inventory_gains(slots, last["slots"])
                if gained or lost:
                    say("ITEMS: " + ", ".join([f"+{n} {item_name(i)}" for i, n in gained.items()]
                                              + [f"-{n} {item_name(i)}" for i, n in lost.items()]), show=False)
                record(event="inventory", slots=slots)
            last["slots"] = slots

            counts = {iid: struct.unpack("<i", conn.read_bytes(inv + off, 4))[0]
                      for iid, off in hv.DEFENSE_COUNT_OFFSETS.items()}
            if last["def"] is not None and counts != last["def"]:
                say("DEFENSIVE: " + ", ".join(f"{item_name(i)} {last['def'][i]} -> {n}"
                                              for i, n in counts.items() if n != last["def"][i]), show=False)
                record(event="defense", counts=counts)
            last["def"] = counts

            picked = struct.unpack("<i", conn.read_bytes(inv + hv.LAST_PICKED_ITEM_OFFSET, 4))[0]
            if last["picked"] is not None and picked != last["picked"]:
                record(event="picked", value=picked)
                if picked > 0:
                    say(f"just picked up / looking at: {item_name(picked)} ({picked})", show=False)
            last["picked"] = picked

            zone = conn.read_bytes(flags - SPAN, 2 * SPAN)
            if last["zone"] is not None:
                changes = bit_changes(last["zone"], zone, -SPAN)
                if len(changes) > BURST:
                    say(f"(burst: {len(changes)} bits changed - door / cutscene / load; kept in the .jsonl)", show=False)
                    record(event="burst", room=number, bits=[[o, b, v] for o, b, v in changes])
                elif changes:
                    kept, newly = noise.keep(changes, now)
                    for o, b in newly:
                        record(event="muted", offset=o, bit=b)
                    if kept:
                        say("FLAGS: " + ", ".join(f"{o:+#x} bit {b} {'ON' if v else 'off'}" for o, b, v in kept),
                            show=False)
                        record(event="flags", room=number, bits=[[o, b, v] for o, b, v in kept])
            last["zone"] = zone
            time.sleep(0.1)
    except ProcessError as exc:
        say(f"ERROR: {exc}")
        return 1
    except KeyboardInterrupt:
        say("Stopped.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
