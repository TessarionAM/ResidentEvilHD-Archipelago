"""
Wrong Door fun trap (2026-11-12). The next door Jill opens takes her somewhere far away; every
door there leads back to the room she left. See claude/wrong-door-trap-design.md and
claude/wrong-door-test-results.md.

How it works (the method that worked in the Wrong Door test v7, Main Hall -> Dark Corridor and
Main Hall -> Lab Cell):
  * The game's live door list: Game object (class "Game", vtable 0xC21854) + 0x1B0:
    +0xE0 = array of door record pointers, +0xD4 = count. Door records start with 0x00C23408:
    +0x30 x/y/z (arrival), +0x40 stage, +0x41 room, +0x42 camera cut, +0x43 LOCK (never touched),
    +0x48 angle (radians).
  * The door animation table door\\doorinfo has one entry per (from room -> to room). The game must
    never see a door whose pair has no entry (v3/v6 crashed), so the entry for
    "this room -> real destination" is pointed at the decoy FIRST, then the door record.
  * Everything is put back afterwards; the patched doorinfo entries are remembered (addresses +
    original bytes) so they can be put back even after a client restart.
Pickups in the decoy are hidden by setting their "picked up" flags before she arrives (the client
masks those flags so they are not sent as checks) and clearing them after she leaves. The decoy's
room-entry check is masked, and its "room visited" flag cleared afterwards if it was off.
The Lab Cell's Chris scene is skipped with flag +0x245 bit 4 (found 2026-11-12: scene flag
finder + flag poke test - with it set, the scene didn't play), cleared again afterwards.
"""
import logging
import math
import threading
import struct
import time
from typing import Callable, Dict, List, Optional, Set, Tuple

from .door_data import ARRIVALS, DOOR_PAIRS

log = logging.getLogger("RE1HDClient")

GAME_VTABLE = 0x00C21854
DOOR_VTABLE = 0x00C23408
DOOR_LIST, LIST_COUNT, LIST_ARRAY = 0x1B0, 0xD4, 0xE0
INFO_KEY = 0x1C                  # doorinfo entry: +0x1C src stage, +0x20 src room, +0x24 dest stage, +0x28 dest room
INFO_DEST = 0x24
CHRIS_SCENE = (0x245, 4)         # "Chris's scene in the Lab B3 Cell has been seen"
CELL = 0x512
CELL_LOCK_SECONDS = 15.0         # TessarionAM (2026-11-12): in the Cell the door stays locked first (5 s, then 15 s at 09:43)
# Lock byte +0x43 = KEY TYPE (& 0x7F); the game maps it to an item through the table at 0xC2FF20
# (1 Lockpick, 3 Sword, 4 Armor ... 13 Control Room Key, 20 Gallery Key). Types 14-19 and 22 map to
# item -1, which no inventory slot can hold, so such a door can never be opened with a key.
# 22 is what the real Graveyard -> Large Gallery door uses (types 1, 0x13 and 0x15 are special-
# cased in 0x4ECE20, so they're avoided). v0.8.6 first build used 0x80 = key type 0 = NOT locked
# (TessarionAM 09:35: "the door doesn't lock"); the high bit is something else.
LOCKED = 22
# The door's unlock flag (+0x44) is an index into the flags structure's "type 4" table:
# 0x4916A0(flags+0x1F8, 4, n) tests bit n of flags + 0x31C (256 bits, up to +0x33B). The lock uses
# the highest index that is OFF right now, so the door counts as not yet unlocked.
UNLOCK_FLAGS = 0x31C
SETTLE = 1.0                     # seconds after a room change before putting doorinfo back
CHUNK = 4 * 1024 * 1024
BACKGROUND = True                # scan in a thread (tests set False)
RESCAN_SECONDS = 30.0            # a scan that found nothing is tried again after this long
# 2026-11-13 (TessarionAM's log 16:58-17:02): after loading a save, no door was changed for 4 minutes -
# no Wrong Door Trap, no door randomiser. The client kept using the memory it found before the load.
# So the door list is now checked against the room Jill is in (watch_list) and the door table against
# the pair asked for (_patch_info); when either is out of date it is looked for again.
STALE_SECONDS = 1.5              # after SETTLE: how long a door list may stay wrong for the room
RELOOK_GAP = 20.0                # at least this long between two "look again"s (no rescan loop)

# Destination (TessarionAM, 2026-11-12 09:35): only the Lab B3 Cell. (The themed list and the "any safe
# room" version were dropped.)
THEMED = {CELL: "Wesker caught you!"}


def arrival(room: int, came_from: Optional[int] = None):
    """(x, y, z, angle radians, cut) for arriving in `room` through the door from `came_from`."""
    doors = ARRIVALS.get(room, [])
    pick = [d for d in doors if d[0] == came_from] or doors
    if not pick:
        return None
    _src, x, y, z, ang, cut = pick[0]
    return x, y, z, math.radians(ang), cut


def choose_decoy(home: int, themed: bool = True, rng=None, exclude: Set[int] = frozenset()) -> Optional[int]:
    """Always the Cell - except when Jill is already in it (then the trap waits)."""
    return CELL if home != CELL and CELL not in exclude and arrival(CELL) else None


class WrongDoor:
    """State machine. `state` is a plain dict (saved in the bridge's state file)."""

    def __init__(self, state: Optional[dict] = None, save: Callable[[], None] = lambda: None):
        self.s: dict = state or {}
        self._save = save
        self.game = 0
        self.game_pid = None
        self.info: Dict[Tuple[int, int], List[int]] = {}
        self.info_pid = None
        self.warm_thread: Optional[threading.Thread] = None
        self.warm_pid = None
        self.next_scan = 0.0
        self.notices: List[Tuple[str, str]] = []
        self.flags = 0
        self.room_changed_at = 0.0
        self.scanner: Optional["WrongDoor"] = None    # the object that owns the shared scan (None = self)
        self.stale_games: Set[int] = set()     # game objects whose door list stopped following the rooms
        self.room_hint: Optional[int] = None   # room Jill is in (picks the right game object in a scan)
        self.w_room: Optional[int] = None      # watch_list: last room whose door list was right
        self.w_sig = None                      # ... and that list (record, destination pairs)
        self.w_bad_since: Optional[float] = None
        self.w_bad_room: Optional[int] = None
        self.last_relook = 0.0

    # ------------------------------------------------------------ public
    @property
    def active(self) -> bool:
        return bool(self.s.get("phase"))

    def needs_cleanup(self) -> bool:
        return bool(self.s.get("phase") or self.s.get("pickups") or self.s.get("info")
                    or self.s.get("visited") or self.s.get("chris") or self.s.get("locks"))

    def masked(self) -> Set[str]:
        """Location names the client must not report right now."""
        return set(self.s.get("pickups", [])) | set(self.s.get("mask_rooms", []))

    def start(self, home: int, sender: str, themed: bool, rng) -> bool:
        decoy = choose_decoy(home, themed, rng)
        if decoy is None:
            return False
        self.s = {"phase": "armed", "home": home, "decoy": decoy, "sender": sender, "themed": themed,
                  "message": THEMED.get(decoy, "Feeling lost?"),
                  "info": [], "pickups": [], "mask_rooms": [], "visited": None, "chris": False,
                  "back_from": None, "prepared": False}
        log.info("Wrong Door Trap armed: the next door from %#x leads to %#x.", home, decoy)
        self._save()
        return True

    def update(self, conn, flags: int, room: Optional[int], pid,
               pickups_in_room: Callable[[int], List[Tuple[str, int, int]]],
               room_check_name: Callable[[int], Optional[str]]):
        """Called every tick while Jill is in this seed's game."""
        s = self.s
        if not s:
            return
        self.flags = flags
        now = time.time()
        if room is None:
            return
        if s.get("room_seen") is None:
            s["room_seen"], self.room_changed_at = room, 0.0     # just armed: change the doors now
        if room != s.get("room_seen"):
            s["room_seen"], self.room_changed_at = room, now
            self._on_room(room, conn, flags, pid)
            self._save()
            return
        if now - self.room_changed_at < SETTLE:
            return
        phase = s.get("phase")
        if s.get("restore_due"):
            self._put_back_info(conn, pid)
            s["restore_due"] = False
            if phase is None:
                self.s["locks"] = []    # she left the Cell: its door records are rebuilt from the game files
                self._finish_flags(conn, flags)
                self.s = {}
                self._save()
                return
            self._save()
        if phase == "armed":
            if room != s["home"]:
                return
            if not s.get("prepared"):
                self._prepare_decoy(conn, flags, pickups_in_room, room_check_name)
            self._point_doors(conn, pid, room, s["decoy"], arrival(s["decoy"]))
        elif phase == "decoy":
            if room != s["decoy"]:
                return
            if s.get("cell_lock_until"):
                if now < s["cell_lock_until"]:
                    self._lock_doors(conn, pid)
                    return
                self._unlock_doors(conn)
                s["cell_lock_until"] = None
                self.notices.append(("...the cell door clicks open.", "info"))
                self._save()
            self._point_doors(conn, pid, room, s["home"], arrival(s["home"], s.get("back_from")))

    def cleanup_after_restart(self, conn, flags: int, pid, room: Optional[int] = None):
        """A trap was in progress when the client stopped: put everything back."""
        if not self.needs_cleanup():
            return
        log.info("Wrong Door Trap: putting back what an earlier session changed.")
        if room is not None and room == self.s.get("decoy") and self.s.get("phase") == "decoy":
            self._unlock_doors(conn)        # still in the Cell: don't leave her locked in
        self.s["locks"] = []
        self._put_back_info(conn, pid, any_pid=False)
        self._finish_flags(conn, flags)
        self.s = {}
        self._save()

    # ------------------------------------------------------------ steps
    def _on_room(self, room: int, conn, flags: int, pid):
        s = self.s
        phase = s.get("phase")
        if phase == "armed":
            if room == s["home"]:
                return
            s["restore_due"] = True
            if room == s["decoy"]:
                s["phase"] = "decoy"
                msg = s["message"] + f" (Wrong Door Trap from {s['sender']})"
                self.notices.append((msg, "info"))
                if room == CELL:
                    s["cell_lock_until"] = time.time() + SETTLE + CELL_LOCK_SECONDS
                log.info("Wrong Door Trap: Jill went through a door into %#x.", room)
            else:
                # walked through before the doors were changed, died, loaded, or a scene moved her:
                # the trap stays armed for the next door from where she is now
                log.info("Wrong Door Trap: Jill is in %#x instead - armed again there.", room)
                s["home"] = room
                if room in DOOR_PAIRS.get(s["decoy"], ()) or room == s["decoy"]:
                    pass        # decoy right next door now - keep it anyway (rare)
        elif phase == "decoy":
            if room == s["decoy"]:
                return
            s["restore_due"] = True
            s["phase"] = None
            log.info("Wrong Door Trap finished (Jill is in %#x).", room)

    def _prepare_decoy(self, conn, flags: int, pickups_in_room, room_check_name):
        """Before she can arrive: hide the decoy's items, mask its room check, skip the Cell scene."""
        s = self.s
        decoy = s["decoy"]
        hidden = []
        for name, off, bit in pickups_in_room(decoy):
            b = conn.read_bytes(flags + off, 1)[0]
            if not b >> bit & 1:
                conn.write_bytes(flags + off, bytes([b | 1 << bit]))
                hidden.append([name, off, bit])
        s["pickups_bits"] = hidden
        s["pickups"] = [h[0] for h in hidden]
        name = room_check_name(decoy)
        if name:
            s["mask_rooms"] = [name]
        from ..game_data import room_visited_flag
        vf = room_visited_flag(decoy)
        if vf:
            off, bit = vf
            if not conn.read_bytes(flags + off, 1)[0] >> bit & 1:
                s["visited"] = [off, bit]
        if decoy == CELL:
            off, bit = CHRIS_SCENE
            b = conn.read_bytes(flags + off, 1)[0]
            if not b >> bit & 1:
                conn.write_bytes(flags + off, bytes([b | 1 << bit]))
                s["chris"] = True
        s["prepared"] = True
        log.info("Wrong Door Trap: %d item(s) hidden in %#x%s.", len(hidden), decoy,
                 ", Chris's scene skipped" if s["chris"] else "")
        self._save()

    def _lock_doors(self, conn, pid):
        """Cell: every door is locked until cell_lock_until (lock byte LOCKED, flag 0); the original
        bytes are kept to put back."""
        game = self._game(conn, pid)
        if not game:
            return
        locks = self.s.setdefault("locks", [])
        done = {l[0] for l in locks}
        flag = self._free_unlock_flag(conn)
        if flag is None:
            return
        for rec, _dest in self._live(conn, game):
            if rec in done:
                if conn.read_bytes(rec + 0x43, 1)[0] != LOCKED:      # the game rebuilt it: lock again
                    conn.write_bytes(rec + 0x43, bytes([LOCKED]))
                    conn.write_bytes(rec + 0x44, struct.pack("<i", flag))
                continue
            orig = conn.read_bytes(rec + 0x43, 5).hex()
            locks.append([rec, orig])
            conn.write_bytes(rec + 0x44, struct.pack("<i", flag))
            conn.write_bytes(rec + 0x43, bytes([LOCKED]))
            log.info("Wrong Door Trap: Cell door %#x locked for %.0f s.", rec, CELL_LOCK_SECONDS)
            self._save()

    def _free_unlock_flag(self, conn) -> Optional[int]:
        """Highest door-unlock flag index (0-255) that is off right now."""
        if self.s.get("lock_flag") is not None:
            return self.s["lock_flag"]
        table = conn.read_bytes(self.flags + UNLOCK_FLAGS, 32)
        for n in range(255, -1, -1):
            if not table[n // 8] >> (n % 8) & 1:
                self.s["lock_flag"] = n
                return n
        return None

    def _unlock_doors(self, conn):
        for rec, orig in self.s.get("locks", []):
            try:
                if struct.unpack("<I", conn.read_bytes(rec, 4))[0] == DOOR_VTABLE \
                        and conn.read_bytes(rec + 0x43, 1)[0] == LOCKED:
                    conn.write_bytes(rec + 0x43, bytes.fromhex(orig))
            except Exception:
                pass                # that room's door records are gone already
        self.s["locks"] = []
        self.s["lock_flag"] = None

    def _finish_flags(self, conn, flags: int):
        """Show the decoy's items again, clear its visited flag (if it was off), restore the Cell scene."""
        s = self.s
        for _name, off, bit in s.get("pickups_bits", []):
            b = conn.read_bytes(flags + off, 1)[0]
            conn.write_bytes(flags + off, bytes([b & ~(1 << bit) & 0xFF]))
        if s.get("visited"):
            off, bit = s["visited"]
            b = conn.read_bytes(flags + off, 1)[0]
            conn.write_bytes(flags + off, bytes([b & ~(1 << bit) & 0xFF]))
        if s.get("chris"):
            off, bit = CHRIS_SCENE
            b = conn.read_bytes(flags + off, 1)[0]
            conn.write_bytes(flags + off, bytes([b & ~(1 << bit) & 0xFF]))
        s["pickups_bits"], s["pickups"], s["mask_rooms"], s["visited"], s["chris"] = [], [], [], None, False

    def _point_doors(self, conn, pid, room: int, target: int, arr):
        """Make every real door of `room` lead to `target` (doorinfo first, then the record)."""
        if arr is None:
            return
        game = self._game(conn, pid)
        if not game:
            return
        real = set(DOOR_PAIRS.get(room, ()))
        for rec, dest in self._live(conn, game):
            if dest == target or dest not in real:
                continue
            if not self._patch_info(conn, pid, room, dest, target):
                continue            # no table entry found: leave this door alone (it would crash)
            if self.s.get("back_from") is None and self.s.get("phase") == "armed":
                self.s["back_from"] = dest
            self._point_records(conn, rec, target, arr)
            self._save()

    # ------------------------------------------------------------ memory helpers
    def warm_up(self, conn, pid):
        """Find the game object and the door animation table ahead of time (once per game process),
        in a background thread, so a Wrong Door Trap can change the doors in the same tick it
        arrives. TessarionAM (2026-11-12): in the test tool the scan made him stand still ~10 s."""
        if self.ready(conn, pid) or (self.warm_thread and self.warm_thread.is_alive()
                                      and self.warm_pid == pid):
            return
        if not hasattr(conn, "readable_regions") or time.time() < self.next_scan:
            return
        self.next_scan = time.time() + RESCAN_SECONDS
        self.warm_pid = pid
        if not BACKGROUND:
            self._scan(conn, pid)
            return
        self.warm_thread = threading.Thread(target=self._scan, args=(conn, pid), daemon=True,
                                            name="WrongDoorScan")
        self.warm_thread.start()

    def ready(self, conn, pid) -> bool:
        if not (self.game and self.info and self.game_pid == pid and self.info_pid == pid):
            return False
        try:
            return struct.unpack("<I", conn.read_bytes(self.game, 4))[0] == GAME_VTABLE
        except Exception:
            return False

    def _scan(self, conn, pid):
        t0 = time.time()
        keep_game = self.game if self.game and self.game_pid == pid else 0
        keep_info = self.info if self.info and self.info_pid == pid else {}
        try:
            game = keep_game or _find_game(conn, self.room_hint, self.stale_games)
            info = (keep_info or _find_info(conn)) if game else {}
        except Exception as exc:          # the game closed mid-scan etc.: try again later
            log.info("Wrong Door Trap: memory scan stopped (%s).", exc)
            return
        if game and info:
            self.game, self.game_pid, self.info, self.info_pid = game, pid, info, pid
            self.w_room = self.w_sig = self.w_bad_since = self.w_bad_room = None
            log.info("Wrong Door Trap ready (%.1f s): game object %#x, door animation table %d entries.",
                     time.time() - t0, game, sum(map(len, info.values())))
        else:
            log.warning("Wrong Door Trap: game object / door animation table not found (will retry).")

    # ------------------------------------------------------------ out-of-date memory
    def _owner(self) -> "WrongDoor":
        return self.scanner if self.scanner is not None else self

    def invalidate(self, game: bool, info: bool, why: str):
        """Look for the game object and/or the door table again (in the background)."""
        o = self._owner()
        if game and o.game:
            o.stale_games.add(o.game)
            o.game = 0
        if info:
            o.info = {}
        now = time.time()
        o.next_scan = max(now, o.last_relook + RELOOK_GAP)    # right away, unless it just did
        o.last_relook = now
        log.warning("Doors: %s - looking for the game's door data again.", why)

    def watch_list(self, conn, pid, room: Optional[int], allowed: Set[int] = frozenset()):
        """Every tick while a door feature is on: is the live door list this room's? A list that
        stays the previous room's (or empty) after the room changed means the game object is out
        of date (a save was loaded). `allowed` = rooms our own door changes may point at here."""
        self.room_hint = room
        if room is None or not DOOR_PAIRS.get(room) or not self.ready(conn, pid):
            return
        try:
            live = self._live(conn, self.game)
        except Exception:
            live = []
        sig = frozenset(live)                                  # (record, destination) pairs
        recs = frozenset(r for r, _d in live)
        if room == self.w_room and live and recs == frozenset(r for r, _d in self.w_sig):
            self.w_sig, self.w_bad_since, self.w_bad_room = sig, None, None
            return                     # the list already accepted here (our own changes included)
        fits = set(DOOR_PAIRS[room]) | set(allowed)
        same_as_before = room != self.w_room and self.w_sig is not None and sig == self.w_sig
        if live and not same_as_before and any(dest in fits for _rec, dest in live):
            self.w_room, self.w_sig, self.w_bad_since, self.w_bad_room = room, sig, None, None
            return
        now = time.time()
        if self.w_bad_room != room:
            self.w_bad_room, self.w_bad_since = room, now
            return
        if now - self.w_bad_since >= SETTLE + STALE_SECONDS:
            why = ("the door list is empty" if not live else
                   "the door list still belongs to the last room" if same_as_before else
                   "no door in the door list leads anywhere from this room")
            self.w_bad_since, self.w_bad_room = None, None
            self.invalidate(True, False, f"in {room:#x} {why}")

    def _game(self, conn, pid) -> int:
        """The game object if the background scan has found it, else 0 (and start the scan)."""
        if self.ready(conn, pid):
            return self.game
        self.warm_up(conn, pid)
        return self.game if self.ready(conn, pid) else 0

    @staticmethod
    def _live(conn, game: int) -> List[Tuple[int, int]]:
        base = game + DOOR_LIST
        count = struct.unpack("<I", conn.read_bytes(base + LIST_COUNT, 4))[0]
        arr = struct.unpack("<I", conn.read_bytes(base + LIST_ARRAY, 4))[0]
        if not arr or count > 64:
            return []
        out = []
        for p in struct.unpack(f"<{count}I", conn.read_bytes(arr, 4 * count)):
            if not p:
                continue
            rec = conn.read_bytes(p, 0x4C)
            if struct.unpack_from("<I", rec, 0)[0] == DOOR_VTABLE:
                out.append((p, rec[0x40] * 0x100 + rec[0x41]))
        return out

    def _entries(self, conn, pid) -> Dict[Tuple[int, int], List[int]]:
        return self.info if self.ready(conn, pid) else {}

    def _patch_info(self, conn, pid, src: int, dest: int, target: int) -> bool:
        """Point the doorinfo entries for src -> dest at target. True if the pair now has an entry."""
        entries = self._entries(conn, pid).get((src, dest), [])
        saved = {i[0] for i in self.s.setdefault("info", [])}
        ok = False
        matched = False
        for e in entries:
            key = struct.unpack("<4i", conn.read_bytes(e + INFO_KEY, 16))
            if key[:2] == (src >> 8, src & 0xFF):
                matched = True
            if key == (src >> 8, src & 0xFF, dest >> 8, dest & 0xFF):
                orig = conn.read_bytes(e + INFO_DEST, 8).hex()
                conn.write_bytes(e + INFO_DEST, struct.pack("<ii", target >> 8, target & 0xFF))
                self.s["info"].append([e, orig, pid, target])
                ok = True
            elif key == (src >> 8, src & 0xFF, target >> 8, target & 0xFF) and e in saved:
                ok = True           # already pointed there by us
        if entries and not matched:
            # every entry we knew for this pair now holds something else: the table was reloaded
            self.invalidate(False, True, f"the door table entries for {src:#x} -> {dest:#x} have moved")
        return ok

    def _point_records(self, conn, rec: int, target: int, arr) -> None:
        """Point one door record at `target` (arrival `arr`), keeping its bytes to put back."""
        recs = self.s.setdefault("recs", [])
        if not any(r[0] == rec for r in recs):
            orig = (conn.read_bytes(rec + 0x30, 12) + conn.read_bytes(rec + 0x40, 3)
                    + conn.read_bytes(rec + 0x48, 4)).hex()
            recs.append([rec, orig, target])
        x, y, z, ang, cut = arr
        conn.write_bytes(rec + 0x30, struct.pack("<fff", x, y, z))
        conn.write_bytes(rec + 0x40, bytes([target >> 8, target & 0xFF, cut & 0xFF]))
        conn.write_bytes(rec + 0x48, struct.pack("<f", ang))

    def _put_back_records(self, conn) -> None:
        """Door records we pointed somewhere, still in the room Jill is in: as they were.
        (Cancelling a shortcut used to leave them pointing at the shortcut's room with no door
        table entry for it - the case that crashed the game in Wrong Door tests v3/v6.)"""
        for rec, orig, target in self.s.get("recs", []):
            try:
                if struct.unpack("<I", conn.read_bytes(rec, 4))[0] != DOOR_VTABLE:
                    continue                    # the room's records are gone already
                if conn.read_bytes(rec + 0x40, 2) != bytes([target >> 8, target & 0xFF]):
                    continue                    # rebuilt by the game, or not ours any more
                raw = bytes.fromhex(orig)
                conn.write_bytes(rec + 0x30, raw[:12])
                conn.write_bytes(rec + 0x40, raw[12:15])
                conn.write_bytes(rec + 0x48, raw[15:19])
            except Exception:
                pass
        self.s["recs"] = []

    def _put_back_info(self, conn, pid, any_pid: bool = True):
        keep = []
        for e, orig, saved_pid, target in self.s.get("info", []):
            if saved_pid != pid and not any_pid:
                continue            # another game process: that memory is gone anyway
            try:
                now = struct.unpack("<ii", conn.read_bytes(e + INFO_DEST, 8))
                if now == (target >> 8, target & 0xFF):
                    conn.write_bytes(e + INFO_DEST, bytes.fromhex(orig))
            except Exception:
                keep.append([e, orig, saved_pid, target])
        self.s["info"] = keep


def _find_game(conn, room: Optional[int] = None, stale: Set[int] = frozenset()) -> int:
    """The game object. More than one can be in memory (after loading a save the old one can still
    be there): prefer one whose door list fits the room Jill is in, then one not known to be old."""
    found = []
    for a in _search(conn, struct.pack("<I", GAME_VTABLE)):
        try:
            count = struct.unpack("<I", conn.read_bytes(a + DOOR_LIST + LIST_COUNT, 4))[0]
            arr = struct.unpack("<I", conn.read_bytes(a + DOOR_LIST + LIST_ARRAY, 4))[0]
        except Exception:
            continue
        if count <= 64 and (count == 0 or arr > 0x10000):
            found.append(a)
    if not found:
        return 0
    real = set(DOOR_PAIRS.get(room, ())) if room is not None else set()

    def fits(a):
        try:
            return any(dest in real for _rec, dest in WrongDoor._live(conn, a))
        except Exception:
            return False
    for want in ((True, False), (True, True), (False, False)):
        for a in found:
            if (not want[0] or fits(a)) and (want[1] or a not in stale):
                return a
    return found[0]


def _find_info(conn) -> Dict[Tuple[int, int], List[int]]:
    """(src, dest) -> doorinfo entry addresses. Finds one known entry (Main Hall -> Dining Room) to
    learn the entries' class pointer, then every object of that class."""
    vt = None
    for h in _search(conn, struct.pack("<4i", 1, 6, 1, 5)):
        e = h - INFO_KEY
        try:
            if conn.read_bytes(e + 8, 2) == b"do":
                vt = conn.read_bytes(e, 4)
                break
        except Exception:
            continue
    info: Dict[Tuple[int, int], List[int]] = {}
    if vt is None:
        return info
    for e in _search(conn, vt):
        try:
            raw = conn.read_bytes(e, 0x2C)
        except Exception:
            continue
        if raw[8:10] != b"do":
            continue
        ss, sr, ds, dr = struct.unpack_from("<4i", raw, INFO_KEY)
        info.setdefault((ss * 0x100 + sr, ds * 0x100 + dr), []).append(e)
    return info


def _search(conn, pattern: bytes, limit: int = 4096) -> List[int]:
    """4-byte-aligned addresses of `pattern` in the game's memory."""
    hits = []
    for base, size in conn.readable_regions(0x7FFF0000):
        off = 0
        while off < size:
            n = min(CHUNK, size - off)
            try:
                data = conn.read_bytes(base + off, n)
            except Exception:
                break
            i = data.find(pattern)
            while i != -1:
                if (base + off + i) % 4 == 0:
                    hits.append(base + off + i)
                    if len(hits) >= limit:
                        return hits
                i = data.find(pattern, i + 1)
            off += CHUNK
    return hits
