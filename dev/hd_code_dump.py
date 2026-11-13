"""
Steam version - CODE DUMP (READ-ONLY). Saves a copy of the running game's own
program memory (bhd.exe as loaded, 'module') to hd_code_dump.bin so Claude can
read the game's code offline: e.g. the instruction BhdTool's "Infinite Health"
cheat disables (0x00572242 in this build) shows where Jill's health is kept.

It only READS. Takes a few seconds. Run with run_hd_code_dump.bat while the game
is running (in-game or at the title screen; either is fine).

Output: hd_code_dump.bin (raw memory) + hd_code_dump.json (base address, size,
build, which 4 KB pages could not be read).
"""
import json
import sys
from pathlib import Path

from client import hd_versions as hv
from client.pc_process import ProcessConnection, ProcessError
from hd_inventory import sha256_of

HERE = Path(__file__).resolve().parent
OUT_BIN = HERE / "hd_code_dump.bin"
OUT_JSON = HERE / "hd_code_dump.json"
PAGE = 0x1000


def dump(conn, base: int, size: int):
    data = bytearray(size)
    unreadable = []
    for off in range(0, size, PAGE):
        n = min(PAGE, size - off)
        try:
            data[off:off + n] = conn.read_bytes(base + off, n)
        except ProcessError:
            unreadable.append(off)
    return bytes(data), unreadable


def main() -> int:
    conn = ProcessConnection("bhd.exe")          # read-only
    if not conn.connect():
        print("bhd.exe is not running. Start the game first.")
        return 1
    build = hv.find_build(sha256_of(conn.exe_path))
    print(f"Game: {build.description if build else 'UNKNOWN build'}")
    print(f"Module base 0x{conn.module_base:08X}, size 0x{conn.module_size:X}. Reading...")
    data, unreadable = dump(conn, conn.module_base, conn.module_size)
    OUT_BIN.write_bytes(data)
    OUT_JSON.write_text(json.dumps({
        "module_base": conn.module_base, "module_size": conn.module_size,
        "build": build.key if build else None, "unreadable_pages": unreadable}, indent=1))
    print(f"Saved {len(data):,} bytes to {OUT_BIN.name} ({len(unreadable)} unreadable pages).")
    print("Done. You can keep playing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
