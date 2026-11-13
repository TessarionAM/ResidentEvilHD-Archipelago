"""
Steam version - CONTROLLER BUTTON FINDER (READ-ONLY). The client can't see a PlayStation pad
through Steam Input (Steam only gives the game itself the virtual Xbox pad), so we read the
button state the GAME keeps instead. This finds where it is.

In the game (Jill standing still is fine):
  - HOLD L1 on the controller and, while holding it, tap Home on the keyboard.     (do 3 times)
    Keep holding L1 for a moment after letting go of Home.
  - With NO controller button held, press Page Up.                                 (do 3 times)
  - Press End when done. Then send Claude hd_button_finder_output.txt.
Hold L1 with a different stick/position each time if you like - only L1 should stay the same.
"""
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
OUTPUT = HERE / "hd_button_finder_output.txt"
DATA_RVA, DATA_SIZE = 0x8B6000, 0xAC000      # bhd.exe .data section (Sept 2026 build)
INPUT_MANAGER = 0x00D599E4    # pointer to the game's input manager (pads at +0xBA0 / bindings +0xCFC)
INPUT_SIZE = 0x1000
KEYS = {0x24: "HELD", 0x21: "RELEASED", 0x23: "DONE"}


def say(text):
    line = f"{time.strftime('%H:%M:%S')} {text}"
    print(line)
    with OUTPUT.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def candidates(held, released, start=DATA_RVA + 0x400000):
    """Bits that are 1 in every 'held' snapshot and 0 in every 'released' one (and the reverse)."""
    out = []
    n = len(held[0]) // 4
    for i in range(n):
        h = [struct.unpack_from("<I", s, 4 * i)[0] for s in held]
        r = [struct.unpack_from("<I", s, 4 * i)[0] for s in released]
        on = 0xFFFFFFFF
        off = 0xFFFFFFFF
        for v in h:
            on &= v
            off &= ~v
        for v in r:
            on &= ~v
            off &= v
        if on or off:
            out.append((start + 4 * i, on, off & 0xFFFFFFFF, h, r))
    return out


def main() -> int:
    OUTPUT.write_text(f"=== Button finder {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n", encoding="utf-8")
    try:
        conn = ProcessConnection("bhd.exe")
        if not conn.connect():
            say("bhd.exe is not running. Start the game and load a save first.")
            return 1
        build = hv.find_build(sha256_of(conn.exe_path))
        if build is None or build.key not in hv.FLAGS_POINTER:
            say("This tool only knows the Sept 2026 Steam build.")
            return 1
        say("READ-ONLY. Hold L1 + press Home (x3). Nothing held + Page Up (x3). End = finish.")
        hd_health_watch.KEYS.clear()
        hd_health_watch.KEYS.update(KEYS)
        keys = Keys()
        base = conn.module_base + DATA_RVA
        held, released = [], []
        iheld, ireleased = [], []
        mgr_ptr = INPUT_MANAGER - hv.DEFAULT_IMAGE_BASE + conn.module_base
        while True:
            for label in keys.poll():
                if label == "DONE":
                    if len(held) < 2 or len(released) < 2:
                        say("Need at least 2 of each first.")
                        continue
                    found = candidates(iheld, ireleased, start=0)
                    say(f"INPUT MANAGER (offsets from [0xD599E4]): {len(found)} candidate(s):")
                    for addr, on, off, h, r in found[:200]:
                        say(f"  +{addr:#06x} set-when-held={on:#010x} clear-when-held={off:#010x} "
                            f"held={[hex(v) for v in h]} released={[hex(v) for v in r]}")
                    found = candidates(held, released)
                    say(f"{len(found)} candidate(s) ({len(held)} held, {len(released)} released):")
                    for addr, on, off, h, r in found[:200]:
                        say(f"  {addr:#010x} set-when-held={on:#010x} clear-when-held={off:#010x} "
                            f"held={[hex(v) for v in h]} released={[hex(v) for v in r]}")
                    say("Done - the results are in hd_button_finder_output.txt.")
                    return 0
                # wait for the keyboard key to be let go (so the game's keyboard state is the
                # same in every snapshot), keep L1 held meanwhile
                t0 = time.time()
                while keys.user32 and any(keys.user32.GetAsyncKeyState(vk) & 0x8000 for vk in KEYS) \
                        and time.time() - t0 < 3:
                    time.sleep(0.02)
                time.sleep(0.2)
                snap = conn.read_bytes(base, DATA_SIZE)
                mgr = struct.unpack("<I", conn.read_bytes(mgr_ptr, 4))[0]
                isnap = conn.read_bytes(mgr, INPUT_SIZE) if mgr else bytes(INPUT_SIZE)
                (held if label == "HELD" else released).append(snap)
                (iheld if label == "HELD" else ireleased).append(isnap)
                say(f">>> {label} #{len(held) if label == 'HELD' else len(released)}")
                beep()
            time.sleep(0.03)
    except ProcessError as exc:
        say(f"Game closed or unreadable: {exc}")
        return 1
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
