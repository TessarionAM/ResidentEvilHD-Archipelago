"""
Steam version - BOSS WATCH (READ-ONLY, 2026-11-14). For the Boss Rush goal.

The full mapping run (2026-11-10) gave ONE sample of each boss's flags. This watch shows those
candidate bits live and logs every other story / kill bit that turns on, so a second play-through
confirms them (or finds the right ones). Two samples = confirmed.

Candidates (flags-relative; "kill" = the per-enemy kill table +0x26C..+0x2AF, "story" = story area):
  Crypt Crimson Head  kill +0x270.6   story +0x222.3 / +0x222.4 (crypt opened?)
  Plant 42            kill +0x270.3   story +0x223.6, +0x23C.0
  Yawn (Library)      kill +0x2A5.0   story +0x232.3
  Black Tiger         kill +0x2AD.0   story +0x236.1
  Neptune (Water Tank) kill +0x2AC.0  story +0x234.0-3   (TessarionAM: most likely Neptune - confirm)
  Lisa (Altar)        kill +0x272.0   story +0x23D.0 / +0x23D.2, +0x200.4 / +0x200.5
  Tyrant (Lab)        kill +0x2AE.1
Not found yet: the Heliport Tyrant (not part of Boss Rush).

Keys (in the game; a beep confirms):
  End       = a boss just died (or ran away / was skipped - type what happened in the window after)
  Page Down = something else worth noting (V-Jolt used, cutscene, Barry/Lisa outcome...)
You can also type a note + Enter in this window at any time.
Worth testing: kill each boss; also Plant 42 with the V-Jolt (does it set the kill bit?), skipping
Black Tiger, the Lisa fight with and without Barry, and the Heliport Tyrant with the Rocket Launcher.
Output: hd_boss_watch_output.txt.
"""
import struct
import sys
import threading
import time
from pathlib import Path

import hd_wrong_door_test as wd
from client import hd_versions as hv
from client.pc_process import ProcessConnection, ProcessError
from client.window_mode import key_held
from hd_event_recorder import beep
from hd_inventory import sha256_of

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "hd_boss_watch_output.txt"
WINDOW = (0x1F0, 0x360)
CANDIDATES = {
    (0x270, 6): "Crypt Crimson Head (kill)", (0x222, 3): "Crypt (story)", (0x222, 4): "Crypt (story)",
    (0x270, 3): "Plant 42 (kill)", (0x223, 6): "Plant 42 (story)", (0x23C, 0): "Plant 42 (story)",
    (0x2A5, 0): "Yawn (kill)", (0x232, 3): "Yawn (story)",
    (0x2AD, 0): "Black Tiger (kill)", (0x236, 1): "Black Tiger (story)",
    (0x2AC, 0): "Neptune (kill)", **{(0x234, b): "Neptune (story)" for b in range(4)},
    (0x272, 0): "Lisa (kill)", (0x23D, 0): "Lisa (story)", (0x23D, 2): "Lisa (story)",
    (0x200, 4): "Lisa (story)", (0x200, 5): "Lisa (story)",
    (0x2AE, 1): "Tyrant Lab (kill)",
}
KILL_TABLE = (0x26C, 0x2B0)
VK_END, VK_PGDN = 0x23, 0x22
name = wd.name


def say(text):
    line = f"{time.strftime('%H:%M:%S')} {text}"
    print(line, flush=True)
    with OUTPUT.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def turned_on(old: bytes, new: bytes, base: int):
    out = []
    for i, (o, n) in enumerate(zip(old, new)):
        if o != n:
            for bit in range(8):
                if (n >> bit & 1) and not (o >> bit & 1):
                    out.append((base + i, bit))
    return out


def describe(off: int, bit: int) -> str:
    where = "kill table" if KILL_TABLE[0] <= off < KILL_TABLE[1] else "flags"
    tag = CANDIDATES.get((off, bit))
    return f"+{off:#05x}.{bit} ({where})" + (f"  <-- candidate: {tag}" if tag else "")


def main() -> int:
    with OUTPUT.open("a", encoding="utf-8") as f:   # every run is kept (2026-11-15)
        f.write("\n" + f"=== Boss watch {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    print(__doc__)
    notes = []
    threading.Thread(target=lambda: [notes.append(line.strip()) for line in sys.stdin], daemon=True).start()
    try:
        conn = ProcessConnection("bhd.exe")             # read-only
        if not conn.connect():
            say("bhd.exe is not running. Start the game and load a save first.")
            return 1
        build = hv.find_build(sha256_of(conn.exe_path))
        if build is None or build.key.replace("_steamless", "") != "hd_6699874012183562949":
            say("This watch only knows the Sept 2026 Steam build.")
            return 1
        ptr = hv.FLAGS_POINTER["hd_6699874012183562949"] - hv.DEFAULT_IMAGE_BASE + conn.module_base
        last, room, last_flags, prev = None, None, None, (False, False)
        while True:
            flags = struct.unpack("<I", conn.read_bytes(ptr, 4))[0]
            while notes:
                say(f"NOTE: {notes.pop(0)}")
            if not flags:
                time.sleep(0.2)
                continue
            stage, r = struct.unpack("<ii", conn.read_bytes(flags + hv.CURRENT_ROOM_OFFSET, 8))
            now_room = stage * 0x100 + r if 1 <= stage <= 6 and 0 <= r < 0x40 else None
            if now_room != room:
                room = now_room
                say(f"Room: {name(room) if room else '-'}")
            data = conn.read_bytes(flags + WINDOW[0], WINDOW[1] - WINDOW[0])
            if last is None or flags != last_flags:
                on = [k for k in CANDIDATES if data[k[0] - WINDOW[0]] >> k[1] & 1]
                say(f"Save state: {len(on)} candidate bit(s) already on: "
                    + (", ".join(f'+{o:#05x}.{b} {CANDIDATES[(o, b)]}' for o, b in on) or "none"))
                if last is not None:
                    say("  (the flags moved: a save was loaded - comparing from here)")
            else:
                changes = turned_on(last, data, WINDOW[0])
                if 0 < len(changes) <= 24:              # more = a load or a big cutscene burst
                    for off, bit in changes:
                        say(f"  ON {describe(off, bit)}   in {name(room) if room else '-'}")
                elif changes:
                    say(f"  ({len(changes)} bits at once - load or cutscene; not listed)")
            last, last_flags = data, flags
            keys = (key_held(VK_END), key_held(VK_PGDN))
            if keys[0] and not prev[0]:
                beep()
                say(">>> BOSS (End) - type what happened + Enter")
            if keys[1] and not prev[1]:
                beep()
                say(">>> NOTE (Page Down) - type what happened + Enter")
            prev = keys
            time.sleep(0.1)
    except ProcessError as exc:
        say(f"Game closed or unreadable: {exc}")
        return 0
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
