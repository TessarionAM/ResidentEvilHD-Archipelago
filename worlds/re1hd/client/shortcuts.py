"""
Key Map shortcuts (TessarionAM, 2026-11-13; every typewriter room since 2026-11-14): buttons that take
Jill to a save room. Each one unlocks once she has been in that room (the game's own "room visited"
flag), and the whole feature is a YAML option (key_map_shortcuts).

How: the method the Wrong Door Trap and the door shuffle lab proved in the game. Pressing a button
"arms" the room Jill is in: every real door there now leads to the shortcut's room (the door
animation table entry first, then the door record). She goes through any door and arrives there;
everything is put back once she has arrived. A shortcut can't fire the moment the button is
pressed: (2026-11-15) the room jump (client/room_jump.py, proven by the random start room) now does
that instantly; this door way is only the fallback if the jump can't be set up.

The memory scan (game object + door animation table) is shared with the Wrong Door Trap, and the
two never run at the same time. State is saved, so if the client stops while a shortcut is armed,
the door table is put back on the next start.
"""
import logging
import time
from typing import Callable, Optional

from . import wrong_door as _wd
from .wrong_door import WrongDoor, arrival

log = logging.getLogger("RE1HDClient")

# name -> (room number, arrive at the door from this room).
# 2026-11-14 (TessarionAM): one shortcut per typewriter room, replacing Main Hall / Garden Shed /
# Lab Entrance. The rooms are the game's own 11 save rooms (autosave.SAVE_ROOMS: the only rooms
# 0x490B90 gives a save name); each arrives at a door with a known arrival spot (door_data.ARRIVALS).
SHORTCUTS = {
    "Mansion Drug Room": (0x100, 0x101),        # from the West Wing Inner Stairway
    "Dining Room": (0x105, 0x106),              # from the Main Hall
    "East Wing Storeroom": (0x118, 0x207),      # from the East Wing Stairway
    "Cabin": (0x314, 0x313),                    # from the Forest Pathway
    "Residence Storeroom": (0x403, 0x400),      # from the Residence Entry Corridor
    "Room 003": (0x40A, 0x408),                 # from the Gallery
    "Mining Area": (0x307, 0x302),              # from the Falls Area
    # 2026-11-15: from the Winding Underground Passage - that door's spot was checked in play (0 units,
    # twice); Barry's lift (from the Generator Room) sets Jill down elsewhere (497 units away)
    "Garbage Compactor Room": (0x316, 0x317),
    "Altar Stairway Passage": (0x31A, 0x106),   # from the Main Hall
    "Lab Item Box Room": (0x502, 0x500),        # from the Lab Entrance
    "Lounge Room": (0x50E, 0x50C),              # the Lab's typewriter room, from the Lab Elevator Entry
}
ORDER = tuple(SHORTCUTS)
# Short button labels for the Key Map (the full name is used everywhere else)
LABELS = {"Mansion Drug Room": "Drug Room", "East Wing Storeroom": "E. Storeroom",
          "Residence Storeroom": "Res. Storeroom", "Garbage Compactor Room": "Compactor",
          "Altar Stairway Passage": "Altar Stairs", "Lab Item Box Room": "Lab Box Room"}


class Shortcut(WrongDoor):
    """Same door helpers as the Wrong Door Trap; its own small state machine."""

    def __init__(self, state: Optional[dict] = None, save: Callable[[], None] = lambda: None,
                 scanner: Optional[WrongDoor] = None):
        super().__init__(state, save)
        self.scanner = scanner          # the Wrong Door Trap's scan (game object + door table)

    # the scan is shared: never scan twice
    def _game(self, conn, pid) -> int:
        if self.scanner is not None:
            return self.scanner._game(conn, pid)
        return super()._game(conn, pid)

    def _entries(self, conn, pid):
        if self.scanner is not None:
            return self.scanner._entries(conn, pid)
        return super()._entries(conn, pid)

    @property
    def target_name(self) -> Optional[str]:
        return self.s.get("name") if self.s.get("phase") else None

    def start(self, name: str, home: int) -> bool:
        room, _from = SHORTCUTS[name]
        if home == room or arrival(room, _from) is None:
            return False
        self.s = {"phase": "armed", "name": name, "target": room, "home": home, "info": []}
        log.info("Shortcut armed: the next door from %#x leads to the %s.", home, name)
        self._save()
        return True

    def cancel(self, conn, pid) -> None:
        # the doors first (they'd lead to the shortcut's room with no door table entry for it -
        # TessarionAM's log 2026-11-13 16:48:15), then the door table
        self._put_back_records(conn)
        if self.s.get("info"):
            self._put_back_info(conn, pid)
        self.s = {}
        self._save()

    def update(self, conn, flags: int, room: Optional[int], pid, *_ignored):
        s = self.s
        if not s or room is None:
            return
        now = time.time()
        if s.get("room_seen") is None:
            s["room_seen"], self.room_changed_at = room, 0.0
        if room != s["room_seen"]:
            s["room_seen"], self.room_changed_at = room, now
            if s.get("phase") == "armed":
                s["restore_due"] = True
                if room == s["target"]:
                    s["phase"] = None
                    self.notices.append((f"Shortcut: {s['name']}.", "info"))
                    log.info("Shortcut used: Jill is in the %s.", s["name"])
                else:
                    # a door the client hadn't changed yet (or a death / load): stay armed here
                    s["home"] = room
            self._save()
            return
        if now - self.room_changed_at < _wd.SETTLE:
            return
        if s.get("restore_due"):
            self._put_back_info(conn, pid)
            s["restore_due"] = False
            if s.get("phase") is None:
                self.s = {}
            self._save()
            return
        if s.get("phase") == "armed" and room == s["home"]:
            if s.get("name") not in SHORTCUTS:           # a shortcut an older version had armed
                self.cancel(conn, pid)
                return
            _room, came_from = SHORTCUTS[s["name"]]
            self._point_doors(conn, pid, room, s["target"], arrival(s["target"], came_from))

    def cleanup_after_restart(self, conn, flags: int, pid, room: Optional[int] = None):
        if self.s:
            log.info("Shortcut: putting back the doors an earlier session changed.")
            self._put_back_info(conn, pid, any_pid=False)
            self.s = {}
            self._save()
