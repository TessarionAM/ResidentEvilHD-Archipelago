"""The game's own settings file (option game_resolution, TessarionAM 2026-11-12).

Resident Evil HD Remaster keeps its settings in
    %LOCALAPPDATA%\\CAPCOM\\Resident Evil - biohazard@HD REMASTER\\config.ini
and only offers resolutions up to your monitor's in its menu - but it renders at any resolution
written there (Capcom's Steam FAQ: change the RESOLUTION line under [DISPLAY]). The game reads
the file at start-up, so a change takes effect the next time it starts.
"""
import glob
import os
import re
import shutil
from pathlib import Path
from typing import Optional

RESOLUTIONS = {1: (1920, 1080), 2: (2560, 1440), 3: (3840, 2160)}
# 2026-11-12 (TessarionAM, 1080p monitor, 4k + borderless): a resolution ABOVE the monitor's does NOT
# work - the picture came out cropped / squeezed (narrower than 4:3). The old option text said it
# would be scaled down; that was wrong. The client now never writes a resolution bigger than the
# monitor, and puts back the original (config.ini.bak) if an earlier version did.


def monitor_size() -> Optional[tuple]:
    """The main monitor's real resolution in pixels (EnumDisplaySettings, not DPI-scaled), or None."""
    try:
        import ctypes
        dm = ctypes.create_string_buffer(220)                 # DEVMODEW
        ctypes.memmove(ctypes.addressof(dm) + 68, (220).to_bytes(2, "little"), 2)   # dmSize
        if not ctypes.windll.user32.EnumDisplaySettingsW(None, -1, dm):          # ENUM_CURRENT_SETTINGS
            return None
        w = int.from_bytes(dm.raw[172:176], "little")
        h = int.from_bytes(dm.raw[176:180], "little")
        return (w, h) if w and h else None
    except Exception:
        return None


def _resolution_in(text: str) -> Optional[tuple]:
    section = None
    for line in text.splitlines():
        st = line.strip()
        if st.startswith("[") and st.endswith("]"):
            section = st[1:-1].strip().upper()
            continue
        m = re.match(r"\s*resolution\s*=\s*(\d+)\s*[xX*]\s*(\d+)", line, re.IGNORECASE)
        if section == "DISPLAY" and m:
            return int(m.group(1)), int(m.group(2))
    return None


def find_config() -> Optional[Path]:
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        return None
    hits = glob.glob(os.path.join(base, "CAPCOM", "Resident Evil*HD REMASTER*", "config.ini"))
    return Path(hits[0]) if hits else None


def with_resolution(text: str, w: int, h: int) -> str:
    """config.ini text with [DISPLAY] Resolution set to WxH (everything else unchanged)."""
    lines = text.splitlines(keepends=True)
    newline = "\r\n" if "\r\n" in text else "\n"
    section, display_at = None, None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1].strip().upper()
            if section == "DISPLAY":
                display_at = i
            continue
        m = re.match(r"(\s*resolution\s*=\s*)(.*?)(\s*)$", line, re.IGNORECASE)
        if section == "DISPLAY" and m:
            value = m.group(2)
            if re.search(r"\d+\s*[xX*]\s*\d+", value):
                value = re.sub(r"(\d+)(\s*[xX*]\s*)(\d+)", lambda g: f"{w}{g.group(2)}{h}", value, count=1)
            else:
                value = f"{w}x{h}"
            lines[i] = m.group(1) + value + (m.group(3) or newline)
            return "".join(lines)
    entry = f"Resolution={w}x{h}{newline}"
    if display_at is None:
        return text + ("" if text.endswith(("\n", "\r")) or not text else newline) + f"[DISPLAY]{newline}" + entry
    lines.insert(display_at + 1, entry)
    return "".join(lines)


def set_resolution(choice: int, monitor: Optional[tuple] = None) -> str:
    """Write the option's resolution into config.ini (backed up once as config.ini.bak) - never
    bigger than the monitor (see the note at RESOLUTIONS)."""
    if choice not in RESOLUTIONS:
        return "Game resolution: left as it is."
    w, h = RESOLUTIONS[choice]
    path = find_config()
    if path is None:
        return ("Game resolution: couldn't find the game's config.ini (start the game once, then "
                "reconnect the client).")
    text = path.read_text(encoding="utf-8", errors="replace")
    backup = path.with_name("config.ini.bak")
    monitor = monitor or monitor_size()
    if monitor and (w > monitor[0] or h > monitor[1]):
        # too big for this screen: don't write it, and undo it if an earlier client version did
        cur = _resolution_in(text)
        orig = _resolution_in(backup.read_text(encoding="utf-8", errors="replace")) if backup.exists() else None
        fallback = orig if orig and orig[0] <= monitor[0] and orig[1] <= monitor[1] else monitor
        note = (f"Game resolution: {w}x{h} is bigger than your monitor ({monitor[0]}x{monitor[1]}) - the game "
                f"can't show that (the picture gets cropped), so it wasn't used.")
        if cur and (cur[0] > monitor[0] or cur[1] > monitor[1]):
            path.write_text(with_resolution(text, *fallback), encoding="utf-8")
            note += f" Put back to {fallback[0]}x{fallback[1]}; restart the game."
        return note + " Set game_resolution to keep (or your monitor's size) in your YAML."
    new = with_resolution(text, w, h)
    if new == text:
        return f"Game resolution: already {w}x{h}."
    if not backup.exists():
        shutil.copy2(path, backup)
    path.write_text(new, encoding="utf-8")
    return (f"Game resolution set to {w}x{h} in the game's config.ini - it takes effect the next time "
            f"the game starts. (Original saved as config.ini.bak.)")
