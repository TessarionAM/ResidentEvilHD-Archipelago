"""
On-screen messages for the RE1 HD client.

A small always-on-top, click-through, see-through window that shows short lines over
the game, e.g.
    You found your Shotgun Shells (6).
    You sent Hookshot to Bob.
    Bob sent you Green Herb.
Lines fade after a few seconds. It never touches the game's memory: it is a separate
window drawn on top, so it works in windowed / borderless mode. (An exclusive
full-screen game can cover it.)

If tkinter isn't available, or anything fails, the overlay switches itself off and the
messages stay in the client's log as before - it can never stop the client.
"""
from __future__ import annotations

import logging
import queue
import sys
import threading
import time
from typing import Callable, Optional

log = logging.getLogger("RE1HDClient")

SHOW_SECONDS = 7.0
MAX_LINES = 6
FONT = ("Segoe UI", 15, "bold")
TEXT_COLOUR = {"found": "#ffe08a", "sent": "#9fd3ff", "received": "#a6f0a6", "info": "#ffffff",
               "warning": "#ff9a8a"}
KEY = "#010203"            # this colour is made fully transparent
SCREEN = "__screen__"      # queue marker for show_screen
FLASH = "__flash__"        # queue marker for show_flash
SCREEN_FONT = ("Times New Roman", 54, "italic")
SCREEN_SMALL = ("Times New Roman", 22, "italic")
FADE_SECONDS = 0.8


# ---------- text (pure, tested) ----------

def with_quantity(item: str, qty: Optional[int]) -> str:
    return f"{item} ({qty})" if qty and qty > 1 else item


# Archipelago's own item colours (its text client / Kivy client): progression = plum, useful =
# slate blue, trap = salmon, anything else = cyan. 2026-11-15 (TessarionAM): the item's name in
# our on-screen lines uses these; the rest of the line keeps its own colour.
ITEM_COLOUR = {"progression": "#af99ef", "useful": "#6d8be8", "trap": "#fa8072", "filler": "#00eeee"}


def item_colour(flags: Optional[int]) -> str:
    """NetworkItem flags: 1 = progression, 2 = useful, 4 = trap (Archipelago's order: trap,
    then progression, then useful)."""
    flags = flags or 0
    if flags & 4:
        return ITEM_COLOUR["trap"]
    if flags & 1:
        return ITEM_COLOUR["progression"]
    if flags & 2:
        return ITEM_COLOUR["useful"]
    return ITEM_COLOUR["filler"]


def message_parts(args: dict, my_slot: int,
                  item_name: Callable[[int, int], str],
                  player_name: Callable[[int], str],
                  quantity: Callable[[str], Optional[int]]) -> Optional[tuple]:
    """(kind, [(text, colour or None), ...]) for a PrintJSON ItemSend/ItemCheat that involves us,
    else None. None as colour = the line's own colour (by kind); the item's name gets
    item_colour(its flags).

    item_name(item_id, receiving_slot), player_name(slot), quantity(item name in OUR game).
    """
    if args.get("type") not in ("ItemSend", "ItemCheat"):
        return None
    receiving = args.get("receiving")
    net = args.get("item")
    if net is None or receiving is None:
        return None
    if isinstance(net, dict):
        item_id, finder, flags = net.get("item"), net.get("player"), net.get("flags", 0)
    else:                                   # NetworkItem(item, location, player, flags)
        item_id, finder = net[0], net[2]
        flags = net[3] if len(net) > 3 else 0
    name = item_name(item_id, receiving)
    colour = item_colour(flags)
    if receiving == my_slot and finder == my_slot:
        return "found", [("You found your ", None), (with_quantity(name, quantity(name)), colour), (".", None)]
    if finder == my_slot:
        return "sent", [("You sent ", None), (name, colour), (f" to {player_name(receiving)}.", None)]
    if receiving == my_slot:
        return "received", [(f"{player_name(finder)} sent you ", None),
                            (with_quantity(name, quantity(name)), colour), (".", None)]
    return None


def message_for(args: dict, my_slot: int,
                item_name: Callable[[int, int], str],
                player_name: Callable[[int], str],
                quantity: Callable[[str], Optional[int]]) -> Optional[tuple]:
    """(kind, text): message_parts as one plain string (logs, tests)."""
    parts = message_parts(args, my_slot, item_name, player_name, quantity)
    return None if parts is None else (parts[0], "".join(t for t, _c in parts[1]))


# ---------- window ----------

def _make_click_through(hwnd: int) -> None:
    try:
        import ctypes
        user32 = ctypes.windll.user32
        GWL_EXSTYLE = -20
        WS_EX_LAYERED, WS_EX_TRANSPARENT = 0x80000, 0x20
        WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE, WS_EX_TOPMOST = 0x80, 0x8000000, 0x8
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT
                              | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST)
    except Exception:  # not Windows / no ctypes: still shows, just not click-through
        pass


class Overlay:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.q: "queue.Queue[tuple]" = queue.Queue()
        self.thread: Optional[threading.Thread] = None
        self.failed = False

    def start(self) -> None:
        if not self.enabled or self.thread or sys.platform != "win32":
            return
        self.thread = threading.Thread(target=self._run, name="RE1HD overlay", daemon=True)
        self.thread.start()

    def show(self, text, kind: str = "info") -> None:
        """text: a string, or [(text, colour or None), ...] (message_parts)."""
        if self.enabled and not self.failed:
            self.q.put((time.time(), kind, text))

    def show_screen(self, steps) -> None:
        """Full-screen black card over everything (To Be Continued Trap). steps: list of
        (seconds, big text, small text); fades in first and out at the end."""
        if self.enabled and not self.failed:
            self.q.put((time.time(), SCREEN, steps))

    def show_flash(self, kind: str) -> None:
        """Fallback for the Danger Flash Trap (vignette.py is the real one): red frame pulsing ~5 s."""
        if self.enabled and not self.failed:
            self.q.put((time.time(), FLASH, kind))

    def stop(self) -> None:
        self.q.put(None)

    # all tkinter calls stay inside this thread
    def _run(self) -> None:
        try:
            import tkinter as tk
            root = tk.Tk()
            root.overrideredirect(True)
            root.attributes("-topmost", True)
            root.attributes("-transparentcolor", KEY)
            root.configure(bg=KEY)
            width, height = 900, 40 * MAX_LINES
            root.geometry(f"{width}x{height}+30+30")
            canvas = tk.Canvas(root, width=width, height=height, bg=KEY, highlightthickness=0)
            canvas.pack()
            root.update_idletasks()
            try:
                import ctypes
                hwnd = ctypes.windll.user32.GetParent(root.winfo_id()) or root.winfo_id()
            except Exception:
                hwnd = root.winfo_id()
            _make_click_through(hwnd)
            lines: list = []
            import tkinter.font as tkfont
            measure = tkfont.Font(root=root, family=FONT[0], size=FONT[1], weight=FONT[2]).measure

            def screen(steps):
                """Black full-screen card: fade in, show each step, fade out (all in this thread)."""
                top = tk.Toplevel(root)
                top.overrideredirect(True)
                top.attributes("-topmost", True)
                w, h = root.winfo_screenwidth(), root.winfo_screenheight()
                top.geometry(f"{w}x{h}+0+0")
                top.configure(bg="black")
                top.attributes("-alpha", 0.0)
                c = tk.Canvas(top, width=w, height=h, bg="black", highlightthickness=0)
                c.pack()
                top.update_idletasks()
                try:
                    import ctypes
                    _make_click_through(ctypes.windll.user32.GetParent(top.winfo_id()) or top.winfo_id())
                except Exception:
                    pass
                plan, t = [], 0.0
                n = int(FADE_SECONDS / 0.04)
                for i in range(n + 1):                                  # fade in
                    plan.append((t + i * 0.04, ("alpha", i / n)))
                t += FADE_SECONDS
                for secs, big, small in steps:
                    plan.append((t, ("text", big, small)))
                    t += secs
                for i in range(n + 1):                                  # fade out
                    plan.append((t + i * 0.04, ("alpha", 1 - i / n)))
                plan.append((t + FADE_SECONDS + 0.05, ("close",)))

                def do(action):
                    try:
                        if action[0] == "alpha":
                            top.attributes("-alpha", max(0.0, min(1.0, action[1])))
                        elif action[0] == "text":
                            c.delete("all")
                            c.create_text(w // 2, h // 2, text=action[1], font=SCREEN_FONT, fill="#e8e8e8")
                            if action[2]:
                                c.create_text(w // 2, h // 2 + 80, text=action[2], font=SCREEN_SMALL, fill="#9a9a9a")
                        else:
                            top.destroy()
                    except tk.TclError:
                        pass                    # the window is already gone
                    except Exception:           # 2026-11-14 audit: don't hide a broken fun trap
                        log.warning("Fun trap screen step %s failed", action[0], exc_info=True)
                for when, action in plan:
                    top.after(int(when * 1000), do, action)

            def flash(kind):
                """Click-through full-screen window: red frame pulsing, or one white flash."""
                top = tk.Toplevel(root)
                top.overrideredirect(True)
                top.attributes("-topmost", True)
                w, h = root.winfo_screenwidth(), root.winfo_screenheight()
                top.geometry(f"{w}x{h}+0+0")
                top.update_idletasks()
                try:
                    import ctypes
                    _make_click_through(ctypes.windll.user32.GetParent(top.winfo_id()) or top.winfo_id())
                except Exception:
                    pass
                if True:
                    top.configure(bg=KEY)
                    top.attributes("-transparentcolor", KEY)
                    c = tk.Canvas(top, width=w, height=h, bg=KEY, highlightthickness=0)
                    c.pack()
                    t = max(24, w // 30)
                    for x0, y0, x1, y1 in ((0, 0, w, t), (0, h - t, w, h), (0, 0, t, h), (w - t, 0, w, h)):
                        c.create_rectangle(x0, y0, x1, y1, fill="#b00000", outline="")
                    steps = []
                    for beat in range(5):                      # 5 pulses, about one a second
                        for i in range(10):
                            a = 0.75 * (1 - abs(i - 5) / 5)
                            steps.append((beat * 1.0 + i * 0.1, a))
                    steps.append((5.0, 0.0))
                top.attributes("-alpha", steps[0][1])

                def set_alpha(a):
                    try:
                        top.attributes("-alpha", max(0.0, min(1.0, a)))
                    except Exception:
                        pass
                for when, a in steps:
                    top.after(int(when * 1000), set_alpha, a)
                top.after(int((steps[-1][0] + 0.2) * 1000), top.destroy)

            def tick():
                now = time.time()
                try:
                    while True:
                        entry = self.q.get_nowait()
                        if entry is None:
                            root.destroy()
                            return
                        if entry[1] == SCREEN:
                            screen(entry[2])
                            continue
                        if entry[1] == FLASH:
                            flash(entry[2])
                            continue
                        lines.append(entry)
                except queue.Empty:
                    pass
                lines[:] = [e for e in lines if now - e[0] < SHOW_SECONDS][-MAX_LINES:]
                canvas.delete("all")
                for row, (_, kind, text) in enumerate(lines):
                    y = 8 + row * 38
                    parts = [(text, None)] if isinstance(text, str) else text
                    x = 10
                    for part, colour in parts:     # coloured item names (message_parts)
                        for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2), (2, 2)):   # dark outline
                            canvas.create_text(x + dx, y + dy, text=part, anchor="nw", font=FONT, fill="#000001")
                        canvas.create_text(x, y, text=part, anchor="nw", font=FONT,
                                           fill=colour or TEXT_COLOUR.get(kind, "#ffffff"))
                        x += measure(part)
                root.attributes("-topmost", True)
                root.after(100, tick)

            tick()
            root.mainloop()
        except Exception:
            self.failed = True
            log.warning("On-screen messages are unavailable (the log still shows everything).", exc_info=True)
