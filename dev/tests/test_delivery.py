"""Offline tests for Milestone 6 (item box delivery) using a fake game memory."""
import struct
import tempfile
import unittest
from pathlib import Path

from client import hd_versions as hv
from client.hd_delivery import DeliveryError, Journal, choose_empty_slot, deliver_to_box
from client.pc_process import ProcessConnection, ProcessError

INV = 0x2DC68C30
BOX = INV + hv.ITEM_BOX_OFFSET


class FakeMemory:
    def __init__(self, box_entries=None, writable=True):
        self.mem = bytearray(0x1000)
        self.writes = []
        self.writable = writable
        self.before_write = None          # hook to simulate the player acting mid-delivery
        for i, (iid, qty) in (box_entries or {}).items():
            struct.pack_into("<ii", self.mem, hv.ITEM_BOX_OFFSET + i * 8, iid, qty)

    def read_bytes(self, address, size):
        o = address - INV
        if self.before_write and size == 8:
            hook, self.before_write = self.before_write, None
            hook(self)
        return bytes(self.mem[o:o + size])

    def write_bytes(self, address, data):
        if not self.writable:
            raise ProcessError("read-only")
        o = address - INV
        self.mem[o:o + len(data)] = data
        self.writes.append((address, bytes(data)))

    def slot(self, i):
        return struct.unpack_from("<ii", self.mem, hv.ITEM_BOX_OFFSET + i * 8)


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.journal = Journal(Path(self.tmp.name) / "j.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def test_first_empty_slot_skips_used_ones_and_gaps_are_reused(self):
        # box doesn't compact: slot 2 empty between used slots 1 and 3
        mem = FakeMemory({0: (33, 1), 2: (47, 1)})
        d = deliver_to_box(mem, INV, 34, 1, self.journal)
        self.assertEqual(d.slot_number, 2)
        self.assertEqual(mem.slot(1), (34, 1))
        self.assertEqual(mem.slot(0), (33, 1))       # untouched
        self.assertEqual(mem.slot(2), (47, 1))       # untouched
        self.assertEqual(len(mem.writes), 1)
        self.assertEqual(mem.writes[0][0], BOX + 8)

    def test_full_box_writes_nothing(self):
        mem = FakeMemory({i: (34, 1) for i in range(256)})
        with self.assertRaises(DeliveryError):
            deliver_to_box(mem, INV, 34, 1, self.journal)
        self.assertEqual(mem.writes, [])
        self.assertEqual(self.journal.entries()[-1]["why"], "box full")

    def test_slot_filled_at_last_moment_writes_nothing(self):
        mem = FakeMemory()
        mem.before_write = lambda m: struct.pack_into("<ii", m.mem, hv.ITEM_BOX_OFFSET, 68, 2)
        with self.assertRaises(DeliveryError):
            deliver_to_box(mem, INV, 34, 1, self.journal)
        self.assertEqual(mem.writes, [])
        self.assertEqual(mem.slot(0), (68, 2))       # player's item kept

    def test_no_game_loaded(self):
        with self.assertRaises(DeliveryError):
            deliver_to_box(FakeMemory(), 0, 34, 1, self.journal)

    def test_journal_records_intent_then_delivered(self):
        deliver_to_box(FakeMemory(), INV, 34, 1, self.journal, reason="test")
        events = [e["event"] for e in self.journal.entries()]
        self.assertEqual(events, ["intent", "delivered"])


    def test_choose_empty_slot(self):
        self.assertEqual(choose_empty_slot(struct.pack("<iiii", 1, 1, 0, 0)), 1)
        self.assertIsNone(choose_empty_slot(struct.pack("<ii", 1, 1)))


class ReadOnlyGuardTests(unittest.TestCase):
    def test_read_only_connection_refuses_to_write(self):
        conn = ProcessConnection.__new__(ProcessConnection)   # skip Windows-only setup
        conn.writable = False
        with self.assertRaises(ProcessError):
            conn.write_bytes(0x1000, b"\x00")


if __name__ == "__main__":
    unittest.main()
