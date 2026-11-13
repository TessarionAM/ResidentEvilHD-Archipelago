"""
Door randomiser, the in-game part (2026-11-13). The seed's layout (slot data "door_shuffle":
{"mode", "targets": {"<door id>@<room hex>": [<door id>, "<room hex>"]}}, door_shuffle.py) says
where each side of each door leads. In the room Jill is in, every door record is pointed at its
target the moment the room's door list is up:
  * the door animation table entry for "this room -> the door's normal room" first (a door whose
    pair has no entry crashes the game - Wrong Door test v3/v6), then
  * the record: +0x30 arrival x/y/z, +0x40 stage, +0x41 room, +0x42 camera cut, +0x48 angle.
    The lock (+0x43 / +0x44) is never touched: locks stay on their physical doors.
Arrival = the target door's spot in the target room (ARRIVALS, the side you'd normally come in by).
This is the method the door shuffle lab proved for doors, double doors, ladders and lifts (lab runs
2026-11-12/13).

The table entries are put back a moment after Jill has arrived somewhere else (the game uses them
during the transition). Door records belong to one room and are rebuilt by the game, so they need
no putting back - except when the Wrong Door Trap or a Key Map shortcut wants the room: then this
gives the doors back (release) and waits until they're done.

Used doors are remembered (discovered) so the Key Map can say where a door leads once you've been
through it.
"""
import logging
import struct
import time
from typing import Callable, Dict, List, Optional, Tuple

from . import wrong_door as _wd
from .door_data import DOOR_PAIRS
from .wrong_door import WrongDoor, arrival

log = logging.getLogger("RE1HDClient")
PATCH_DELAY = 0.3      # seconds after a room change before its doors are changed (its door list is up)


def door_id(a: int, b: int) -> str:
    lo, hi = sorted((a, b))
    return f"{lo:x}-{hi:x}"


def end_key(room: int, dest: int) -> str:
    """The layout key of the door side in `room` that normally leads to `dest`."""
    return f"{door_id(room, dest)}@{room:x}"


class DoorShuffler(WrongDoor):
    """Shares the Wrong Door Trap's memory scan; its own state (saved for restarts)."""

    def __init__(self, layout: Optional[dict] = None, state: Optional[dict] = None,
                 save: Callable[[], None] = lambda: None, scanner: Optional[WrongDoor] = None):
        super().__init__(state, save)
        self.scanner = scanner
        self.targets: Dict[str, List] = dict((layout or {}).get("targets", {}))
        self.s.setdefault("info", [])
        self.s.setdefault("old_info", [])
        self.s.setdefault("discovered", {})      # end key -> [target room number] once used
        self.recs: Dict[int, Tuple[int, Dict[int, bytes]]] = {}   # record -> (target, original bytes)
        self.room: Optional[int] = None
        self.room_changed_at = 0.0
        self.leaving: Dict[int, str] = {}        # target room -> end key, for the room Jill is in

    @property
    def on(self) -> bool:
        return bool(self.targets)

    def _game(self, conn, pid) -> int:
        if self.scanner is not None:
            return self.scanner._game(conn, pid)
        return super()._game(conn, pid)

    def _entries(self, conn, pid):
        if self.scanner is not None:
            return self.scanner._entries(conn, pid)
        return super()._entries(conn, pid)

    # ------------------------------------------------------------ public
    def targets_from(self, room: int) -> set:
        """Rooms the shuffled doors of `room` lead to (for the door list check)."""
        if not hasattr(self, "_from"):
            self._from: Dict[int, set] = {}
            for k, t in self.targets.items():
                self._from.setdefault(int(k.split("@")[1], 16), set()).add(int(t[1], 16))
        return self._from.get(room, set())

    def target_of(self, room: int, dest: int) -> Optional[Tuple[int, int]]:
        """(target room, came-from room) for the door in `room` that normally leads to `dest`."""
        t = self.targets.get(end_key(room, dest))
        if not t:
            return None
        did, troom = t[0], int(t[1], 16)
        lo, hi = (int(x, 16) for x in did.split("-"))
        return troom, (hi if troom == lo else lo)

    def update(self, conn, flags: int, room: Optional[int], pid, busy: bool = False):
        """Every tick while Jill is in this seed's game. busy = the Wrong Door Trap or a shortcut
        has the room: give its doors back and keep out of the way."""
        if not self.on or room is None:
            return
        now = time.time()
        if room != self.room:
            prev = self.room
            if prev is not None and room in self.leaving:
                key = self.leaving[room]
                if key not in self.s["discovered"]:
                    self.s["discovered"][key] = room
                    log.info("Door randomiser: the %s door from %#x leads to %#x.", key, prev, room)
            self.room, self.room_changed_at = room, now
            self.recs, self.leaving = {}, {}
            self.s["old_info"] += self.s["info"]          # still needed for the trip that just happened
            self.s["info"] = []
            self._save()
        if self.s["old_info"] and now - self.room_changed_at >= _wd.SETTLE:
            self._restore(conn, pid, "old_info")
            self._save()
        if busy:
            if self.recs or self.s["info"]:
                self.release(conn, pid)
            return
        if now - self.room_changed_at >= PATCH_DELAY:
            self._patch_room(conn, pid, room)

    def release(self, conn, pid):
        """Put the room's doors back as the game made them (records and table entries)."""
        for rec, (_target, orig) in self.recs.items():
            try:
                if struct.unpack("<I", conn.read_bytes(rec, 4))[0] != _wd.DOOR_VTABLE:
                    continue
                for off, data in orig.items():
                    conn.write_bytes(rec + off, data)
            except Exception:
                pass
        self.recs, self.leaving = {}, {}
        self._restore(conn, pid, "info")
        self._save()

    def cleanup_after_restart(self, conn, flags: int, pid, room: Optional[int] = None):
        """Table entries an earlier client session changed: put them back."""
        if self.s.get("info") or self.s.get("old_info"):
            log.info("Door randomiser: putting back the door table entries an earlier session changed.")
            self._restore(conn, pid, "info", any_pid=False)
            self._restore(conn, pid, "old_info", any_pid=False)
            self._save()

    # ------------------------------------------------------------ steps
    def _restore(self, conn, pid, which: str, any_pid: bool = True):
        saved = self.s.get("info")
        self.s["info"] = self.s.get(which, [])
        self._put_back_info(conn, pid, any_pid)
        left = self.s["info"]
        self.s["info"] = saved if which != "info" else left
        if which != "info":
            self.s[which] = left

    def _patch_room(self, conn, pid, room: int):
        game = self._game(conn, pid)
        if not game:
            return
        live = self._live(conn, game)
        real = set(DOOR_PAIRS.get(room, ()))
        if not live:
            return
        # the list must be this room's: a door we haven't changed must lead to one of its rooms
        if not all(rec in self.recs or dest in real for rec, dest in live):
            return
        for rec, dest in live:
            done = self.recs.get(rec)
            if done is not None and dest == done[0]:
                continue                       # already ours
            t = self.target_of(room, dest)
            if t is None:
                continue                       # this door isn't shuffled
            troom, came_from = t
            arr = arrival(troom, came_from)
            if arr is None:
                log.warning("Door randomiser: no arrival spot for %#x (from %#x) - door left as it is.",
                            troom, came_from)
                continue
            if not self._patch_info(conn, pid, room, dest, troom):
                log.warning("Door randomiser: no door table entry %#x -> %#x - door left as it is.", room, dest)
                continue
            orig = {0x30: conn.read_bytes(rec + 0x30, 12), 0x40: conn.read_bytes(rec + 0x40, 3),
                    0x48: conn.read_bytes(rec + 0x48, 4)}
            x, y, z, ang, cut = arr
            conn.write_bytes(rec + 0x30, struct.pack("<fff", x, y, z))
            conn.write_bytes(rec + 0x40, bytes([troom >> 8, troom & 0xFF, cut & 0xFF]))
            conn.write_bytes(rec + 0x48, struct.pack("<f", ang))
            self.recs[rec] = (troom, orig)
            self.leaving.setdefault(troom, end_key(room, dest))
            self._save()
