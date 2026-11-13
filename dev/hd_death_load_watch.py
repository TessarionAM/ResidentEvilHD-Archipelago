"""
Steam version - DEATH & LOAD WATCH (READ-ONLY). For "autoload the autosave when Jill dies".
Records which of the game's global values change while you: die -> go through the screens after
death -> load a save -> are back in the game. Claude uses it to find the game's own "screen /
game state" values and the moment a load starts, so the client can do the same steps itself.

Keys (press each at the moment it happens):
  Home      = Jill just died (the death animation starts)
  Page Up   = a new screen appeared (YOU DIED / Game Over / title / continue / load menu ...)
  Page Down = you picked the save to load (loading starts)
  End       = you're back in control of Jill
Close the window (or Ctrl+C) when done, then send Claude hd_death_load_watch_output.txt and
hd_death_load_watch_events.jsonl.
"""
import json
import struct
import sys
import time
from pathlib import Path

from client import hd_versions as hv
from client.pc_process import ProcessConnection, ProcessError
from hd_event_recorder import beep
import hd_health_watch
from hd_health_watch import Keys
from hd_inventory import sha256_of

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "hd_death_load_watch_output.txt"
EVENTS = HERE / "hd_death_load_watch_events.jsonl"
DATA_RVA, DATA_SIZE = 0x8B6000, 0xAC000      # bhd.exe .data section (Sept 2026 build)
NOISY = 12          # a value that changed more often than this is a counter/timer: stop logging it
KEYS = {0x24: "Jill died", 0x21: "new screen", 0x22: "picked the save / loading", 0x23: "back in control"}


def say(text):
    line = f"{time.strftime('%H:%M:%S')} {text}"
    print(line)
    with OUTPUT.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def record(**event):
    event["t"] = round(time.time(), 2)
    with EVENTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def main() -> int:
    OUTPUT.write_text(f"=== Death & load watch {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n", encoding="utf-8")
    EVENTS.write_text("", encoding="utf-8")
    try:
        conn = ProcessConnection("bhd.exe")            # read-only
        if not conn.connect():
            say("bhd.exe is not running. Start the game and load a save first.")
            return 1
        build = hv.find_build(sha256_of(conn.exe_path))
        if build is None or build.key not in hv.FLAGS_POINTER:
            say("This watch only knows the Sept 2026 Steam build.")
            return 1
        say("READ-ONLY. Home = died, Page Up = new screen, Page Down = loading, End = back in control.")
        hd_health_watch.KEYS.clear()
        hd_health_watch.KEYS.update(KEYS)
        keys = Keys()
        base = conn.module_base + DATA_RVA
        last = conn.read_bytes(base, DATA_SIZE)
        counts = {}
        say(f"Watching {DATA_SIZE:,} bytes of game globals. Go ahead.")
        while True:
            for label in keys.poll():
                say(f">>> {label}")
                record(label=label)
                beep()
            now = conn.read_bytes(base, DATA_SIZE)
            changes = []
            for chunk in range(0, DATA_SIZE, 256):
                if now[chunk:chunk + 256] == last[chunk:chunk + 256]:
                    continue
                for off in range(chunk, min(chunk + 256, DATA_SIZE), 4):
                    if now[off:off + 4] != last[off:off + 4]:
                        n = counts.get(off, 0) + 1
                        counts[off] = n
                        if n <= NOISY:
                            old, new = struct.unpack_from("<I", last, off)[0], struct.unpack_from("<I", now, off)[0]
                            changes.append([DATA_RVA + 0x400000 + off, old, new])
            if changes:
                record(changes=changes)
            last = now
            time.sleep(0.1)
    except ProcessError as exc:
        say(f"Game closed or unreadable: {exc}")
        return 0
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
