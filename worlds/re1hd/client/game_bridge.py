"""
The part of the Archipelago client that talks to the GAME (no networking here,
so it can be tested offline with a fake memory).

Each tick():
  1. reads the pickup flags; any detected pickup that is "on" counts as checked
     (a pickup taken while the client was closed still counts - the game itself
     remembers it in the save);
  2. when a flag turns on WHILE we're watching, takes the vanilla item back out
     of the inventory (the Milestone 7 pickup guard), unless the player is
     re-taking an item they put back (e.g. the Wooden Emblem on the fireplace);
  3. delivers received items, one at a time, into the item box (Milestone 6).
     The Lock Pick goes into its hidden slot instead, like in the real game,
     and daggers / battery packs raise their counters (defensive items are
     counts, not inventory slots - found 2026-11-10).

Never lose / never duplicate:
  * The number of received items already delivered is saved in a small JSON
    file per seed + slot ("delivered"). Before each write we also save what we
    are about to do ("pending"). If the client stops between writing and
    saving, the next start sees the pending entry, looks at that box slot, and
    counts it as delivered only if our item is really there.
  * Reloading an OLDER save in the game loses items delivered after that save
    (the game puts the box back how it was). The save marker in box slot 256
    (see _check_save_marker) tells us how many that save has, and we re-send the
    rest automatically. Traps are never re-applied.
"""

import hashlib
import json
import logging
import math
import struct
import time
from dataclasses import dataclass, field
from pathlib import Path
from .autosave import SAVE_ROOMS, AutosaveError, Autosaver
from .box_sort import sorted_box
from .door_skip import DoorSkipError, set_door_skip
from .wrong_door import CELL, UNLOCK_FLAGS, WrongDoor
from .shortcuts import SHORTCUTS, Shortcut
from .door_shuffle_client import DoorShuffler
from .window_mode import Borderless, VK_CODES, key_held, game_has_focus
from .gamepad import BUTTONS, COMBOS, button_down
from typing import Callable, Dict, List, Optional, Tuple

from . import hd_versions as hv
from .hd_delivery import (EMPTY, SLOT, DeliveryError, InventoryFull, Journal, deliver_to_box,
                          deliver_to_inventory)
from .hd_pickups import GUARDED_SLOTS, parse_slots, plan_removal, player_put_back
from .pc_process import ProcessConnection, ProcessError
from .pickup_mapper import LearnedFile, PickupMapper, virtual_slots
from ..game_data import (AMMO_IDS, DEFENCE_BUNDLE, DEFENCE_BUNDLE_CONTENTS, GUN_CAPACITY,
                         INFINITE_AMMO_SECONDS, DETECTED_PICKUPS, DIRECT_INVENTORY_ITEMS, EQUIPPED_SLOT_OFFSET, HIDDEN_SLOT_ITEMS,
                         SAVE_MARKER_SLOT, SEED_TAG_SLOT, START_BOX_RIBBONS, START_ROOM_NUMBER, STACK_LIMITS,
                         VANILLA_BOX_RIBBON, VANILLA_BOX_SPRAY, VANILLA_START, ROOM_NUMBERS, ROOM_VISITED_VERIFIED,
                         delivery_quantity, room_visited_flag)

log = logging.getLogger("RE1HDClient")

ITEM_BOX, INVENTORY_THEN_BOX = 0, 1          # option received_item_destination
LOAD_BURST = 3                               # this many pickup flags turning on in one tick = a load
ZONE = (0x2C0, 0x33C)          # where all detected pickup flags live
VISITED = (0x33C, 0x352)       # the game's saved "room visited" flags (see game_data)
NO_TAKE_BACK = {130, 9001}     # maps and files (FILE_MARKER): the check counts, nothing is taken back
# Missable story items (Barry's Magnum 15, Assault Shotgun 13): their checks hold junk and the
# real item is in the pool. Claude's choice: the client does NOT take the vanilla one back -
# Barry's gun is part of the Altar choice (give it back or keep it), so removing it from Jill's
# hands could break that scene. You may end up with two of them; that's harmless.
NO_TAKE_BACK |= {13, 15}
# The Rocket Launcher (10) Brad drops is how you beat the Tyrant at the end - never take it back.
NO_TAKE_BACK |= {10}
WAIT_FOR_VANILLA = 5.0         # seconds to wait for the vanilla item after its flag


@dataclass
class Incoming:
    index: int                 # position in the server's received-items list
    game_id: Optional[int]
    label: str                 # e.g. "Golden Arrow from TessarionAM"
    starting: bool = False     # starting inventory (start_with_sword_key etc.): straight to Jill
    trap: Optional[str] = None # a name in EFFECT_ITEMS: an effect on Jill, not an item


# Received "items" that are effects applied once (never re-applied after loading a save): the
# traps, and Infinite Ammo (a timed effect). The Defence Bundle is a real delivery, not here.
# Fun traps (2026-11-12): pranks done on the PC by the client (fun_effects.py / overlay.py).
FUN_TRAPS = frozenset({"Fake Crash Trap", "To Be Continued Trap", "Fake Item Trap",
                       "Fake Death Link Trap", "Window Shake Trap", "Self-Destruct Trap",
                       "Danger Flash Trap"})
SWORD_KEY_ID = 45                              # the Sword Key (inside the Book of Curses)
WRONG_DOOR = "Wrong Door Trap"                 # fun trap handled here (wrong_door.py), not by FUN_TRAPS
# Key items a Fake Item Trap may pretend to send (never one Jill already received).
FAKE_ITEM_CHOICES = ("Master Key", "Helmet Key", "Armor Key", "Shield Key", "Book of Curses",
                     "Power Key", "Control Room Key", "Square Crank", "Hexagonal Crank", "Battery",
                     "Magnum", "Gold Emblem", "Golden Arrow", "MO Disk 1", "Fuel Capsule")
EFFECT_ITEMS = frozenset({"Damage Trap", "Poison Trap", "Critical Damage Trap", "Ammo Leak Trap",
                          "Infinite Ammo (20s)", WRONG_DOOR} | FUN_TRAPS)


@dataclass
class BridgeState:
    delivered: int = 0
    pending: Optional[dict] = None
    undeliverable: List[dict] = field(default_factory=list)
    start_swapped: bool = False        # random starting inventory already applied this seed
    applied_traps: List[int] = field(default_factory=list)   # trap item indices already applied
    box_unseen: List[str] = field(default_factory=list)      # put in the box since you last stood by one
    wrong_door: dict = field(default_factory=dict)           # Wrong Door Trap in progress (wrong_door.py)
    sword_uses_set: bool = False       # door lock randomiser: the Sword Key got the seed's number of uses
    shortcut: dict = field(default_factory=dict)             # Key Map shortcut in progress (shortcuts.py)
    door_shuffle: dict = field(default_factory=dict)         # door randomiser: changed table entries, used doors


class StateFile:
    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> BridgeState:
        if not self.path.exists():
            return BridgeState()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return BridgeState(data.get("delivered", 0), data.get("pending"), data.get("undeliverable", []),
                           data.get("start_swapped", False), data.get("applied_traps", []),
                           data.get("box_unseen", []), data.get("wrong_door", {}),
                           data.get("sword_uses_set", False), data.get("shortcut", {}),
                           data.get("door_shuffle", {}))

    def save(self, st: BridgeState):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"delivered": st.delivered, "pending": st.pending,
                                   "undeliverable": st.undeliverable, "start_swapped": st.start_swapped,
                                   "applied_traps": st.applied_traps, "box_unseen": st.box_unseen,
                                   "wrong_door": st.wrong_door, "sword_uses_set": st.sword_uses_set,
                                   "shortcut": st.shortcut, "door_shuffle": st.door_shuffle},
                              indent=1), encoding="utf-8")
        tmp.replace(self.path)          # atomic: never a half-written state file


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


from ..data import BOX_ROOMS as _BOX_ROOMS
INSECTICIDE_ID, FLAMETHROWER_ID = 100, 107        # game item ids (items.py)
SPRAY_CHECK = "Gallery - Insecticide Spray"
GARBAGE_COMPACTOR_ROOM = 0x316
BOX_ROOM_NUMBERS = {ROOM_NUMBERS[r] for r in _BOX_ROOMS if ROOM_NUMBERS.get(r)}
JILL_HELD_WEAPON = 0x15D0     # Jill's held weapon type (item id - 1), 0 = nothing (equip watch)
JILL_VARIANT = 0x1580         # which column of the weapon tables (0x4FB600; the menu passes it to 0x48D190)
UNARM_TIMEOUT = 20.0          # seconds for the whole menu-style unequip
MENU_FLAGS, MENU_SCREEN = 0x2C, 0x34   # inventory struct: bit 0x1000 / value 3 while the menu is open

# Jill's health states, from the game's own status code (0x0054E170, 2026-11-11): health below
# 25 % of max = Danger, below 50 % = Caution (orange), below 75 % = Caution (yellow), else Fine.
HEALTH_STATE_LIMITS = (0.75, 0.5, 0.25)


def below_next_state(hp: int, mx: int) -> int:
    """Highest health that is one health state lower than `hp` (1 if already in Danger)."""
    for frac in HEALTH_STATE_LIMITS:
        limit = -(-int(mx * frac * 1000) // 1000)          # ceil(mx * frac)
        if hp >= limit:
            return limit - 1
    return 1


def box_summary(names: List[str], limit: int = 6) -> str:
    """'Armor Key, Shotgun Shells (6) x2, ... and 3 more'"""
    counts: Dict[str, int] = {}
    for n in names:
        counts[n] = counts.get(n, 0) + 1
    parts = [n + (f" x{c}" if c > 1 else "") for n, c in counts.items()]
    more = len(parts) - limit
    return ", ".join(parts[:limit]) + (f" and {more} more" if more > 0 else "")


def room_entry_checks() -> Dict[int, str]:
    """game room number -> its "First Visit" location name."""
    from ..data import EXTRA_CHECKS
    return {ROOM_NUMBERS[room]: name for category, room, name, _ in EXTRA_CHECKS
            if category == "room" and ROOM_NUMBERS.get(room)}


def world_rooms_for_number(number: int) -> set:
    """Our world's room name(s) for a game room number (0x103 is both Tea Room and Northern Corridor)."""
    return {name for name, nb in ROOM_NUMBERS.items() if nb == number}


def pickups_by_room() -> Dict[int, List[Tuple[str, int, int]]]:
    """game room number -> [(location name, flag offset, bit)] of its detected pickups / maps / files
    (the Wrong Door Trap hides these while Jill is in a room she was sent to)."""
    from ..data import EXTRA_CHECKS, FILE_CHECKS, PICKUPS
    room_of = {name: room for room, name, _item, _req in PICKUPS}
    room_of.update({name: room for _cat, room, name, _req in EXTRA_CHECKS})
    room_of.update({name: room for room, name, _off, _bit in FILE_CHECKS})
    out: Dict[int, List[Tuple[str, int, int]]] = {}
    for name, (off, bit, _vanilla) in DETECTED_PICKUPS.items():
        number = ROOM_NUMBERS.get(room_of.get(name))
        if number:
            out.setdefault(number, []).append((name, off, bit))
    return out


def pickup_catalogue() -> dict:
    """Every pickup and extra check (maps...) with its in-game item id and known flag bit (for the mapper)."""
    from ..data import EXTRA_CATEGORY_GAME_ID, EXTRA_CHECKS, PICKUPS
    from ..items import item_table
    cat = {}
    for room, name, item, _req in PICKUPS:
        known = DETECTED_PICKUPS.get(name)
        cat[name] = {"room": room, "room_nb": ROOM_NUMBERS.get(room), "item": item,
                     "item_id": item_table[item].game_id, "known": [known[0], known[1]] if known else None}
    for category, room, name, _req in EXTRA_CHECKS:
        if category not in EXTRA_CATEGORY_GAME_ID:
            continue                     # room entries etc. aren't pickups - nothing to map
        known = DETECTED_PICKUPS.get(name)
        cat[name] = {"room": room, "room_nb": ROOM_NUMBERS.get(room), "item": category,
                     "item_id": EXTRA_CATEGORY_GAME_ID.get(category), "known": [known[0], known[1]] if known else None}
    return cat


class GameBridge:
    def __init__(self, state_file: StateFile, journal: Journal,
                 connect: Optional[Callable[[], Tuple[object, int, int]]] = None,
                 learned_file: Optional[Path] = None):
        """connect() -> (connection, inventory pointer address, flags pointer address);
        the default connects to the real bhd.exe. Tests pass a fake."""
        self.state_file = state_file
        self.state = state_file.load()
        self.infinite_until, self.infinite_floor = 0.0, {}   # Infinite Ammo: end time, gun id -> rounds
        self.rng = __import__("random").Random()
        self.journal = journal
        self._connect = connect or connect_to_game
        self.conn = None
        self.inv_ptr = self.flags_ptr = 0
        self.last_bits: Optional[Dict[str, bool]] = None
        self.last_inv = None
        self.last_def: Optional[Dict[int, int]] = None
        self.pending_removals: List[Tuple[str, list, dict, float]] = []
        self.put_back = set()
        self.next_delivery_try = 0.0
        self.current_room: Optional[int] = None       # game room number, e.g. 0x106 = Main Hall
        self.room_checks = room_entry_checks()
        self.room_entries_on = False             # option first_room_entries (Wrong Door Trap's room list)
        self.wrong_door = WrongDoor(self.state.wrong_door, save=self._save_wrong_door)
        self.wrong_door_restart_checked = False  # put back what a previous client session left
        self.shortcut = Shortcut(self.state.shortcut, save=self._save_shortcut, scanner=self.wrong_door)
        self.shortcuts_on = False                # YAML key_map_shortcuts
        self.door_shuffler = DoorShuffler(None, self.state.door_shuffle, self._save_door_shuffle, self.wrong_door)
        self.door_shuffle_checked = False        # an earlier session's table changes put back
        self.shortcuts_unlocked: frozenset = frozenset()   # names whose room Jill has been in
        self.session_token = self.rng.getrandbits(48)
        self.pickups_by_room = pickups_by_room()
        # door lock randomiser (slot_data "door_locks" / "key_uses", set by the client)
        self.lock_sides: Dict[str, Tuple[int, int]] = {}   # "from->to" (hex room numbers) -> (key type, flag)
        self.key_qty: Dict[int, int] = {}                   # game item id -> uses (= doors it opens)
        self.sword_uses: Optional[int] = None
        self.locks_written = 0
        self.unlocked_flags: frozenset = frozenset()   # door unlock flags set in the game (Key Map)
        self.jill_pos = None                           # (x, y, z) in the room's coordinates (Key Map)
        self.destination = ITEM_BOX              # set from slot_data by the client
        self.random_start = False                # option random_starting_inventory
        self.trap_damage_percent = 25            # options damage_trap_amount / _can_kill
        self.trap_can_kill = False
        self.death_link_kill = False             # option death_link_effect (False = lose a state)
        self.deaths_to_apply = 0                 # Death Links received, not yet applied
        self.jill_died = False                   # set when Jill's health reaches 0 (client sends)
        self.last_hp: Optional[int] = None
        self.ignore_death_until = 0.0
        self.notices: list = []                  # overlay messages: text, or (text, kind)
        self.timed_notices: list = []            # (due time, text, kind) - shown when due
        self.fun_done: list = []                 # (due time, trap name): prank over, announce it now
        self.fun_requests: list = []             # (fun trap name, sender) for the client to do
        self.last_received: list = []            # the received list from the last tick
        self.start_box: List[Tuple[int, int]] = []   # slot_data: [spray replacement, ribbon replacement]
        self.autosave_slot: Optional[int] = None  # option autosave: slot index 0-7, None = off
        self.autosaver = None
        self.autosaver_pid = None
        self.autosaver_factory = Autosaver       # tests replace this
        self.as_room: Optional[int] = None       # room Jill is in, for "just walked into a save room"
        self.as_since = 0.0
        self.as_armed = False                    # walked in through a door (not a load) -> may save
        self.last_load_time = 0.0                # last time a save load / death was seen
        self.next_drop_try = 0.0                 # held-weapon fix rate limit
        self.unarmed_once = False                # random start: empty hands confirmed this run
        self._in_tick, self._jill_cache = False, None   # Jill's object: looked up once per tick
        self.visited_block: Optional[bytes] = None       # the game's "room visited" flags, last tick
        self._room_flags, self._room_flags_for = [], None
        self.last_spray: Optional[int] = None    # Insecticide Sprays in the inventory + box last tick
        self.last_inv_spray: Optional[int] = None
        self.extra_checked: set = set()          # checks the client sends itself (a spray used)
        self.lisa_warned = False                 # flamethrower warning shown for this visit
        self.unarm: Optional[dict] = None        # the menu's unequip in progress (_unarm_step)
        self.room_since = 0.0
        self.fresh_handled = False               # this new game has already been reset
        self.as_deadline: Optional[float] = None # a save is running until this time
        self.door_skip = False                   # option door_skip / command /doorskip
        self.borderless = False                  # option borderless_fullscreen / command /borderless
        self.box_anywhere = 0                    # option item_box_anywhere: 0 off, 1 save rooms, 2 anywhere
        self.box_hotkey = "F7"                   # key that opens the item box anywhere (/itembox key)
        self.box_button: Optional[str] = None    # option item_box_button (controller)
        self.box_key_was_down = False
        self.window = Borderless()
        self.next_window_check = 0.0
        self.door_skip_pid = None                # game process door skip was last set for
        self.door_skip_retry = 0.0
        self.last_game_error: Optional[str] = None
        self.box_room_seen: Optional[int] = None
        self.box_sort_due: Optional[float] = None   # when to (re)try the automatic sort
        self.box_open_deadline: Optional[float] = None   # item box anywhere request in flight
        self.seed_tag = 0                        # this seed's tag (client sets it); 0 = don't check
        self.adopt_save = False                  # /adopt: tag the loaded save as this seed's
        self.foreign_save = False
        self.foreign_notice_at = 0.0
        self.save_known_ours = False             # the loaded save passed the seed check
        self.box_ui_was_open = False
        self.box_debug = False                   # research log (see _box_debug); /boxdebug on
        self.box_debug_last = None
        self.box_debug_lines = 0                 # cap, so a busy value can't flood the log
        self.box_debug_triggers_due: Optional[float] = None
        self.box_auto_sort = False               # option item_box_auto_sort / command /sortbox
        self.door_skip_warned = False
        self.flag_confirmed: set = set()
        self.marker_warned = False
        self.cur_inv = 0
        self.force_marker = False      # unverified rooms whose predicted flag was seen ON
        # Learns new pickup flags while you play (read-only). See pickup_mapper.py.
        self.mapper = PickupMapper(pickup_catalogue(), LearnedFile(learned_file), log=log.info) \
            if learned_file else None

    # ---------------------------------------------------------------- game link
    def set_door_shuffle(self, layout: dict):
        """Door randomiser: the seed's layout (slot data "door_shuffle"; {} = off)."""
        self.door_shuffler = DoorShuffler(layout or {}, self.state.door_shuffle,
                                          self._save_door_shuffle, self.wrong_door)
        if layout:
            log.info("Door randomiser on (%s, experimental - keep a spare save): %d door sides "
                     "lead somewhere new.", layout.get("mode", "?"), len(layout.get("targets", {})))

    def _save_door_shuffle(self):
        self.state.door_shuffle = self.door_shuffler.s
        self.state_file.save(self.state)

    def _door_shuffle_tick(self, flags: int, number: Optional[int]):
        ds = self.door_shuffler
        if not self.save_known_ours or not self._jill_present():
            return
        pid = getattr(self.conn, "pid", None)
        if not self.door_shuffle_checked:
            self.door_shuffle_checked = True
            if ds.s.get("session") != self.session_token:
                ds.cleanup_after_restart(self.conn, flags, pid, number)
                ds.s["session"] = self.session_token
        if not ds.on:
            return
        self.wrong_door.warm_up(self.conn, pid)
        busy = self.wrong_door.active or bool(self.shortcut.s)
        ds.update(self.conn, flags, number, pid, busy=busy)

    def _door_list_check(self, number: Optional[int]):
        """Door randomiser / Wrong Door Trap / shortcut: make sure the door data the client found is
        still the game's (after loading a save it may not be - wrong_door.watch_list)."""
        wd, ds, sc = self.wrong_door, self.door_shuffler, self.shortcut
        if not (ds.on or wd.s or sc.s) or not self.save_known_ours or not self._jill_present():
            return
        allowed = set(ds.targets_from(number)) if ds.on and number is not None else set()
        allowed |= {room for room, _from in SHORTCUTS.values()} | {CELL}
        if wd.s.get("home"):
            allowed.add(wd.s["home"])
        wd.watch_list(self.conn, getattr(self.conn, "pid", None), number, allowed)

    def _save_shortcut(self):
        self.state.shortcut = self.shortcut.s
        self.state_file.save(self.state)

    def request_shortcut(self, name: str) -> str:
        """Key Map button: arm (or, pressed again, cancel) a shortcut. Returns the message to show."""
        if not self.shortcuts_on:
            return "Shortcuts are off in your YAML (key_map_shortcuts: true)."
        if name not in SHORTCUTS:
            return f"No shortcut called {name}."
        if self.conn is None or not self._jill_present() or self.current_room is None:
            return "Jill isn't in the game right now."
        if not self.save_known_ours:
            return "Load this seed's save first."
        if name not in self.shortcuts_unlocked:
            return f"Visit the {name} first to unlock that shortcut."
        if self.wrong_door.active:
            return "Not during a Wrong Door Trap."
        pid = getattr(self.conn, "pid", None)
        if self.shortcut.target_name == name:
            self.shortcut.cancel(self.conn, pid)
            return f"Shortcut to the {name} cancelled."
        if self.shortcut.s:
            self.shortcut.cancel(self.conn, pid)
        if self.current_room == SHORTCUTS[name][0]:
            return f"Jill is already in the {name}."
        if not self.shortcut.start(name, self.current_room):
            return f"The shortcut to the {name} can't be used from here."
        self.shortcut.s["session"] = self.session_token
        self._save_shortcut()
        return f"Shortcut: the next door Jill goes through takes her to the {name}. (Press it again to cancel.)"

    def _shortcut_tick(self, flags: int, number: Optional[int]):
        sc = self.shortcut
        if not sc.s:
            return
        pid = getattr(self.conn, "pid", None)
        if sc.s.get("session") != self.session_token:
            sc.cleanup_after_restart(self.conn, flags, pid, number)   # an earlier client session's
            return
        if not self.save_known_ours or not self._jill_present() or self.wrong_door.active:
            return
        sc.update(self.conn, flags, number, pid)
        self.notices.extend(sc.notices)
        sc.notices.clear()

    def _save_wrong_door(self):
        self.state.wrong_door = self.wrong_door.s
        self.state_file.save(self.state)

    def set_door_locks(self, layout: dict, key_uses: dict):
        """Door lock randomiser: the seed's layout (door_locks.py) and key uses (item name -> n)."""
        from ..items import item_table
        self.lock_sides = {side: (int(v[0]), int(v[1])) for entry in (layout or {}).values()
                           for side, v in entry["sides"].items()}
        self.key_qty, self.sword_uses = {}, None
        for name, n in (key_uses or {}).items():
            if name == "Book of Curses":
                self.sword_uses = int(n)        # the Sword Key comes out of the book: fixed in _lock_tick
            elif name in item_table and item_table[name].game_id is not None:
                self.key_qty[item_table[name].game_id] = int(n)
        if self.lock_sides:
            log.info("Door lock randomiser: %d door sides, key uses %s.", len(self.lock_sides), key_uses)

    def _jill_position(self):
        """Jill's (x, y, z) through the pointer paths in hd_versions.JILL_POSITION: the first that
        gives sane numbers (None if none does, e.g. while a room loads)."""
        for static, offsets, z_step in hv.JILL_POSITION.get(getattr(self.conn, "build_key", None), ()):
            try:
                a = struct.unpack("<I", self.conn.read_bytes(static - hv.DEFAULT_IMAGE_BASE + self.conn.module_base, 4))[0]
                for off in offsets[:-1]:
                    if not a:
                        break
                    a = struct.unpack("<I", self.conn.read_bytes(a + off, 4))[0]
                if not a:
                    continue
                a += offsets[-1]
                x, y = struct.unpack("<ff", self.conn.read_bytes(a, 8))
                z, = struct.unpack("<f", self.conn.read_bytes(a + z_step, 4))
            except Exception:
                continue
            if all(math.isfinite(v) and abs(v) < 1e5 for v in (x, y, z)):
                return x, y, z
        return None

    def _check_position(self, number: Optional[int]):
        """Self-check, logged: right after a door, Jill's position should be the game's own arrival
        spot for that door (door_data.ARRIVALS). Logs once per room change."""
        due = getattr(self, "_pos_check", None)
        if not due or time.time() < due[2]:
            return
        self._pos_check = None
        came_from, room = due[0], due[1]
        if room != number or self.jill_pos is None:
            return
        from .door_data import ARRIVALS
        spots = [a for a in ARRIVALS.get(room, []) if a[0] == came_from and any(a[1:4])]
        if not spots:
            return
        x, _y, z = self.jill_pos
        d = min(math.hypot(x - s[1], z - s[3]) for s in spots)
        if d <= 60:
            log.info("Jill position check %#x (from %#x): OK, at the door spot (%.0f units).", room, came_from, d)
        else:
            log.info("Jill position check %#x (from %#x): %.0f units from the door spot - the Key Map may "
                     "be off; please report this with your client log.", room, came_from, d)

    def _lock_tick(self, inv: int, number: Optional[int]):
        """Door lock randomiser: write the seed's lock into every door record of the room Jill is in
        (the game rebuilds them on every room load; this runs every 0.1 s, long before she can reach
        a door). Same live door list as the Wrong Door Trap. Verified in-game 2026-11-12: a lock
        written like this works, a key loses one use per door, both sides share one unlock flag."""
        if not self.lock_sides or number is None:
            return
        wd = self.wrong_door
        pid = getattr(self.conn, "pid", None)
        game = wd._game(self.conn, pid)
        if game:
            for rec, dest in wd._live(self.conn, game):
                want = self.lock_sides.get(f"{number:x}->{dest:x}")
                if want is None:
                    continue
                t, flag = want
                cur = self.conn.read_bytes(rec + 0x43, 5)
                new = bytes([(cur[0] & 0x80) | t]) + struct.pack("<i", flag)
                if cur != new:
                    self.conn.write_bytes(rec + 0x44, new[1:])
                    self.conn.write_bytes(rec + 0x43, new[:1])
                    self.locks_written += 1
        if self.sword_uses and not self.state.sword_uses_set:
            base = inv + hv.INVENTORY_SLOTS_OFFSET
            for i in range(hv.INVENTORY_SLOT_COUNT):
                iid, qty = struct.unpack("<ii", self.conn.read_bytes(base + i * 8, 8))
                if iid == SWORD_KEY_ID:
                    self.conn.write_bytes(base + i * 8, struct.pack("<ii", iid, self.sword_uses))
                    self.state.sword_uses_set = True
                    self.state_file.save(self.state)
                    log.info("Door lock randomiser: Sword Key set to %d uses.", self.sword_uses)
                    break

    def _wrong_door_tick(self, flags: int, number: Optional[int]):
        """Wrong Door Trap (wrong_door.py): runs before the pickup flags are read, so flags it
        sets or clears this tick are already masked / unmasked."""
        wd = self.wrong_door
        if not self.save_known_ours or not self._jill_present():
            return
        pid = getattr(self.conn, "pid", None)
        wd.warm_up(self.conn, pid)               # find the door data ahead of time (background, once)
        if not wd.s:
            return
        if not self.wrong_door_restart_checked:
            self.wrong_door_restart_checked = True
            if wd.s.get("session") != self.session_token:
                # a trap from an earlier client session: put everything back, re-arm if not used yet
                was = dict(wd.s)
                wd.cleanup_after_restart(self.conn, flags, pid, number)
                if was.get("phase") == "armed" and number is not None:
                    wd.start(number, was.get("sender", "someone"), bool(was.get("themed")), self.rng)
                    wd.s["session"] = self.session_token
                return
        was_active = wd.active
        wd.update(self.conn, flags, number, pid, lambda r: self.pickups_by_room.get(r, []),
                  self.room_checks.get)
        if was_active and not wd.active:
            self.fun_done.append((time.time(), WRONG_DOOR))     # back home: announce it now
        self.notices.extend(wd.notices)
        wd.notices.clear()

    def ensure_game(self) -> bool:
        if self.conn is not None:
            return True
        try:
            self.conn, self.inv_ptr, self.flags_ptr = self._connect()
            # Jill's character manager pointer sits at a fixed distance from the flags pointer
            # in bhd.exe's data (0xCF2E84 vs 0xCF2FC8).
            self.char_mgr_ptr = self.flags_ptr - hv.CHARACTER_MANAGER_BEFORE_FLAGS
            log.info("Connected to Resident Evil HD Remaster.")
            self.last_game_error = None
            return True
        except (ProcessError, GameNotReady) as exc:
            if str(exc) != self.last_game_error:
                self.last_game_error = str(exc)
                log.info("Game not available: %s", exc)
            self.conn = None
            return False

    def set_door_skip(self, enable: bool) -> str:
        """Door skip in the game's code (same patches as BhdTool, see door_skip.py)."""
        key = getattr(self.conn, "build_key", None)
        if self.conn is None or key is None:
            return "The game isn't connected."
        try:
            set_door_skip(self.conn, key, enable)
        except (DoorSkipError, ProcessError) as exc:
            # Seed test 3: right after the game starts, Steam's copy protection hasn't unpacked
            # the game's code yet, so the bytes look "unexpected". Try again in a few seconds.
            self.door_skip_retry = time.time() + 5
            if not self.door_skip_warned:
                self.door_skip_warned = True
                log.info("Door skip not possible yet (%s) - will keep trying.", exc)
            return f"Door skip couldn't be changed yet: {exc}"
        self.door_skip_pid = getattr(self.conn, "pid", None)
        self.door_skip_warned = False
        log.info("Door skip %s.", "on" if enable else "off")
        return f"Door skip {'on' if enable else 'off'}."

    def set_borderless(self, enable: bool) -> str:
        self.borderless = enable
        if enable:
            self.next_window_check = 0.0
            return ("Borderless fullscreen on. The game must be in Windowed mode (Options > Display), "
                    "ideally at your monitor's resolution.")
        return "Borderless fullscreen off." if self.window.restore() else "Borderless fullscreen off."

    def drop_game(self, why: str):
        log.info("Lost the game connection (%s). Will keep trying.", why)
        self.conn, self.last_bits, self.last_inv, self.pending_removals = None, None, None, []
        self.last_def = None

    def _ptr(self, address: int) -> int:
        return int.from_bytes(self.conn.read_bytes(address, 4), "little")

    def inventory_empty_now(self) -> bool:
        """Jill's 8 inventory slots are all empty right now (read live; False if unknown).
        Used by the helicopter-ending check, which must work while no game is "loaded"."""
        try:
            if not self.conn:
                return False
            inv = self._ptr(self.inv_ptr)
            if not inv:
                return False
            return all(iid == 0 for iid, _ in self._slots(inv)[:8])
        except Exception:
            return False

    # ---------------------------------------------------------------- one tick
    def tick(self, received: List[Incoming]) -> Optional[set]:
        """Returns the set of detected location names whose flag is on, or None
        if no game is loaded right now."""
        self._in_tick, self._jill_cache = True, None
        try:
            return self._tick(received)
        finally:
            self._in_tick, self._jill_cache = False, None

    def _tick(self, received: List[Incoming]) -> Optional[set]:
        if not self.ensure_game():
            return None
        if (self.door_skip and self.door_skip_pid != getattr(self.conn, "pid", None)
                and time.time() >= self.door_skip_retry):
            self.set_door_skip(True)
        if self.box_anywhere and (self.box_hotkey or self.box_button):
            down = ((bool(self.box_hotkey) and key_held(VK_CODES[self.box_hotkey]))
                    or self._game_button_down(self.box_button) or button_down(self.box_button))
            if down and not self.box_key_was_down and game_has_focus(getattr(self.conn, "pid", 0)):
                answer = self.open_item_box()
                if answer != "Opening the item box...":
                    self.notices.append(answer)
            self.box_key_was_down = down
        if self.borderless and time.time() >= self.next_window_check:
            self.next_window_check = time.time() + 2      # the game may put its border back
            try:
                self.window.ensure(getattr(self.conn, "pid", 0))
            except Exception as exc:
                log.debug("Borderless window: %s", exc)
        try:
            inv, flags = self._ptr(self.inv_ptr), self._ptr(self.flags_ptr)
            if inv == 0 or flags == 0:          # title screen / loading
                self.last_bits, self.last_inv, self.pending_removals = None, None, []
                self.as_room, self.as_armed = None, False
                self.last_spray = self.last_inv_spray = None
                if self.mapper:
                    self.mapper.last_zone = self.mapper.last_inv = None
                return None
            stage, room = struct.unpack("<ii", self.conn.read_bytes(flags + hv.CURRENT_ROOM_OFFSET, 8))
            number = stage * 0x100 + room if 1 <= stage <= 6 and 0 <= room < 0x100 else None
            if number != self.current_room and number is not None:
                log.debug("Room: %#x %s", number, sorted(world_rooms_for_number(number)))
                if self.current_room is not None:
                    self._pos_check = (self.current_room, number, time.time() + 0.6)
                self.room_since = time.time()
                self.box_debug_triggers_due = time.time() + 1.0
            self._box_debug(flags)
            self.current_room = number
            self._door_list_check(number)
            self._door_shuffle_tick(flags, number)     # first: gives the room back to a trap / shortcut
            self._wrong_door_tick(flags, number)
            self._shortcut_tick(flags, number)
            if self.save_known_ours and self._jill_present():
                self._lock_tick(inv, number)
            self.jill_pos = self._jill_position()
            self._check_position(number)
            try:                                # Key Map: doors you've unlocked show as ordinary doors
                table = self.conn.read_bytes(flags + UNLOCK_FLAGS, 32)
                self.unlocked_flags = frozenset(n for n in range(256) if table[n // 8] >> (n % 8) & 1)
            except Exception:
                pass
            zone = self.conn.read_bytes(flags + ZONE[0], ZONE[1] - ZONE[0])
            bits = {name: bool(zone[off - ZONE[0]] >> bit & 1)
                    for name, (off, bit, _) in DETECTED_PICKUPS.items()}
            masked = self.wrong_door.masked()
            for name in masked:
                if name in bits:
                    bits[name] = False          # flags the Wrong Door Trap set: not pickups
            slots = self._slots(inv)
            defense = self._defense(inv)
            if self.mapper:
                picked = struct.unpack("<i", self.conn.read_bytes(inv + hv.LAST_PICKED_ITEM_OFFSET, 4))[0]
                self.mapper.update(zone, slots + virtual_slots(defense), picked=picked,
                                   rooms=world_rooms_for_number(number) if number else None)
            self.cur_inv = inv
            self._health()
            if not self._jill_present():
                # Title screen / menus / loading: the game's memory there is NOT the game you're
                # about to play (seed test 3, 2026-11-11: items "delivered" at the title screen
                # were wiped by New Game). Touch nothing until Jill is really in the game.
                return None
            self._new_game_reset(inv, number, bits)
            if self._protect_records(inv):
                pass                          # item box open in a save we already know: carry on
            elif not self._save_is_ours(inv, bits):
                # a save from another seed / a vanilla save: its flags would send this seed's
                # checks and deliveries would go into the wrong game (seed test 4, 02:21: 244
                # checks sent at once after loading an old Laboratory save). Do nothing at all.
                return None
            if self.random_start and not self.state.start_swapped:
                self._swap_start(inv, number, bits, slots)
                slots = self._slots(inv)
            if self.random_start and self.state.start_swapped:
                self._unequip_missing(inv, slots)
            self._guard(inv, bits, slots)
            self._setup_start_box(inv, number, bits)
            self._check_save_marker(inv, bits)
            self.last_received = received
            self._deliver(inv, received)
            self._infinite_ammo(inv)
            self._flush_timed_notices()
            self._autosave(number)
            self._box_reminder(number)
            self._box_open_poll()
            self.last_bits = bits
            self.last_inv = self._slots(inv)
            self.last_def = self._defense(inv)
            self._spray_watch(inv)
            self._flamethrower_warning(number)
            checked = {name for name, on in bits.items() if on}
            checked |= self._room_entries(flags, number)
            checked |= self.extra_checked
            return checked - masked
        except ProcessError as exc:
            self.drop_game(str(exc))
            return None

    def _spray_watch(self, inv: int):
        """Using an Insecticide Spray removes the Gallery's own spray from the game (TessarionAM,
        2026-11-13), so that check could never be done. It only ever holds junk (data.MISSABLE),
        so when the number of sprays in the inventory + box goes down, send it. A drop for any
        other reason (taken back after its pickup, an older save loaded) is harmless: the check
        is junk either way."""
        try:
            in_inv = [s[0] for s in self._slots(inv)[:8]].count(INSECTICIDE_ID)
            if in_inv == self.last_inv_spray and self.last_spray is not None:
                return          # nothing left the inventory: the box needn't be read (2 KB)
            self.last_inv_spray = in_inv
            box = self.conn.read_bytes(inv + hv.ITEM_BOX_OFFSET, SEED_TAG_SLOT * SLOT.size)
            count = in_inv + sum(1 for i in range(SEED_TAG_SLOT)
                                 if SLOT.unpack_from(box, i * SLOT.size)[0] == INSECTICIDE_ID)
        except Exception:
            return
        if (self.last_spray is not None and count < self.last_spray
                and SPRAY_CHECK not in self.extra_checked):
            self.extra_checked.add(SPRAY_CHECK)
            log.info("An Insecticide Spray was used: the Gallery's spray is gone, its check is sent.")
        self.last_spray = count

    def _flamethrower_warning(self, room: Optional[int]):
        """Barry takes the cave lift up as soon as Jill enters the passage beyond the Garbage
        Compactor Room, and the lift breaks: the only way out is Lisa's door, which needs the
        Broken Flamethrower. Received items go to the box, so warn if she isn't carrying it."""
        if room != GARBAGE_COMPACTOR_ROOM:
            self.lisa_warned = False
            return
        if self.lisa_warned or time.time() - self.room_since < 1.0:
            return
        self.lisa_warned = True
        if all(sid != FLAMETHROWER_ID for sid, _q in self._slots(self.cur_inv)[:8]):
            self.notices.append(("Carry the Broken Flamethrower before going on! Past the next door "
                                 "Barry takes the lift up and Lisa's door is the only way out.", "warning"))
            log.warning("Garbage Compactor Room without the Broken Flamethrower in the inventory.")

    def _swap_start(self, inv: int, room: Optional[int], bits: Dict[str, bool], slots):
        """Random starting inventory: on a brand-new game (Main Hall, nothing picked up, exactly
        the vanilla Handgun + Combat Knife), take those two away once per seed. The two random
        starting items arrive as normal starting items. EXPERIMENTAL (needs an in-game test)."""
        fresh = (room == START_ROOM_NUMBER and not any(bits.values())
                 and [tuple(s) for s in slots[:2]] == VANILLA_START
                 and all(tuple(s) == EMPTY for s in slots[2:8]))
        if not fresh:
            return
        for i, expected in enumerate(VANILLA_START):
            addr = inv + hv.INVENTORY_SLOTS_OFFSET + i * SLOT.size
            if SLOT.unpack(self.conn.read_bytes(addr, SLOT.size)) == expected:
                self.conn.write_bytes(addr, SLOT.pack(*EMPTY))
        eq = inv + EQUIPPED_SLOT_OFFSET
        if SLOT.unpack(self.conn.read_bytes(eq, SLOT.size))[0] == VANILLA_START[0][0]:
            self.conn.write_bytes(eq, SLOT.pack(*EMPTY))       # unequip the removed Handgun
        self.state.start_swapped = True
        self.state_file.save(self.state)
        log.info("Random starting inventory: took the Handgun and Combat Knife; your 2 starting items follow.")
        self.notices.append("Your Handgun and Knife are now in the multiworld - 2 random items instead!")

    def _unequip_missing(self, inv: int, slots):
        """The equipped weapon (+0x80 id, +0x84 loaded ammo; confirmed with hd_equip_watch
        2026-11-11) is always also in an inventory slot in the normal game. After the random
        start took the Handgun away, the game could still show it in Jill's hands - so if the
        equipped item isn't in her inventory any more, unequip it."""
        eq = inv + EQUIPPED_SLOT_OFFSET
        eid, eqty = SLOT.unpack(self.conn.read_bytes(eq, SLOT.size))
        if eid and all(sid != eid for sid, _ in slots[:8]):
            self.conn.write_bytes(eq, SLOT.pack(*EMPTY))
            log.info("Unequipped item %d: it isn't in Jill's inventory any more.", eid)
            eid = 0
        if eid == 0:
            self._drop_held_weapon(inv, slots)

    def _drop_held_weapon(self, inv: int, slots):
        """Nothing is equipped, but Jill may still hold (or look like she holds) a weapon: the
        game only changes her weapon when the inventory menu closes after a change. We do what
        the menu does on unequip (v0.9.8, see _unarm_step), with the menu closed, after 2 s in the
        room, and only while Jill can move. Done when she holds a weapon that isn't in her
        inventory, and once per client run after the random start (that also fixes a save
        already stuck in the Handgun pose, seed test 6)."""
        if self.unarm:
            self._unarm_step()
            return
        now = time.time()
        if now < self.next_drop_try or now - self.room_since < 2.0:
            return
        obj = self._jill()
        if not obj:
            return
        held = self._u32(obj + JILL_HELD_WEAPON)
        stray = held != 0 and not any(sid == held + 1 for sid, _ in slots[:8])
        if not stray and self.unarmed_once:
            return
        menu = struct.unpack("<ii", self.conn.read_bytes(inv + MENU_FLAGS, 4) + self.conn.read_bytes(inv + MENU_SCREEN, 4))
        if menu[0] & 0x1000 or menu[1] != 0:
            return                                      # inventory menu open
        self.next_drop_try = now + 5
        self.unarm = {"phase": "find", "since": now, "held": held, "stray": stray}
        self._unarm_step()

    def _unarm_step(self):
        """The inventory menu's own unequip, one game call per step (each on the game's thread):
          1. find the weapon archive loader (find_object, as menu 0x549B3F);
          2. switch the weapon archive to "empty hands" (weapon_arc(0, Jill+0x1580), as menu
             0x549B06 - Jill goes to a neutral pose, wep11 starts loading);
          3. poll loader_ready on loader +0x358 and +0x390 until both are done (as menu 0x549B5C);
          4. queue the weapon change (queue_weapon(0, 0), as menu 0x549BC1).
        v0.9.6/v0.9.7 skipped 1-3, so the game had to load pl01_2w01 (in wep11) from a loose file
        and crashed ("Failed open file ...pl01_2w01.lmt", seed test 6). Steps 1, 2 and 4 only run
        while Jill can move. Gives up after UNARM_TIMEOUT s."""
        st = self.unarm
        saver = self._ensure_hook()
        if saver is None or time.time() - st["since"] > UNARM_TIMEOUT:
            log.warning("Couldn't put Jill's weapon away (step %s) - it will be tried again.", st["phase"])
            self.unarm = None
            return
        if not saver.call_ready():
            return                                       # the last step hasn't run yet
        try:
            phase = st["phase"]
            if phase == "find":
                objects = self._u32(saver.address("object_list"))
                if objects:
                    saver.request_call("find_object", objects, (saver.address("weapon_object_class"),), in_control=True)
                    st["phase"] = "found"
            elif phase == "found":
                obj, jill = saver.call_result(), self._jill()
                if not obj or not jill:
                    st["phase"] = "find"
                    return
                st["obj"] = obj
                saver.request_call("weapon_arc", obj + 0x50, (0, self._u32(jill + JILL_VARIANT)), in_control=True)
                st["phase"] = "loading"
            elif phase == "loading":
                saver.request_call("loader_ready", st["obj"] + 0x358)
                st["phase"] = "ready1"
            elif phase == "ready1":
                if saver.call_result() & 0xFF:
                    saver.request_call("loader_ready", st["obj"] + 0x390)
                    st["phase"] = "ready2"
                else:
                    st["phase"] = "loading"
            elif phase == "ready2":
                jill = self._jill()
                if saver.call_result() & 0xFF and jill:
                    saver.request_call("queue_weapon", jill, (0, 0), in_control=True)
                    st["phase"] = "queued"
                else:
                    st["phase"] = "loading"
            elif phase == "queued":
                self.unarm = None
                self.unarmed_once = True
                if st["stray"]:
                    log.info("Jill was still holding weapon type %d with nothing equipped - put it away "
                             "(the same way the inventory menu does).", st["held"])
                else:
                    log.info("Random start: made sure Jill's hands are empty (nothing equipped).")
        except (AutosaveError, ProcessError) as exc:
            log.warning("Couldn't put the held weapon away: %s", exc)
            self.unarm = None

    def _room_entries(self, flags: int, number: Optional[int]) -> set:
        """ "First Visit" checks. Verified rooms use the game's saved "room visited" flag (works
        after reloads and for rooms entered while the client was closed); other rooms use the
        live room number, and we log whether their predicted flag agrees so it can be verified."""
        visited = self.conn.read_bytes(flags + VISITED[0], VISITED[1] - VISITED[0])
        self.visited_block = visited
        # Key Map shortcuts unlock with their room's visited flag (from this same read)
        self.shortcuts_unlocked = frozenset(
            name for name, (room, _f) in SHORTCUTS.items()
            if (lambda o, b: VISITED[0] <= o < VISITED[1] and visited[o - VISITED[0]] >> b & 1)(*room_visited_flag(room)))
        if self._room_flags_for is not self.room_checks:
            # the rooms' flag positions, worked out once (were recalculated every tick)
            self._room_flags = [(nb, name) + room_visited_flag(nb) for nb, name in self.room_checks.items()]
            self._room_flags_for = self.room_checks
        out = set()
        for room_nb, name, off, bit in self._room_flags:
            flag_on = bool(visited[off - VISITED[0]] >> bit & 1)
            if room_nb in ROOM_VISITED_VERIFIED:
                if flag_on:
                    out.add(name)
            elif room_nb == number and self._jill_present():
                # live method: only while Jill is actually in the game - at the title screen the
                # game also reports the Main Hall (seed test 1, 2026-11-11)
                out.add(name)
                if flag_on and room_nb not in self.flag_confirmed:
                    self.flag_confirmed.add(room_nb)
                    log.info("Room flag check: %s's predicted visited flag +%#x.%d is ON - matches.",
                             name, off, bit)
        return out

    # ------------------------------------------------------- health, traps, Death Link
    def _hp(self, obj: int) -> Tuple[int, int]:
        return struct.unpack("<ii", self.conn.read_bytes(obj + hv.JILL_HEALTH_OFFSET, 8))

    def _set_hp(self, obj: int, hp: int):
        self.conn.write_bytes(obj + hv.JILL_HEALTH_OFFSET, struct.pack("<i", hp))

    def _health(self):
        """Notice Jill dying (Death Link out) and apply received Death Links (Death Link in)."""
        obj = self._jill()
        if not obj:
            self.last_hp = None
            return
        hp, mx = self._hp(obj)
        if self.last_hp is not None and self.last_hp > 0 and hp <= 0 and time.time() >= self.ignore_death_until:
            self.jill_died = True
            self.as_room, self.as_armed, self.last_load_time = None, False, time.time()
            log.info("Jill died.")
        self.last_hp = hp
        if self.deaths_to_apply and hp > 0 and mx > 0:
            self.deaths_to_apply -= 1
            if self.death_link_kill:
                new = 0
            else:
                new = max(1, min(hp - 1, below_next_state(hp, mx)))   # exactly one health state down
            self.ignore_death_until = time.time() + 15   # a death we caused isn't sent back
            self._set_hp(obj, new)
            self.last_hp = new
            log.info("Death Link: Jill's health %d -> %d.", hp, new)
            self.notices.append("Death Link! Jill " + ("dies." if new <= 0 else "loses a health state."))

    # ------------------------------------------------------- starting box, autosave
    def _vanilla_box_slots(self, inv: int):
        """(spray slot, ribbon slot) if the item box is exactly a new game's box, else None."""
        data = self.conn.read_bytes(inv + hv.ITEM_BOX_OFFSET, SAVE_MARKER_SLOT * SLOT.size)
        used = [(i, SLOT.unpack_from(data, i * SLOT.size)) for i in range(SAVE_MARKER_SLOT)]
        used = [(i, s) for i, s in used if s[0] != 0]
        if len(used) != 2:
            return None
        spray = [i for i, s in used if s[0] == VANILLA_BOX_SPRAY]
        ribbon = [i for i, s in used if tuple(s) == VANILLA_BOX_RIBBON]
        if len(spray) != 1 or len(ribbon) != 1:
            return None
        return spray[0], ribbon[0]

    def _box_ui_open(self) -> bool:
        """The item box screen is up (menu object [[0xCF30D8]+0x40] +0x60A0 = 5, BOXDEBUG log)."""
        try:
            root = self._u32(self.flags_ptr - 0x00CF2FC8 + 0x00CF30D8)
            menu = self._u32(root + 0x40) if root else 0
            return bool(menu) and self._u32(menu + 0x60A0) == 5
        except Exception:
            return False

    def _protect_records(self, inv: int) -> bool:
        """The last two box slots hold the client's records (seed tag, delivery count) and look empty
        in the box screen, so the player can put an item there (seed test 5: the Grenade Launcher,
        Stone Ring and a mask sat there and the sort never moved them). When the box screen closes,
        move any item out of those two slots into a free slot and write the records back.
        Returns True while the box screen is open in a save already known to be ours (the seed
        check waits until it closes, so an item put there doesn't look like a foreign save)."""
        if self._box_ui_open():
            self.box_ui_was_open = True
            return self.save_known_ours
        if not self.box_ui_was_open:
            return False
        self.box_ui_was_open = False
        if not self.save_known_ours:
            return False
        base = inv + hv.ITEM_BOX_OFFSET
        for idx in (SEED_TAG_SLOT, SAVE_MARKER_SLOT):
            iid, qty = SLOT.unpack(self.conn.read_bytes(base + idx * SLOT.size, SLOT.size))
            if iid == 0:
                continue
            data = self.conn.read_bytes(base, SEED_TAG_SLOT * SLOT.size)
            free = next((i for i in range(SEED_TAG_SLOT) if SLOT.unpack_from(data, i * SLOT.size) == EMPTY), None)
            if free is None:
                log.warning("Item %d is in box slot %d (the client's record slot) and the box is full.", iid, idx + 1)
                self.notices.append(f"Box slot {idx + 1} must stay empty - make room in the box.")
                continue
            self.conn.write_bytes(base + free * SLOT.size, SLOT.pack(iid, qty))
            self.conn.write_bytes(base + idx * SLOT.size, SLOT.pack(0, 0))
            log.info("Moved item %d x%d out of box slot %d (kept for the client's records) to slot %d.",
                     iid, qty, idx + 1, free + 1)
            if idx == SEED_TAG_SLOT and self.seed_tag:
                self.conn.write_bytes(self._tag_address(inv), SLOT.pack(0, self.seed_tag))
            else:
                self._write_marker(inv)
            self.box_sort_due = time.time()           # and tidy it into place
        return False

    def _tag_address(self, inv: int) -> int:
        return inv + hv.ITEM_BOX_OFFSET + SEED_TAG_SLOT * SLOT.size

    def _save_is_ours(self, inv: int, bits: Dict[str, bool]) -> bool:
        """Is the loaded game this seed's? Box slot 255 holds {0, seed tag} (written by us).
        A game with nothing picked up yet (New Game keeps the old box records) is ours; so is an
        untagged save that has our delivery record in slot 256 (an older client, this seed). Both
        get the tag.
        Anything else - another seed's tag, an item in slot 255, or an untagged save with things
        picked up and no delivery record - is someone else's save: /adopt overrides."""
        if not self.seed_tag:
            self.save_known_ours = True
            return True
        tag_id, tag = SLOT.unpack(self.conn.read_bytes(self._tag_address(inv), SLOT.size))
        if (tag_id, tag) == (0, self.seed_tag):
            self.foreign_save = False
            self.save_known_ours = True
            return True
        mid, mcount = SLOT.unpack(self.conn.read_bytes(self._marker_address(inv), SLOT.size))
        why = None
        if self.adopt_save:
            self.adopt_save = False
        elif not any(bits.values()):
            pass        # nothing picked up yet (e.g. New Game, which keeps the old box records): ours
        elif tag_id != 0:
            why = "item box slot 255 holds an item (the client keeps this seed's tag there)"
        elif tag != 0:
            why = "it was played with a different seed"
        elif not (mid == 0 and mcount > 0):
            why = "it has pickups done but no record from this seed"
        if why is None:
            self.conn.write_bytes(self._tag_address(inv), SLOT.pack(0, self.seed_tag))
            log.info("This save now belongs to this seed (tag %d written to box slot 255).", self.seed_tag)
            self.foreign_save = False
            self.save_known_ours = True
            return True
        now = time.time()
        if not self.foreign_save or now >= self.foreign_notice_at:
            log.warning("This save isn't from this seed (%s). The client does nothing with it - no "
                        "checks, no items. Load this seed's save, or start a new game. If it really "
                        "is this seed's save, type /adopt.", why)
            self.notices.append("This save isn't from this seed - load the right save (or /adopt).")
            self.foreign_notice_at = now + 30
        self.foreign_save = True
        self.save_known_ours = False
        return False

    def _new_game_reset(self, inv: int, room: Optional[int], bits: Dict[str, bool]):
        """A NEW game (Main Hall, nothing picked up, the untouched new-game item box) has none of
        your received items - but the game leaves the old delivery record in box slot 256
        (seed test 3). So: forget it, and send everything again (starting items included)."""
        if room != START_ROOM_NUMBER or any(bits.values()) or self._vanilla_box_slots(inv) is None:
            self.fresh_handled = False
            return
        if self.fresh_handled:                 # already reset for this new game
            return
        self.fresh_handled = True
        st = self.state
        mid, mcount = SLOT.unpack(self.conn.read_bytes(self._marker_address(inv), SLOT.size))
        if st.delivered == 0 and not st.start_swapped and (mid, mcount) == (0, 0):
            return
        log.info("New game started - sending all %d received item(s) again.", st.delivered)
        if st.delivered:
            self.notices.append("New game: your received items are on their way.")
        st.delivered, st.pending, st.start_swapped = 0, None, False
        self.state_file.save(st)
        if mid == 0:
            self.conn.write_bytes(self._marker_address(inv), SLOT.pack(0, 0))
        self.as_armed, self.last_load_time = False, time.time()

    def _setup_start_box(self, inv: int, room: Optional[int], bits: Dict[str, bool]):
        """New game: the item box holds exactly a First Aid Spray and 3 Ink Ribbons. Replace the
        spray with the seed's random item and the ribbons with 99 Ink Ribbons (or, with autosave
        on, a second random item). Only that exact vanilla box is touched, so it never repeats."""
        if len(self.start_box) != 2 or room != START_ROOM_NUMBER or any(bits.values()):
            return
        found = self._vanilla_box_slots(inv)
        if found is None:
            return
        for i, new in zip(found, self.start_box):
            self.conn.write_bytes(inv + hv.ITEM_BOX_OFFSET + i * SLOT.size, SLOT.pack(*new))
        log.info("New game: item box set up with %s and %s.", self.start_box[0], self.start_box[1])

    def _ensure_hook(self):
        """Install the game-thread routine (autosave + game function calls) once per game process."""
        pid = (id(self.conn), getattr(self.conn, "pid", None))    # one install per game process
        if self.autosaver_pid == pid:
            return self.autosaver
        self.autosaver_pid, self.autosaver, self.as_deadline = pid, None, None
        try:
            key = getattr(self.conn, "build_key", None) or "hd_6699874012183562949"
            saver = self.autosaver_factory(self.conn, key)
            saver.install()
            self.autosaver = saver
            log.info("Game-thread routine ready%s.",
                     f", working through another hook at {saver.chained_to:#010x} (BhdTool or an older client)"
                     if getattr(saver, "chained_to", None) else "")
        except (AutosaveError, ProcessError) as exc:
            log.warning("Autosave / unequip are off for this game session: %s", exc)
            self.notices.append("Autosave couldn't start - see the client log.")
        return self.autosaver

    def _autosave(self, room: Optional[int]):
        """Save to the autosave slot a moment after Jill walks into a save room (not after a load)."""
        if self.autosave_slot is None:
            return
        now = time.time()
        self._ensure_hook()
        saver = self.autosaver
        if saver is None:
            return
        if self.as_deadline is not None:
            result = saver.poll()
            if result is None:
                if now > self.as_deadline:
                    saver.cancel()
                    self.as_deadline = None
                    log.warning("Autosave didn't finish in time.")
                    self.notices.append("Autosave didn't happen - save at a typewriter to be safe.")
                return
            self.as_deadline = None
            if result == 0:
                log.info("Autosaved to slot %d.", self.autosave_slot + 1)
                self.notices.append(f"Autosaved (slot {self.autosave_slot + 1}).")
            else:
                log.warning("Autosave failed: the game reported error %d.", result)
                self.notices.append("Autosave failed - save at a typewriter to be safe.")
            return
        present = self._jill_present()
        if room != self.as_room:
            # walked from one real room into another. A load (title screen, many pickup flags at
            # once) or a death resets this, so loading a save never overwrites the autosave.
            self.as_armed = (self.as_room is not None and room is not None
                             and now - self.last_load_time > 10)
            self.as_room, self.as_since = room, now
        if (self.as_armed and room in SAVE_ROOMS and present and now - self.as_since >= 2.0
                and saver.game_idle()):
            self.as_armed = False
            saver.request(self.autosave_slot)
            self.as_deadline = now + 30
            log.info("Autosaving in %s...", SAVE_ROOMS[room])

    def sort_box(self, why: str = "") -> str:
        """Sort the item box (see box_sort.py). Only while Jill is in the game, with the inventory
        menu closed and no delivery or autosave half-way; one write for the whole box."""
        inv = self.cur_inv
        if not inv or self.conn is None:
            return "The game isn't running."
        if self.state.pending is not None or self.as_deadline is not None:
            return "Busy (delivering or saving) - try again in a moment."
        menu = struct.unpack("<ii", self.conn.read_bytes(inv + MENU_FLAGS, 4) + self.conn.read_bytes(inv + MENU_SCREEN, 4))
        if menu[0] & 0x1000 or menu[1] != 0:
            return "Close the menu first."
        base = inv + hv.ITEM_BOX_OFFSET
        raw = self.conn.read_bytes(base, SEED_TAG_SLOT * SLOT.size)       # never the last 2 slots
        slots = [tuple(SLOT.unpack_from(raw, i * SLOT.size)) for i in range(SEED_TAG_SLOT)]
        new = sorted_box(slots, STACK_LIMITS)
        if new == slots:
            return "The item box is already sorted."
        data = b"".join(SLOT.pack(*s) for s in new)
        if self.conn.read_bytes(base, len(raw)) != raw:       # changed while we worked: leave it
            return "The box changed while sorting - try again."
        self.conn.write_bytes(base, data)
        log.info("Item box sorted%s (%d items).", f" ({why})" if why else "", sum(1 for s in new if s[0]))
        return "Item box sorted."

    def _box_debug(self, flags: int):
        """Research log for item box anywhere (seed test 4: F7 = "Failed open file
        nativePC\\arc\\itemv\\v.arc" - the menu tried to load an item viewer with an empty name).
        Logs the menu object's state fields whenever they change, and the room's trigger list once
        per room, so a real item box opening can be compared with F7. Read-only."""
        if not self.box_debug:
            return
        try:
            root = self._u32(self.flags_ptr - 0x00CF2FC8 + 0x00CF30D8)
            menu = self._u32(root + 0x40) if root else 0
            if menu:
                raw = self.conn.read_bytes(menu + 0x60A0, 0x40) + self.conn.read_bytes(menu + 0x6860, 0x10)
                vals = struct.unpack("<16i4i", raw)
                state = vals[:16] + vals[16:] + (self._u32(menu + 0x624C),)
                if state != self.box_debug_last and self.box_debug_lines < 600:
                    self.box_debug_lines += 1
                    log.info("BOXDEBUG menu +60a0..60dc=%s +6860..686c=%s +624c=%d", list(vals[:16]),
                             [hex(v & 0xFFFFFFFF) for v in vals[16:]], state[-1])
                    self.box_debug_last = state
            if self.box_debug_triggers_due and time.time() >= self.box_debug_triggers_due:
                self.box_debug_triggers_due = None
                mgr = flags + 0x3A0
                count = min(self._u32(mgr + 0xD4), 64)
                arr = self._u32(mgr + 0xE0)
                for i in range(count if arr else 0):
                    t = self._u32(arr + 4 * i)
                    if t:
                        log.info("BOXDEBUG room %s trigger %d @%#x: %s", f"{self.current_room:#05x}"
                                 if self.current_room is not None else "?", i, t,
                                 self.conn.read_bytes(t, 0x40).hex(" "))
        except Exception as exc:
            log.debug("box debug: %s", exc)

    def _box_reminder(self, room: Optional[int]):
        """Walking into an item box room: tell the player what's arrived in the box since last time,
        and (auto sort) sort the box. The sort starts 0.3 s after the room change and retries every
        0.5 s while she's there (seed test 4: sorting on the very frame of the room change never
        worked - the game is still busy with the door - and it was never retried)."""
        if room not in BOX_ROOM_NUMBERS:
            self.box_room_seen, self.box_sort_due = None, None
            return
        now = time.time()
        if room != self.box_room_seen:
            self.box_room_seen = room
            self.box_sort_due = now + 0.3 if self.box_auto_sort else None
            if self.state.box_unseen:
                self.notices.append("In the item box: " + box_summary(self.state.box_unseen))
                self.state.box_unseen = []
                self.state_file.save(self.state)
        if self.box_sort_due is not None and now >= self.box_sort_due:
            answer = self.sort_box("walked into an item box room")
            if answer in ("Item box sorted.", "The item box is already sorted."):
                self.box_sort_due = None
            else:
                log.debug("Auto sort waiting: %s", answer)
                self.box_sort_due = now + 0.5

    def _game_button_down(self, name: Optional[str]) -> bool:
        """Is this controller button held, as the GAME sees it? Steam Input gives the virtual pad
        only to the game, so the client's own XInput sees nothing (seed test 4: L1 did nothing).
        The game's input manager [0xD599E4] keeps the pad's XInput-style button bits at +0x198
        (button finder, 2026-11-12 03:06: L1 held = 0x100 there, 0 released). Triggers aren't
        in that word, so lt_l2 / rt_r2 still use the client's own XInput."""
        if not name or name == "off" or self.conn is None:
            return False
        parts = COMBOS.get(name, (name,))
        if any(p not in BUTTONS for p in parts):
            return False
        try:
            mgr = self._u32(self.flags_ptr - 0x00CF2FC8 + 0x00D599E4)
            if not mgr:
                return False
            held = self._u32(mgr + 0x198)
        except Exception:
            return False
        return all(held & BUTTONS[p] for p in parts)

    def open_item_box(self) -> str:
        """/itembox (or the hotkey): open the item box wherever Jill is, by queueing the same game
        event an item box uses. Only with Jill standing in a room (alive, menu closed, not just
        through a door) and no delivery / save / other game call half-way."""
        if not self.box_anywhere:
            return "Item box anywhere is off in your YAML (item_box_anywhere: save_rooms or anywhere)."
        if self.box_anywhere == 1 and self.current_room not in SAVE_ROOMS:
            return "The item box only opens in rooms with a typewriter (item_box_anywhere: save_rooms)."
        inv = self.cur_inv
        if not inv or self.conn is None:
            return "The game isn't running."
        obj = self._jill()
        if not obj or self._hp(obj)[0] <= 0:
            return "Jill isn't in the game right now."
        if time.time() - self.room_since < 1.0:
            return "Wait until Jill is in the room."
        if self.state.pending is not None or self.as_deadline is not None:
            return "Busy (delivering or saving) - try again in a moment."
        menu = struct.unpack("<ii", self.conn.read_bytes(inv + MENU_FLAGS, 4) + self.conn.read_bytes(inv + MENU_SCREEN, 4))
        if menu[0] & 0x1000 or menu[1] != 0:
            return "Close the menu first."
        saver = self._ensure_hook()
        if saver is None:
            return "The game-thread routine isn't ready - see the client log."
        if self.box_auto_sort:
            self.sort_box("opening the box anywhere")      # sorted before it opens
        try:
            saver.open_item_box()
        except (AutosaveError, ProcessError) as exc:
            log.warning("Couldn't open the item box: %s", exc)
            return f"Couldn't open the item box: {exc}"
        self.box_open_deadline = time.time() + 2
        log.info("Item box requested in room %s.", f"{self.current_room:#05x}" if self.current_room is not None else "?")
        return "Opening the item box..."

    def _box_open_poll(self):
        """Follow an item box request: done, or withdrawn if the game didn't take it within 2 s
        (a cutscene, a door...) so the box can't pop up later by surprise."""
        if self.box_open_deadline is None or self.autosaver is None:
            return
        try:
            state = self.autosaver.box_state()
            if state == 2:
                self.autosaver.clear_item_box_done()
                self.box_open_deadline = None
                log.info("Item box opened.")
            elif time.time() > self.box_open_deadline:
                self.autosaver.cancel_item_box()
                self.box_open_deadline = None
                self.notices.append("The item box can't open right now.")
        except (AutosaveError, ProcessError) as exc:
            self.box_open_deadline = None
            log.warning("Item box request: %s", exc)

    def autosave_now(self) -> str:
        """/autosave: save to the autosave slot right now (only in a save room)."""
        if self.autosave_slot is None:
            return "Autosave is off in your YAML (autosave: true)."
        if self.autosaver is None:
            return "Autosave isn't ready - is the game running? See the client log."
        if self.current_room not in SAVE_ROOMS:
            return "Only in a save room (a room with a typewriter)."
        if self.as_deadline is not None or not self.autosaver.game_idle():
            return "The game is busy saving - try again in a moment."
        self.autosaver.request(self.autosave_slot)
        self.as_deadline = time.time() + 30
        return f"Saving to slot {self.autosave_slot + 1}..."

    def _menu_open(self, inv: int) -> bool:
        menu = struct.unpack("<ii", self.conn.read_bytes(inv + MENU_FLAGS, 4) + self.conn.read_bytes(inv + MENU_SCREEN, 4))
        return bool(menu[0] & 0x1000 or menu[1] != 0) or self._box_ui_open()

    def _apply_trap(self, item: Incoming) -> bool:
        """Apply a trap to Jill. False = she isn't in the game right now (try again later)."""
        sender = item.label.split(" from ")[-1]
        if item.trap == WRONG_DOOR:
            if not self._jill_present() or self.current_room is None or not self.save_known_ours:
                return False
            if self.wrong_door.active or self.shortcut.s:
                return False                          # one at a time: wait for this one to finish
            if not self.wrong_door.start(self.current_room, sender, self.room_entries_on, self.rng):
                return False                          # she's in the Cell itself: wait until she leaves
            self.wrong_door.s["session"] = self.session_token
            self.wrong_door_restart_checked = True
            self._save_wrong_door()
            log.info("Wrong Door Trap from %s: armed.", sender)
            return True
        if item.trap in FUN_TRAPS:
            # pranks: only while Jill is really in the game (not the title screen)
            if not self._jill_present():
                return False
            self._fun_trap(item.trap, sender)
            return True
        if item.trap in ("Ammo Leak Trap", "Infinite Ammo (20s)"):
            inv = self.cur_inv
            if not inv or not self._jill_present() or self._menu_open(inv):
                return False                          # only while Jill is walking around
            if item.trap == "Ammo Leak Trap":
                self._ammo_leak(inv, sender)
            else:
                self._start_infinite_ammo(inv, sender)
            return True
        obj = self._jill()
        if not obj:
            return False
        hp, mx = self._hp(obj)
        if hp <= 0 or mx <= 0:
            return False
        if item.trap == "Damage Trap":
            # at least the set damage, and always at least one health state (TessarionAM, seed test 3:
            # a 25 % hit from full health left him on Fine)
            new = min(hp - mx * self.trap_damage_percent // 100, below_next_state(hp, mx))
            new = max(new, 0 if self.trap_can_kill else 1)
            if new <= 0:
                self.ignore_death_until = 0.0            # a trap death IS Jill's own death
            self._set_hp(obj, new)
            log.info("Damage Trap: Jill's health %d -> %d.", hp, new)
            self.notices.append("Damage Trap! " + item.label.split(" from ")[-1] + " hurt you.")
        elif item.trap == "Poison Trap":
            addr = obj + hv.JILL_POISON_OFFSET
            b = self.conn.read_bytes(addr, 1)[0]
            self.conn.write_bytes(addr, bytes([b | (1 << hv.JILL_POISON_BIT)]))
            log.info("Poison Trap: Jill is poisoned.")
            self.notices.append("Poison Trap! Find a Blue Herb.")
        elif item.trap == "Critical Damage Trap":
            # TessarionAM: rare, and puts Jill on one health. Never kills (she's already at 1 = no change).
            self._set_hp(obj, min(hp, 1))
            log.info("Critical Damage Trap: Jill's health %d -> %d.", hp, min(hp, 1))
            self.notices.append("CRITICAL DAMAGE TRAP! " + sender + " left you on 1 health.")
        return True

    def _fun_trap(self, name: str, sender: str):
        """Queue a fun trap for the client window (fun_requests) or the overlay (notices).
        Messages with a delay go to timed_notices: (due time, text, kind)."""
        now = time.time()
        log.info("%s from %s.", name, sender)
        # v0.9.9 (TessarionAM): Archipelago's own "X sent you <trap>" line is held back by the client
        # until the prank is over (fun_done), so it can't give the joke away.
        if name == "Fake Item Trap":
            have = {i.label.split(" from ")[0] for i in self.last_received}
            choices = [n for n in FAKE_ITEM_CHOICES if n not in have] or list(FAKE_ITEM_CHOICES)
            fake = self.rng.choice(choices)
            self.notices.append((f"{sender} sent you {fake}.", "received"))
            self.timed_notices.append((now + 3.0, f"...Just kidding! ({fake} was a fake item sent by {sender})",
                                       "info"))
            self.fun_done.append((now + 3.0, name))
        elif name == "Self-Destruct Trap":
            self.notices.append(("Self-Destruct Sequence Activated! Run to a safe room to survive!", "info"))
            self.timed_notices.append((now + 6.0, f"...Just kidding! (Self-Destruct Trap from {sender})", "info"))
            self.fun_done.append((now + 6.0, name))
        elif name == "Fake Death Link Trap":
            what = "dies." if self.death_link_kill else "loses a health state."
            self.notices.append(("Death Link! Jill " + what, "info"))
            self.timed_notices.append((now + 3.0, f"...Just kidding! (Fake Death Link from {sender})", "info"))
            self.fun_done.append((now + 3.0, name))
        else:
            self.fun_requests.append((name, sender))       # crash box, screen, shake: client side

    def play_game_sound(self, bank: int, sound_id: int) -> bool:
        """Queue one of the game's own sound effects (sSound 0x4E0C40, via the game-thread routine).
        False = not possible right now (no game / routine / sound system, or another call running)."""
        if not self.conn:
            return False
        saver = self._ensure_hook()
        if saver is None:
            return False
        try:
            return saver.play_sound(bank, sound_id)
        except (AutosaveError, ProcessError) as exc:
            log.warning("Couldn't play game sound %d/%d: %s", bank, sound_id, exc)
            return False

    def _flush_timed_notices(self):
        now = time.time()
        due = [n for n in self.timed_notices if n[0] <= now]
        self.timed_notices = [n for n in self.timed_notices if n[0] > now]
        for _, text, kind in due:
            self.notices.append((text, kind))

    def _ammo_leak(self, inv: int, sender: str):
        """Ammo Leak Trap: one ammo stack, picked at random from Jill's inventory and the item box
        (never the client's record slots), disappears. Loaded ammo in guns is left alone."""
        inv_base = inv + hv.INVENTORY_SLOTS_OFFSET
        box_base = inv + hv.ITEM_BOX_OFFSET
        found = []
        for i, (iid, qty) in enumerate(self._slots(inv)[:8]):
            if iid in AMMO_IDS and qty > 0:
                found.append((inv_base + i * SLOT.size, iid, qty, f"inventory slot {i + 1}"))
        box = self.conn.read_bytes(box_base, SEED_TAG_SLOT * SLOT.size)
        for i in range(SEED_TAG_SLOT):
            iid, qty = SLOT.unpack_from(box, i * SLOT.size)
            if iid in AMMO_IDS and qty > 0:
                found.append((box_base + i * SLOT.size, iid, qty, f"item box slot {i + 1}"))
        if not found:
            log.info("Ammo Leak Trap from %s: no ammo to leak.", sender)
            self.notices.append("Ammo Leak Trap from " + sender + " - but you had no ammo!")
            return
        addr, iid, qty, where = self.rng.choice(found)
        if SLOT.unpack(self.conn.read_bytes(addr, SLOT.size)) == (iid, qty):
            self.conn.write_bytes(addr, SLOT.pack(*EMPTY))
        name = AMMO_NAMES.get(iid, f"item {iid}")
        log.info("Ammo Leak Trap from %s: removed %s x%d (%s).", sender, name, qty, where)
        self.notices.append(f"Ammo Leak! {sender} took your {name} x{qty} ({where}).")

    def _start_infinite_ammo(self, inv: int, sender: str):
        self.infinite_until = time.time() + INFINITE_AMMO_SECONDS
        self.infinite_floor = {}
        log.info("Infinite Ammo from %s for %d s.", sender, INFINITE_AMMO_SECONDS)
        self.notices.append(f"Infinite Ammo for {INFINITE_AMMO_SECONDS} seconds! (from {sender})")
        self._infinite_ammo(inv)

    def _infinite_ammo(self, inv: int):
        """While Infinite Ammo runs, keep the equipped gun's loaded rounds (equipped slot +0x84, and
        the matching inventory slot) at the level it had when the effect started (or, for an empty
        gun, GUN_CAPACITY). EXPERIMENTAL: which copy the game counts down is to be confirmed."""
        if not self.infinite_until:
            return
        if time.time() >= self.infinite_until:
            self.infinite_until, self.infinite_floor = 0.0, {}
            self.notices.append("Infinite Ammo has run out.")
            log.info("Infinite Ammo ended.")
            return
        eq = inv + EQUIPPED_SLOT_OFFSET
        eid, eqty = SLOT.unpack(self.conn.read_bytes(eq, SLOT.size))
        if eid not in GUN_CAPACITY:
            return
        floor = self.infinite_floor.setdefault(eid, eqty if eqty > 0 else GUN_CAPACITY[eid])
        if eqty < floor:
            self.conn.write_bytes(eq, SLOT.pack(eid, floor))
        base = inv + hv.INVENTORY_SLOTS_OFFSET
        for i, (iid, qty) in enumerate(self._slots(inv)[:8]):
            if iid == eid and qty < floor:
                self.conn.write_bytes(base + i * SLOT.size, SLOT.pack(eid, floor))

    def _jill_present(self) -> bool:
        """True when Jill's character object exists with health > 0."""
        obj = self._jill()
        if not obj:
            return False
        try:
            return struct.unpack("<i", self.conn.read_bytes(obj + hv.JILL_HEALTH_OFFSET, 4))[0] > 0
        except Exception:
            return False

    def _jill(self) -> int:
        """Address of Jill's character object, or 0 (verified path, see
        claude/health-and-death.md). 0 at the title screen / while loading.
        Looked up once per tick (it was read 5 times per tick); calls from outside a tick (the
        item box button, shortcuts) always read it fresh."""
        if self._in_tick and self._jill_cache is not None:
            return self._jill_cache
        obj = self._read_jill()
        if self._in_tick:
            self._jill_cache = obj
        return obj

    def _read_jill(self) -> int:
        try:
            mgr = self._u32(self.char_mgr_ptr)
            if not mgr:
                return 0
            lo, hi = self._u32(mgr + 0x20), self._u32(mgr + 0x24)
            index = (hi >> 16) & 0xFFFF
            if index >= 0x40:
                return 0
            entry = mgr + 0x8B0 + index * 24
            obj = self._u32(entry)
            if not obj or self._u32(entry + 4) != lo:
                return 0
            return obj
        except Exception:
            return 0

    def _u32(self, addr: int) -> int:
        return struct.unpack("<I", self.conn.read_bytes(addr, 4))[0]

    def _defense(self, inv: int) -> Dict[int, int]:
        return {iid: struct.unpack("<i", self.conn.read_bytes(inv + off, 4))[0]
                for iid, off in hv.DEFENSE_COUNT_OFFSETS.items()}

    def _slots(self, inv: int):
        return parse_slots(self.conn.read_bytes(inv + hv.INVENTORY_SLOTS_OFFSET, GUARDED_SLOTS * SLOT.size))

    # ---------------------------------------------------------------- pickups
    def _guard(self, inv: int, bits: Dict[str, bool], slots):
        now = time.time()
        if self.last_bits is not None:
            turned_on = sum(1 for n, on in bits.items() if on and not self.last_bits[n])
            if turned_on >= LOAD_BURST:
                # several pickups at once = a save was loaded, not a pickup. Taking "vanilla"
                # items back now would remove items the player legitimately holds (seed test 2:
                # a reload set the Battery Pack count to 0). Just take the new state as given.
                log.info("A save was loaded (%d pickup flags changed at once) - not taking anything back.",
                         turned_on)
                self.pending_removals = []
                self.as_armed, self.last_load_time = False, now
                return
            for name, on in bits.items():
                was = self.last_bits[name]
                vanilla = DETECTED_PICKUPS[name][2]
                if was and not on and player_put_back(self.last_inv, slots, vanilla):
                    self.put_back.add(name)
                    log.info("You put the item back (%s). Taking it again will leave it with you.", name)
                    self.journal.write(event="put_back", location=name)
                elif on and not was:
                    log.info("Check found: %s", name)
                    self.journal.write(event="check_collected", location=name)
                    if name in self.put_back:
                        self.put_back.discard(name)
                        self.journal.write(event="vanilla_kept", location=name, why="player re-took own item")
                    else:
                        self.pending_removals.append((name, self.last_inv, self.last_def, now))
        still = []
        for name, before, before_def, t0 in self.pending_removals:
            vanilla = DETECTED_PICKUPS[name][2]
            if vanilla in NO_TAKE_BACK:
                continue                       # e.g. maps: nothing to take back
            if vanilla in hv.DEFENSE_COUNT_OFFSETS:
                result = self._take_back_count(inv, vanilla, before_def[vanilla])
                if result == "wait" and now - t0 < WAIT_FOR_VANILLA:
                    still.append((name, before, before_def, t0))
                elif result == "done":
                    self.journal.write(event="vanilla_removed", location=name)
                else:
                    log.warning("Left the %s count alone after %s.", vanilla, name)
                    self.journal.write(event="vanilla_not_removed", location=name, why=f"count {result}")
                continue
            after = self._slots(inv)
            plan = plan_removal(before, after, vanilla)
            if plan == [] and now - t0 < WAIT_FOR_VANILLA:
                still.append((name, before, before_def, t0))
                continue
            if not plan:
                why = "no item seen" if plan == [] else "unexpected inventory change"
                log.warning("Left the inventory alone after %s (%s).", name, why)
                self.journal.write(event="vanilla_not_removed", location=name, why=why)
                continue
            if self._apply(inv, plan, after):
                self.journal.write(event="vanilla_removed", location=name)
            else:
                log.warning("Couldn't take back the vanilla item for %s - left it.", name)
                self.journal.write(event="vanilla_not_removed", location=name, why="slot changed")
        self.pending_removals = still

    def _take_back_count(self, inv: int, item_id: int, before: int) -> str:
        """A vanilla dagger / battery pack was picked up: put the count back to `before`."""
        addr = inv + hv.DEFENSE_COUNT_OFFSETS[item_id]
        now = struct.unpack("<i", self.conn.read_bytes(addr, 4))[0]
        if now == before:
            return "wait"
        if now != before + 1:
            return "changed unexpectedly"
        self.conn.write_bytes(addr, struct.pack("<i", before))
        return "done" if struct.unpack("<i", self.conn.read_bytes(addr, 4))[0] == before else "write failed"

    def _apply(self, inv, plan, expected) -> bool:
        base = inv + hv.INVENTORY_SLOTS_OFFSET
        for index, (iid, qty) in plan:
            addr = base + index * SLOT.size
            if SLOT.unpack(self.conn.read_bytes(addr, SLOT.size)) != tuple(expected[index]):
                return False
            self.conn.write_bytes(addr, SLOT.pack(iid, qty))
            if SLOT.unpack(self.conn.read_bytes(addr, SLOT.size)) != (iid, qty):
                return False
        return True

    # ---------------------------------------------------------------- deliveries
    def _deliver(self, inv: int, received: List[Incoming]):
        st = self.state
        if st.pending is not None:
            self._resolve_pending(inv)
        if st.delivered >= len(received) or time.time() < self.next_delivery_try:
            return
        if self.as_deadline is not None:
            return          # an autosave is copying the game: no item may land halfway through
        item = received[st.delivered]
        if item.trap:
            if item.index in st.applied_traps:            # e.g. re-sent after loading a save
                self._finish(item, "(trap already applied earlier)")
                return
            if not self._apply_trap(item):
                self.next_delivery_try = time.time() + 2    # Jill isn't in the game yet
                return
            st.applied_traps.append(item.index)
            self._finish(item, "trap applied")
            return
        if item.game_id is None:
            log.error("Can't deliver %s: no in-game item for it yet. Noted in the client state file.", item.label)
            st.undeliverable.append({"index": item.index, "label": item.label})
            st.delivered += 1
            self.state_file.save(st)
            return
        qty = self.key_qty.get(item.game_id) or delivery_quantity(item.game_id)   # keys: the seed's door count
        if item.game_id == DEFENCE_BUNDLE:
            # several counters in one delivery; "multi" lets _resolve_pending finish a half-done one
            multi = []
            for iid, add in DEFENCE_BUNDLE_CONTENTS.items():
                addr = inv + hv.DEFENSE_COUNT_OFFSETS[iid]
                old = struct.unpack("<i", self.conn.read_bytes(addr, 4))[0]
                multi.append([addr, old, old + add])
            st.pending = {"index": item.index, "game_id": item.game_id, "multi": multi}
            self.state_file.save(st)
            for addr, _, new in multi:
                self.conn.write_bytes(addr, struct.pack("<i", new))
            self._finish(item, "Defence Bundle (daggers %d, battery packs %d)" % (multi[0][2], multi[1][2]))
            return
        if item.game_id in hv.DEFENSE_COUNT_OFFSETS:
            addr = inv + hv.DEFENSE_COUNT_OFFSETS[item.game_id]
            new = struct.unpack("<i", self.conn.read_bytes(addr, 4))[0] + qty
            st.pending = {"index": item.index, "address": addr, "game_id": item.game_id, "count": new}
            self.state_file.save(st)
            self.conn.write_bytes(addr, struct.pack("<i", new))
            self._finish(item, f"defensive items (now {new})")
            return
        if item.game_id in HIDDEN_SLOT_ITEMS:
            hidden = inv + hv.HIDDEN_SLOTS_OFFSET
            if SLOT.unpack(self.conn.read_bytes(hidden, SLOT.size)) == EMPTY:
                st.pending = {"index": item.index, "address": hidden, "game_id": item.game_id, "qty": qty}
                self.state_file.save(st)
                self.conn.write_bytes(hidden, SLOT.pack(item.game_id, qty))
                self._finish(item, "Jill's hidden Lock Pick slot")
                return
        st.pending = {"index": item.index, "address": None, "game_id": item.game_id, "qty": qty,
                      "tag": delivery_tag(item)}
        self.state_file.save(st)
        try:
            direct = item.starting or item.game_id in DIRECT_INVENTORY_ITEMS
            if self.destination == INVENTORY_THEN_BOX or direct:
                try:
                    d = deliver_to_inventory(self.conn, inv, item.game_id, qty, self.journal,
                                             reason=delivery_tag(item))
                    self._finish(item, f"Jill's inventory, slot {d.slot_number}")
                    return
                except InventoryFull:
                    name = item.label.split(" from ")[0]
                    if direct:
                        # must NOT go to a box (it may be what you need to reach one): wait for room
                        st.pending = None
                        self.state_file.save(st)
                        log.warning("Inventory full - make room for %s (it can't go to the item box).", item.label)
                        self.notices.append(f"Make room in your inventory: {name} is waiting for you.")
                        self.next_delivery_try = time.time() + 15
                        return
                    log.info("Inventory full - %s goes to the item box instead.", item.label)
                    self.notices.append(f"Inventory full: {name} went to the item box.")
            d = deliver_to_box(self.conn, inv, item.game_id, qty, self.journal, reason=delivery_tag(item),
                               stack_limit=STACK_LIMITS.get(item.game_id))
        except DeliveryError as exc:
            st.pending = None
            self.state_file.save(st)
            log.warning("Couldn't deliver %s yet: %s Retrying in 10 s.", item.label, exc)
            self.next_delivery_try = time.time() + 10
            return
        self.state.box_unseen.append(item.label.split(" from ")[0] + (f" ({qty})" if qty > 1 else ""))
        self._finish(item, f"item box slot {d.slot_number}")

    def _finish(self, item: Incoming, where: str):
        self.state.delivered = item.index + 1
        self.state.pending = None
        self.state_file.save(self.state)
        if self.cur_inv:
            self._write_marker(self.cur_inv)
        log.info("Received %s -> %s", item.label, where)

    def _marker_address(self, inv: int) -> int:
        return inv + hv.ITEM_BOX_OFFSET + SAVE_MARKER_SLOT * SLOT.size

    def _check_save_marker(self, inv: int, bits: Dict[str, bool]):
        """Received items live in the game's memory, so loading an older save (e.g. after dying)
        wipes the ones delivered since that save (seed test 2, 2026-11-11). We keep the number of
        delivered items in the LAST item box slot as {0, count}: it's saved with the game, so after
        a load it tells us exactly what that save already has, and we deliver the rest again."""
        st = self.state
        if st.pending is not None:
            self._resolve_pending(inv)          # settle an interrupted delivery first
        mid, mcount = SLOT.unpack(self.conn.read_bytes(self._marker_address(inv), SLOT.size))
        if self.force_marker:                    # /redeliver: the player's choice wins
            self.force_marker = False
            self._write_marker(inv)
            return
        if mid != 0 or mcount < 0:
            if not self.marker_warned:
                self.marker_warned = True
                log.warning("The last item box slot (256) holds an item, so the client can't track "
                            "deliveries in your save. Please keep box slot 256 empty.")
                self.notices.append("Please keep item box slot 256 empty (the client uses it).")
            return
        if mcount == st.delivered:
            return
        if mcount < st.delivered:
            new_game = not any(bits.values())
            if mcount == 0 and not new_game:
                # an older save from before the marker existed, or the marker was cleared
                if not self.marker_warned:
                    self.marker_warned = True
                    log.warning("This save has no delivery record. If you're missing items, type "
                                "/redeliver 0 (everything is sent again; you may get duplicates).")
                    self.notices.append("Missing items after loading? Type /redeliver 0 in the client.")
                self._write_marker(inv)
                return
            log.info("Loaded a save made after %d received items (client had delivered %d) - "
                     "sending items %d onwards again.", mcount, st.delivered, mcount)
            self.notices.append(f"Earlier save loaded: re-sending {st.delivered - mcount} item(s).")
        else:
            log.info("This save already has %d received items (client record said %d) - "
                     "continuing from there.", mcount, st.delivered)
        st.delivered = mcount
        self.state_file.save(st)
        self.as_armed, self.last_load_time = False, time.time()     # a save was loaded

    def _write_marker(self, inv: int):
        addr = self._marker_address(inv)
        mid, _ = SLOT.unpack(self.conn.read_bytes(addr, SLOT.size))
        if mid == 0:
            self.conn.write_bytes(addr, SLOT.pack(0, self.state.delivered))

    def _resolve_pending(self, inv: int):
        """The client stopped mid-delivery last time: was the write done?"""
        p = self.state.pending
        landed = False
        if "multi" in p:
            # finish whichever counter wasn't written yet; a counter that moved otherwise is left alone
            for addr, old, new in p["multi"]:
                if struct.unpack("<i", self.conn.read_bytes(addr, 4))[0] == old:
                    self.conn.write_bytes(addr, struct.pack("<i", new))
            landed = True
        elif "count" in p:
            landed = struct.unpack("<i", self.conn.read_bytes(p["address"], 4))[0] == p["count"]
        elif p.get("address"):
            landed = SLOT.unpack(self.conn.read_bytes(p["address"], SLOT.size)) == (p["game_id"], p["qty"])
        else:
            # find the box slot chosen for THIS delivery (journal "intent" carries its unique tag)
            intents = [e for e in self.journal.entries()
                       if e.get("event") == "intent" and e.get("reason") == p.get("tag")]
            if intents:
                address = intents[-1]["address"]
                expect = tuple(intents[-1].get("expect") or (p["game_id"], p["qty"]))   # stacks: old+new
                landed = SLOT.unpack(self.conn.read_bytes(address, SLOT.size)) == expect
        if landed:
            self.state.delivered = p["index"] + 1
            log.info("Item %d had already been delivered before the client stopped.", p["index"])
        self.state.pending = None
        self.state_file.save(self.state)
        if landed:
            self._write_marker(inv)

    def redeliver_from(self, index: int):
        """After reloading an older save: deliver everything from received item `index` again."""
        self.state.delivered = max(0, index)
        self.state.pending = None
        self.state_file.save(self.state)
        self.force_marker = True


AMMO_NAMES = {16: "Grenade Shells", 17: "Handgun Magazine", 18: "Shotgun Shells", 19: "Acid Shells",
              20: "Incendiary Shells", 25: "Magnum Rounds"}


class EndingWatcher:
    """Goal "complete_game": the helicopter ending.

    Seen in TessarionAM's full run (2026-11-10): after the ending at the Heliport (room 0x303)
    the game drops back to a fresh state - room 0x106 (Main Hall) with an EMPTY inventory -
    while the credits/title load. We call the game complete when that happens within
    ENDING_WINDOW seconds of last being at the Heliport. (Dying at the Heliport reloads a
    save instead, which has items; /escaped stays as the manual backup.)
    UNVERIFIED as a goal signal until the seed test - it is what the log showed once.
    """
    HELIPORT, RESET_ROOM, ENDING_WINDOW = 0x303, 0x106, 600.0

    def __init__(self):
        self.last_heliport: Optional[float] = None

    def update(self, room: Optional[int], inventory_empty: bool, now: float) -> bool:
        if room == self.HELIPORT:
            self.last_heliport = now
            return False
        return (self.last_heliport is not None and room == self.RESET_ROOM and inventory_empty
                and now - self.last_heliport <= self.ENDING_WINDOW)


def delivery_tag(item: Incoming) -> str:
    """Unique per received item, so a restart can tell two identical herbs apart."""
    return f"AP item #{item.index}: {item.label}"


class GameNotReady(Exception):
    pass


def connect_to_game():
    conn = ProcessConnection("bhd.exe", writable=True)
    if not conn.connect():
        raise GameNotReady("bhd.exe is not running")
    build = hv.find_build(sha256_of(conn.exe_path))
    if build is None or not build.verified or build.key not in hv.FLAGS_POINTER:
        conn.disconnect()
        raise GameNotReady("this bhd.exe version isn't supported yet")
    inv_ptr = build.inventory_pointer - hv.DEFAULT_IMAGE_BASE + conn.module_base
    flags_ptr = hv.FLAGS_POINTER[build.key] - hv.DEFAULT_IMAGE_BASE + conn.module_base
    log.info("Game version: %s", build.description)
    conn.build_key = build.key
    return conn, inv_ptr, flags_ptr
