"""
Autosave in save rooms - the game's OWN save routine, run on the game's own update loop.
No extra tool: the client writes a tiny piece of code into the game's memory.

FOUND BY US (2026-11-11) in TessarionAM's memory dump (hd_code_dump.bin, Sept 2026 build):
  * 0x00490800  SaveToSlot(slot, mode)  thiscall, ecx = [0xCF2F28] + 0x5370 (the save object),
                returns al = 1 when finished. A state machine: call it every frame until it
                returns 1. The typewriter menu calls it this way (0x0052EBCF).
                - slot 0..7 = the 8 save slots (GAMEDATA0..7 in biodata.bin), 9 = system data.
                - mode 3 = save WITHOUT using an Ink Ribbon (the menu passes 3 when a flag at
                  menu+0x284 is set), anything else takes one Ink Ribbon (0x4EF6D0(0x44)).
                - state at save object +0xDF36C (0 = idle), result at +0xDF368 (0 = OK).
                - it builds the slot from the live game (0x490B90, which copies all 8 slots to the
                  file buffers) and asks the storage system (singleton [0xD5A9D8], busy flag +0x24)
                  to write biodata.bin (0x872220).
  * 0x00490B90  room -> save name: only 11 rooms get a real name (the others show "No data",
                which is what BhdTool's INVALID_SAVE_FIX works around). Those 11 rooms are the
                save rooms below, so autosaves only happen there.
  * 0x0089151B  CALL 0x7BEE70: the late game update, every frame, on the game's own thread.
                (BhdTool hooks the same call, Hooks.cpp, credited.) We point this CALL at our code,
                which calls the original first and then, when the client asks, SaveToSlot(slot, 3).

Safety: every address/byte we change is checked first; anything unexpected = nothing written.
If another mod (BhdTool) already redirected the CALL, our code calls that mod's code instead of
the game's, so the chain stays intact.
The hook only lives in memory until the game closes. If the client restarts, it finds its own
code again (magic bytes) instead of installing twice.
"""
import struct
import time
from typing import Dict, Optional

from . import hd_versions as hv

MAGIC = b"RE1HDAS9"           # v2: "call a game function"; v4: item box anywhere; v5: menu mode 5; v6: call arguments;
                               # v7: calls that wait until Jill can move (IN_CONTROL); v8: call result (eax) kept;
                               # v9: autosave starts only while Jill can move (WAIT_CONTROL)
OLD_MAGICS = (b"RE1HDAS1", b"RE1HDAS2", b"RE1HDAS3", b"RE1HDAS4", b"RE1HDAS5")   # an older client's routine: chained through, not reused

# Rooms the game itself names in a save (from 0x490B90): stage*0x100 + room.
SAVE_ROOMS = {
    0x100: "Mansion Drug Room (1F save room)", 0x105: "Dining Room", 0x118: "East Wing Storeroom",
    0x307: "Mining Area", 0x314: "Cabin", 0x316: "Garbage Compactor Room",
    0x31A: "Altar Stairway Passage", 0x403: "Residence Storeroom", 0x40A: "Room 003",
    0x502: "Lab Item Box Room", 0x50E: "Lab save room",
}

ADDR: Dict[str, Dict[str, int]] = {
    "hd_6699874012183562949": {
        "hook": 0x0089151B, "late_update": 0x007BEE70, "save_to_slot": 0x00490800,
        "inv_ptr": 0x00CF2F28, "savedata_singleton": 0x00D5A9D8,
        "remove_weapon": 0x004FB2F0, "queue_weapon": 0x006AA710,
        "find_object": 0x004D3040, "object_list": 0x00D597D0, "weapon_object_class": 0x00CEDCC8,
        "weapon_arc": 0x0048D190, "loader_ready": 0x00482530,
        "examine_hook": 0x004F2E97, "examine": 0x0047FE80, "execute_trigger": 0x0046B420,
        "open_menu": 0x004F6F60, "menu_ptr": 0x00CF30D8, "set_state_bit": 0x004EE130,
        "play_se": 0x004E0C40, "sound_ptr": 0x00D5971C,
    },
}
# Game functions the client may ask the routine to call (thiscall, no arguments), with their
# first bytes from TessarionAM's memory dump - checked before use.
#   remove_weapon (0x4FB2F0): Jill drops the weapon she holds (deletes the model, sets
#   Jill+0x15D0 = 0). The game calls it when the inventory menu closes after unequipping
#   (equip watch, 2026-11-11 18:57: JILL+0x15D0 2 -> 0, +0x15D4 -> -1 exactly then).
#   play_se (0x4E0C40, thiscall on sSound = [0xD5971C], 3 args, ret 0xC): queue sound effect
#   (bank, id, 0). The game's most-called sound function (608 call sites; banks 0-3 seen). It
#   does nothing when that bank isn't loaded (pointer test), and only queues a request for the
#   sound thread. Found 2026-11-12 from the disassembly: [0xD5971C] sits next to the sSound
#   type info (name "sSound" at 0xC81D44, DTI object 0xD59724).
#   queue_weapon (0x6AA710, thiscall on Jill, 2 args (weapon type, loaded ammo), ret 8): the
#   game's own "change the held weapon" request - Jill+0x1D40 = type, +0x1D44 = ammo, then
#   Jill+0x1530 |= 0x10. Jill's next update (0x69DE60) sees the bit and calls 0x6AC140, which
#   drops the old model AND sets the new animation set (0x535730). The inventory menu calls it
#   on close when the equipped weapon changed (0x549BC1). Found 2026-11-12: remove_weapon alone
#   took the gun model away but left Jill in the Handgun pose (seed test 6).
#   v0.9.7 crash: queue_weapon(0) alone made the game load pl01_2w01 (Jill's empty-hands /
#   knife motion), which lives in arc\wep\wep11 (table 0xC26218: type -> weapon archive) - not
#   loaded while she has the Handgun (wep12). The inventory menu first switches the weapon
#   archive, waits for it, and only then queues the change. So do we, with the menu's own calls:
#   find_object (0x4D3040, thiscall on [0xD597D0], 1 arg = class 0xCEDCC8, ret 4) -> the object
#     whose +0x50 is the weapon archive loader (menu 0x549B3F);
#   weapon_arc (0x48D190, thiscall on that object + 0x50, args (type, Jill+0x1580), ret 8): puts
#     Jill in a neutral pose, unloads the old weapon archive, starts loading the new one (menu
#     0x549B06);
#   loader_ready (0x482530, thiscall, no args, al = 1 when done): polled on object + 0x358
#     (0x48C680 = +0x308 of +0x50) and object + 0x390 every frame by the menu (0x549B5C/0x549B6F).
CALLABLE = {"remove_weapon": bytes.fromhex("568bf18b0d842ecf00"),
            "find_object": bytes.fromhex("5356578bf98bb724380000"),
            "weapon_arc": bytes.fromhex("568bf18b0d842ecf00e8"),
            "loader_ready": bytes.fromhex("51538bd9b001565733ff"),
            "queue_weapon": bytes.fromhex("8b442404898140 1d00008b442408".replace(" ", "")),
            "play_se": bytes.fromhex("8b442404538bd9558bac83f0c60500")}

# Item box anywhere. v0.6.7 queued the box's game event from the late-update hook; v0.6.8 ran a
# fake type-12 trigger through ExecuteTrigger in place of the trigger scan. Both crashed: the game
# showed "Failed open file ...\arc\itemv\v.arc" (seed test 4). The BOXDEBUG log (v0.7.2) showed
# why: a real item box opens the menu in mode 5 (menu object [[0xCF30D8]+0x40] +0x60A0 = 5),
# ours opened mode 2 (the "examine" viewer, which loads a 3D item model and found none).
# The real box is opened from Jill's item-box action at 0x694765:
#     [0xCF2F28]->0x4EE130(7)                      (state bit 7; thiscall, ret 4)
#     [0xCF30D8]->OpenMenu 0x4F6F60(5, 0, 0, 0, 0, 1)   (thiscall, ret 0x18)
# v0.7.3 does exactly those two calls, in place of the trigger scan 0x47FE80 (called from
# 0x4F2E97, thiscall 1 arg ret 4) for one frame - i.e. while Jill can move, like BhdTool's
# "Open save menu".
FIRST_BYTES = {"examine": bytes.fromhex("558bec83e4f083ec34"),
               "open_menu": bytes.fromhex("8b494085c90f8535de0400"),
               "set_state_bit": bytes.fromhex("568bf157807e1c0075")}
SAVE_OBJECT = 0x5370          # save object = [inv_ptr] + this
STATE = 0xDF36C               # save state machine (0 = idle)
RESULT = 0xDF368              # last result (0 = OK)
STORAGE_BUSY = 0x24           # storage singleton: != 0 while reading/writing

# data block inside our code page
D_MAGIC, D_FLAG, D_SLOT, D_RESULT, D_COUNT = 0x200, 0x208, 0x20C, 0x210, 0x214
D_CALL_FLAG, D_CALL_FUNC, D_CALL_THIS = 0x218, 0x21C, 0x220
D_BOX_FLAG = 0x224                         # item box request
D_CALL_ARGS = 0x228                        # 3 stack arguments for the call request (v6)
D_CALL_RESULT = 0x234                      # eax after the call (v8)
BOX_STUB = 0x300                          # code: replacement for the examine call
IDLE, REQUESTED, DONE, RUNNING = 0, 1, 2, 3
# v7 (2026-11-12): a call request with flag IN_CONTROL is run by the box stub instead of the
# late-update routine. The box stub replaces the trigger scan, which the game only runs while Jill
# can move - never while a save loads, in menus or in scenes. Seed test 6: the weapon change ran
# while a save was still loading and the game couldn't find Jill's motion file
# ("Failed open file ...\motion\pl\pl01\pl01_2w01.lmt").
IN_CONTROL = 4
IN_CONTROL_TIMEOUT = 20.0     # seconds: a request the stub never picked up is withdrawn
# v9 (2026-11-14, TessarionAM): an autosave made 1.8 s before a pickup finished (the "take it?"
# prompt was up) loads with the game stuck in that menu - no camera, no inventory, no item box.
# The autosave request now waits in WAIT_CONTROL until the box stub (= the trigger scan, which
# only runs while Jill can move) starts the save itself, in place of that frame's scan - so no
# prompt can open in the frame the save copies the game. The late update carries it on.
WAIT_CONTROL = 5


class AutosaveError(Exception):
    pass


class _Asm:
    """Just enough x86 for the cave (verified by disassembling the output in the tests)."""
    def __init__(self, base: int):
        self.base, self.code, self.labels, self.fix = base, bytearray(), {}, []

    def here(self):
        return self.base + len(self.code)

    def raw(self, b: bytes):
        self.code += b

    def label(self, name):
        self.labels[name] = self.here()

    def rel32(self, opcode: bytes, target):
        self.code += opcode
        self.fix.append((len(self.code), target))
        self.code += b"\0\0\0\0"

    def build(self) -> bytes:
        for pos, target in self.fix:
            t = self.labels[target] if isinstance(target, str) else target
            struct.pack_into("<i", self.code, pos, t - (self.base + pos + 4))
        return bytes(self.code)


def cave_code(base: int, a: Dict[str, int], chain_to: Optional[int] = None) -> bytes:
    """Machine code for the hook. `a` holds the game's absolute addresses (already rebased).
    chain_to: what the CALL pointed at before us (another mod's hook, e.g. BhdTool) - we call
    that instead of the game's function, so both keep working."""
    d = lambda off: struct.pack("<I", base + off)
    i32 = lambda v: struct.pack("<I", v & 0xFFFFFFFF)
    asm = _Asm(base)
    asm.rel32(b"\xE8", chain_to or a["late_update"])        # call original late update (or the mod before us)
    asm.raw(b"\x60\x9C")                                    # pushad / pushfd
    # --- request 2: call one whitelisted game function, thiscall, up to 3 stack arguments.
    # ebp keeps esp, so it works whatever the function pops (ret / ret 0xC); thiscall keeps ebp.
    asm.raw(b"\x83\x3D" + d(D_CALL_FLAG) + b"\x01")         # cmp [call_flag],1
    asm.rel32(b"\x0F\x85", "save")                         # jne save
    asm.raw(b"\x89\xE5")                                   # mov ebp,esp
    asm.raw(b"\xFF\x35" + d(D_CALL_ARGS + 8))               # push [arg3]
    asm.raw(b"\xFF\x35" + d(D_CALL_ARGS + 4))               # push [arg2]
    asm.raw(b"\xFF\x35" + d(D_CALL_ARGS))                   # push [arg1]
    asm.raw(b"\x8B\x0D" + d(D_CALL_THIS))                   # mov ecx,[call_this]
    asm.raw(b"\xFF\x15" + d(D_CALL_FUNC))                   # call [call_func]
    asm.raw(b"\xA3" + d(D_CALL_RESULT))                    # mov [call_result],eax
    asm.raw(b"\x89\xEC")                                   # mov esp,ebp
    asm.raw(b"\xC7\x05" + d(D_CALL_FLAG) + i32(DONE))       # mov [call_flag],2
    asm.label("save")
    # --- request 1: autosave
    asm.raw(b"\x83\x3D" + d(D_FLAG) + b"\x01")              # cmp [flag],1
    asm.rel32(b"\x0F\x84", "start")                         # je start
    asm.raw(b"\x83\x3D" + d(D_FLAG) + b"\x03")              # cmp [flag],3
    asm.rel32(b"\x0F\x84", "cont")                          # je cont
    asm.rel32(b"\xE9", "done")
    asm.label("start")
    asm.raw(b"\x8B\x35" + i32(a["inv_ptr"]))                # mov esi,[inv_ptr]
    asm.raw(b"\x85\xF6")                                    # test esi,esi
    asm.rel32(b"\x0F\x84", "done")
    asm.raw(b"\x83\xBE" + i32(SAVE_OBJECT + STATE) + b"\x00")   # cmp [esi+state],0
    asm.rel32(b"\x0F\x85", "done")                          # a save is already running: wait
    asm.raw(b"\xA1" + i32(a["savedata_singleton"]))         # mov eax,[storage]
    asm.raw(b"\x85\xC0")                                    # test eax,eax
    asm.rel32(b"\x0F\x84", "done")
    asm.raw(b"\x83\x78" + bytes([STORAGE_BUSY]) + b"\x00")  # cmp [eax+0x24],0
    asm.rel32(b"\x0F\x85", "done")                          # storage busy: wait
    asm.raw(b"\xC7\x05" + d(D_FLAG) + i32(RUNNING))         # mov [flag],3
    asm.label("cont")
    asm.raw(b"\x8B\x35" + i32(a["inv_ptr"]))                # mov esi,[inv_ptr]
    asm.raw(b"\x85\xF6")
    asm.rel32(b"\x0F\x84", "done")
    asm.raw(b"\x8D\x8E" + i32(SAVE_OBJECT))                 # lea ecx,[esi+0x5370]
    asm.raw(b"\x6A\x03")                                    # push 3 (no Ink Ribbon)
    asm.raw(b"\xFF\x35" + d(D_SLOT))                        # push [slot]
    asm.rel32(b"\xE8", a["save_to_slot"])                   # call SaveToSlot (ret 8)
    asm.raw(b"\x84\xC0")                                    # test al,al
    asm.rel32(b"\x0F\x84", "done")                          # not finished yet
    asm.raw(b"\x8B\x86" + i32(SAVE_OBJECT + RESULT))        # mov eax,[esi+result]
    asm.raw(b"\xA3" + d(D_RESULT))                          # mov [result],eax
    asm.raw(b"\xFF\x05" + d(D_COUNT))                       # inc [count]
    asm.raw(b"\xC7\x05" + d(D_FLAG) + i32(DONE))            # mov [flag],2
    asm.label("done")
    asm.raw(b"\x9D\x61")                                    # popfd / popad
    asm.raw(b"\xC3")                                        # ret
    code = asm.build()
    assert len(code) < D_MAGIC
    return code


def box_stub_code(base: int, a: Dict[str, int], chain_to: Optional[int] = None) -> bytes:
    """Code at base + BOX_STUB, called instead of the trigger scan (thiscall, 1 arg, ret 4).
    Item box requested: open the item box menu the way the game does (see above), once.
    Otherwise jump on to the scan (or to another mod's hook on it), with the stack untouched."""
    d = lambda off: struct.pack("<I", base + off)
    i32 = lambda v: struct.pack("<I", v & 0xFFFFFFFF)
    asm = _Asm(base + BOX_STUB)
    # --- autosave that must wait until Jill can move (v9): start it here, instead of this scan
    asm.raw(b"\x83\x3D" + d(D_FLAG) + bytes([WAIT_CONTROL]))   # cmp [flag],5
    asm.rel32(b"\x0F\x85", "incall")                       # jne incall
    asm.raw(b"\x60\x9C")                                    # pushad / pushfd
    asm.raw(b"\x8B\x35" + i32(a["inv_ptr"]))                # mov esi,[inv_ptr]
    asm.raw(b"\x85\xF6")                                    # test esi,esi
    asm.rel32(b"\x0F\x84", "notyet")
    asm.raw(b"\x83\xBE" + i32(SAVE_OBJECT + STATE) + b"\x00")   # cmp [esi+state],0
    asm.rel32(b"\x0F\x85", "notyet")                        # a save is running: wait
    asm.raw(b"\xA1" + i32(a["savedata_singleton"]))         # mov eax,[storage]
    asm.raw(b"\x85\xC0")                                    # test eax,eax
    asm.rel32(b"\x0F\x84", "notyet")
    asm.raw(b"\x83\x78" + bytes([STORAGE_BUSY]) + b"\x00")  # cmp [eax+0x24],0
    asm.rel32(b"\x0F\x85", "notyet")                        # storage busy: wait
    asm.raw(b"\xC7\x05" + d(D_FLAG) + i32(RUNNING))         # mov [flag],3 (late update carries on)
    asm.raw(b"\x8D\x8E" + i32(SAVE_OBJECT))                 # lea ecx,[esi+0x5370]
    asm.raw(b"\x6A\x03")                                    # push 3 (no Ink Ribbon)
    asm.raw(b"\xFF\x35" + d(D_SLOT))                        # push [slot]
    asm.rel32(b"\xE8", a["save_to_slot"])                   # call SaveToSlot (ret 8)
    asm.raw(b"\x84\xC0")                                    # test al,al
    asm.rel32(b"\x0F\x84", "skipscan")                      # not finished yet
    asm.raw(b"\x8B\x86" + i32(SAVE_OBJECT + RESULT))        # mov eax,[esi+result]
    asm.raw(b"\xA3" + d(D_RESULT))                          # mov [result],eax
    asm.raw(b"\xFF\x05" + d(D_COUNT))                       # inc [count]
    asm.raw(b"\xC7\x05" + d(D_FLAG) + i32(DONE))            # mov [flag],2
    asm.label("skipscan")
    asm.raw(b"\x9D\x61")                                    # popfd / popad
    asm.raw(b"\xB8\x01\x00\x00\x00")                        # mov eax,1 (as the box path)
    asm.raw(b"\xC2\x04\x00")                                # ret 4: no scan this frame
    asm.label("notyet")
    asm.raw(b"\x9D\x61")                                    # popfd / popad, then as usual
    asm.label("incall")
    # --- a call that must wait until Jill can move (v7): same fields as request 2
    asm.raw(b"\x83\x3D" + d(D_CALL_FLAG) + bytes([IN_CONTROL]))   # cmp [call_flag],4
    asm.rel32(b"\x0F\x85", "box")                          # jne box
    asm.raw(b"\x60\x9C")                                    # pushad / pushfd
    asm.raw(b"\x89\xE5")                                    # mov ebp,esp
    asm.raw(b"\xFF\x35" + d(D_CALL_ARGS + 8))               # push [arg3]
    asm.raw(b"\xFF\x35" + d(D_CALL_ARGS + 4))               # push [arg2]
    asm.raw(b"\xFF\x35" + d(D_CALL_ARGS))                   # push [arg1]
    asm.raw(b"\x8B\x0D" + d(D_CALL_THIS))                   # mov ecx,[call_this]
    asm.raw(b"\xFF\x15" + d(D_CALL_FUNC))                   # call [call_func]
    asm.raw(b"\xA3" + d(D_CALL_RESULT))                    # mov [call_result],eax
    asm.raw(b"\x89\xEC")                                    # mov esp,ebp
    asm.raw(b"\xC7\x05" + d(D_CALL_FLAG) + i32(DONE))       # mov [call_flag],2
    asm.raw(b"\x9D\x61")                                    # popfd / popad (stack as on entry)
    asm.label("box")
    asm.raw(b"\x83\x3D" + d(D_BOX_FLAG) + b"\x01")          # cmp [box_flag],1
    asm.rel32(b"\x0F\x85", "scan")                          # jne scan
    asm.raw(b"\xC7\x05" + d(D_BOX_FLAG) + i32(DONE))         # mov [box_flag],2
    asm.raw(b"\x6A\x07")                                     # push 7
    asm.raw(b"\x8B\x0D" + i32(a["inv_ptr"]))                 # mov ecx,[0xCF2F28]
    asm.rel32(b"\xE8", a["set_state_bit"])                   # call 0x4EE130 (ret 4)
    asm.raw(b"\x6A\x01\x6A\x00\x6A\x00\x6A\x00\x6A\x00\x6A\x05")   # push 1,0,0,0,0,5
    asm.raw(b"\x8B\x0D" + i32(a["menu_ptr"]))                # mov ecx,[0xCF30D8]
    asm.rel32(b"\xE8", a["open_menu"])                       # call OpenMenu (ret 0x18)
    asm.raw(b"\xB8\x01\x00\x00\x00")                        # mov eax,1
    asm.raw(b"\xC2\x04\x00")                                # ret 4
    asm.label("scan")
    asm.rel32(b"\xE9", chain_to or a["examine"])             # jmp to the real scan
    return asm.build()


class Autosaver:
    """Installs the hook once per game process and runs saves on request."""
    def __init__(self, conn, build_key: str):
        key = build_key.replace("_steamless", "")
        if key not in ADDR:
            raise AutosaveError("Autosave isn't known for this game version.")
        self.conn = conn
        self.a = {k: v - hv.DEFAULT_IMAGE_BASE + conn.module_base for k, v in ADDR[key].items()}
        self.cave: Optional[int] = None
        self.chained_to: Optional[int] = None   # another mod's hook we call through (BhdTool)
        self.box_hook_error: Optional[str] = "not installed"

    # ------------------------------------------------------------------ install
    def _call_target(self, site: str = "hook") -> int:
        code = self.conn.read_bytes(self.a[site], 5)
        if code[0] != 0xE8:
            raise AutosaveError(f"Unexpected game code at the {site}: {code.hex(' ')}")
        return (self.a[site] + 5 + struct.unpack("<i", code[1:])[0]) & 0xFFFFFFFF

    def install(self) -> int:
        target = self._call_target()
        chain_to = None
        if target != self.a["late_update"]:
            # already hooked: ours (client restarted) or another mod's. Seed test 3 (2026-11-11):
            # BhdTool's dinput8.dll hooks this same call at game start, even when its menu never
            # appears. Then we call BhdTool's hook from ours, and it calls the game as before.
            try:
                ours = self.conn.read_bytes(target + D_MAGIC, 8) == MAGIC
            except Exception:
                ours = False
            if ours:
                self.cave = target
                try:
                    hooked = self._call_target("examine_hook") == target + BOX_STUB
                except Exception:
                    hooked = False
                self.box_hook_error = None if hooked else self._install_box_hook(target)
                return target
            chain_to = target      # another mod's hook, or an older version of ours
        base = self.conn.alloc_code(0x1000)
        code = cave_code(base, self.a, chain_to)
        self.conn.write_bytes(base, code)
        self.conn.write_bytes(base + D_MAGIC, MAGIC + struct.pack("<IIIIIIII", IDLE, 0, 0, 0, IDLE, 0, 0, IDLE))
        rel = struct.pack("<i", base - (self.a["hook"] + 5))
        self.conn.write_code(self.a["hook"] + 1, rel)        # only the 4 target bytes change
        if self._call_target() != base:
            raise AutosaveError("The hook didn't take (read-back mismatch).")
        self.cave = base
        self.chained_to = chain_to
        self.box_hook_error = self._install_box_hook(base)
        return base

    def _install_box_hook(self, base: int) -> Optional[str]:
        """Point the trigger-scan call at our box stub. None = done, else why not (autosave and
        the rest still work without it)."""
        try:
            for name, first in FIRST_BYTES.items():
                code = self.conn.read_bytes(self.a[name], len(first))
                if code != first and code[0] != 0xE9:      # E9 = BhdTool's detour on it: fine
                    return f"unexpected game code at {name}"
            target = self._call_target("examine_hook")
            chain = None if target == self.a["examine"] else target   # e.g. another mod's hook
            stub = base + BOX_STUB
            self.conn.write_bytes(stub, box_stub_code(base, self.a, chain))
            self.conn.write_code(self.a["examine_hook"] + 1, struct.pack("<i", stub - (self.a["examine_hook"] + 5)))
            if self._call_target("examine_hook") != stub:
                return "read-back mismatch"
            return None
        except Exception as exc:          # ProcessError etc.
            return str(exc)

    # ------------------------------------------------------------------ saving
    def _u32(self, addr):
        return struct.unpack("<I", self.conn.read_bytes(addr, 4))[0]

    def flag(self) -> int:
        return self._u32(self.cave + D_FLAG)

    def game_idle(self) -> bool:
        """No save running and storage not busy (checked again by the cave itself)."""
        inv = self._u32(self.a["inv_ptr"])
        store = self._u32(self.a["savedata_singleton"])
        if not inv or not store:
            return False
        return self._u32(inv + SAVE_OBJECT + STATE) == 0 and self._u32(store + STORAGE_BUSY) == 0

    def request(self, slot_index: int):
        """Save to a slot. With the box stub in place the save starts only in a frame Jill can
        move (WAIT_CONTROL, v9); without it, at the next late update (as before)."""
        if not 0 <= slot_index <= 7:
            raise AutosaveError("Save slot must be 1-8.")
        if self.flag() in (REQUESTED, RUNNING, WAIT_CONTROL):
            raise AutosaveError("A save is already running.")
        self.conn.write_bytes(self.cave + D_SLOT, struct.pack("<I", slot_index))
        flag = REQUESTED if self.box_hook_error else WAIT_CONTROL
        self.conn.write_bytes(self.cave + D_FLAG, struct.pack("<I", flag))

    def waiting_for_control(self) -> bool:
        return self.flag() == WAIT_CONTROL

    def poll(self) -> Optional[int]:
        """None while saving; the game's result code (0 = saved) once done."""
        if self.flag() != DONE:
            return None
        result = self._u32(self.cave + D_RESULT)
        self.conn.write_bytes(self.cave + D_FLAG, struct.pack("<I", IDLE))
        return result

    def cancel(self):
        """Give up a request that never started (e.g. the player left to the title screen)."""
        if self.flag() in (REQUESTED, WAIT_CONTROL):
            self.conn.write_bytes(self.cave + D_FLAG, struct.pack("<I", IDLE))

    # ------------------------------------------------------------------ calls
    def play_sound(self, bank: int, sound_id: int) -> bool:
        """Queue a game sound effect (see CALLABLE play_se). False = no sound system yet / busy."""
        if not (0 <= bank <= 3 and 0 <= sound_id <= 0x3FF):
            raise AutosaveError("Sound bank must be 0-3 and id 0-1023.")
        snd = self._u32(self.a["sound_ptr"])
        if not snd or not self.call_ready():
            return False
        self.request_call("play_se", snd, (bank, sound_id, 0))
        return True

    def call_result(self) -> int:
        """eax of the last finished call (v8)."""
        return self._u32(self.cave + D_CALL_RESULT)

    def call_done(self) -> bool:
        return self.cave is not None and self._u32(self.cave + D_CALL_FLAG) == DONE

    def address(self, name: str) -> int:
        return self.a[name]

    def call_ready(self) -> bool:
        if self.cave is None:
            return False
        flag = self._u32(self.cave + D_CALL_FLAG)
        if flag == IN_CONTROL and time.time() - getattr(self, "in_control_since", 0) > IN_CONTROL_TIMEOUT:
            self.conn.write_bytes(self.cave + D_CALL_FLAG, struct.pack("<I", IDLE))   # never picked up
            return True
        return flag in (IDLE, DONE)

    def request_call(self, name: str, this: int, args=(), in_control: bool = False):
        """Ask the routine to run game function `name` with ecx = this and up to 3 int arguments,
        on the game's thread. in_control: only once Jill can move (run from the box stub, v7)."""
        if in_control and self.box_hook_error:
            raise AutosaveError(f"Can't wait for player control: {self.box_hook_error}")
        if name not in CALLABLE or not this or len(args) > 3:
            raise AutosaveError(f"Not allowed: {name}")
        func = self.a[name]
        if self.conn.read_bytes(func, len(CALLABLE[name])) != CALLABLE[name]:
            raise AutosaveError(f"Unexpected game code at {name}; not calling it.")
        if not self.call_ready():
            raise AutosaveError("Another call is still running.")
        a = list(args) + [0] * (3 - len(args))
        self.conn.write_bytes(self.cave + D_CALL_ARGS, struct.pack("<III", *[v & 0xFFFFFFFF for v in a]))
        self.conn.write_bytes(self.cave + D_CALL_THIS, struct.pack("<I", this))
        self.conn.write_bytes(self.cave + D_CALL_FUNC, struct.pack("<I", func))
        if in_control:
            self.in_control_since = time.time()
        self.conn.write_bytes(self.cave + D_CALL_FLAG, struct.pack("<I", IN_CONTROL if in_control else REQUESTED))

    # ------------------------------------------------------------------ item box
    def box_state(self) -> int:
        """IDLE, REQUESTED (waiting for the game's next trigger scan) or DONE (opened)."""
        return self._u32(self.cave + D_BOX_FLAG)

    def open_item_box(self):
        """Ask for the item box: it opens at the game's next trigger scan (next frame Jill can move)."""
        if self.box_hook_error:
            raise AutosaveError(f"Item box anywhere isn't available: {self.box_hook_error}")
        if self.box_state() == REQUESTED:
            raise AutosaveError("Already opening.")
        self.conn.write_bytes(self.cave + D_BOX_FLAG, struct.pack("<I", REQUESTED))

    def clear_item_box_done(self):
        """Opened: back to idle for the next request."""
        if self.box_state() == DONE:
            self.conn.write_bytes(self.cave + D_BOX_FLAG, struct.pack("<I", IDLE))

    def cancel_item_box(self):
        """Withdraw a request the game never picked up (so the box doesn't pop up later)."""
        if self.box_state() == REQUESTED:
            self.conn.write_bytes(self.cave + D_BOX_FLAG, struct.pack("<I", IDLE))
