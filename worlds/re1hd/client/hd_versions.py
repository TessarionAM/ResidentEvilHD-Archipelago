"""
Known builds of Resident Evil HD Remaster (Steam, bhd.exe) and their addresses.

SOURCE: BhdTool by eleval (GPL-3.0) - https://github.com/eleval/BhdTool
        files REmakeHook/src/Game/GameVersion.cpp and GameAddress.cpp,
        as of its commit dated 2026-09-30.

The build is identified by the SHA-256 hash of bhd.exe. The long numbers are
Steam depot manifest IDs (see steamdb.info/depot/304242/manifests/).
"Steamless" builds have the Steam DRM wrapper removed - normal players won't
have those, but they're listed so we recognise them.

Addresses are absolute, assuming bhd.exe loads at its default base 0x00400000
(BhdTool uses them as-is inside the game). Our reader checks the real base
and corrects for it if it ever differs.

The September 2026 build is VERIFIED on TessarionAM's PC (2026-11-09); the others are not.
"""

from dataclasses import dataclass
from typing import Optional

DEFAULT_IMAGE_BASE = 0x00400000


@dataclass(frozen=True)
class HDBuild:
    key: str
    description: str
    sha256: str
    inventory_pointer: int   # address holding a pointer to the inventory structure
    verified: bool = False


_OLD_INV = 0x00D7C9C0   # same for every build before September 2026
_SEP2026_INV = 0x00CF2F28

BUILDS = [
    HDBuild("hd_3831846201811674141", "Steam build 3831846201811674141 (older)",
            "0ab61bada34783a684490858e2005bbd2e9a1b1353eaaad44337bf7abb773b72", _OLD_INV),
    HDBuild("hd_7029559557684186662", "Steam build 7029559557684186662 (older)",
            "d18cdf473c01afbd90ce1df0c3f3bb4a3d6c4ebfe4d792a035894c63a2790f8f", _OLD_INV),
    HDBuild("hd_7029559557684186662_steamless", "Steam build 7029559557684186662, DRM removed",
            "0cb0dc1d2f8d9b2e56de380c39dab3ed93fba10fc063a85e0c5b0623f1869345", _OLD_INV),
    HDBuild("hd_9087090834863155228", "Steam build 9087090834863155228 (pre-Sept 2026)",
            "1f4b8b17a34e65a518508e00002fdb02c5c72fadbb8bc778045d66bbfb8ce28a", _OLD_INV),
    HDBuild("hd_9087090834863155228_steamless", "Steam build 9087090834863155228, DRM removed",
            "6f060443b0ef58bbf79bbe5f3b13ea9664f3fbd5ead3728d65bcac32f6a82baf", _OLD_INV),
    # VERIFIED 2026-11-09 on TessarionAM's PC: loads at 0x00400000, 32-bit, inventory pointer
    # and slot layout correct (Pistol x15 -> x0, Knife, Ink Ribbon x3 matched the screen).
    HDBuild("hd_6699874012183562949", "Steam build 6699874012183562949 (September 2026 update)",
            "39b840663e4b1a6835c60cbd176e4ee6c21b9197fc2c2dd733f2a7c36a0b429a", _SEP2026_INV,
            verified=True),
    HDBuild("hd_6699874012183562949_steamless", "Steam build 6699874012183562949 (Sept 2026), DRM removed",
            "c84611c289f82783ba751d45b81e41616d6b6714d521cf20a2128132e83c4db4", _SEP2026_INV),
]

# Inventory structure (from BhdTool's InventoryTool.cpp):
#   [pointer at inventory_pointer] -> structure:
#       0x00..0x37  unknown (padding)
#       0x38        8 slots, each: int32 item_id, int32 quantity  (little-endian)
INVENTORY_SLOTS_OFFSET = 0x38
INVENTORY_SLOT_COUNT = 8
INVENTORY_SLOT_SIZE = 8

# Found by us (not in BhdTool), Sept 2026 build, 2026-11-09, CONFIRMED against
# TessarionAM's in-game box list (first slot = Shield Key, last slot = Shotgun):
#
#   structure +0x38  8 inventory slots          {int32 id, int32 qty}
#   structure +0x78  HIDDEN slot 1: Jill's Lock Pick lives here (id 43, qty 0)
#                    when she has it - it doesn't take an inventory slot.
#   structure +0x80  HIDDEN slot 2: looks like the EQUIPPED WEAPON (Handgun id 3 in a new
#                    game; its count updated 1 -> 15 when a menu opened). Empty in another save.
#   structure +0x88  ITEM BOX, 256 slots         {int32 id, int32 qty}
#                    box slot 1 in-game = index 0 here.
#
# Item box behaviour seen:
#   - putting an item in stacks onto a matching entry (Ink Ribbon 2 -> 4)
#   - taking an item out leaves an EMPTY slot (the box does not close up)
#   - a new item goes into the slot under the box cursor
# Defensive items (daggers, stun gun batteries) are stored somewhere else - not found yet.
HIDDEN_SLOTS_OFFSET = INVENTORY_SLOTS_OFFSET + INVENTORY_SLOT_COUNT * INVENTORY_SLOT_SIZE   # 0x78
HIDDEN_SLOT_COUNT = 2
ITEM_BOX_OFFSET = HIDDEN_SLOTS_OFFSET + HIDDEN_SLOT_COUNT * INVENTORY_SLOT_SIZE              # 0x88
ITEM_BOX_SLOTS = 256


# ---------------------------------------------------------------------------
# DEFENSIVE ITEMS - found by us 2026-11-10 (finder + live watcher, TessarionAM's save).
# Not in the inventory slots: the game keeps a COUNT per type, int32, in the
# inventory structure. Confirmed by 2 daggers in / 2 used / 3 in / 1 used, and a
# battery pack in / used - the values followed exactly.
DAGGER_COUNT_OFFSET = 0x5088      # item 112 Dagger
BATTERY_COUNT_OFFSET = 0x508C     # item 121 Battery Pack (stun gun)
DEFENSE_COUNT_OFFSETS = {112: DAGGER_COUNT_OFFSET, 121: BATTERY_COUNT_OFFSET}
# Holds the id of the item just picked up (21 Golden Arrow, 22 Book of Curses,
# 112 Dagger, 121 Battery Pack seen), cleared a moment later. Not used yet;
# could help detect maps/files, which aren't inventory items either.
LAST_PICKED_ITEM_OFFSET = 0x50F4


# ---------------------------------------------------------------------------
# CURRENT ROOM - found by us 2026-11-10 (room finder + live watcher).
# Two int32s (stage, room), relative to the FLAGS structure (pointer below).
# Room number = stage * 0x100 + room (numbering from BhdTool's rooms.json).
#   -0x3E0 : the room you are in (updates once the new room has loaded)
#   -0x404 : the room a door is taking you to (changes ~1 s earlier)
#   +0x1F0 : another copy of the current room; -0x288 is a loading copy
#            that briefly shows stage 0 during transitions - not used.
CURRENT_ROOM_OFFSET = -0x3E0
DOOR_TARGET_ROOM_OFFSET = -0x404


# ---------------------------------------------------------------------------
# PICKUP FLAGS - found by us (not in BhdTool), Sept 2026 build only, 2026-11-09.
#
# bhd.exe 0x00CF2FC8 holds a pointer to a structure that contains the
# "item already picked up" bits. It sits in a table of pointers right next to
# the inventory pointer (0x00CF2F28). The same address held the same value in
# every step of two separate runs.
#
# How we know: TessarionAM saved at the typewriter before and after taking the Wooden
# Emblem. Each save makes a new copy of the game state; comparing those copies
# showed 2 bits (plus the inventory). The same bits exist in live memory under
# this pointer, and in the earlier live run they flipped exactly at the pickup
# moment and at no other time:
#     Ink Ribbons (Dining Room)  -> +0x2F2 bit 1
#     Wooden Emblem (Dining Room)-> +0x2EC bit 4  AND  +0x319 bit 5
# Which of the emblem's two bits is "picked up" and which is something else
# (e.g. a puzzle/event state) is NOT known yet. See client/hd_flags.py.
FLAGS_POINTER = {
    "hd_6699874012183562949": 0x00CF2FC8,
    "hd_6699874012183562949_steamless": 0x00CF2FC8,   # same code, assumed (not tested)
}
# Jill's position (x, y, z floats, in the room's own coordinates): pointer paths from bhd.exe,
# found with hd_jill_position_finder.py. Each path: (static address, [offsets], z step).
# Found 2026-11-12 (TessarionAM's run, hd_jill_position_finder_output.txt): one object holds her position
# at +0x40 (and copies at +0xA0, +0xE0); every path below was right after a door in 3 rooms in a
# row (0x405, 0x400, 0x403 - read x -160.6 z 57.3 = the game's own 0x403 door spot). The client
# uses the first path that gives sane numbers; the others are spares from the same run.
_JILL_PATHS = [
    (0x00D59380, [0x14C, 0x40], 8),      # [bhd.exe+0x959380] +0x14C -> object, +0x40 = x, y, z
    (0x00CF3018, [0x5C, 0x530], 8),      # next to the flags pointer (0xCF2FC8)
    (0x00D59380, [0x44, 0xEC0], 8),
]
JILL_POSITION = {
    "hd_6699874012183562949": _JILL_PATHS,
    "hd_6699874012183562949_steamless": _JILL_PATHS,   # same code, assumed (not tested)
}
# How much around the pointer the flag watcher reads (bytes before / after).
# Starts at -0x100 on purpose: from about -0x400 to -0x3E0 there are constantly
# changing floating-point values that would drown out the flags.
FLAGS_WINDOW_BEFORE = 0x100
FLAGS_WINDOW_AFTER = 0x400


def find_build(sha256: str) -> Optional[HDBuild]:
    sha256 = sha256.lower()
    for b in BUILDS:
        if b.sha256 == sha256:
            return b
    return None


# Jill's character data (verified 2026-11-10 with hd_health_watch, see claude/health-and-death.md):
#   manager = [bhd.exe+0x00CF2E84]; index = [manager+0x24] >> 16 (< 0x40)
#   entry = manager + 0x8B0 + index*24; Jill = [entry] if [entry+4] == [manager+0x20]
#   health = int32 at Jill+0x13BC, max health at +0x13C0 (960 on Normal); poisoned = +0x1584 bit 0
CHARACTER_MANAGER_BEFORE_FLAGS = 0x00CF2FC8 - 0x00CF2E84     # same for both Sept 2026 builds
JILL_HEALTH_OFFSET = 0x13BC
JILL_MAX_HEALTH_OFFSET = 0x13C0
JILL_POISON_OFFSET, JILL_POISON_BIT = 0x1584, 0
