"""
Steam version - DEATH & RELOAD MEMORY TEST (READ-ONLY, 2026-11-14).

What changes in the game's memory when Jill dies and a save is loaded? The client keeps door data,
locks, shortcuts and the Wrong Door trap in step with the game, so it must know exactly what the
game throws away and rebuilds. It also watches the door-unlock flags all the time, to catch the
Graveyard gate (flag 39) locking itself again (TessarionAM, 2026-11-14 01:23).

Recorded automatically:
  * the flags structure's address (does it move on death / load?), the room, Jill's health;
  * every change in the door-unlock flags (flags+0x31C, 256 flags), with the room it happened in;
  * the Game object (owner of the room's door list): which ones exist, after each room change.
Keys (in the game; a beep confirms):
  Home      = take snapshot A (e.g. just before dying / loading)
  End       = take snapshot B and list everything that differs from A (story/pickup/kill flags,
              unlock flags, inventory pointer, Game object)
  Page Down = list this room's doors: where each leads, its lock type and unlock flag (+ is it set)
Suggested run (spare save, client closed or open - both are useful, say which):
  1. In a room with a door you unlocked (e.g. the Graveyard gate), press Page Down.
  2. Home, then die. Load the save. End.  Page Down again in the same room.
  3. Home, load a DIFFERENT save. End. Page Down.
  4. If the Graveyard gate ever locks itself again: press Page Down there and send the log at once.
Output: hd_death_memory_test_output.txt (+ .jsonl with every detail).
"""
import json
import struct
import sys
import time
from pathlib import Path

import hd_wrong_door_test as wd
from client import hd_versions as hv
from client.pc_process import ProcessConnection, ProcessError
from client.window_mode import key_held
from hd_event_recorder import beep
from hd_health_watch import find_jill
from hd_inventory import sha256_of

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "hd_death_memory_test_output.txt"
EVENTS = HERE / "hd_death_memory_test_events.jsonl"
UNLOCK_FLAGS, UNLOCK_BYTES = 0x31C, 32
STORY = (0x1F0, 0x360)          # story, kill, pickup, map, file flags (flags-relative)
NAMED_FLAGS = {39: "Graveyard gate (Large Gallery)", 16: "East Wing doorknob door"}
VK_HOME, VK_END, VK_PGDN = 0x24, 0x23, 0x22
name = wd.name


def say(text):
    line = f"{time.strftime('%H:%M:%S')} {text}"
    print(line, flush=True)
    with OUTPUT.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def record(**event):
    event["t"] = round(time.time(), 2)
    with EVENTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def flag_label(n: int) -> str:
    return f"flag {n}" + (f" ({NAMED_FLAGS[n]})" if n in NAMED_FLAGS else "")


def unlock_diff(old: bytes, new: bytes):
    out = []
    for n in range(UNLOCK_BYTES * 8):
        a, b = old[n // 8] >> (n % 8) & 1, new[n // 8] >> (n % 8) & 1
        if a != b:
            out.append((n, b))
    return out


def byte_diff(old: bytes, new: bytes, base: int):
    return [(base + i, o, n) for i, (o, n) in enumerate(zip(old, new)) if o != n]


class Probe:
    def __init__(self, conn):
        self.conn = conn
        self.flags_ptr = hv.FLAGS_POINTER["hd_6699874012183562949"] - hv.DEFAULT_IMAGE_BASE + conn.module_base

    def flags(self) -> int:
        return struct.unpack("<I", self.conn.read_bytes(self.flags_ptr, 4))[0]

    def room(self, flags: int):
        if not flags:
            return None
        stage, r = struct.unpack("<ii", self.conn.read_bytes(flags + hv.CURRENT_ROOM_OFFSET, 8))
        return stage * 0x100 + r if 1 <= stage <= 6 and 0 <= r < 0x40 else None

    def health(self):
        jill, _why = find_jill(self.conn, self.conn.module_base)
        if not jill:
            return None
        return struct.unpack("<i", self.conn.read_bytes(jill + hv.JILL_HEALTH_OFFSET, 4))[0]

    def snapshot(self) -> dict:
        flags = self.flags()
        snap = {"flags": flags, "room": self.room(flags), "health": self.health(),
                "games": sorted(self.games())}
        if flags:
            snap["unlock"] = self.conn.read_bytes(flags + UNLOCK_FLAGS, UNLOCK_BYTES).hex()
            snap["story"] = self.conn.read_bytes(flags + STORY[0], STORY[1] - STORY[0]).hex()
        return snap

    def games(self):
        hits = wd.search(self.conn, [struct.pack("<I", wd.GAME_VTABLE)])[struct.pack("<I", wd.GAME_VTABLE)]
        return [a for a in hits if self._game_like(a)]

    def _game_like(self, a: int) -> bool:
        try:
            count = struct.unpack("<I", self.conn.read_bytes(a + wd.DOOR_LIST + wd.LIST_COUNT, 4))[0]
            arr = struct.unpack("<I", self.conn.read_bytes(a + wd.DOOR_LIST + wd.LIST_ARRAY, 4))[0]
        except ProcessError:
            return False
        return count <= 64 and (count == 0 or arr > 0x10000)

    def doors(self, flags: int):
        table = self.conn.read_bytes(flags + UNLOCK_FLAGS, UNLOCK_BYTES)
        out = []
        for game in self.games():
            try:
                records = wd.live_records(self.conn, game)
            except ProcessError:
                continue                 # a freed Game object (the case this test is about)
            for rec, dest in records:
                raw = self.conn.read_bytes(rec, 0x4C)
                lock, unlock = raw[0x43], struct.unpack_from("<i", raw, 0x44)[0]
                is_set = 0 <= unlock < 256 and table[unlock // 8] >> (unlock % 8) & 1
                out.append((game, rec, dest, lock, unlock, bool(is_set)))
        return out


def compare(a: dict, b: dict):
    say("=== Snapshot A -> B ===")
    for key in ("flags", "room", "health"):
        va, vb = a.get(key), b.get(key)
        shown = (lambda v: name(v) if key == "room" and v else (f"{v:#x}" if key == "flags" and v else v))
        say(f"  {key}: {shown(va)} -> {shown(vb)}" + ("" if va == vb else "   CHANGED"))
    say(f"  Game objects: {[hex(g) for g in a['games']]} -> {[hex(g) for g in b['games']]}"
        + ("" if a["games"] == b["games"] else "   CHANGED (old door records are gone)"))
    if "unlock" in a and "unlock" in b:
        d = unlock_diff(bytes.fromhex(a["unlock"]), bytes.fromhex(b["unlock"]))
        say(f"  unlock flags changed: {len(d)}")
        for n, v in d:
            say(f"    {flag_label(n)}: {'ON' if v else 'OFF'}")
        sd = byte_diff(bytes.fromhex(a["story"]), bytes.fromhex(b["story"]), STORY[0])
        say(f"  story/pickup/kill bytes changed: {len(sd)}")
        for off, o, n in sd[:80]:
            say(f"    +{off:#05x}: {o:08b} -> {n:08b}")
        if len(sd) > 80:
            say(f"    ... {len(sd) - 80} more in the .jsonl")
        record(kind="compare", unlock=d, story=sd)


def main() -> int:
    with OUTPUT.open("a", encoding="utf-8") as f:   # every run is kept (2026-11-15)
        f.write("\n" + f"=== Death & reload memory test {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    print(__doc__)
    try:
        conn = ProcessConnection("bhd.exe")             # read-only
        if not conn.connect():
            say("bhd.exe is not running. Start the game and load a save first.")
            return 1
        build = hv.find_build(sha256_of(conn.exe_path))
        if build is None or build.key.replace("_steamless", "") != "hd_6699874012183562949":
            say("This test only knows the Sept 2026 Steam build.")
            return 1
        probe = Probe(conn)
        say("READ-ONLY. Home = snapshot A, End = snapshot B + compare, Page Down = this room's doors.")
        last_flags, last_room, last_unlock, last_hp = None, None, None, None
        snap_a, prev = None, (False, False, False)
        while True:
            flags = probe.flags()
            if flags != last_flags:
                say(f"Flags structure at {flags:#x}" + ("" if last_flags is None else f" (was {last_flags:#x})"))
                record(kind="flags_ptr", value=flags)
                last_flags, last_unlock = flags, None
            room = probe.room(flags)
            if room != last_room:
                say(f"Room: {name(room) if room else '- (loading / menu)'}")
                record(kind="room", room=room)
                last_room = room
            if flags:
                unlock = conn.read_bytes(flags + UNLOCK_FLAGS, UNLOCK_BYTES)
                if last_unlock is not None and unlock != last_unlock:
                    for n, v in unlock_diff(last_unlock, unlock):
                        say(f"  UNLOCK {flag_label(n)} -> {'ON' if v else 'OFF'} in {name(room) if room else '-'}")
                        record(kind="unlock", flag=n, on=v, room=room)
                last_unlock = unlock
            hp = probe.health()
            if hp != last_hp and (hp is None or last_hp is None or hp <= 0 or last_hp <= 0):
                say(f"Health: {last_hp} -> {hp}" + ("   (DIED)" if hp is not None and hp <= 0 else ""))
                record(kind="health", value=hp)
            last_hp = hp
            keys = (key_held(VK_HOME), key_held(VK_END), key_held(VK_PGDN))
            if keys[0] and not prev[0]:
                beep()
                say("Home: snapshot A (scanning for the Game object, a few seconds)...")
                snap_a = probe.snapshot()
                record(kind="snapshot", which="A", **snap_a)
                say(f"  A taken in {name(snap_a['room']) if snap_a['room'] else '-'}.")
            if keys[1] and not prev[1]:
                beep()
                if snap_a is None:
                    say("End: take snapshot A first (Home).")
                else:
                    say("End: snapshot B (scanning)...")
                    snap_b = probe.snapshot()
                    record(kind="snapshot", which="B", **snap_b)
                    compare(snap_a, snap_b)
            if keys[2] and not prev[2] and flags:
                beep()
                say(f"Page Down: doors in {name(room) if room else '-'} (scanning)...")
                doors = probe.doors(flags)
                for game, rec, dest, lock, unlock, is_set in doors:
                    say(f"  game {game:#x} record {rec:#x} -> {name(dest)}: lock type {lock & 0x7F}"
                        f"{' (+0x80)' if lock & 0x80 else ''}, {flag_label(unlock)} {'SET' if is_set else 'not set'}")
                record(kind="doors", room=room, doors=doors)
                if not doors:
                    say("  no door records found (loading? try again in a moment).")
            prev = keys
            time.sleep(0.1)
    except ProcessError as exc:
        say(f"Game closed or unreadable: {exc}")
        return 0
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
