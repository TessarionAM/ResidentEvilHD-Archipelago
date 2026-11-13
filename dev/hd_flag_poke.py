"""
Steam version - FLAG POKE (testing helper, 2026-11-12). WRITES one or two flag bits (memory only).

Tests which flag stops Chris's scene in the Lab B3 Cell from playing (for the Wrong Door trap).
The scene flag finder (09:05) left these candidates (bits that turned on with the scene and
didn't change when walking in again without it):
   1 = +0x245 bit 4               (turned on 1 s after entering the Cell)
   2 = +0x18D bit 2 and +0x39D bit 2   (same bit in two places - probably a flag and its copy)

How to use:
  1. Reload your older save (from before the scene) WITHOUT saving the run where you saw it.
  2. Teleport to the Cell Entrance (Tools\\run_hd_door_teleport.bat, F10, as before).
  3. Run Tools\\run_hd_flag_poke.bat, type 1 (try candidate 1 first), press F9 in the game.
  4. Teleport into the Cell (F10). Did the scene play? Tell Claude.
  5. If it played: reload the older save again and repeat with 2.
Nothing else is written. Output: hd_flag_poke_output.txt.
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
OUTPUT = HERE / "hd_flag_poke_output.txt"
VK_F9 = 0x78
CANDIDATES = {
    "1": [(0x245, 4)],
    "2": [(0x18D, 2), (0x39D, 2)],
}


def say(text):
    line = f"{time.strftime('%H:%M:%S')} {text}"
    print(line, flush=True)
    with OUTPUT.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def main() -> int:
    with OUTPUT.open("a", encoding="utf-8") as f:
        f.write(f"=== Flag poke {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    print(__doc__)
    choice = (sys.argv[1] if len(sys.argv) > 1 else input("Which candidate (1 or 2)? ")).strip()
    if choice not in CANDIDATES:
        print("Type 1 or 2.")
        return 1
    bits = CANDIDATES[choice]
    try:
        conn = ProcessConnection("bhd.exe", writable=True)
        if not conn.connect():
            say("bhd.exe is not running.")
            return 1
        build = hv.find_build(sha256_of(conn.exe_path))
        if build is None or build.key not in hv.FLAGS_POINTER:
            say("This tool only knows the Sept 2026 Steam build.")
            return 1
        ptr = hv.FLAGS_POINTER[build.key] - hv.DEFAULT_IMAGE_BASE + conn.module_base
        say(f"Candidate {choice}: " + ", ".join(f"+{o:#x} bit {b}" for o, b in bits) + ". Press F9 in the game to set it.")
        was = False
        while True:
            down = key_held(VK_F9)
            if down and not was:
                flags = struct.unpack("<I", conn.read_bytes(ptr, 4))[0]
                if not flags:
                    say("No game loaded yet.")
                else:
                    stage, r = struct.unpack("<ii", conn.read_bytes(flags + hv.CURRENT_ROOM_OFFSET, 8))
                    for off, bit in bits:
                        old = conn.read_bytes(flags + off, 1)[0]
                        conn.write_bytes(flags + off, bytes([old | (1 << bit)]))
                        say(f"  +{off:#x} bit {bit}: was {(old >> bit) & 1}, now 1  (room {stage * 0x100 + r:#x})")
                    say("Set. Now teleport into the Cell and see whether Chris's scene plays. You can close this window.")
            was = down
            time.sleep(0.1)
    except ProcessError as exc:
        say(f"ERROR: {exc}")
        return 1
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
