"""
Steam version - DOOR TELEPORT (testing helper, 2026-11-12). WRITES to the game (memory only).

Press F10 in any room: every door you can open in that room now leads to the target room
(default: Laboratory B3 - Cell Entrance, 50b). Walk through one and you arrive there.
It's a one-way trip; the doors work normally again once you've arrived.

Uses the method that worked in the Wrong Door test v7: the door animation table is patched
first, then the live door list (Game+0x1B0). Locks are never touched.

F10 (not F9) so it can run at the same time as the scene flag finder, which uses F9.
Locked doors stay locked - but the target can be any room, so e.g. from the Cell Entrance you can
use its unlocked door (to the Pass Code Corridor) to reach the Cell (512) without the key.

Usage: Tools\\run_hd_door_teleport.bat. It asks for the room number(s); just press Enter for
"50b,512,512": the first F10 goes to the Cell Entrance, the next two to the Cell.
"""
import struct
import sys
import time

import hd_wrong_door_test as wd
from client import hd_versions as hv
from client.pc_process import ProcessConnection, ProcessError
from client.window_mode import key_held
from hd_inventory import sha256_of

wd.OUTPUT = wd.HERE / "hd_door_teleport_output.txt"
say, name = wd.say, wd.name
DEFAULT_TARGETS = (0x50B, 0x512, 0x512)  # Cell Entrance, then the Cell twice (scene, then control walk)


def main() -> int:
    wd.OUTPUT.write_text(f"=== Door teleport {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n", encoding="utf-8")
    print(__doc__)
    answer = (sys.argv[1] if len(sys.argv) > 1 else
              input("Room number(s) to go to, in order, separated by commas [50b,512,512 = Cell Entrance, then the Cell twice]: ")).strip()
    try:
        targets = [int(x, 16) for x in answer.replace(" ", "").split(",") if x] if answer else list(DEFAULT_TARGETS)
    except ValueError:
        print("That isn't a room number (e.g. 50b).")
        return 1
    for t in targets:
        if f"{t:x}" not in wd.NAMES:
            print(f"Unknown room {t:x}.")
            return 1
    target = targets.pop(0)
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
        say(f"Target: {name(target)}. Stand in any room and press F10, then wait for 'Walk through any door'.")
        game, room, armed, saved, was = None, None, False, [], False
        while True:
            flags = struct.unpack("<I", conn.read_bytes(ptr, 4))[0]
            now_room = None
            if flags:
                stage, r = struct.unpack("<ii", conn.read_bytes(flags + hv.CURRENT_ROOM_OFFSET, 8))
                if 1 <= stage <= 6 and 0 <= r < 0x40:
                    now_room = stage * 0x100 + r
            if now_room is not None and now_room != room:
                room = now_room
                say(f"Room: {name(room)}")
                if armed:
                    time.sleep(2.0)
                    wd.put_back(conn, saved)
                    saved, armed = [], False
                    if room == target:
                        say("  You're there!")
                        if targets:
                            target = targets.pop(0)
                            say(f"  Next target: {name(target)} - press F10 when you're ready.")
                    else:
                        say("  Arrived somewhere else - press F10 to try again.")
            down = key_held(wd.VK_F10)
            if down and not was and room is not None and not armed:
                if room == target:
                    say("You're already there.")
                else:
                    if game is None:
                        say("F10: finding the game's door list (once, a few seconds - stand still)...")
                        game = wd.find_game(conn)
                    if game is None:
                        say("  Game object NOT found - send me hd_door_teleport_output.txt.")
                    else:
                        recs = wd.live_records(conn, game)
                        say(f"  {len(recs)} doors here. Patching the door animations (stand still)...")
                        saved = wd.patch_info(conn, room, recs, target)
                        if not saved:
                            say("  no door animation entries found - not changing the doors.")
                        else:
                            wd.redirect(conn, recs, target, wd.arrival(target))
                            armed = True
                            say(f"  Walk through any door that isn't locked -> {name(target)}.")
            was = down
            time.sleep(0.1)
    except ProcessError as exc:
        say(f"ERROR: {exc}")
        return 1
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
