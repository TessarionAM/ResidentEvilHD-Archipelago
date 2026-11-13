"""Controller buttons through XInput (Xbox pads, and PlayStation pads through Steam Input or
DS4Windows). Read-only, Windows only: elsewhere every button reads as up."""
import ctypes
from typing import Optional

BUTTONS = {          # XINPUT_GAMEPAD wButtons bits
    "back_select": 0x0020, "l3": 0x0040, "r3": 0x0080, "lb_l1": 0x0100, "rb_r1": 0x0200,
}
TRIGGERS = {"lt_l2": 0, "rt_r2": 1}   # analog triggers: index into (left, right)
COMBOS = {"back_plus_lb": ("back_select", "lb_l1")}
TRIGGER_DOWN = 100   # 0-255


class _Gamepad(ctypes.Structure):
    _fields_ = [("wButtons", ctypes.c_ushort), ("bLeftTrigger", ctypes.c_ubyte),
                ("bRightTrigger", ctypes.c_ubyte), ("sThumbLX", ctypes.c_short),
                ("sThumbLY", ctypes.c_short), ("sThumbRX", ctypes.c_short), ("sThumbRY", ctypes.c_short)]


class _State(ctypes.Structure):
    _fields_ = [("dwPacketNumber", ctypes.c_uint), ("Gamepad", _Gamepad)]


def _load():
    for name in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
        try:
            return ctypes.WinDLL(name)
        except (OSError, AttributeError):
            continue
    return None


_xinput = None
_tried = False


def button_down(name: Optional[str]) -> bool:
    """Is this button (an ItemBoxButton option name) held on any connected controller?"""
    global _xinput, _tried
    if not name or name == "off":
        return False
    if name in COMBOS:
        return all(button_down(part) for part in COMBOS[name])
    if not _tried:
        _tried, _xinput = True, _load()
    if _xinput is None:
        return False
    state = _State()
    for pad in range(4):
        if _xinput.XInputGetState(pad, ctypes.byref(state)) != 0:
            continue                      # no controller in this slot
        g = state.Gamepad
        if name in BUTTONS and g.wButtons & BUTTONS[name]:
            return True
        if name in TRIGGERS and (g.bLeftTrigger, g.bRightTrigger)[TRIGGERS[name]] >= TRIGGER_DOWN:
            return True
    return False
