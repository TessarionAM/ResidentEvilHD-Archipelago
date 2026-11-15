"""
Autoload after a death (option autoload_after_death, EXPERIMENTAL; needs autosave).

After Jill dies the game goes back to the title screen. The client then does what picking
"Load Game" does and loads the autosave slot, so the player is straight back in the last save
room. Proven by hand with dev\\hd_load_menu_watch.py F11 (2026-11-15, TessarionAM: worked twice).

FOUND BY US in the Sept 2026 Steam build (claude/test-02-autoload-results.md):
  * Title screen object: vtable 0x00C21BE8, built by 0x466D70, update 0x469310 = jmp [this+0xB8].
    It runs one "mode" at a time: +0xB8 handler, +0xBC mode, +0xC0 = -1, +0xD8 step.
    Handlers are the table at 0x00CB6530 (mode n = [0xCB6530 + 4n]).
    Mode 4 (0x467DB0) = the main menu. Its item 0 (0x467E3E) switches to mode 6 (0x468120) =
    Load Game: fade, hide the title menu, open the Load menu (0x4F9530(0)), then wait for the
    result (0x4F8A00) and start the game.
  * Load menu: [0x00CF30D8] + 0x10C, vtable 0x00C38320. Phase +0x254: 2 = waiting to be opened,
    4 = showing the slots. Inner state +0x25C: 4 = choosing a slot; writing slot +0x260 (0-7)
    and then state 7 loads that slot (0x48FC10).
Nothing is written unless the title is in its main menu (mode 4) and its handler matches the
game's own table, and the slot is only written while the Load menu shows its slots.
"""
import struct
import time
from typing import Optional

TITLE_VTABLE, TITLE_MODES = 0x00C21BE8, 0x00CB6530
T_HANDLER, T_MODE, T_C0, T_STEP = 0xB8, 0xBC, 0xC0, 0xD8
TITLE_SIZE = 0xE8
MODE_MAIN_MENU, MODE_LOAD = 4, 6
MENU_MANAGER, MENU_SLOT = 0x00CF30D8, 0x10C
LOAD_MENU_VTABLE = 0x00C38320
PHASE, STATE, SLOT = 0x254, 0x25C, 0x260
PHASE_SLOTS, CHOOSING, LOAD = 4, 4, 7
SCAN_EVERY = 2.0          # seconds between searches for the title object
OPEN_TIMEOUT = 20.0       # mode 6 -> slots showing
GIVE_UP_AFTER = 180.0     # armed, but never reached the title's main menu
CHUNK = 0x100000


class AutoLoader:
    """One per game connection. `arm()` after a death; `tick()` every client tick while Jill is
    not in the game. Returns a notice string when something happens, else None."""

    def __init__(self, conn, shift: int, slot: int, log=None):
        self.conn, self.shift, self.slot, self.log = conn, shift, slot, log
        self.armed_at: Optional[float] = None
        self.title: Optional[int] = None
        self.next_scan = 0.0
        self.opened_at: Optional[float] = None
        self.last_mode = None

    # ------------------------------------------------------------------ helpers
    def _u32(self, address: int) -> int:
        return struct.unpack("<I", self.conn.read_bytes(address, 4))[0]

    def _i32(self, address: int) -> int:
        return struct.unpack("<i", self.conn.read_bytes(address, 4))[0]

    def _info(self, text: str):
        if self.log:
            self.log.info(text)

    def is_title(self, address: int) -> bool:
        try:
            raw = self.conn.read_bytes(address, TITLE_SIZE)
        except Exception:
            return False
        vt = struct.unpack_from("<I", raw, 0)[0]
        handler = struct.unpack_from("<I", raw, T_HANDLER)[0]
        mode = struct.unpack_from("<i", raw, T_MODE)[0]
        if vt != TITLE_VTABLE + self.shift or not 0 <= mode < 16:
            return False
        try:
            return handler == self._u32(TITLE_MODES + self.shift + 4 * mode)
        except Exception:
            return False

    def find_title(self) -> Optional[int]:
        pattern = struct.pack("<I", TITLE_VTABLE + self.shift)
        for base, size in self.conn.readable_regions(0x7FFF0000):
            off = 0
            while off < size:
                n = min(CHUNK, size - off)
                try:
                    data = self.conn.read_bytes(base + off, n)
                except Exception:
                    break
                i = data.find(pattern)
                while i != -1:
                    address = base + off + i
                    if address % 4 == 0 and self.is_title(address):
                        return address
                    i = data.find(pattern, i + 1)
                off += n
        return None

    def load_menu(self) -> Optional[int]:
        mgr = self._u32(MENU_MANAGER + self.shift)
        if not mgr:
            return None
        menu = self._u32(mgr + MENU_SLOT)
        if not menu or self._u32(menu) != LOAD_MENU_VTABLE + self.shift:
            return None
        return menu

    # ------------------------------------------------------------------ control
    @property
    def armed(self) -> bool:
        return self.armed_at is not None

    def arm(self):
        self.armed_at, self.opened_at, self.title, self.last_mode = time.time(), None, None, None
        self.next_scan = 0.0
        self._info("Autoload: armed (Jill died).")

    def disarm(self, why: str = ""):
        if self.armed_at is not None and why:
            self._info(f"Autoload: stopped ({why}).")
        self.armed_at, self.opened_at, self.title = None, None, None

    def tick(self) -> Optional[str]:
        """Call while Jill isn't in the game (title screen / loading)."""
        if self.armed_at is None:
            return None
        now = time.time()
        if self.opened_at is not None:
            return self._wait_for_slots(now)
        if now - self.armed_at > GIVE_UP_AFTER:
            self.disarm("the title screen's menu never came up")
            return "Autoload gave up - load your save yourself."
        if self.title is not None and not self.is_title(self.title):
            self.title = None
        if self.title is None:
            if now < self.next_scan:
                return None
            self.next_scan = now + SCAN_EVERY
            self.title = self.find_title()
            if self.title is None:
                return None
        mode = self._i32(self.title + T_MODE)
        if mode != self.last_mode:
            self._info(f"Autoload: title screen mode {mode}.")
            self.last_mode = mode
        if mode != MODE_MAIN_MENU:
            return None
        handler = self._u32(TITLE_MODES + self.shift + 4 * MODE_LOAD)
        self.conn.write_bytes(self.title + T_STEP, struct.pack("<i", 0))
        self.conn.write_bytes(self.title + T_C0, struct.pack("<i", -1))
        self.conn.write_bytes(self.title + T_MODE, struct.pack("<i", MODE_LOAD))
        self.conn.write_bytes(self.title + T_HANDLER, struct.pack("<I", handler))   # last
        self.opened_at = now
        self._info("Autoload: title switched to Load Game.")
        return None

    def _wait_for_slots(self, now: float) -> Optional[str]:
        if now - self.opened_at > OPEN_TIMEOUT:
            self.disarm("the Load menu never showed its slots")
            return "Autoload didn't finish - load your save yourself."
        menu = self.load_menu()
        if menu is None:
            return None
        phase, state = self._i32(menu + PHASE), self._i32(menu + STATE)
        if phase != PHASE_SLOTS or state != CHOOSING:
            return None
        self.conn.write_bytes(menu + SLOT, struct.pack("<i", self.slot))
        self.conn.write_bytes(menu + STATE, struct.pack("<i", LOAD))
        self.disarm()
        self._info(f"Autoload: loading slot {self.slot + 1}.")
        return f"Loading your autosave (slot {self.slot + 1})..."
