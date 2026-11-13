"""
Fun traps (TessarionAM's picks, 2026-11-12): harmless pranks done by the CLIENT on the PC, never in the
game's memory. They need the game in windowed / borderless mode to be seen over it.

  * fake_crash(pid)   - a real Windows error box worded like the game's own "Fatal error" (the
                        one seen in seed test 4), in a separate thread so nothing waits for it.
  * shake(pid)        - moves the game window back and forth for about a second, then puts it
                        back exactly where it was.
The "To Be Continued..." screen lives in overlay.py (it needs the overlay's tkinter thread), and
the fake item / Death Link messages are plain overlay lines (game_bridge.py).
Everything here fails silently off Windows (tests) or when the window can't be found.
"""
from __future__ import annotations

import logging
import random
import threading
import time
from typing import Callable, Optional

log = logging.getLogger("RE1HDClient")

# Claude's wording: the dialog the game showed in seed test 4 was "Fatal error." followed by
# "Failed open file <game folder>\\nativePC\\arc\\itemv\\v.arc 2". The title is a best guess
# (send a screenshot of a real one if it differs).
CRASH_TITLE = "Resident Evil"
CRASH_FILE = r"nativePC\arc\itemv\v.arc"

MB_OK, MB_ICONERROR, MB_SYSTEMMODAL, MB_SETFOREGROUND, MB_TOPMOST = 0x0, 0x10, 0x1000, 0x10000, 0x40000


def game_folder(pid: int) -> str:
    """The folder bhd.exe runs from (for a realistic path in the fake error), or a stand-in."""
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, pid)          # PROCESS_QUERY_LIMITED_INFORMATION
        if h:
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(1024)
            ok = k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
            k32.CloseHandle(h)
            if ok:
                return buf.value.rsplit("\\", 1)[0]
    except Exception:
        pass
    return r"C:\Program Files (x86)\Steam\steamapps\common\Resident Evil Biohazard HD REMASTER"


def crash_text(folder: str) -> str:
    return f"Fatal error.\n\nFailed open file {folder}\\{CRASH_FILE} 2"


def fake_crash(pid: int, after: Optional[Callable[[], None]] = None) -> bool:
    """Show the fake error box (non-blocking). `after` runs once the player clicks OK."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
    except Exception:
        return False
    text = crash_text(game_folder(pid))

    def run():
        try:
            user32.MessageBoxW(None, text, CRASH_TITLE,
                               MB_OK | MB_ICONERROR | MB_SYSTEMMODAL | MB_SETFOREGROUND | MB_TOPMOST)
        except Exception:
            log.debug("Fake crash box failed", exc_info=True)
        if after:
            after()

    threading.Thread(target=run, name="RE1HD fake crash", daemon=True).start()
    return True


def shake_offsets(seconds: float = 1.2, amplitude: int = 16, step: float = 0.016, seed=None):
    """(dx, dy) per frame: a random jolt that dies down, ending at (0, 0)."""
    rnd = random.Random(seed)
    n = max(1, int(seconds / step))
    out = []
    for i in range(n):
        fade = 1.0 - i / n
        a = amplitude * fade
        out.append((int(rnd.uniform(-a, a)), int(rnd.uniform(-a, a) * 0.6)))
    out.append((0, 0))
    return out


def shake(pid: int, seconds: float = 1.2, amplitude: int = 16) -> bool:
    """Shake the game window (background thread). False if the window isn't found."""
    try:
        import ctypes
        from ctypes import wintypes
        from .window_mode import find_game_window
        user32 = ctypes.windll.user32
    except Exception:
        return False
    hwnd = find_game_window(pid)
    if not hwnd:
        return False
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    x0, y0 = r.left, r.top
    SWP = 0x0001 | 0x0004 | 0x0010                    # NOSIZE | NOZORDER | NOACTIVATE

    def run():
        try:
            for dx, dy in shake_offsets(seconds, amplitude):
                user32.SetWindowPos(hwnd, None, x0 + dx, y0 + dy, 0, 0, SWP)
                time.sleep(0.016)
        finally:
            user32.SetWindowPos(hwnd, None, x0, y0, 0, 0, SWP)

    threading.Thread(target=run, name="RE1HD shake", daemon=True).start()
    return True
