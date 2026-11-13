"""
The "pickup guard".

When a randomised pickup's flag bit turns on, the location counts as checked
and the vanilla item the game just gave is taken back out of Jill's inventory,
so the only items the player gets are the ones the multiworld sends.

Why this method: finding and rewriting the room's own pickup records (the
cleaner method) is still being investigated - see claude/milestone-7 notes.
This one only needs things already proven: the flag bits (Milestone 5), the
inventory layout, and careful memory writes (Milestone 6).

Inventory facts it relies on (ours, 2026-11-09):
  * 8 inventory slots at structure +0x38, then hidden slot 1 (Jill's Lock Pick)
    at +0x78 - so we treat the Lock Pick slot as a 9th slot (index 8).
  * a new item goes into the first empty slot; matching ammo / ink ribbons
    stack onto an existing slot.
  * the game tolerates a gap in the inventory (it only tidies up when the
    inventory menu opens), so emptying a slot is safe.

Known limits (written down so nobody is surprised):
  * the pickup message still names the vanilla item.
  * defensive items (daggers, batteries) and maps/files aren't in the
    inventory slots, so they are not handled - leave those locations vanilla.
  * if the client isn't running at the moment of the pickup, the vanilla item
    stays (the journal will show the check without a removal).
"""

import struct
from typing import List, Optional, Tuple

SLOT = struct.Struct("<ii")
GUARDED_SLOTS = 9          # 8 inventory slots + hidden slot 1 (Lock Pick)


# (flag offset, bit) -> pickup. Only CONFIRMED inventory pickups from
# claude/pickup-flags.md. Dagger (+0x2F0 bit 7) and the 1F map (+0x316 bit 0)
# are left out on purpose (not inventory items / only "probable").


def parse_slots(data: bytes) -> List[Tuple[int, int]]:
    return [SLOT.unpack_from(data, i * SLOT.size) for i in range(len(data) // SLOT.size)]


def plan_removal(before: List[Tuple[int, int]], after: List[Tuple[int, int]],
                 item_id: int) -> Optional[List[Tuple[int, Tuple[int, int]]]]:
    """Work out which slot writes undo the gain of item_id between two inventory reads.

    Returns [(slot_index, (new_id, new_qty))], [] if nothing of item_id was gained,
    or None if the change doesn't look like a simple pickup (then we don't touch anything).
    """
    changed = [i for i, (b, a) in enumerate(zip(before, after)) if b != a]
    if not changed:
        return []
    if len(changed) != 1:
        return None                       # several slots moved at once - menu reshuffle? play safe
    i = changed[0]
    (b_id, b_qty), (a_id, a_qty) = before[i], after[i]
    if a_id != item_id:
        return None
    if b_id == 0:
        return [(i, (0, 0))]              # brand-new slot -> empty it again
    if b_id == item_id and a_qty > b_qty:
        return [(i, (item_id, b_qty))]    # stacked onto existing -> put the old amount back
    return None


def player_put_back(before: List[Tuple[int, int]], after: List[Tuple[int, int]], item_id: int) -> bool:
    """True if, between two reads, exactly one inventory slot changed and it LOST some of
    item_id - i.e. the player put the item back (e.g. the Wooden Emblem onto the fireplace)."""
    changed = [i for i, (b, a) in enumerate(zip(before, after)) if b != a]
    if len(changed) != 1:
        return False
    (b_id, b_qty), (a_id, a_qty) = before[changed[0]], after[changed[0]]
    if b_id != item_id:
        return False
    return a_id == 0 or (a_id == item_id and a_qty < b_qty)


