"""
Steam version - LOAD MENU WATCH (2026-11-14). For "load the autosave automatically after a death".
Read-only, except F10 (one optional write, see step 3).

What we know from the code dump (claude/autoload-and-l1-research.md and 2026-11-14 notes):
  * The menu manager is [0x00CF30D8]. Its +0x10C holds the open save/load menu object.
    0x4F7B40(0) opens the LOAD menu (class vtable 0x00C38320, update 0x52E400);
    0x4F7B40(1) opens the SAVE menu (typewriter, vtable 0x00C38238). The title screen's "Load"
    calls 0x4F7B40(0) from 0x469031; the typewriter calls 0x4F7B40(1) from 0x6682A5.
  * The Load menu's state is at +0x25C (12 states); state 7 loads slot [+0x260] through 0x48FC10.
This tool shows that menu object and its state live, so we can see which state means "choosing a
slot" and test whether setting slot + state 7 loads the save with no button presses.

Steps (use a spare save; the autosave slot is slot 8 if the client made one):
  1. Start it, then in the game: die (or quit to the title), go to Load, move the cursor over
     a few slots, back out, open Load again, load a save. Then use a typewriter and back out.
     Press Home whenever something happens on screen (it just adds a mark to the log).
  2. Send Claude hd_load_menu_watch_output.txt.
  3. Only when Claude asks: with the Load menu open and NOT loading, press F10 - the tool sets the
     slot to the number you typed at the start and the state to 7. Does the save load?
  4. Only when Claude asks: at the title screen's main menu, F11 does what picking "Load Game"
     does (the title screen switches itself to its Load mode), then loads the slot by itself as
     soon as the slots are showing. F10 still works on its own.
Output: hd_load_menu_watch_output.txt.
"""
import struct
import sys
import time

from client import hd_versions as hv
from client.pc_process import ProcessConnection, ProcessError
from client.window_mode import key_held
from hd_event_recorder import beep
from hd_inventory import sha256_of
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "hd_load_menu_watch_output.txt"
MENU_MANAGER = 0x00CF30D8
MENU_SLOT = 0x10C
LOAD_MENU_VTABLE, SAVE_MENU_VTABLE = 0x00C38320, 0x00C38238
STATE, SLOT, ERROR = 0x25C, 0x260, 0x274
# 2026-11-15 (code dump 0x52FC30..0x52FE4D): the menu task runs in phases at +0x254: 0 set-up -> 1
# (clears the fields) -> 2 = WAITING to be opened (byte +0x26E) -> 3 -> 4 = shows the slots (inner
# state machine, update 0x52E400) -> 5 done (+0x270 = result) or 7 error -> back to 1 -> 2.
# The 14:18 log showed phase 2 at the title, so "idle" is phase 2 (not 6 as first thought).
PHASE, OPENED, RESULT, SUBSTATE = 0x254, 0x26E, 0x270, 0x258
PHASE_SLOTS = 4
LOAD_STATE, CHOOSING_STATE = 7, 4
# The title screen (class vtable 0x00C21BE8, built by 0x466D70, update 0x469310 = jmp [this+0xB8]).
# It runs one "mode" at a time: +0xB8 = handler, +0xBC = mode number, +0xC0 = -1, +0xD8 = step.
# Handlers are the table at 0x00CB6530 (mode n = [0xCB6530 + 4n]). Mode 4 (0x467DB0) is the main
# menu; picking menu item 0 (0x467E3E) switches to mode 6 (0x468120) = Load Game: it fades, hides
# the title menu, opens the Load menu through the manager (0x4F9530), then waits for the result
# (0x4F8A00: 1 = loaded -> mode 12 starts the game, 2/3 = backed out).
TITLE_VTABLE, TITLE_MODES = 0x00C21BE8, 0x00CB6530
T_HANDLER, T_MODE, T_C0, T_STEP = 0xB8, 0xBC, 0xC0, 0xD8
MODE_MAIN_MENU, MODE_LOAD = 4, 6
AUTO_TIMEOUT = 20.0
VK_HOME, VK_F10, VK_F11 = 0x24, 0x79, 0x7A


def say(text):
    line = f"{time.strftime('%H:%M:%S')} {text}"
    print(line, flush=True)
    with OUTPUT.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def kind(vtable: int, shift: int) -> str:
    if vtable == LOAD_MENU_VTABLE + shift:
        return "LOAD menu"
    if vtable == SAVE_MENU_VTABLE + shift:
        return "SAVE menu"
    return f"other menu (vtable {vtable:#x})"


def is_title(conn, address: int, shift: int) -> bool:
    """True when `address` is the title screen object: its mode handler matches the mode table."""
    try:
        raw = conn.read_bytes(address, 0xE8)
    except Exception:
        return False
    vt, handler, mode = (struct.unpack_from("<I", raw, 0)[0], struct.unpack_from("<I", raw, T_HANDLER)[0],
                         struct.unpack_from("<i", raw, T_MODE)[0])
    if vt != TITLE_VTABLE + shift or not 0 <= mode < 16:
        return False
    expected = struct.unpack("<I", conn.read_bytes(TITLE_MODES + shift + 4 * mode, 4))[0]
    return handler == expected


def find_title(conn, shift: int):
    """Address of the title screen object, or None (it only exists on the title screen)."""
    pattern = struct.pack("<I", TITLE_VTABLE + shift)
    for base, size in conn.readable_regions(0x7FFF0000):
        off = 0
        while off < size:
            n = min(0x100000, size - off)
            try:
                data = conn.read_bytes(base + off, n)
            except Exception:
                break
            i = data.find(pattern)
            while i != -1:
                address = base + off + i
                if address % 4 == 0 and is_title(conn, address, shift):
                    return address
                i = data.find(pattern, i + 1)
            off += n
    return None


def title_mode(conn, title: int):
    mode, = struct.unpack("<i", conn.read_bytes(title + T_MODE, 4))
    step, = struct.unpack("<i", conn.read_bytes(title + T_STEP, 4))
    return mode, step


def open_load_from_title(conn, title: int, shift: int) -> None:
    """What the title's main menu does for "Load Game" (0x467E3E): switch to mode 6."""
    handler = struct.unpack("<I", conn.read_bytes(TITLE_MODES + shift + 4 * MODE_LOAD, 4))[0]
    conn.write_bytes(title + T_STEP, struct.pack("<i", 0))
    conn.write_bytes(title + T_C0, struct.pack("<i", -1))
    conn.write_bytes(title + T_MODE, struct.pack("<i", MODE_LOAD))
    conn.write_bytes(title + T_HANDLER, struct.pack("<I", handler))     # last: the game calls this


def snapshot(conn, shift):
    """(menu address, vtable, state, slot, error) or None when no save/load menu is open."""
    mgr = struct.unpack("<I", conn.read_bytes(MENU_MANAGER + shift, 4))[0]
    if not mgr:
        return None
    menu = struct.unpack("<I", conn.read_bytes(mgr + MENU_SLOT, 4))[0]
    if not menu:
        return None
    vt = struct.unpack("<I", conn.read_bytes(menu, 4))[0]
    state, slot = struct.unpack("<ii", conn.read_bytes(menu + STATE, 8))
    error = struct.unpack("<i", conn.read_bytes(menu + ERROR, 4))[0]
    phase = struct.unpack("<i", conn.read_bytes(menu + PHASE, 4))[0]
    return menu, vt, state, slot, error, phase


def main() -> int:
    with OUTPUT.open("a", encoding="utf-8") as f:   # every run is kept (2026-11-15)
        f.write("\n" + f"=== Load menu watch {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    print(__doc__)
    answer = (sys.argv[1] if len(sys.argv) > 1 else
              input("Slot for the F10 test (1-8, Enter = 8 = the autosave slot): ")).strip() or "8"
    try:
        test_slot = int(answer) - 1
        assert 0 <= test_slot <= 7
    except (ValueError, AssertionError):
        print("Type a number from 1 to 8.")
        return 1
    try:
        conn = ProcessConnection("bhd.exe", writable=True)
        if not conn.connect():
            say("bhd.exe is not running.")
            return 1
        build = hv.find_build(sha256_of(conn.exe_path))
        if build is None or build.key.replace("_steamless", "") != "hd_6699874012183562949":
            say("This tool only knows the Sept 2026 Steam build.")
            return 1
        shift = conn.module_base - hv.DEFAULT_IMAGE_BASE
        say(f"Watching the save/load menu. Home = mark, F11 = open the Load menu, F10 = load slot {test_slot + 1} (only when asked).")
        last, prev_keys, start, prev_f11 = "start", (False, False), time.time(), False
        title, last_title, auto_until = None, "start", 0.0
        while True:
            try:
                snap = snapshot(conn, shift)
            except ProcessError:
                if not conn.is_connected():
                    raise
                snap = None             # the menu object was freed between two reads
            if snap is None:
                text = "no save/load menu open"
            else:
                menu, vt, state, slot, error, phase = snap
                text = (f"{kind(vt, shift)} at {menu:#x}: phase {phase}, state {state}, slot {slot + 1}, "
                        f"error {error}")
            if text != last:
                say(f"[{time.time() - start:7.1f}s] {text}")
                last = text
            if title is not None and not is_title(conn, title, shift):
                title = None
            if title is not None:
                t_text = "title screen: mode %d, step %d" % title_mode(conn, title)
            else:
                t_text = "no title screen known"
            if t_text != last_title:
                say(f"[{time.time() - start:7.1f}s] {t_text}")
                last_title = t_text
            if auto_until and snap is not None and snap[1] == LOAD_MENU_VTABLE + shift \
                    and snap[5] == PHASE_SLOTS and snap[2] == CHOOSING_STATE:
                say(f"F11 (auto): slots are showing; writing slot {test_slot + 1} and state {LOAD_STATE}.")
                conn.write_bytes(snap[0] + SLOT, struct.pack("<i", test_slot))
                conn.write_bytes(snap[0] + STATE, struct.pack("<i", LOAD_STATE))
                auto_until = 0.0
                beep()
            elif auto_until and time.time() > auto_until:
                say("F11 (auto): the slots never showed within 20 s - stopped waiting.")
                auto_until = 0.0
            home, f10, f11 = key_held(VK_HOME), key_held(VK_F10), key_held(VK_F11)
            if f11 and not prev_f11:
                if title is None:
                    say("F11: looking for the title screen...")
                    title = find_title(conn, shift)
                if title is None:
                    say("F11: no title screen found - nothing written. Be on the title screen's menu.")
                else:
                    mode, step = title_mode(conn, title)
                    if mode != MODE_MAIN_MENU:
                        say(f"F11: the title screen is in mode {mode}, not its main menu (4) - nothing written.")
                    else:
                        say(f"F11: title at {title:#x}: switching mode 4 -> 6 (Load Game); will load slot "
                            f"{test_slot + 1} when the slots show.")
                        open_load_from_title(conn, title, shift)
                        auto_until = time.time() + AUTO_TIMEOUT
                        beep()
            prev_f11 = f11
            if home and not prev_keys[0]:
                say(">>> mark")
                beep()
            if f10 and not prev_keys[1]:
                if snap is None or snap[1] != LOAD_MENU_VTABLE + shift:
                    say("F10: the Load menu isn't open - nothing written.")
                elif snap[5] != PHASE_SLOTS:
                    say(f"F10: the Load menu isn't showing its slots (phase {snap[5]}) - nothing written. "
                        "Open it first (Load, or F11).")
                elif snap[2] == LOAD_STATE:
                    say("F10: it's already loading - nothing written.")
                else:
                    menu = snap[0]
                    say(f"F10: was state {snap[2]}; writing slot {test_slot + 1} and state {LOAD_STATE}.")
                    conn.write_bytes(menu + SLOT, struct.pack("<i", test_slot))
                    conn.write_bytes(menu + STATE, struct.pack("<i", LOAD_STATE))
                    beep()
            prev_keys = (home, f10)
            time.sleep(0.05)
    except ProcessError as exc:
        say(f"Game closed or unreadable: {exc}")
        return 0
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
