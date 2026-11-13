"""Offline tests for the Steam (HD Remaster) inventory reader, using a fake process."""

import struct
import unittest

from client import hd_versions as hv
from client.hd_items import ITEM_NAMES, item_name
from client.pc_process import ProcessError
import hd_inventory


class FakeProcess:
    """Pretends to be bhd.exe: a pointer at the build's address -> inventory struct."""
    def __init__(self, build, base=hv.DEFAULT_IMAGE_BASE, slots=None, null_pointer=False):
        self.module_base = base
        self.memory = {}
        inv_addr = 0x12340000
        ptr_addr = build.inventory_pointer - hv.DEFAULT_IMAGE_BASE + base
        self.memory[ptr_addr] = (0 if null_pointer else inv_addr).to_bytes(4, "little")
        slots = slots or [(0, 0)] * 8
        self.memory[inv_addr + hv.INVENTORY_SLOTS_OFFSET] = b"".join(struct.pack("<ii", *s) for s in slots)

    def read_bytes(self, address, size):
        if address not in self.memory:
            raise ProcessError(f"bad address 0x{address:08X}")
        return self.memory[address][:size]


SEP2026 = hv.find_build("39b840663e4b1a6835c60cbd176e4ee6c21b9197fc2c2dd733f2a7c36a0b429a")


class HDTests(unittest.TestCase):
    def test_build_lookup(self):
        self.assertEqual(SEP2026.inventory_pointer, 0x00CF2F28)
        self.assertIsNone(hv.find_build("00" * 32))
        self.assertEqual(len({b.sha256 for b in hv.BUILDS}), len(hv.BUILDS))

    def test_item_table(self):
        self.assertEqual(len(ITEM_NAMES), 133)
        self.assertEqual(item_name(34), "Green Herb")
        self.assertEqual(item_name(999), "Unknown item 999")

    def test_reads_slots(self):
        slots = [(1, 1), (3, 15), (34, 1)] + [(0, 0)] * 5
        got = hd_inventory.read_inventory(FakeProcess(SEP2026, slots=slots), SEP2026, 4)
        self.assertEqual(got, slots)

    def test_rebases_if_loaded_elsewhere(self):
        slots = [(43, 1)] + [(0, 0)] * 7
        fake = FakeProcess(SEP2026, base=0x00A00000, slots=slots)
        self.assertEqual(hd_inventory.read_inventory(fake, SEP2026, 4), slots)

    def test_title_screen_null_pointer(self):
        self.assertIsNone(hd_inventory.read_inventory(FakeProcess(SEP2026, null_pointer=True), SEP2026, 4))


if __name__ == "__main__":
    unittest.main()


class ItemBoxLayoutTests(unittest.TestCase):
    """Layout confirmed against TessarionAM's in-game box list on 2026-11-09."""

    def test_offsets(self):
        self.assertEqual(hv.HIDDEN_SLOTS_OFFSET, 0x78)
        self.assertEqual(hv.ITEM_BOX_OFFSET, 0x88)
        self.assertEqual(hv.ITEM_BOX_SLOTS, 256)

    def test_box_numbered_like_the_game(self):
        inv = 0x2DC68C30
        box = [(0, 0)] * 256
        box[0], box[11], box[255] = (47, 1), (68, 2), (6, 0)   # Shield Key first, Shotgun last

        class Fake:
            module_base = hv.DEFAULT_IMAGE_BASE
            mem = {SEP2026.inventory_pointer: inv.to_bytes(4, "little"),
                   inv + 0x78: struct.pack("<iiii", 43, 0, 0, 0),
                   inv + 0x88: b"".join(struct.pack("<ii", *b) for b in box)}

            def read_bytes(self, a, n):
                return self.mem[a][:n]

        hidden, entries = hd_inventory.read_item_box(Fake(), SEP2026, 4)
        self.assertEqual(hidden[0], (43, 0))                   # Jill's Lock Pick lives here
        self.assertEqual(entries[0], (1, 47, 1))
        self.assertEqual(entries[-1], (256, 6, 0))
