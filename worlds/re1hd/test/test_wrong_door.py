"""Offline tests for the Wrong Door Trap (client/wrong_door.py) with a fake game memory."""
import struct

from ..client import hd_versions as hv
from ..client import wrong_door as wdm
from ..client.game_bridge import Incoming
from ..game_data import DETECTED_PICKUPS, room_visited_flag
from .test_client import FLAGS, BridgeTest

GAME = 0x50000
ARRAY = 0x51000
RECS = 0x52000
INFO = 0x60000
INFO_VT = 0x00ABCD00


class WrongDoorTest(BridgeTest):
    def setUp(self):
        super().setUp()
        self._settle, wdm.SETTLE = wdm.SETTLE, 0.0
        self._bg, wdm.BACKGROUND = wdm.BACKGROUND, False
        self._lock, wdm.CELL_LOCK_SECONDS = wdm.CELL_LOCK_SECONDS, 0.0
        self.game.readable_regions = lambda limit=0: [(0, len(self.game.mem))]
        mem = self.game.mem
        struct.pack_into("<I", mem, GAME, wdm.GAME_VTABLE)
        struct.pack_into("<I", mem, GAME + wdm.DOOR_LIST + wdm.LIST_ARRAY, ARRAY)
        # door animation table: Main Hall -> Dining Room / Art Room, Bar -> Tea Room
        self.info = {}
        for i, (src, dest) in enumerate([(0x106, 0x105), (0x106, 0x107), (0x10F, 0x103), (0x512, 0x50B)]):
            e = INFO + i * 0x40
            struct.pack_into("<I", mem, e, INFO_VT)
            mem[e + 8:e + 14] = b"do117\0"
            struct.pack_into("<4i", mem, e + 0x1C, src >> 8, src & 0xFF, dest >> 8, dest & 0xFF)
            self.info[(src, dest)] = e
        self.set_room(0x106)
        self.set_doors([0x105, 0x107])

    def tearDown(self):
        wdm.SETTLE = self._settle
        wdm.BACKGROUND = self._bg
        wdm.CELL_LOCK_SECONDS = self._lock
        super().tearDown()

    def set_room(self, number):
        struct.pack_into("<ii", self.game.mem, FLAGS + hv.CURRENT_ROOM_OFFSET, number >> 8, number & 0xFF)

    def set_doors(self, dests):
        mem = self.game.mem
        struct.pack_into("<I", mem, GAME + wdm.DOOR_LIST + wdm.LIST_COUNT, len(dests))
        for i, d in enumerate(dests):
            rec = RECS + i * 0x100
            mem[rec:rec + 0x4C] = bytes(0x4C)
            struct.pack_into("<I", mem, rec, wdm.DOOR_VTABLE)
            mem[rec + 0x40:rec + 0x44] = bytes([d >> 8, d & 0xFF, 0, 0x83])     # lock byte 0x83
            struct.pack_into("<I", mem, ARRAY + i * 4, rec)

    def rec(self, i):
        r = RECS + i * 0x100
        return self.game.mem[r + 0x40] * 0x100 + self.game.mem[r + 0x41], self.game.mem[r + 0x43]

    def info_dest(self, pair):
        ds, dr = struct.unpack_from("<ii", self.game.mem, self.info[pair] + 0x24)
        return ds * 0x100 + dr

    def bit(self, off, bit):
        return self.game.mem[FLAGS + off] >> bit & 1

    def test_full_trip_bar(self):
        b = self.bridge()
        b.tick([])                                   # Jill in the Main Hall, save is ours
        self.assertTrue(b._apply_trap(Incoming(-1, None, "Wrong Door Trap from Friend", trap="Wrong Door Trap")))
        b.wrong_door.s.update(decoy=0x10F, message="Last orders!")
        checked = b.tick([])
        checked = b.tick([])
        # doors point at the Bar, doorinfo first, locks untouched
        self.assertEqual(self.rec(0), (0x10F, 0x83))
        self.assertEqual(self.rec(1), (0x10F, 0x83))
        self.assertEqual(self.info_dest((0x106, 0x105)), 0x10F)
        self.assertEqual(self.info_dest((0x106, 0x107)), 0x10F)
        # the Bar's items are hidden (flags set) but not reported as checks
        bar = [n for n in DETECTED_PICKUPS if n.startswith("Bar - ")]
        self.assertTrue(bar)
        for n in bar:
            off, bit, _ = DETECTED_PICKUPS[n]
            self.assertEqual(self.bit(off, bit), 1)
            self.assertNotIn(n, checked)
        # Jill walks through: now in the Bar
        self.set_room(0x10F)
        self.set_doors([0x103])
        checked = b.tick([])
        self.assertTrue(any("Last orders!" in (n[0] if isinstance(n, tuple) else n) for n in b.notices))
        self.assertNotIn("Bar - First Visit", checked)
        checked = b.tick([])
        self.assertEqual(self.info_dest((0x106, 0x105)), 0x105)     # put back after arriving
        self.assertEqual(self.rec(0), (0x106, 0x83))                 # Bar door leads home
        self.assertEqual(self.info_dest((0x10F, 0x103)), 0x106)
        for n in bar:
            self.assertNotIn(n, checked)
        # back home: everything put back
        self.set_room(0x106)
        self.set_doors([0x105, 0x107])
        b.tick([])
        checked = b.tick([])
        self.assertEqual(self.info_dest((0x10F, 0x103)), 0x103)
        for n in bar:
            off, bit, _ = DETECTED_PICKUPS[n]
            self.assertEqual(self.bit(off, bit), 0)
            self.assertNotIn(n, checked)
        off, bit = room_visited_flag(0x10F)
        self.assertEqual(self.bit(off, bit), 0)
        self.assertEqual(b.wrong_door.s, {})
        self.assertEqual(b.state_file.load().wrong_door, {})

    def test_one_at_a_time_and_cell_scene(self):
        b = self.bridge()
        b.tick([])
        trap = Incoming(-1, None, "Wrong Door Trap from Friend", trap="Wrong Door Trap")
        self.assertTrue(b._apply_trap(trap))
        self.assertFalse(b._apply_trap(trap))          # second one waits
        b.wrong_door.s.update(decoy=0x512, message="Wesker caught you!")
        b.tick([])
        b.tick([])
        off, bit = wdm.CHRIS_SCENE
        self.assertEqual(self.bit(off, bit), 1)
        self.set_room(0x512)
        self.set_doors([0x50B])
        b.tick([])
        b.tick([])
        self.set_room(0x106)
        self.set_doors([0x105, 0x107])
        b.tick([])
        b.tick([])
        self.assertEqual(self.bit(off, bit), 0)         # the real visit still plays the scene

    def test_restart_puts_back_and_rearms(self):
        b = self.bridge()
        b.tick([])
        b._apply_trap(Incoming(-1, None, "Wrong Door Trap from Friend", trap="Wrong Door Trap"))
        b.wrong_door.s.update(decoy=0x10F, message="Last orders!")
        b.tick([])
        b.tick([])
        self.assertEqual(self.info_dest((0x106, 0x105)), 0x10F)
        b2 = self.bridge()                              # client restarted mid-trap
        b2.tick([])                                     # (first tick: save check)
        b2.tick([])                                     # put back, then armed again
        self.assertEqual(self.info_dest((0x106, 0x105)), 0x105)
        self.assertEqual(b2.wrong_door.s.get("phase"), "armed")     # still armed for the next door

    def test_no_table_entry_means_door_untouched(self):
        mem = self.game.mem
        struct.pack_into("<4i", mem, self.info[(0x106, 0x107)] + 0x1C, 9, 9, 9, 9)   # entry missing
        b = self.bridge()
        b.tick([])
        b._apply_trap(Incoming(-1, None, "Wrong Door Trap from Friend", trap="Wrong Door Trap"))
        b.wrong_door.s.update(decoy=0x10F, message="Last orders!")
        b.tick([])
        b.tick([])
        self.assertEqual(self.rec(0)[0], 0x10F)
        self.assertEqual(self.rec(1)[0], 0x107)        # would crash the game: left alone

    def test_decoy_is_always_the_cell(self):
        self.assertEqual(wdm.choose_decoy(0x106), 0x512)
        self.assertEqual(wdm.choose_decoy(0x50B), 0x512)       # even right next door
        self.assertIsNone(wdm.choose_decoy(0x512))              # already there: the trap waits
        b = self.bridge()
        self.set_room(0x512)
        self.set_doors([0x50B])
        b.tick([])
        self.assertFalse(b._apply_trap(Incoming(-1, None, "Wrong Door Trap from Friend", trap="Wrong Door Trap")))

    def test_cell_door_locked_for_a_while(self):
        wdm.CELL_LOCK_SECONDS = 100.0
        b = self.bridge()
        b.tick([])
        b._apply_trap(Incoming(-1, None, "Wrong Door Trap from Friend", trap="Wrong Door Trap"))
        b.wrong_door.s.update(decoy=0x512, message="Wesker caught you!")
        b.tick([])
        b.tick([])
        self.set_room(0x512)
        self.set_doors([0x50B])
        struct.pack_into("<i", self.game.mem, RECS + 0x44, 77)         # the Cell door's own flag
        b.tick([])                                       # arrived: "Wesker caught you!"
        b.tick([])
        self.assertEqual(self.rec(0), (0x50B, wdm.LOCKED))            # locked, still the real door
        self.assertEqual(struct.unpack_from("<i", self.game.mem, RECS + 0x44)[0], 255)   # an unlock flag that's off
        b.wrong_door.s["cell_lock_until"] = 1.0                          # 5 s are up
        b.tick([])
        self.assertEqual(self.rec(0), (0x106, 0x83))                  # unlocked, leads home
        self.assertEqual(struct.unpack_from("<i", self.game.mem, RECS + 0x44)[0], 77)
        self.assertTrue(any("clicks open" in (n[0] if isinstance(n, tuple) else n) for n in b.notices))


class ShortcutTest(WrongDoorTest):
    """Key Map shortcuts (client/shortcuts.py, 2026-11-13): the next door leads to the room."""

    def visit(self, number):
        off, bit = room_visited_flag(number)
        self.game.mem[FLAGS + off] |= 1 << bit

    def test_locked_until_visited_then_full_trip(self):
        b = self.bridge()
        b.shortcuts_on = True
        self.set_room(0x10F)
        self.set_doors([0x103])
        b.tick([])
        off, bit = room_visited_flag(0x106)
        self.game.mem[FLAGS + off] &= ~(1 << bit) & 0xFF
        b.tick([])
        self.assertIn("Visit the Main Hall first", b.request_shortcut("Main Hall"))
        self.visit(0x106)
        b.tick([])
        self.assertIn("Main Hall", b.shortcuts_unlocked)
        self.assertIn("next door", b.request_shortcut("Main Hall"))
        b.tick([])
        b.tick([])
        self.assertEqual(self.info_dest((0x10F, 0x103)), 0x106)     # table entry first
        self.assertEqual(self.rec(0), (0x106, 0x83))                 # then the door; lock untouched
        self.assertEqual(b.shortcut.target_name, "Main Hall")
        # she goes through: Main Hall
        self.set_room(0x106)
        self.set_doors([0x105, 0x107])
        b.tick([])
        self.assertTrue(any("Shortcut: Main Hall" in (n[0] if isinstance(n, tuple) else n) for n in b.notices))
        b.tick([])
        self.assertEqual(self.info_dest((0x10F, 0x103)), 0x103)     # put back
        self.assertEqual(b.shortcut.s, {})
        self.assertEqual(b.state_file.load().shortcut, {})

    def test_cancel_and_off(self):
        b = self.bridge()
        self.set_room(0x10F)
        self.set_doors([0x103])
        self.visit(0x106)
        b.tick([])
        self.assertIn("off in your YAML", b.request_shortcut("Main Hall"))
        b.shortcuts_on = True
        b.request_shortcut("Main Hall")
        b.tick([])
        b.tick([])
        self.assertEqual(self.info_dest((0x10F, 0x103)), 0x106)
        self.assertIn("cancelled", b.request_shortcut("Main Hall"))
        self.assertEqual(self.info_dest((0x10F, 0x103)), 0x103)
        self.assertEqual(b.shortcut.s, {})

    def test_wrong_door_waits_for_a_shortcut(self):
        b = self.bridge()
        b.shortcuts_on = True
        self.set_room(0x10F)
        self.set_doors([0x103])
        self.visit(0x106)
        b.tick([])
        b.request_shortcut("Main Hall")
        trap = Incoming(-1, None, "Wrong Door Trap from Friend", trap="Wrong Door Trap")
        self.assertFalse(b._apply_trap(trap))


class DoorShuffleClientTest(WrongDoorTest):
    """Door randomiser, the in-game part (client/door_shuffle_client.py, 2026-11-13)."""
    LAYOUT = {"mode": "decoupled", "targets": {"105-106@106": ["103-10f", "10f"]}}

    def setUp(self):
        super().setUp()
        from ..client import door_shuffle_client as dsc
        self.dsc = dsc
        self._delay, dsc.PATCH_DELAY = dsc.PATCH_DELAY, 0.0

    def tearDown(self):
        self.dsc.PATCH_DELAY = self._delay
        super().tearDown()

    def test_door_leads_to_its_target_and_table_is_put_back(self):
        b = self.bridge()
        b.set_door_shuffle(self.LAYOUT)
        b.tick([])
        b.tick([])
        self.assertEqual(self.info_dest((0x106, 0x105)), 0x10F)     # table entry first
        self.assertEqual(self.rec(0), (0x10F, 0x83))                 # Dining Room door -> Bar, lock kept
        self.assertEqual(self.rec(1), (0x107, 0x83))                 # not shuffled: untouched
        # she goes through: the Bar
        self.set_room(0x10F)
        self.set_doors([0x103])
        b.tick([])
        self.assertEqual(b.door_shuffler.s["discovered"], {"105-106@106": 0x10F})
        b.tick([])
        self.assertEqual(self.info_dest((0x106, 0x105)), 0x105)     # put back after arriving
        self.assertEqual(self.rec(0), (0x103, 0x83))                 # the Bar's door isn't shuffled
        self.assertEqual(b.state_file.load().door_shuffle["discovered"], {"105-106@106": 0x10F})

    def test_gives_the_room_to_a_wrong_door_trap(self):
        b = self.bridge()
        b.set_door_shuffle(self.LAYOUT)
        b.tick([])
        b.tick([])
        self.assertEqual(self.rec(0), (0x10F, 0x83))
        self.assertTrue(b._apply_trap(Incoming(-1, None, "Wrong Door Trap from Friend", trap="Wrong Door Trap")))
        b.wrong_door.s.update(decoy=0x512, message="Wesker caught you!")
        b.tick([])
        b.tick([])
        # the trap has the room: both doors lead to its decoy, not to the shuffled target
        self.assertEqual(self.rec(0), (0x512, 0x83))
        self.assertEqual(self.rec(1), (0x512, 0x83))
        self.assertEqual(self.info_dest((0x106, 0x105)), 0x512)
        self.assertEqual(b.door_shuffler.recs, {})

    def test_off_changes_nothing(self):
        b = self.bridge()
        b.set_door_shuffle({})
        b.tick([])
        b.tick([])
        self.assertEqual(self.rec(0), (0x105, 0x83))
        self.assertEqual(self.info_dest((0x106, 0x105)), 0x105)


class StaleMemoryTest(DoorShuffleClientTest):
    """2026-11-13 (TessarionAM): after loading a save no door was changed any more - the client kept
    the game object / door table it found before the load. Also: cancelling a shortcut left the
    door pointing at the shortcut's room."""
    GAME2, ARRAY2, RECS2 = 0x58000, 0x59000, 0x5A000

    def setUp(self):
        super().setUp()
        self._stale, wdm.STALE_SECONDS = wdm.STALE_SECONDS, 0.0
        self._gap, wdm.RELOOK_GAP = wdm.RELOOK_GAP, 0.0

    def tearDown(self):
        wdm.STALE_SECONDS = self._stale
        wdm.RELOOK_GAP = self._gap
        super().tearDown()

    def set_doors2(self, dests):
        """The new game object's door list (the one the game uses after the load)."""
        mem = self.game.mem
        struct.pack_into("<I", mem, self.GAME2, wdm.GAME_VTABLE)
        struct.pack_into("<I", mem, self.GAME2 + wdm.DOOR_LIST + wdm.LIST_ARRAY, self.ARRAY2)
        struct.pack_into("<I", mem, self.GAME2 + wdm.DOOR_LIST + wdm.LIST_COUNT, len(dests))
        for i, d in enumerate(dests):
            rec = self.RECS2 + i * 0x100
            mem[rec:rec + 0x4C] = bytes(0x4C)
            struct.pack_into("<I", mem, rec, wdm.DOOR_VTABLE)
            mem[rec + 0x40:rec + 0x44] = bytes([d >> 8, d & 0xFF, 0, 0x83])
            struct.pack_into("<I", mem, self.ARRAY2 + i * 4, rec)

    def rec2(self, i):
        r = self.RECS2 + i * 0x100
        return self.game.mem[r + 0x40] * 0x100 + self.game.mem[r + 0x41]

    def test_load_with_the_old_game_object_still_in_memory(self):
        b = self.bridge()
        b.set_door_shuffle(self.LAYOUT)
        b.tick([])
        b.tick([])
        self.assertEqual(self.rec(0), (0x10F, 0x83))                 # shuffled as usual
        self.assertEqual(b.wrong_door.game, GAME)
        # a save is loaded in the Bar: the game uses a new object; the old one keeps the Main Hall list
        self.set_room(0x10F)
        self.set_doors2([0x103])
        for _ in range(4):
            b.tick([])
        self.assertEqual(b.wrong_door.game, self.GAME2)              # found the one that fits the room
        self.assertIn(GAME, b.wrong_door.stale_games)
        # back to the Main Hall: the new object's door is shuffled
        self.set_room(0x106)
        self.set_doors2([0x105, 0x107])
        b.tick([])
        b.tick([])
        self.assertEqual(self.rec2(0), 0x10F)
        self.assertEqual(self.rec2(1), 0x107)

    def test_room_with_a_good_list_is_left_alone(self):
        b = self.bridge()
        b.set_door_shuffle(self.LAYOUT)
        for _ in range(5):
            b.tick([])
        self.assertEqual(self.rec(0), (0x10F, 0x83))     # our own change doesn't look out of date
        self.set_room(0x10F)
        self.set_doors([0x103])
        for _ in range(5):
            b.tick([])
        self.assertEqual(b.wrong_door.game, GAME)
        self.assertEqual(b.wrong_door.stale_games, set())

    def test_door_table_reloaded(self):
        b = self.bridge()
        b.set_door_shuffle(self.LAYOUT)
        b.tick([])
        # the table moved: the entry we knew for Main Hall -> Dining Room now holds another pair,
        # and a new copy of the table is elsewhere
        e = self.info[(0x106, 0x105)]
        struct.pack_into("<4i", self.game.mem, e + 0x1C, 3, 1, 3, 2)
        new = INFO + 0x400
        struct.pack_into("<I", self.game.mem, new, INFO_VT)
        self.game.mem[new + 8:new + 14] = b"do117\0"
        struct.pack_into("<4i", self.game.mem, new + 0x1C, 1, 6, 1, 5)
        b.tick([])
        b.tick([])
        b.tick([])
        ds, dr = struct.unpack_from("<ii", self.game.mem, new + 0x24)
        self.assertEqual(ds * 0x100 + dr, 0x10F)
        self.assertEqual(self.rec(0), (0x10F, 0x83))

    def test_shortcut_cancel_puts_the_door_back(self):
        b = self.bridge()
        b.shortcuts_on = True
        self.set_room(0x10F)
        self.set_doors([0x103])
        off, bit = room_visited_flag(0x106)
        self.game.mem[FLAGS + off] |= 1 << bit
        b.tick([])
        b.request_shortcut("Main Hall")
        b.tick([])
        b.tick([])
        self.assertEqual(self.rec(0), (0x106, 0x83))
        self.assertIn("cancelled", b.request_shortcut("Main Hall"))
        self.assertEqual(self.rec(0), (0x103, 0x83))                 # the door, not just the table
        self.assertEqual(self.info_dest((0x10F, 0x103)), 0x103)
