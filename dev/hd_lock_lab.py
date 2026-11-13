"""
Steam version - LOCK LAB (testing helper for the door lock randomiser, 2026-11-12).
WRITES door locks and inventory slots (memory only; nothing is written to the game files).

Type commands in THIS window (Alt-Tab), play in the game. Rules you set are re-applied every
0.1 s whenever you're in that room, so they survive the game rebuilding the room's doors.

Commands
  list                     doors of the room Jill is in: number, where it leads, key type, flag
  key N TYPE               door N (this side) needs TYPE, with a NEW unlock flag nobody uses
  key N TYPE keepflag      ... but keep the door's own unlock flag
  both N TYPE              lock BOTH sides of door N with TYPE and one new shared flag
                           (the far side is applied when you enter that room)
  split N TYPE_A TYPE_B    this side TYPE_A, far side TYPE_B, SEPARATE new flags (TessarionAM's
                           "Helmet on side A, Sword on side B" test)
  onesided N               this side locked (22), far side opens it (21), one new shared flag
  open N                   door N (this side) not locked (key type 0)
  rules                    show every rule; clear = remove all rules (the game resets on re-entry)
  give ITEM QTY            put ITEM into the first empty inventory slot with quantity QTY
  qty ITEM QTY             set the quantity of ITEM in the inventory
  inv                      show the inventory
  flags                    which door unlock flags (0-255) are on
  quit

TYPE / ITEM names: lockpick sword armor shield helmet 001 003 power master control gallery
  (TYPE also: none, 21 = opens-from-this-side, 22 = locked-from-this-side, or any number)

The tests (design doc, section 8):
  T1 give shield 3 (or qty armor 9): use it on its door; does the quantity drop by 1? at 0 discarded?
  T2 both N armor on an OPEN door: locked message? opens with the key? still open after save+reload?
  T3 key N helmet on a Sword door        T4 onesided N on an open door
  T5 open N on a vanilla locked door     T6 key N lockpick on a key door / key N armor on a lock pick door
  T7 split N helmet sword: open side A with the Helmet Key - is side B still locked (needs Sword)?
Output: hd_lock_lab_output.txt.
"""
import struct
import sys
import threading
import time

import hd_wrong_door_test as wd
from client import hd_versions as hv
from client.pc_process import ProcessConnection, ProcessError
from hd_inventory import inventory_struct_address, is_32bit_process, sha256_of

wd.OUTPUT = wd.HERE / "hd_lock_lab_output.txt"
say, name = wd.say, wd.name
TYPES = {"none": 0, "lockpick": 1, "sword": 3, "armor": 4, "shield": 5, "helmet": 6, "001": 7, "003": 8,
         "power": 9, "master": 10, "closet": 11, "emblem": 12, "control": 13, "gallery": 20,
         "21": 21, "22": 22}
ITEMS = {"lockpick": 43, "sword": 45, "armor": 46, "shield": 47, "helmet": 48, "001": 49, "003": 50,
         "power": 54, "master": 55, "control": 110, "gallery": 30}
TYPE_NAME = {v: k for k, v in TYPES.items()}
UNLOCK_FLAGS = 0x31C                    # door unlock flags: bit n of flags + 0x31C (n = 0-255)


class Lab:
    def __init__(self, conn, ptr, build, ptr_size):
        self.conn, self.ptr, self.build, self.ptr_size = conn, ptr, build, ptr_size
        self.game = None
        self.rules = {}                 # (room, dest) -> (key type, flag or None = keep)
        self.room = None
        self.lock = threading.Lock()
        self.used_flags = set()

    def flags(self) -> int:
        return struct.unpack("<I", self.conn.read_bytes(self.ptr, 4))[0]

    def current_room(self):
        f = self.flags()
        if not f:
            return None
        stage, r = struct.unpack("<ii", self.conn.read_bytes(f + hv.CURRENT_ROOM_OFFSET, 8))
        return stage * 0x100 + r if 1 <= stage <= 6 and 0 <= r < 0x40 else None

    def doors(self):
        if not self.game:
            say("Finding the game's door list (once, a few seconds)...")
            self.game = wd.find_game(self.conn)
        return wd.live_records(self.conn, self.game) if self.game else []

    def free_flag(self) -> int:
        table = self.conn.read_bytes(self.flags() + UNLOCK_FLAGS, 32)
        for n in range(254, 50, -1):            # 255 is the Wrong Door trap's; 1-50 are the game's doors
            if not table[n // 8] >> (n % 8) & 1 and n not in self.used_flags:
                self.used_flags.add(n)
                return n
        raise RuntimeError("no free unlock flag")

    def apply(self):
        """Write the rules for the room Jill is in (called every 0.1 s)."""
        room = self.current_room()
        if room != self.room:
            self.room = room
            if room is not None:
                say(f"Room: {name(room)}")
        if room is None or not self.rules or not self.game:
            return
        with self.lock:
            for rec, dest in wd.live_records(self.conn, self.game):
                rule = self.rules.get((room, dest))
                if rule is None:
                    continue
                key, flag = rule
                cur = self.conn.read_bytes(rec + 0x43, 5)
                want_key = (cur[0] & 0x80) | key if key else 0
                want = bytes([want_key]) + (struct.pack("<i", flag) if flag is not None else cur[1:])
                if cur != want:
                    self.conn.write_bytes(rec + 0x44, want[1:])
                    self.conn.write_bytes(rec + 0x43, want[:1])

    # ------------------------------------------------------------ commands
    def cmd_list(self):
        room = self.current_room()
        if room is None:
            say("No game loaded.")
            return []
        recs = self.doors()
        say(f"{name(room)}: {len(recs)} door(s)")
        table = self.conn.read_bytes(self.flags() + UNLOCK_FLAGS, 32)
        out = []
        for i, (rec, dest) in enumerate(recs, 1):
            raw = self.conn.read_bytes(rec + 0x43, 5)
            key, flag = raw[0], struct.unpack("<i", raw[1:])[0]
            opened = 0 <= flag < 256 and table[flag // 8] >> (flag % 8) & 1
            t = key & 0x7F
            say(f"  {i}: -> {name(dest)}   key type {t} ({TYPE_NAME.get(t, '?')}){' +high bit' if key & 0x80 else ''}"
                f"   flag {flag}{' (opened)' if opened else ''}")
            out.append((rec, dest))
        return out

    def pick(self, n):
        recs = self.doors()
        room = self.current_room()
        i = int(n) - 1
        if not (0 <= i < len(recs)):
            raise ValueError(f"no door {n} here (type list)")
        return room, recs[i][1]

    def rule(self, room, dest, key, flag):
        with self.lock:
            self.rules[(room, dest)] = (key, flag)
        say(f"  rule: {name(room)} -> {name(dest)}: key type {key} ({TYPE_NAME.get(key, '?')}), "
            f"flag {flag if flag is not None else 'kept'}")

    def give(self, item, qty, set_only=False):
        inv = inventory_struct_address(self.conn, self.build, self.ptr_size)
        if not inv:
            say("No game loaded.")
            return
        base = inv + hv.INVENTORY_SLOTS_OFFSET
        slots = [struct.unpack("<ii", self.conn.read_bytes(base + i * 8, 8)) for i in range(hv.INVENTORY_SLOT_COUNT)]
        for i, (iid, q) in enumerate(slots):
            if iid == item:
                self.conn.write_bytes(base + i * 8, struct.pack("<ii", item, qty))
                say(f"  slot {i + 1}: item {item} quantity {q} -> {qty}")
                return
        if set_only:
            say("  that item isn't in the inventory.")
            return
        for i, (iid, q) in enumerate(slots):
            if iid == 0:
                self.conn.write_bytes(base + i * 8, struct.pack("<ii", item, qty))
                say(f"  slot {i + 1}: item {item} x{qty} added")
                return
        say("  inventory full.")

    def inv(self):
        inv = inventory_struct_address(self.conn, self.build, self.ptr_size)
        base = inv + hv.INVENTORY_SLOTS_OFFSET
        for i in range(hv.INVENTORY_SLOT_COUNT):
            say(f"  slot {i + 1}: {struct.unpack('<ii', self.conn.read_bytes(base + i * 8, 8))}")

    def run(self, line: str):
        p = line.split()
        if not p:
            return
        c = p[0].lower()
        if c == "list":
            self.cmd_list()
        elif c in ("key", "open", "onesided", "both", "split"):
            room, dest = self.pick(p[1])
            if c == "open":
                self.rule(room, dest, 0, None)
            elif c == "key":
                t = TYPES[p[2].lower()] if not p[2].isdigit() else int(p[2])
                keep = len(p) > 3 and p[3].lower() == "keepflag"
                self.rule(room, dest, t, None if keep else self.free_flag())
            elif c == "both":
                t = TYPES[p[2].lower()] if not p[2].isdigit() else int(p[2])
                f = self.free_flag()
                self.rule(room, dest, t, f)
                self.rule(dest, room, t, f)
            elif c == "split":
                ta = TYPES[p[2].lower()] if not p[2].isdigit() else int(p[2])
                tb = TYPES[p[3].lower()] if not p[3].isdigit() else int(p[3])
                self.rule(room, dest, ta, self.free_flag())
                self.rule(dest, room, tb, self.free_flag())
            else:
                f = self.free_flag()
                self.rule(room, dest, 22, f)
                self.rule(dest, room, 21, f)
        elif c == "rules":
            for (r, d), (k, f) in self.rules.items():
                say(f"  {name(r)} -> {name(d)}: key type {k}, flag {f if f is not None else 'kept'}")
        elif c == "clear":
            self.rules.clear()
            say("  rules cleared (doors go back to normal next time you enter a room).")
        elif c in ("give", "qty"):
            self.give(ITEMS[p[1].lower()], int(p[2]), set_only=c == "qty")
        elif c == "inv":
            self.inv()
        elif c == "flags":
            table = self.conn.read_bytes(self.flags() + UNLOCK_FLAGS, 32)
            on = [n for n in range(256) if table[n // 8] >> (n % 8) & 1]
            say(f"  unlock flags on: {on}")
        else:
            say("  unknown command (see the list at the top).")


def main() -> int:
    wd.OUTPUT.write_text(f"=== Lock lab {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n", encoding="utf-8")
    print(__doc__)
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
        lab = Lab(conn, ptr, build, 4 if is_32bit_process(conn) else 8)
        stop = threading.Event()

        def watch():
            while not stop.is_set():
                try:
                    lab.apply()
                except Exception as exc:          # loading screen etc.
                    pass
                time.sleep(0.1)
        threading.Thread(target=watch, daemon=True).start()
        while True:
            try:
                line = input("lock lab> ").strip()
            except EOFError:
                break
            if line.lower() in ("quit", "exit"):
                break
            with open(wd.OUTPUT, "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%H:%M:%S')} > {line}\n")
            try:
                lab.run(line)
            except (ValueError, KeyError, IndexError) as exc:
                say(f"  ? {exc}")
            except ProcessError as exc:
                say(f"  game error: {exc}")
        stop.set()
        return 0
    except ProcessError as exc:
        say(f"ERROR: {exc}")
        return 1
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
