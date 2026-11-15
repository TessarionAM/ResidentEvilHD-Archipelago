"""Autoload after a death (client/autoload.py) - offline tests with a fake game memory."""
import struct
import unittest

from ..client import autoload as al
from ..client import hd_versions as hv


class SparseGame:
    """Sparse memory: the title mode table, a title object and the Load menu behind the manager."""
    TITLE, MGR, MENU = 0x2000000, 0x3000000, 0x3100000

    def __init__(self, mode=4):
        self.mem = {}
        for n, h in enumerate((0x466E20, 0x467090, 0x467A60, 0x467C00, 0x467DB0, 0x468040, 0x468120)):
            self.put(al.TITLE_MODES + 4 * n, struct.pack("<I", h))
        self.put(self.TITLE, b"\0" * al.TITLE_SIZE)
        self.put(self.TITLE, struct.pack("<I", al.TITLE_VTABLE))
        self.set_mode(mode)
        self.put(al.MENU_MANAGER, struct.pack("<I", self.MGR))
        self.put(self.MGR + al.MENU_SLOT, struct.pack("<I", self.MENU))
        self.put(self.MENU, struct.pack("<I", al.LOAD_MENU_VTABLE))
        self.menu(2, 0)
        self.scans = 0

    def set_mode(self, mode):
        handler = struct.unpack("<I", self.read_bytes(al.TITLE_MODES + 4 * mode, 4))[0]
        self.put(self.TITLE + al.T_HANDLER, struct.pack("<Ii", handler, mode))

    def menu(self, phase, state):
        self.put(self.MENU + al.PHASE, struct.pack("<i", phase))
        self.put(self.MENU + al.STATE, struct.pack("<i", state))

    def put(self, address, data):
        for i, b in enumerate(data):
            self.mem[address + i] = b

    def read_bytes(self, address, size):
        return bytes(self.mem.get(address + i, 0) for i in range(size))

    def write_bytes(self, address, data):
        self.put(address, data)

    def readable_regions(self, limit=0):
        self.scans += 1
        return [(self.TITLE - 0x100, 0x400)]

    def i32(self, address):
        return struct.unpack("<i", self.read_bytes(address, 4))[0]


class AutoLoaderTests(unittest.TestCase):
    def loader(self, game, slot=7):
        return al.AutoLoader(game, 0, slot)

    def test_does_nothing_unless_armed(self):
        game = SparseGame()
        a = self.loader(game)
        self.assertIsNone(a.tick())
        self.assertEqual(game.scans, 0)
        self.assertEqual(game.i32(game.TITLE + al.T_MODE), 4)

    def test_title_main_menu_to_load_then_slot(self):
        game = SparseGame()
        a = self.loader(game)
        a.arm()
        self.assertIsNone(a.tick())                         # finds the title, switches it to Load
        self.assertEqual(game.i32(game.TITLE + al.T_MODE), 6)
        self.assertEqual(game.i32(game.TITLE + al.T_STEP), 0)
        self.assertEqual(game.i32(game.TITLE + al.T_C0), -1)
        self.assertEqual(struct.unpack("<I", game.read_bytes(game.TITLE + al.T_HANDLER, 4))[0], 0x468120)
        self.assertIsNone(a.tick())                         # menu still opening: nothing written
        self.assertEqual(game.i32(game.MENU + al.STATE), 0)
        game.menu(4, 3)
        self.assertIsNone(a.tick())
        game.menu(4, 4)                                     # slots showing
        self.assertIn("slot 8", a.tick())
        self.assertEqual((game.i32(game.MENU + al.SLOT), game.i32(game.MENU + al.STATE)), (7, 7))
        self.assertFalse(a.armed)

    def test_waits_while_the_title_is_not_on_its_main_menu(self):
        game = SparseGame(mode=0)
        a = self.loader(game)
        a.arm()
        a.tick()
        self.assertEqual(game.i32(game.TITLE + al.T_MODE), 0)   # untouched
        game.set_mode(4)
        a.tick()
        self.assertEqual(game.i32(game.TITLE + al.T_MODE), 6)

    def test_rejects_an_object_whose_handler_does_not_match(self):
        game = SparseGame()
        game.put(game.TITLE + al.T_HANDLER, struct.pack("<I", 0x468040))
        a = self.loader(game)
        self.assertFalse(a.is_title(game.TITLE))
        a.arm()
        a.tick()
        self.assertEqual(game.i32(game.TITLE + al.T_MODE), 4)

    def test_scans_are_throttled(self):
        game = SparseGame()
        game.put(game.TITLE, b"\0\0\0\0")                   # no title yet
        a = self.loader(game)
        a.arm()
        a.tick()
        a.tick()
        self.assertEqual(game.scans, 1)

    def test_gives_up_when_slots_never_show(self):
        game = SparseGame()
        a = self.loader(game)
        a.arm()
        a.tick()
        a.opened_at -= al.OPEN_TIMEOUT + 1
        self.assertIn("load your save yourself", a.tick())
        self.assertFalse(a.armed)
        self.assertEqual(game.i32(game.MENU + al.STATE), 0)

    def test_gives_up_when_the_title_never_comes(self):
        game = SparseGame()
        game.put(game.TITLE, b"\0\0\0\0")
        a = self.loader(game)
        a.arm()
        a.armed_at -= al.GIVE_UP_AFTER + 1
        self.assertIn("gave up", a.tick())
        self.assertFalse(a.armed)
