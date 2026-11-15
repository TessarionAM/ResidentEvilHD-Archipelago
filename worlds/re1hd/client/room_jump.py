"""
Room jump: move Jill straight to a room without a door (random_start_room, 2026-11-15).

The method is BhdTool's Room Jump (eleval, GPL-3.0, REmakeHook/src/Tools/RoomJumpTool.cpp), done
with our own code. Proven in game with dev\\hd_room_jump_test.py (TessarionAM, test 03, 2026-11-15:
7 rooms, "very clean", items, camera and doors all fine).

How it works (Sept 2026 Steam build, checked in the code dump):
  * Every frame Jill can move, the game calls CHECK_FOR_TRIGGERS (0x47D6E0) from 0x48AF56 with a
    32-byte "target room" buffer (x, y, z, page, angle, stage, room, cut). If it returns 1, the game
    changes room to whatever is in that buffer (0x48B291).
  * We point that one CALL at a small stub. When armed, the stub fills the buffer with the target
    (a real door arrival spot from door_data.ARRIVALS) and returns 1 once. Every other frame it
    calls the game's own function (or a mod hooked there before us, e.g. BhdTool).
  * The stub only runs while Jill is in control, so a jump can't land in a menu, door or scene.
    On a new game the game doesn't call it for the first ~10 s (test 03: 10.1 s both times).
The stub uses the same magic as the dev tool, so either one reuses the other's stub.
"""
import struct
from typing import Optional

from . import hd_versions as hv
from .pc_process import ProcessError
from .wrong_door import arrival

CALL_SITE = 0x0048AF56          # E8 -> CHECK_FOR_TRIGGERS
CHECK_FOR_TRIGGERS = 0x0047D6E0
FIRST_BYTES = bytes.fromhex("558bec83e4f083ec388bc156")   # start of CHECK_FOR_TRIGGERS
MAGIC = b"RE1HDRJ1"
D_MAGIC, D_FLAG, D_TARGET = 0x80, 0x100, 0x104      # flag: 0 idle, 1 armed, 2 jumped
IDLE, ARMED, JUMPED = 0, 1, 2


def stub_code(base: int, chain_to: int) -> bytes:
    """cmp [flag],1 / jne pass / [flag]=2 / copy 32 bytes to arg3 / eax=1 / ret 0Ch; pass: jmp chain."""
    flag, target = base + D_FLAG, base + D_TARGET
    code = bytearray()
    code += b"\x83\x3D" + struct.pack("<I", flag) + b"\x01"            # cmp dword [flag], 1
    jne_at = len(code)
    code += b"\x0F\x85\0\0\0\0"                                          # jne pass
    code += b"\xC7\x05" + struct.pack("<I", flag) + struct.pack("<I", JUMPED)   # mov [flag], 2
    code += b"\x56\x57"                                                  # push esi / push edi
    code += b"\x8B\x7C\x24\x14"                                          # mov edi, [esp+14h] (arg3)
    code += b"\x51"                                                      # push ecx (this)
    code += b"\xBE" + struct.pack("<I", target)                          # mov esi, target
    code += b"\xB9\x08\x00\x00\x00"                                      # mov ecx, 8
    code += b"\xF3\xA5"                                                  # rep movsd
    code += b"\x59\x5F\x5E"                                              # pop ecx / edi / esi
    code += b"\xB8\x01\x00\x00\x00"                                      # mov eax, 1
    code += b"\xC2\x0C\x00"                                              # ret 0Ch
    pass_at = len(code)
    struct.pack_into("<i", code, jne_at + 2, pass_at - (jne_at + 6))
    code += b"\xE9" + struct.pack("<i", chain_to - (base + pass_at + 5))   # jmp chain_to
    return bytes(code)


def target_bytes(room: int, spot) -> bytes:
    """TargetRoomData, filled the way the game's own FETCH_DOOR_ROOM_DATA (0x47DFF0) fills it."""
    x, y, z, ang, cut = spot
    return struct.pack("<3fIf3i", x, y, z, 0, ang, room >> 8, room & 0xFF, cut)


class RoomJumper:
    def __init__(self, conn, log=None):
        self.conn, self.log = conn, log
        shift = conn.module_base - hv.DEFAULT_IMAGE_BASE
        self.site, self.check = CALL_SITE + shift, CHECK_FOR_TRIGGERS + shift
        self.base = 0

    def _say(self, text):
        if self.log:
            self.log.info(text)

    def _call_target(self) -> int:
        code = self.conn.read_bytes(self.site, 5)
        if code[0] != 0xE8:
            raise ProcessError(f"unexpected game code at {self.site:#x}: {code.hex(' ')}")
        return (self.site + 5 + struct.unpack("<i", code[1:])[0]) & 0xFFFFFFFF

    def install(self) -> None:
        """Checks the game's bytes first; anything unexpected = nothing written (ProcessError)."""
        first = self.conn.read_bytes(self.check, len(FIRST_BYTES))
        if first != FIRST_BYTES and first[0] != 0xE9:          # E9 = another mod's detour: fine
            raise ProcessError(f"CHECK_FOR_TRIGGERS doesn't look as expected: {first.hex(' ')}")
        target = self._call_target()
        if target != self.check:
            try:
                if self.conn.read_bytes(target + D_MAGIC, len(MAGIC)) == MAGIC:
                    self.base = target                          # ours (client or dev tool): reuse
                    return
            except ProcessError:
                pass
            self._say(f"Room jump: another mod has hooked {self.site:#x} ({target:#x}); chaining to it.")
        base = self.conn.alloc_code(0x1000)
        self.conn.write_bytes(base, stub_code(base, target))
        self.conn.write_bytes(base + D_MAGIC, MAGIC)
        self.conn.write_bytes(base + D_FLAG, struct.pack("<I", IDLE))
        self.conn.write_code(self.site + 1, struct.pack("<i", base - (self.site + 5)))
        if self._call_target() != base:
            raise ProcessError("the room jump hook didn't take (read-back mismatch)")
        self.base = base

    def arm(self, room: int, came_from: Optional[int] = None) -> bool:
        spot = arrival(room, came_from)
        if spot is None:
            return False
        self.conn.write_bytes(self.base + D_TARGET, target_bytes(room, spot))
        self.conn.write_bytes(self.base + D_FLAG, struct.pack("<I", ARMED))
        return True

    def flag(self) -> int:
        return struct.unpack("<I", self.conn.read_bytes(self.base + D_FLAG, 4))[0]

    def cancel(self) -> None:
        self.conn.write_bytes(self.base + D_FLAG, struct.pack("<I", IDLE))
