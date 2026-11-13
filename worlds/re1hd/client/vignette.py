"""
Danger Flash Trap (2026-11-12, TessarionAM): a red glow that is strongest at the screen edges and fades
to fully clear towards the centre, pulsing like Jill's Danger state. No damage.

Drawn with a Windows "layered" window that has a different transparency for every pixel
(UpdateLayeredWindow with a 32-bit premultiplied bitmap), so the game stays visible through
it. Click-through, never takes focus. Pure ctypes (no extra packages); off Windows it does
nothing and returns False.

edge_alpha() / vignette_rows() are pure and tested; draw() is the Windows part.
"""
from __future__ import annotations

import logging
import threading
import time

log = logging.getLogger("RE1HDClient")

RED = (170, 0, 0)          # glow colour (R, G, B)
MAX_ALPHA = 200            # opacity at the very edge (0-255)
MARGIN = 0.38              # fraction of the shorter screen side the glow reaches in from each edge


def edge_alpha(n: int, margin: int, max_alpha: int = MAX_ALPHA) -> bytes:
    """Alpha along one axis of length n: max_alpha at both ends, easing to 0 at `margin` pixels in."""
    out = bytearray(n)
    for i in range(n):
        d = min(i, n - 1 - i)
        if d < margin:
            t = 1.0 - d / margin
            out[i] = int(max_alpha * t * t)          # quadratic ease: soft towards the centre
    return bytes(out)


def vignette_rows(w: int, h: int, margin: int = None, colour=RED, max_alpha: int = MAX_ALPHA):
    """Yield one BGRA (premultiplied) row per screen line, top to bottom. Each pixel's alpha is the
    stronger of its column and row glow, so the corners are the most opaque."""
    margin = margin or max(8, int(min(w, h) * MARGIN))
    col = edge_alpha(w, margin, max_alpha)
    row = edge_alpha(h, margin, max_alpha)
    r, g, b = colour
    scale = [bytes(c * a // 255 for a in range(256)) for c in (b, g, r)]
    cache = {}
    for y in range(h):
        ey = row[y]
        line = cache.get(ey)
        if line is None:
            a = col.translate(bytes(max(i, ey) for i in range(256)))
            buf = bytearray(w * 4)
            buf[0::4] = a.translate(scale[0])
            buf[1::4] = a.translate(scale[1])
            buf[2::4] = a.translate(scale[2])
            buf[3::4] = a
            line = cache[ey] = bytes(buf)
        yield line


def pulse_levels(seconds: float = 5.0, beats: int = 5, step: float = 0.05):
    """Overall opacity (0-255) over time: `beats` smooth pulses, ending at 0."""
    import math
    n = int(seconds / step)
    return [int(255 * (0.5 - 0.5 * math.cos(2 * math.pi * beats * i / n))) for i in range(n)] + [0]


def danger_flash(seconds: float = 5.0) -> bool:
    """Show the pulsing glow over the whole primary screen (background thread)."""
    try:
        import ctypes
        from ctypes import wintypes
        user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    except Exception:
        return False

    def run():
        try:
            w, h = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
            WS_EX = 0x80000 | 0x20 | 0x8 | 0x80 | 0x8000000      # LAYERED|TRANSPARENT|TOPMOST|TOOLWINDOW|NOACTIVATE
            user32.CreateWindowExW.restype = wintypes.HWND
            user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                               ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                               wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
            hwnd = user32.CreateWindowExW(WS_EX, "STATIC", "RE1HD danger", 0x80000000, 0, 0, w, h,
                                          None, None, None, None)                      # WS_POPUP
            if not hwnd:
                raise OSError("CreateWindowEx failed")

            class BITMAPINFOHEADER(ctypes.Structure):
                _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                            ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
                            ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                            ("biXPelsPerMeter", ctypes.c_long), ("biYPelsPerMeter", ctypes.c_long),
                            ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]

            class BLENDFUNCTION(ctypes.Structure):
                _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                            ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]

            bmi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
            screen = user32.GetDC(None)
            mem = gdi32.CreateCompatibleDC(screen)
            bits = ctypes.c_void_p()
            gdi32.CreateDIBSection.restype = wintypes.HBITMAP
            gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT,
                                               ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
            dib = gdi32.CreateDIBSection(mem, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
            old = gdi32.SelectObject(mem, dib)
            stride = w * 4
            for y, line in enumerate(vignette_rows(w, h)):
                ctypes.memmove(bits.value + y * stride, line, stride)

            size, src, dst = wintypes.SIZE(w, h), wintypes.POINT(0, 0), wintypes.POINT(0, 0)
            blend = BLENDFUNCTION(0, 0, 0, 1)                    # AC_SRC_OVER, AC_SRC_ALPHA
            user32.ShowWindow(hwnd, 4)                           # SW_SHOWNOACTIVATE
            msg = wintypes.MSG()
            for level in pulse_levels(seconds):
                blend.SourceConstantAlpha = level
                user32.UpdateLayeredWindow(hwnd, screen, ctypes.byref(dst), ctypes.byref(size), mem,
                                           ctypes.byref(src), 0, ctypes.byref(blend), 2)   # ULW_ALPHA
                while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):          # keep it responsive
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
                time.sleep(0.05)
            user32.DestroyWindow(hwnd)
            gdi32.SelectObject(mem, old)
            gdi32.DeleteObject(dib)
            gdi32.DeleteDC(mem)
            user32.ReleaseDC(None, screen)
        except Exception:
            log.debug("Danger flash failed", exc_info=True)

    threading.Thread(target=run, name="RE1HD danger flash", daemon=True).start()
    return True
