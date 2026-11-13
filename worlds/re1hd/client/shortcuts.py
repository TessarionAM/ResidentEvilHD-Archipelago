"""
Key Map shortcuts (TessarionAM, 2026-11-13): buttons that take Jill to the Main Hall, the Garden Shed or
the Lab Entrance. Each one unlocks once she has been in that room (the game's own "room visited"
flag), and the whole feature is a YAML option (key_map_shortcuts).

How: the method the Wrong Door Trap and the door shuffle lab proved in the game. Pressing a button
"arms" the room Jill is in: every real door there now leads to the shortcut's room (the door
animation table entry first, then the door record). She goes through any door and arrives there;
everything is put back once she has arrived. A shortcut can't fire the moment the button is
pressed: an instant warp with no door has never been tested in the game, so it isn't used.

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

# name -> (room number, arrive at the door from this room)
SHORTCUTS = {
    "Main Hall": (0x106, 0x105),        # the Dining Room door
    "Garden Shed": (0x11B, 0x11A),      # the Roofed Passage door
    "Lab Entrance": (0x500, 0x305),     # from the Fountain
}
ORDER = ("Main Hall", "Garden Shed", "Lab Entrance")


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
            _room, came_from = SHORTCUTS[s["name"]]
            self._point_doors(conn, pid, room, s["target"], arrival(s["target"], came_from))

    def cleanup_after_restart(self, conn, flags: int, pid, room: Optional[int] = None):
        if self.s:
            log.info("Shortcut: putting back the doors an earlier session changed.")
            self._put_back_info(conn, pid, any_pid=False)
            self.s = {}
            self._save()
