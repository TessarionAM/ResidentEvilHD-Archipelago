"""
Door Skip without BhdTool: the same five code patches BhdTool v1.6 applies for the
September 2026 build (Tools/OptionsTool.cpp, GameAddress.cpp; BhdTool by Eleval, GPL-3.0;
the lab elevator sound fix is credited there to FluffyQuack's door skip mod).

Every patch lists the ORIGINAL bytes, read from TessarionAM's game memory on 2026-11-10
(hd_code_dump.bin, Sept 2026 build). A patch is only written if the game's bytes are exactly
the original ones (or already patched, e.g. by BhdTool). Anything else = unknown build or another
mod: we touch nothing. Patches live only in memory: restarting the game removes them.
"""
from typing import Dict, List, Tuple

from . import hd_versions as hv

# build key -> [(address, original bytes, door-skip bytes, what it does)]
PATCHES: Dict[str, List[Tuple[int, bytes, bytes, str]]] = {
    "hd_6699874012183562949": [
        (0x0047C8DD, bytes.fromhex("83f801"), bytes.fromhex("eb0e90"), "skip the door animation"),
        (0x0047C8ED, bytes.fromhex("837f1c038b"), bytes.fromhex("e92d000000"), "skip the door sounds"),
        (0x0048B8B8, bytes.fromhex("0f8251070000"), b"\x90" * 6, "door not drawn for 5 frames"),
        (0x0048B5BE, bytes.fromhex("0f844b0a0000"), b"\x90" * 6, "skip the start of the animation"),
        (0x00668A9A, bytes.fromhex("fb"), bytes.fromhex("fa"), "lab elevator sound doesn't loop"),
    ],
}

# Where BhdTool hooks the game first (Hooks::InstallHooks): a CALL that BhdTool redirects to
# its own code. Original target 0x007BEE70. Used to tell whether BhdTool is really running.
BHDTOOL_FIRST_HOOK = {"hd_6699874012183562949": (0x0089151B, 0x007BEE70)}


class DoorSkipError(Exception):
    pass


def _addr(conn, a: int) -> int:
    return a - hv.DEFAULT_IMAGE_BASE + conn.module_base


def supported(build_key: str) -> bool:
    return build_key.replace("_steamless", "") in PATCHES


def status(conn, build_key: str) -> str:
    """'on', 'off', 'mixed' or 'unknown' (bytes match neither: another mod or another build)."""
    patches = PATCHES.get(build_key.replace("_steamless", ""))
    if not patches:
        return "unknown"
    states = set()
    for a, orig, new, _ in patches:
        cur = conn.read_bytes(_addr(conn, a), len(orig))
        states.add("on" if cur == new else "off" if cur == orig else "unknown")
    if "unknown" in states:
        return "unknown"
    return states.pop() if len(states) == 1 else "mixed"


def set_door_skip(conn, build_key: str, enable: bool) -> int:
    """Turn door skip on/off. Returns how many patches were written. Checks every patch
    before writing any, so it never leaves the game half-patched by surprise."""
    patches = PATCHES.get(build_key.replace("_steamless", ""))
    if not patches:
        raise DoorSkipError("Door skip isn't known for this game version.")
    todo = []
    for a, orig, new, what in patches:
        cur = conn.read_bytes(_addr(conn, a), len(orig))
        want, other = (new, orig) if enable else (orig, new)
        if cur == want:
            continue
        if cur != other:
            raise DoorSkipError(f"Unexpected game code at {a:#010x} ({what}): {cur.hex(' ')}. "
                                "Another mod may be changing it; nothing was written.")
        todo.append((a, want))
    for a, want in todo:
        conn.write_code(_addr(conn, a), want)
    return len(todo)


def bhdtool_report(conn, build_key: str) -> List[str]:
    """Plain-English lines about BhdTool: is its DLL loaded, and did it hook the game?"""
    lines = []
    dll = [path for name, path in conn.modules() if name.lower() == "dinput8.dll"]
    game_dir = (conn.exe_path or "").rsplit("\\", 1)[0].lower()
    if not dll:
        lines.append("dinput8.dll is NOT loaded in the game at all.")
    else:
        where = dll[0]
        lines.append(f"dinput8.dll loaded from: {where}")
        if game_dir and not where.lower().startswith(game_dir):
            lines.append("  -> That's Windows' own dinput8.dll, NOT BhdTool's: the game ignored the file "
                         "in its folder.")
    hook = BHDTOOL_FIRST_HOOK.get(build_key.replace("_steamless", ""))
    if hook:
        a, original_target = hook
        code = conn.read_bytes(_addr(conn, a), 5)
        if code[0] == 0xE8:
            target = (_addr(conn, a) + 5 + int.from_bytes(code[1:], "little", signed=True)) & 0xFFFFFFFF
            if target == _addr(conn, original_target):
                lines.append("BhdTool has NOT hooked the game (its first hook is missing).")
            else:
                lines.append(f"BhdTool's first hook IS in place (calls {target:#010x}).")
        else:
            lines.append(f"Unexpected code where BhdTool hooks: {code.hex(' ')}")
    lines.append(f"Door skip patches: {status(conn, build_key)}")
    return lines
