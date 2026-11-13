"""
Steam version - DOOR SKIP (no BhdTool needed) + BhdTool check.

Leave this window open while you play. Every time the game starts it:
  1. says whether BhdTool is really running (and why not, if it can tell), then
  2. turns Door Skip on, using the same code patches as BhdTool v1.6 (credit: Eleval, GPL-3.0).
The patches only exist in the game's memory; nothing on disk is changed.
Press Ctrl+C or close the window to stop (door skip stays on until the game closes).
"""
import sys
import time

from client import hd_versions as hv
from client.door_skip import DoorSkipError, bhdtool_report, set_door_skip, supported
from client.pc_process import ProcessConnection, ProcessError
from hd_inventory import sha256_of


def main() -> int:
    print(__doc__)
    conn = ProcessConnection("bhd.exe", writable=True)
    announced_wait = False
    while True:
        try:
            if not conn.connect():
                if not announced_wait:
                    print("Waiting for the game (bhd.exe)...")
                    announced_wait = True
                time.sleep(2)
                continue
            announced_wait = False
            build = hv.find_build(sha256_of(conn.exe_path))
            if build is None or not supported(build.key):
                print("This game version isn't supported for door skip.")
                return 1
            time.sleep(5)            # let the game finish starting (and BhdTool hook in, if it will)
            for line in bhdtool_report(conn, build.key):
                print("  " + line)
            n = set_door_skip(conn, build.key, True)
            print("Door skip is ON." + (f" ({n} patches written)" if n else " (it already was)"))
            while conn.is_connected():
                time.sleep(2)
            print("Game closed.")
        except DoorSkipError as exc:
            print(f"Door skip NOT turned on: {exc}")
            while conn.is_connected():
                time.sleep(2)
        except ProcessError as exc:
            print(f"Lost the game: {exc}")
            time.sleep(2)
        except KeyboardInterrupt:
            return 0


if __name__ == "__main__":
    sys.exit(main())
