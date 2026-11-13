"""
Milestone 6: put an item into the item box (Steam HD Remaster).

This is the first code in the project that WRITES to the game's memory, so it is
deliberately small and careful:

  * It only ever writes into an EMPTY box slot ({0, 0}). It never overwrites,
    merges or stacks anything the player owns.
  * It re-reads the chosen slot immediately before writing and gives up if it
    changed (e.g. the player moved something in that instant).
  * After writing it reads the slot back and checks it holds exactly what we wrote.
  * Every delivery is recorded in a journal file (one JSON object per line):
    first an "intent" line, then "delivered" or "failed". The AP client will use
    this journal so an item is never lost and never delivered twice.
  * Undo only removes our item if the slot still holds exactly what we wrote.

Tested in-game by TessarionAM, 2026-11-09:
  * the item appears in the slot we chose, works normally and stays after
    closing/reopening the box;
  * writing while the box menu is OPEN is fine too - it shows up in real time.
    Only cosmetic glitch: if the cursor is already on that slot, the picture
    shows without the name until the cursor moves.

Layout (ours, confirmed 2026-11-09, see hd_versions.py): item box = 256 slots of
{int32 item_id, int32 quantity} at inventory structure + 0x88.
"""

import json
import struct
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import hd_versions as hv

SLOT = struct.Struct("<ii")
EMPTY = (0, 0)


class DeliveryError(Exception):
    pass


@dataclass
class Delivery:
    item_id: int
    quantity: int
    slot_number: int      # 1-256, as shown in-game
    address: int


def choose_empty_slot(box_bytes: bytes) -> Optional[int]:
    """Index (0-255) of the first empty slot, or None if the box is full."""
    for i in range(len(box_bytes) // SLOT.size):
        if SLOT.unpack_from(box_bytes, i * SLOT.size) == EMPTY:
            return i
    return None


class Journal:
    """Append-only record of every delivery attempt."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def write(self, **entry):
        entry.setdefault("time", time.strftime("%Y-%m-%d %H:%M:%S"))
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def entries(self):
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]


def box_address(inventory_struct: int) -> int:
    return inventory_struct + hv.ITEM_BOX_OFFSET


def deliver_to_box(conn, inventory_struct: int, item_id: int, quantity: int, journal: Journal,
                   reason: str = "", stack_limit: Optional[int] = None) -> Delivery:
    """Put {item_id, quantity} in the item box. If stack_limit is given (ammo, ink ribbons) and a
    box slot already holds that item with room to spare, add to that stack (TessarionAM, 2026-11-11);
    otherwise use the first empty slot. Raises DeliveryError on any doubt."""
    if inventory_struct == 0:
        raise DeliveryError("No game is loaded (inventory pointer is 0).")
    base = box_address(inventory_struct)
    if stack_limit:
        data = conn.read_bytes(base, hv.ITEM_BOX_SLOTS * SLOT.size)
        for index in range(hv.ITEM_BOX_SLOTS - 2):
            sid, sq = SLOT.unpack_from(data, index * SLOT.size)
            if sid == item_id and 0 < sq and sq + quantity <= stack_limit:
                return _stack_onto(conn, base + index * SLOT.size, index, item_id, sq, quantity,
                                   journal, reason)
    # the last two slots are the client's records (seed tag, delivery count): never items
    return _deliver_into(conn, base, hv.ITEM_BOX_SLOTS - 2, "box", item_id, quantity, journal, reason)


def _stack_onto(conn, address: int, index: int, item_id: int, old_qty: int, quantity: int,
                journal: Journal, reason: str) -> Delivery:
    """Add quantity to an existing box stack, with the same intent / re-check / read-back rules."""
    new_qty = old_qty + quantity
    journal.write(event="intent", item_id=item_id, quantity=quantity, slot_number=index + 1,
                  address=address, reason=reason, where="box", stacked_from=old_qty, expect=[item_id, new_qty])
    if SLOT.unpack(conn.read_bytes(address, SLOT.size)) != (item_id, old_qty):
        journal.write(event="failed", item_id=item_id, quantity=quantity, slot_number=index + 1,
                      why="stack changed just before writing")
        raise DeliveryError(f"Box slot {index + 1} changed just before writing - nothing written.")
    new = SLOT.pack(item_id, new_qty)
    conn.write_bytes(address, new)
    back = conn.read_bytes(address, SLOT.size)
    if back != new:
        journal.write(event="failed", item_id=item_id, quantity=quantity, slot_number=index + 1,
                      why=f"read-back mismatch {back.hex()}")
        raise DeliveryError(f"Wrote box slot {index + 1} but read back {SLOT.unpack(back)} - please report this with your client log.")
    journal.write(event="delivered", item_id=item_id, quantity=quantity, slot_number=index + 1,
                  address=address, where="box", stacked_onto=old_qty)
    return Delivery(item_id, quantity, index + 1, address)


class InventoryFull(DeliveryError):
    """Jill's 8 inventory slots are all in use."""


def deliver_to_inventory(conn, inventory_struct: int, item_id: int, quantity: int, journal: Journal,
                         reason: str = "") -> Delivery:
    """Write {item_id, quantity} into Jill's first empty INVENTORY slot (added 2026-11-10 so a
    received key can't get stuck in an item box you can't reach). Raises InventoryFull if all
    8 slots are used, DeliveryError on any other doubt. Same safety rules as the box."""
    if inventory_struct == 0:
        raise DeliveryError("No game is loaded (inventory pointer is 0).")
    return _deliver_into(conn, inventory_struct + hv.INVENTORY_SLOTS_OFFSET, hv.INVENTORY_SLOT_COUNT,
                         "inventory", item_id, quantity, journal, reason)


def _deliver_into(conn, base: int, slots: int, where: str, item_id: int, quantity: int,
                  journal: Journal, reason: str) -> Delivery:
    if item_id <= 0 or quantity < 0:
        raise DeliveryError(f"Refusing odd item/quantity: {item_id} x{quantity}")

    data = conn.read_bytes(base, slots * SLOT.size)
    index = choose_empty_slot(data)
    if index is None:
        journal.write(event="failed", item_id=item_id, quantity=quantity, why=f"{where} full", reason=reason)
        if where == "inventory":
            raise InventoryFull("Jill's inventory is full.")
        raise DeliveryError("The item box is full (all 256 slots used). Item kept for later.")

    address = base + index * SLOT.size
    journal.write(event="intent", item_id=item_id, quantity=quantity, slot_number=index + 1,
                  address=address, reason=reason, where=where)

    # Last-moment check: still empty?
    if SLOT.unpack(conn.read_bytes(address, SLOT.size)) != EMPTY:
        journal.write(event="failed", item_id=item_id, quantity=quantity, slot_number=index + 1,
                      why="slot stopped being empty", where=where)
        raise DeliveryError(f"{where.title()} slot {index + 1} changed just before writing - nothing written.")

    new = SLOT.pack(item_id, quantity)
    conn.write_bytes(address, new)

    back = conn.read_bytes(address, SLOT.size)
    if back != new:
        journal.write(event="failed", item_id=item_id, quantity=quantity, slot_number=index + 1,
                      why=f"read-back mismatch {back.hex()}", where=where)
        raise DeliveryError(f"Wrote {where} slot {index + 1} but read back {SLOT.unpack(back)} - please report this with your client log.")

    journal.write(event="delivered", item_id=item_id, quantity=quantity, slot_number=index + 1,
                  address=address, where=where)
    return Delivery(item_id, quantity, index + 1, address)


