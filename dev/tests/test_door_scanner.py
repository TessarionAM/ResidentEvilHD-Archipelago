"""The door scanner must never collect millions of matches (2026-11-11: a 0,0,0 door position
filled TessarionAM's RAM)."""
import struct
import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import hd_door_scanner as ds


class FakeConn:
    def __init__(self, mem: bytes):
        self.mem = mem

    def readable_regions(self, _max):
        yield 0x10000, len(self.mem)

    def read_bytes(self, a, n):
        return self.mem[a - 0x10000:a - 0x10000 + n]


class ScanTests(unittest.TestCase):
    def test_matches_are_capped(self):
        # scanner v2: a pattern found everywhere (a 0,0,0 position) stops at MAX_HITS matches
        zero = struct.pack("<fff", 0, 0, 0)
        found = ds.scan(FakeConn(bytes(8 * 1024 * 1024)), [zero])
        self.assertLessEqual(len(found[zero]), ds.MAX_HITS)

    def test_hits_are_capped(self):
        p = struct.pack("<fff", 1.5, -2.25, 3.0)
        mem = (p + b"\x11" * 4) * 100000
        found = ds.scan(FakeConn(mem), [p])
        self.assertEqual(len(found[p]), ds.MAX_HITS)

    def test_real_door_found(self):
        p = struct.pack("<fff", 1.5, -2.25, 3.0)
        mem = bytes(1000) + p + bytes(1000)
        self.assertEqual(ds.scan(FakeConn(mem), [p])[p], [0x10000 + 1000])


if __name__ == "__main__":
    unittest.main()
