"""
Borderless fullscreen for the game window (TessarionAM, 2026-11-11).

The game's own fullscreen is exclusive: nothing (not even our on-screen messages) can be drawn
over it. Borderless fullscreen = the game in WINDOWED mode, with its title bar and border taken
away and the window stretched over the whole monitor. Windows then draws our overlay on top.

Only plain Win32 window calls on the game's window - nothing inside the game is changed.
Set the game to Windowed mode, at your monitor's resolution, for the sharpest picture.
"""
import ctypes
import logging
from typing import Optional, Tuple

log = logging.getLogger("RE1HDClient")

GWL_STYLE, GWL_EXSTYLE = -16, -20
WS_CAPTION, WS_THICKFRAME, WS_MINIMIZEBOX, WS_MAXIMIZEBOX, WS_SYSMENU = (
    0x00C00000, 0x00040000, 0x00020000, 0x00010000, 0x00080000)
WS_EX_DLGMODALFRAME, WS_EX_WINDOWEDGE, WS_EX_CLIENTEDGE, WS_EX_STATICEDGE = 0x1, 0x100, 0x200, 0x20000
BORDER_STYLES = WS_CAPTION | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU
BORDER_EX = WS_EX_DLGMODALFRAME | WS_EX_WINDOWEDGE | WS_EX_CLIENTEDGE | WS_EX_STATICEDGE
SWP_NOZORDER, SWP_FRAMECHANGED, SWP_SHOWWINDOW, SWP_NOOWNERZORDER = 0x4, 0x20, 0x40, 0x200


def borderless_style(style: int, ex_style: int) -> Tuple[int, int]:
    """The window styles without title bar and borders."""
    return style & ~BORDER_STYLES, ex_style & ~BORDER_EX


try:
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    _get_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
    _set_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
    _get_long.restype = ctypes.c_ssize_t
    _get_long.argtypes = [wintypes.HWND, ctypes.c_int]
    _set_long.restype = ctypes.c_ssize_t
    _set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.GetWindow.argtypes = [wintypes.HWND, ctypes.c_uint]
    user32.GetWindow.restype = wintypes.HWND
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.MonitorFromWindow.restype = wintypes.HANDLE
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, ctypes.c_uint]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]
except Exception:                          # not Windows (tests)
    user32 = None


def find_game_window(pid: int) -> Optional[int]:
    """The game's main window: the biggest visible top-level window of that process."""
    if user32 is None:
        return None
    found = []

    def callback(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd) and not user32.GetWindow(hwnd, 4):
            r = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            found.append(((r.right - r.left) * (r.bottom - r.top), hwnd))
        return True

    user32.EnumWindows(WNDENUMPROC(callback), 0)
    return max(found)[1] if found else None


class Borderless:
    """Keeps the game borderless-fullscreen; can put the window back the way it was."""
    def __init__(self):
        self.hwnd: Optional[int] = None
        self.original = None                 # (style, ex_style, rect) to restore

    def _monitor_rect(self, hwnd):
        mon = user32.MonitorFromWindow(hwnd, 2)            # MONITOR_DEFAULTTONEAREST
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(info)
        user32.GetMonitorInfoW(mon, ctypes.byref(info))
        r = info.rcMonitor
        return r.left, r.top, r.right - r.left, r.bottom - r.top

    def _rect(self, hwnd):
        r = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        return r.left, r.top, r.right - r.left, r.bottom - r.top

    def ensure(self, pid: int) -> bool:
        """Make (or keep) the game borderless fullscreen. True if anything was changed."""
        if user32 is None:
            return False
        hwnd = find_game_window(pid)
        if not hwnd:
            return False
        if hwnd != self.hwnd:
            self.hwnd, self.original = hwnd, None
        style, ex = _get_long(hwnd, GWL_STYLE), _get_long(hwnd, GWL_EXSTYLE)
        new_style, new_ex = borderless_style(style, ex)
        target = self._monitor_rect(hwnd)
        if (new_style, new_ex) == (style, ex) and self._rect(hwnd) == target:
            return False                                    # already borderless fullscreen
        if self.original is None:
            self.original = (style, ex, self._rect(hwnd))
        _set_long(hwnd, GWL_STYLE, new_style)
        _set_long(hwnd, GWL_EXSTYLE, new_ex)
        user32.SetWindowPos(hwnd, None, *target, SWP_NOZORDER | SWP_NOOWNERZORDER | SWP_FRAMECHANGED
                            | SWP_SHOWWINDOW)
        log.info("Game window made borderless fullscreen (%dx%d).", target[2], target[3])
        return True

    def restore(self) -> bool:
        if user32 is None or not self.hwnd or self.original is None:
            return False
        style, ex, (x, y, w, h) = self.original
        _set_long(self.hwnd, GWL_STYLE, style)
        _set_long(self.hwnd, GWL_EXSTYLE, ex)
        user32.SetWindowPos(self.hwnd, None, x, y, w, h, SWP_NOZORDER | SWP_NOOWNERZORDER
                            | SWP_FRAMECHANGED | SWP_SHOWWINDOW)
        self.original = None
        log.info("Game window put back to normal.")
        return True


VK_CODES = {f"F{n}": 0x6F + n for n in range(1, 13)}     # F1 = 0x70 ... F12 = 0x7B


def key_held(vk: int) -> bool:
    """Is this key down right now (anywhere)? Always False off Windows."""
    if user32 is None:
        return False
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def game_has_focus(pid: int) -> bool:
    """Is the game's window the one the player is using? (So a hotkey in another app does nothing.)"""
    if user32 is None or not pid:
        return False
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return False
    owner = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
    return owner.value == pid
