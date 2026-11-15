"""Offline tests for the 2026-11-14 test tools (room jump, load menu watch, death memory, boss watch)."""
import struct
import unittest

import hd_boss_watch as boss
import hd_death_memory_test as death
import hd_load_menu_watch as load
import hd_room_jump_test as jump


class RoomJumpStubTests(unittest.TestCase):
    BASE = 0x10000000

    def test_stub_layout(self):
        code = jump.stub_code(self.BASE, 0x0047D6E0)
        flag = struct.pack("<I", self.BASE + jump.D_FLAG)
        self.assertEqual(code[:7], b"\x83\x3D" + flag + b"\x01")             # cmp [flag], 1
        self.assertIn(b"\x8B\x7C\x24\x14", code)                             # arg3 after two pushes
        self.assertIn(b"\xBE" + struct.pack("<I", self.BASE + jump.D_TARGET), code)
        self.assertIn(b"\xF3\xA5", code)                                     # rep movsd (8 dwords)
        self.assertIn(b"\xC2\x0C\x00", code)                                 # ret 0Ch, like the game's
        self.assertLess(len(code), jump.D_MAGIC)                             # code stays below the data

    def test_jne_lands_on_the_pass_through_jump(self):
        code = jump.stub_code(self.BASE, 0x0047D6E0)
        rel = struct.unpack_from("<i", code, 9)[0]
        target = 13 + rel                                                    # jne is at 7..12
        self.assertEqual(code[target], 0xE9)
        dest = self.BASE + target + 5 + struct.unpack_from("<i", code, target + 1)[0]
        self.assertEqual(dest, 0x0047D6E0)

    def test_target_matches_fetch_door_room_data(self):
        raw = jump.target_bytes(0x314, (1.0, 2.0, 3.0, 0.5, 7))
        self.assertEqual(len(raw), 32)
        x, y, z, page, ang, stage, room, cut = struct.unpack("<3fIf3i", raw)
        self.assertEqual((x, y, z, page, ang, stage, room, cut), (1.0, 2.0, 3.0, 0, 0.5, 3, 0x14, 7))

    def test_parse(self):
        self.assertEqual(jump.parse("105, 314/313"), [(0x105, None), (0x314, 0x313)])


class LoadMenuTests(unittest.TestCase):
    def test_kind(self):
        self.assertEqual(load.kind(0x00C38320, 0), "LOAD menu")
        self.assertEqual(load.kind(0x00C38238 + 0x10000, 0x10000), "SAVE menu")
        self.assertTrue(load.kind(0x1234, 0).startswith("other"))


class FakeGame:
    """A flat memory image: the mode table at 0xCB6530 and a title object at 0x2000000."""
    def __init__(self):
        self.mem = {}
        for n, h in enumerate((0x466E20, 0x467090, 0x467A60, 0x467C00, 0x467DB0, 0x468040, 0x468120)):
            self.put(load.TITLE_MODES + 4 * n, struct.pack("<I", h))
        self.title = 0x2000000
        self.put(self.title, b"\0" * 0xE8)
        self.put(self.title, struct.pack("<I", load.TITLE_VTABLE))
        self.put(self.title + load.T_HANDLER, struct.pack("<Ii", 0x467DB0, 4))
        self.put(self.title + load.T_STEP, struct.pack("<i", 2))

    def put(self, address, data):
        for i, b in enumerate(data):
            self.mem[address + i] = b

    def read_bytes(self, address, size):
        return bytes(self.mem.get(address + i, 0) for i in range(size))

    def write_bytes(self, address, data):
        self.put(address, data)

    def readable_regions(self, limit=0):
        return [(self.title - 0x100, 0x200)]


class TitleLoadTests(unittest.TestCase):
    def test_finds_and_checks_the_title(self):
        game = FakeGame()
        self.assertEqual(load.find_title(game, 0), game.title)
        self.assertEqual(load.title_mode(game, game.title), (4, 2))
        game.put(game.title + load.T_HANDLER, struct.pack("<I", 0x468040))   # handler != mode 4's
        self.assertFalse(load.is_title(game, game.title, 0))

    def test_open_load_is_what_the_menu_item_does(self):
        game = FakeGame()
        load.open_load_from_title(game, game.title, 0)
        handler, mode, c0 = struct.unpack("<IiI", game.read_bytes(game.title + load.T_HANDLER, 12))
        self.assertEqual((handler, mode, c0), (0x468120, 6, 0xFFFFFFFF))
        self.assertEqual(load.title_mode(game, game.title), (6, 0))
        self.assertTrue(load.is_title(game, game.title, 0))


class DeathMemoryTests(unittest.TestCase):
    def test_unlock_diff_names_flag_39(self):
        old = bytearray(32)
        new = bytearray(32)
        new[39 // 8] |= 1 << (39 % 8)
        self.assertEqual(death.unlock_diff(bytes(new), bytes(old)), [(39, 0)])
        self.assertIn("Graveyard", death.flag_label(39))

    def test_byte_diff(self):
        self.assertEqual(death.byte_diff(b"\x00\x01", b"\x00\x03", 0x200), [(0x201, 1, 3)])


class BossWatchTests(unittest.TestCase):
    def test_turned_on_only_reports_new_bits(self):
        self.assertEqual(boss.turned_on(b"\x01\x00", b"\x00\x05", 0x270), [(0x271, 0), (0x271, 2)])

    def test_candidates_marked(self):
        self.assertIn("Tyrant", boss.describe(0x2AE, 1))
        self.assertIn("kill table", boss.describe(0x2AE, 1))
        self.assertNotIn("candidate", boss.describe(0x300, 0))


if __name__ == "__main__":
    unittest.main()
