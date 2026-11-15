"""
Steam version - ROOM JUMP TEST (testing helper, 2026-11-14). WRITES to the game (memory and one CALL).

For the "random starting room" plan: moves Jill straight to a room WITHOUT a door, the way BhdTool's
Room Jump does it (eleval, GPL-3.0, REmakeHook/src/Tools/RoomJumpTool.cpp). Use a spare save.

How it works (Sept 2026 build, checked in the code dump):
  * Every frame Jill can move, the game calls CHECK_FOR_TRIGGERS (0x47D6E0) from 0x48AF56 with a
    32-byte "target room" buffer (Game+0x250 = x, y, z, page, angle, stage, room, cut). If it returns
    1, the game changes room to whatever is in that buffer (0x48B291).
  * This tool points that one CALL at a small stub. When you press F10, the stub fills the buffer
    with the room you picked (arrival spot = a real door arrival from door_data.ARRIVALS) and
    returns 1 once. Every other frame it just calls the game's own function (or the mod that was
    hooked there before, e.g. BhdTool), so nothing else changes.
  * The stub only runs while Jill is in control, so a jump can't land in a menu, door or scene.

Usage: Tools\\run_hd_room_jump_test.bat. Type the rooms to try, in order (hex, e.g. 106,314,403),
optionally with the room you "come from" for the arrival spot (e.g. 314/313). Then in the game:
  F10 = jump to the next room in the list      F11 = list the arrival spots for the next room
Watch for: a crash, a black screen, Jill in a wall, a missing or wrong cutscene, doors that don't
work in the new room, the camera. Write down what you see; the log has the rest.
Output: hd_room_jump_test_output.txt (every run is added to the end).

The stub stays in the game until it closes (harmless: it only does something after F10).
"""
import struct
import sys
import time

import hd_wrong_door_test as wd
from client import hd_versions as hv
from client.door_data import ARRIVALS
from client.pc_process import ProcessConnection, ProcessError
from client.window_mode import key_held
from client.wrong_door import arrival
from hd_inventory import sha256_of

wd.OUTPUT = wd.HERE / "hd_room_jump_test_output.txt"
say, name = wd.say, wd.name
VK_F10, VK_F11 = 0x79, 0x7A

# Sept 2026 Steam build (default image base 0x400000; rebased at run time)
CALL_SITE = 0x0048AF56          # E8 -> CHECK_FOR_TRIGGERS
CHECK_FOR_TRIGGERS = 0x0047D6E0
FIRST_BYTES = bytes.fromhex("558bec83e4f083ec388bc156")   # start of CHECK_FOR_TRIGGERS
CURRENT_STAGE_ROOM = 0xE4750    # [0x00CF2F28]+0xE4750 / +0xE4754 (used by the room change at 0x48B291)
SAVE_OBJECT = 0x00CF2F28

# Layout of our page
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
    """TargetRoomData, filled the way the game's own FETCH_DOOR_ROOM_DATA (0x47DFF0) fills it from
    a door record: page = 0, angle in radians (as in the door record), stage/room/cut as numbers."""
    x, y, z, ang, cut = spot
    return struct.pack("<3fIf3i", x, y, z, 0, ang, room >> 8, room & 0xFF, cut)


class Jumper:
    def __init__(self, conn):
        self.conn = conn
        shift = conn.module_base - hv.DEFAULT_IMAGE_BASE
        self.site, self.check = CALL_SITE + shift, CHECK_FOR_TRIGGERS + shift
        self.save_obj = SAVE_OBJECT + shift
        self.base = 0

    def _call_target(self) -> int:
        code = self.conn.read_bytes(self.site, 5)
        if code[0] != 0xE8:
            raise ProcessError(f"unexpected game code at {self.site:#x}: {code.hex(' ')}")
        return (self.site + 5 + struct.unpack("<i", code[1:])[0]) & 0xFFFFFFFF

    def install(self) -> None:
        first = self.conn.read_bytes(self.check, len(FIRST_BYTES))
        if first != FIRST_BYTES and first[0] != 0xE9:          # E9 = another mod's detour: fine
            raise ProcessError(f"CHECK_FOR_TRIGGERS doesn't look as expected: {first.hex(' ')}")
        target = self._call_target()
        if target != self.check:
            try:
                if self.conn.read_bytes(target + D_MAGIC, len(MAGIC)) == MAGIC:
                    self.base = target
                    say(f"Our stub from an earlier run is still installed at {target:#x} - reusing it.")
                    self.conn.write_bytes(self.base + D_FLAG, struct.pack("<I", IDLE))
                    return
            except ProcessError:
                pass
            say(f"Another mod has hooked this call ({target:#x}); we'll call it from our stub.")
        base = self.conn.alloc_code(0x1000)
        self.conn.write_bytes(base, stub_code(base, target))
        self.conn.write_bytes(base + D_MAGIC, MAGIC)
        self.conn.write_bytes(base + D_FLAG, struct.pack("<I", IDLE))
        self.conn.write_code(self.site + 1, struct.pack("<i", base - (self.site + 5)))
        if self._call_target() != base:
            raise ProcessError("the hook didn't take (read-back mismatch)")
        self.base = base
        say(f"Stub installed at {base:#x} (the call at {self.site:#x} now goes through it).")

    def arm(self, room: int, spot) -> None:
        self.conn.write_bytes(self.base + D_TARGET, target_bytes(room, spot))
        self.conn.write_bytes(self.base + D_FLAG, struct.pack("<I", ARMED))

    def flag(self) -> int:
        return struct.unpack("<I", self.conn.read_bytes(self.base + D_FLAG, 4))[0]

    def cancel(self) -> None:
        self.conn.write_bytes(self.base + D_FLAG, struct.pack("<I", IDLE))

    def game_room(self):
        obj = struct.unpack("<I", self.conn.read_bytes(self.save_obj, 4))[0]
        if not obj:
            return None
        stage, room = struct.unpack("<ii", self.conn.read_bytes(obj + CURRENT_STAGE_ROOM, 8))
        return stage * 0x100 + room if 1 <= stage <= 6 and 0 <= room < 0x40 else None


def parse(answer: str):
    """'106, 314/313' -> [(0x106, None), (0x314, 0x313)]"""
    out = []
    for part in answer.replace(" ", "").split(","):
        if not part:
            continue
        room, _, came = part.partition("/")
        out.append((int(room, 16), int(came, 16) if came else None))
    return out


def main() -> int:
    with wd.OUTPUT.open("a", encoding="utf-8") as f:   # every run is kept (2026-11-15)
        f.write("\n" + f"=== Room jump test {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    print(__doc__)
    answer = (sys.argv[1] if len(sys.argv) > 1 else
              input("Rooms to jump to, in order (e.g. 105,118,314/313,403,40a,307,502): ")).strip()
    try:
        plan = parse(answer or "105,118,314,403,40a,307,502")
    except ValueError:
        print("That isn't a room list (e.g. 105,314/313).")
        return 1
    for room, came in plan:
        if arrival(room, came) is None:
            print(f"No known arrival spot for {name(room)} - pick another room.")
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
        jumper = Jumper(conn)
        jumper.install()
        say("Plan: " + ", ".join(name(r) + (f" (as if from {name(c)})" if c else "") for r, c in plan))
        say("Load a spare save, then press F10 in the game while Jill can move.")
        room, armed_at, prev = jumper.game_room(), None, (False, False)
        say(f"Room now: {name(room) if room else '-'}")
        while True:
            now = jumper.game_room()
            if now != room:
                say(f"Room: {name(now) if now else '- (loading / title)'}")
                room = now
            f10, f11 = key_held(VK_F10), key_held(VK_F11)
            if f11 and not prev[1] and plan:
                r, c = plan[0]
                say(f"Arrival spots for {name(r)}:")
                for src, x, y, z, ang, cut in ARRIVALS.get(r, []):
                    say(f"   from {name(src)}: ({x:.1f}, {y:.1f}, {z:.1f}) angle {ang:.0f} cut {cut}")
            if f10 and not prev[0]:
                if armed_at is not None:
                    say("Still waiting for the last jump (Jill must be able to move). F10 again cancels it.")
                    jumper.cancel()
                    armed_at = None
                elif not plan:
                    say("No more rooms in the list. Close the window to finish.")
                else:
                    r, c = plan[0]
                    spot = arrival(r, c)
                    jumper.arm(r, spot)
                    armed_at = time.time()
                    x, y, z, ang, cut = spot
                    say(f"F10: jump armed -> {name(r)} at ({x:.1f}, {y:.1f}, {z:.1f}), cut {cut}.")
            prev = (f10, f11)
            if armed_at is not None and jumper.flag() == JUMPED:
                r, _c = plan.pop(0)
                say(f"  The stub fired after {time.time() - armed_at:.1f} s (target {name(r)}).")
                armed_at = None
                deadline = time.time() + 15
                while time.time() < deadline and jumper.game_room() != r:
                    time.sleep(0.1)
                got = jumper.game_room()
                say(f"  Arrived in {name(got) if got else '-'}"
                    + ("  OK" if got == r else f"  - NOT the target ({name(r)})"))
                say("  Look around: crash? black screen? cutscene? Do the doors work? Then F10 for the next room.")
                jumper.cancel()
            time.sleep(0.05)
    except ProcessError as exc:
        say(f"ERROR: {exc}")
        return 1
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
