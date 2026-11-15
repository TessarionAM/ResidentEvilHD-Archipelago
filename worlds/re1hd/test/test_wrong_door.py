"""Offline tests for the Wrong Door Trap (client/wrong_door.py) with a fake game memory."""
import unittest
import struct

from ..client import hd_versions as hv
from ..client import wrong_door as wdm
from ..client.door_data import DOOR_PAIRS
from ..client.game_bridge import Incoming
from ..game_data import DETECTED_PICKUPS, room_visited_flag
from .test_client import FLAGS, BridgeTest

GAME = 0x50000
ARRAY = 0x51000
RECS = 0x52000
INFO = 0x60000
INFO_VT = 0x00ABCD00


class _NoJump:
    """No room jump stub in these tests: shortcuts fall back to the door way (client/shortcuts.py)."""
    def __init__(self, conn, log=None):
        pass

    def install(self):
        from ..client.pc_process import ProcessError
        raise ProcessError("no room jump in this test")


class WrongDoorTest(BridgeTest):
    def setUp(self):
        super().setUp()
        from ..client import game_bridge as gb
        self._jumper_factory, gb.RoomJumper = gb.RoomJumper, _NoJump
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
        from ..client import game_bridge as gb
        gb.RoomJumper = self._jumper_factory
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
        off, bit = room_visited_flag(0x105)
        self.game.mem[FLAGS + off] &= ~(1 << bit) & 0xFF
        b.tick([])
        self.assertIn("Visit the Dining Room first", b.request_shortcut("Dining Room"))
        self.visit(0x105)
        b.tick([])
        self.assertIn("Dining Room", b.shortcuts_unlocked)
        self.assertIn("next door", b.request_shortcut("Dining Room"))
        b.tick([])
        b.tick([])
        self.assertEqual(self.info_dest((0x10F, 0x103)), 0x105)     # table entry first
        self.assertEqual(self.rec(0), (0x105, 0x83))                 # then the door; lock untouched
        self.assertEqual(b.shortcut.target_name, "Dining Room")
        # she goes through: Dining Room
        self.set_room(0x105)
        self.set_doors([0x103, 0x106])
        b.tick([])
        self.assertTrue(any("Shortcut: Dining Room" in (n[0] if isinstance(n, tuple) else n) for n in b.notices))
        b.tick([])
        self.assertEqual(self.info_dest((0x10F, 0x103)), 0x103)     # put back
        self.assertEqual(b.shortcut.s, {})
        self.assertEqual(b.state_file.load().shortcut, {})

    def test_cancel_and_off(self):
        b = self.bridge()
        self.set_room(0x10F)
        self.set_doors([0x103])
        self.visit(0x105)
        b.tick([])
        self.assertIn("off in your YAML", b.request_shortcut("Dining Room"))
        b.shortcuts_on = True
        b.request_shortcut("Dining Room")
        b.tick([])
        b.tick([])
        self.assertEqual(self.info_dest((0x10F, 0x103)), 0x105)
        self.assertIn("cancelled", b.request_shortcut("Dining Room"))
        self.assertEqual(self.info_dest((0x10F, 0x103)), 0x103)
        self.assertEqual(b.shortcut.s, {})

    def test_wrong_door_waits_for_a_shortcut(self):
        b = self.bridge()
        b.shortcuts_on = True
        self.set_room(0x10F)
        self.set_doors([0x103])
        self.visit(0x105)
        b.tick([])
        b.request_shortcut("Dining Room")
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
        off, bit = room_visited_flag(0x105)
        self.game.mem[FLAGS + off] |= 1 << bit
        b.tick([])
        b.request_shortcut("Dining Room")
        b.tick([])
        b.tick([])
        self.assertEqual(self.rec(0), (0x105, 0x83))
        self.assertIn("cancelled", b.request_shortcut("Dining Room"))
        self.assertEqual(self.rec(0), (0x103, 0x83))                 # the door, not just the table
        self.assertEqual(self.info_dest((0x10F, 0x103)), 0x103)


class GameObjectFreedTest(StaleMemoryTest):
    """2026-11-14 (TessarionAM's log 00:56): after a death + reload the old game object was freed.
    The rescan kept its address, "found" it every 30 s and shortcuts never worked again."""

    def test_freed_game_object_is_replaced_on_rescan(self):
        b = self.bridge()
        b.set_door_shuffle(self.LAYOUT)
        b.tick([])
        b.tick([])
        self.assertEqual(b.wrong_door.game, GAME)
        # death + reload: the old object is gone (vtable overwritten), a new one is in use
        struct.pack_into("<I", self.game.mem, GAME, 0)
        self.set_doors2([0x105, 0x107])
        for _ in range(3):
            b.tick([])
        self.assertEqual(b.wrong_door.game, self.GAME2)
        self.assertEqual(self.rec2(0), 0x10F)               # and the doors are shuffled again


class TypewriterShortcutTableTest(unittest.TestCase):
    """2026-11-14: one shortcut per typewriter room."""

    def test_every_save_room_has_a_working_shortcut(self):
        from ..client.autosave import SAVE_ROOMS
        from ..client.shortcuts import LABELS, ORDER, SHORTCUTS
        self.assertEqual({room for room, _f in SHORTCUTS.values()}, set(SAVE_ROOMS))
        self.assertEqual(set(ORDER), set(SHORTCUTS))
        for name, (room, came_from) in SHORTCUTS.items():
            self.assertIsNotNone(wdm.arrival(room, came_from), name)          # a real arrival spot
            self.assertIn(came_from, DOOR_PAIRS[room], name)                 # a real door
            self.assertIsNotNone(room_visited_flag(room), name)              # it can unlock
            self.assertLessEqual(len(LABELS.get(name, name)), 14, name)      # fits a Key Map button


class DoorknobTest(WrongDoorTest):
    """2026-11-15 (test 06): the East Wing Stairway <-> Dark Corridor doorknob is put back as new
    the moment it breaks (+0x23A bit 0), with its two use counters (+0x248 bits 3 and 4)."""

    def test_second_trip_is_uncounted(self):
        b = self.bridge()
        self.set_room(0x10A)                                    # Jill is in the Dark Corridor
        self.game.mem[FLAGS + 0x248] = 0x18 | 0x01            # both trips counted (+ an unrelated bit)
        for _ in range(3):
            b.tick([])
        self.assertEqual(self.game.mem[FLAGS + 0x248], 0x08 | 0x01)    # back to "one trip"

    def test_first_trip_alone_is_left_alone(self):
        b = self.bridge()
        self.game.mem[FLAGS + 0x248] = 0x08
        for _ in range(3):
            b.tick([])
        self.assertEqual(self.game.mem[FLAGS + 0x248], 0x08)

    def test_already_broken_save_is_mended(self):
        b = self.bridge()
        self.set_room(0x207)
        self.game.mem[FLAGS + 0x248] = 0x18
        self.game.mem[FLAGS + 0x23A] = 0x01 | 0x40            # broken (+ an unrelated bit)
        for _ in range(3):
            b.tick([])
        self.assertEqual(self.game.mem[FLAGS + 0x23A], 0x40)
        self.assertEqual(self.game.mem[FLAGS + 0x248], 0x08)

    def test_lift_byte_next_door_untouched(self):
        b = self.bridge()
        self.set_room(0x106)
        self.game.mem[FLAGS + 0x249] = 0x06
        self.game.mem[FLAGS + 0x23A] = 0x01
        for _ in range(3):
            b.tick([])
        self.assertEqual(self.game.mem[FLAGS + 0x249], 0x06)


class CourtyardLiftTest(WrongDoorTest):
    """Courtyard lifts follow Jill's floor (2026-11-14), set for the room she's GOING to, and only
    once each lift works in the game (2026-11-15)."""

    def lifts(self):
        from ..client.game_bridge import LIFT_FLAGS_BYTE
        return self.game.mem[FLAGS + LIFT_FLAGS_BYTE]

    def working(self, pool=True, battery=True):
        from ..client.game_bridge import (BATTERY_IN_BIT, BATTERY_IN_BYTE, POOL_DRAINED_BIT,
                                          POOL_DRAINED_BYTE)
        if pool:
            self.game.mem[FLAGS + POOL_DRAINED_BYTE] |= POOL_DRAINED_BIT
        if battery:
            self.game.mem[FLAGS + BATTERY_IN_BYTE] |= BATTERY_IN_BIT

    def target(self, number):
        struct.pack_into("<ii", self.game.mem, FLAGS + hv.DOOR_TARGET_ROOM_OFFSET, number >> 8, number & 0xFF)

    def test_upper_floor_brings_both_lifts_up(self):
        from ..client.game_bridge import LIFT_FLAGS_BYTE
        self.working()
        b = self.bridge()
        self.game.mem[FLAGS + LIFT_FLAGS_BYTE] = 0x01 | 0x02          # pool lift down, other bit kept
        self.set_room(0x11B)                                           # Garden Shed
        self.target(0x11B)
        for _ in range(3):
            b.tick([])
        self.assertEqual(self.lifts(), 0x01 | 0x04)                    # pool lift up, Battery lift up

    def test_lower_floor_brings_both_lifts_down(self):
        self.working()
        b = self.bridge()
        self.set_room(0x304)                                           # Zigzag Path
        self.game.mem[FLAGS + 0x249] = 0x04 | 0x80
        for _ in range(3):
            b.tick([])
        self.assertEqual(self.lifts(), 0x02 | 0x80)

    def test_set_for_the_room_she_is_going_to(self):
        """TessarionAM 2026-11-15: pool lift down from the Water Pool -> the Falls Area loaded with the
        Battery lift still at the top. The target room changes before the room loads."""
        self.working()
        b = self.bridge()
        self.set_room(0x301)                                           # Water Pool (top)
        self.target(0x301)
        for _ in range(3):
            b.tick([])
        self.assertEqual(self.lifts(), 0x04)
        self.target(0x302)                                             # riding down to the Falls Area
        b.tick([])
        self.assertEqual(self.lifts(), 0x02)                           # both lifts at the bottom already

    def test_written_once_per_change(self):
        self.working()
        b = self.bridge()
        self.set_room(0x300)
        self.target(0x300)
        for _ in range(3):
            b.tick([])
        self.assertEqual(self.lifts(), 0x04)
        self.game.mem[FLAGS + 0x249] = 0x00                           # a ride changes it itself
        b.tick([])
        b.tick([])
        self.assertEqual(self.lifts(), 0x00)                           # not written back while nothing changed

    def test_a_lift_that_does_not_work_yet_is_left_alone(self):
        """The pool lift moved down before the pool was drained let Jill ride up without the crank."""
        b = self.bridge()
        self.set_room(0x304)
        self.game.mem[FLAGS + 0x249] = 0x04                            # vanilla: pool lift up, Battery lift up
        for _ in range(3):
            b.tick([])
        self.assertEqual(self.lifts(), 0x04)                           # neither works yet: untouched
        self.working(pool=False, battery=True)
        self.set_room(0x302)
        for _ in range(3):
            b.tick([])
        self.assertEqual(self.lifts(), 0x00)                           # only the Battery lift came down

    def test_other_rooms_untouched(self):
        self.working()
        b = self.bridge()
        self.set_room(0x106)
        self.game.mem[FLAGS + 0x249] = 0x02
        for _ in range(3):
            b.tick([])
        self.assertEqual(self.lifts(), 0x02)


class GateOpenForFarStartTest(WrongDoorTest):
    """Random start beyond the Stone & Metal gate (TessarionAM, 2026-11-15 19:15): the client puts the
    object in the gate from the start; a copy taken from it is taken away again."""

    def test_open_from_the_start(self):
        b = self.bridge()
        b.gate_open = True
        for _ in range(3):
            b.tick([])
        self.assertTrue(self.game.mem[FLAGS + 0x22D] & 0x08)
        self.assertFalse(self.game.mem[FLAGS + 0x304] & 0x01)          # never the crash bit

    def test_copy_taken_from_it_is_removed(self):
        b = self.bridge()
        b.gate_open = True
        self.set_room(0x11A)
        for _ in range(3):
            b.tick([])
        self.game.mem[FLAGS + 0x22D] &= ~0x08 & 0xFF                   # the drawn object is taken...
        self.game.mem[FLAGS + 0x304] |= 0x01
        b.tick([])
        self.game.set_slot(3, 53, 1)                                   # ...and lands in the inventory
        for _ in range(3):
            b.tick([])
        self.assertEqual(self.game.slot(3), (0, 0))                     # the copy is gone
        self.assertTrue(self.game.mem[FLAGS + 0x22D] & 0x08)           # and the gate is open again

    def test_off_by_default(self):
        b = self.bridge()
        for _ in range(3):
            b.tick([])
        self.assertFalse(self.game.mem[FLAGS + 0x22D] & 0x08)


class BossRushTest(WrongDoorTest):
    """2026-11-14: the Boss Rush check is sent once every boss's kill bit is on."""

    def test_sent_only_when_all_seven_are_dead(self):
        from ..data import BOSSES, BOSS_RUSH_LOCATION
        b = self.bridge()
        b.boss_rush = True
        for _ in range(3):
            self.assertNotIn(BOSS_RUSH_LOCATION, b.tick([]) or set())
        for i, (_name, _room, (off, bit), _req) in enumerate(BOSSES):
            self.game.mem[FLAGS + off] |= 1 << bit
            got = b.tick([]) or set()
            self.assertEqual(BOSS_RUSH_LOCATION in got, i == len(BOSSES) - 1)
        self.assertTrue(all(line.endswith("dead") for line in b.bosses_status()))

    def test_off_by_default(self):
        from ..data import BOSSES, BOSS_RUSH_LOCATION
        b = self.bridge()
        for _name, _room, (off, bit), _req in BOSSES:
            self.game.mem[FLAGS + off] |= 1 << bit
        for _ in range(3):
            self.assertNotIn(BOSS_RUSH_LOCATION, b.tick([]) or set())

    def test_main_lab_warning(self):
        b = self.bridge()
        b.boss_rush = True
        self.set_room(0x513)
        for _ in range(3):
            b.tick([])
        self.assertTrue(any("self-destructs" in (n[0] if isinstance(n, tuple) else n) for n in b.notices))


class StoneMetalGateTest(WrongDoorTest):
    """2026-11-14 (test 07): the Roofed Passage gate is kept open once the object was received or
    taken back; an object picked up from a gate the client opened is taken away again."""

    def gate(self):
        return bool(self.game.mem[FLAGS + 0x22D] & 0x08)

    def test_received_object_opens_the_gate(self):
        b = self.bridge()
        b.state.delivered = 1
        rec = [Incoming(0, 53, "Stone & Metal Object")]
        for _ in range(3):
            b.tick(rec)
        self.assertTrue(self.gate())
        self.assertFalse(self.game.mem[FLAGS + 0x304] & 0x01)          # never the crash bit

    def test_closed_without_the_object(self):
        b = self.bridge()
        for _ in range(3):
            b.tick([])
        self.assertFalse(self.gate())

    def test_take_back_keeps_it_open(self):
        b = self.bridge()
        self.game.mem[FLAGS + 0x304] |= 0x01                           # taken back for the Altar
        for _ in range(3):
            b.tick([])
        self.assertTrue(self.gate())

    def test_copy_from_a_client_opened_gate_is_taken_away(self):
        b = self.bridge()
        self.set_room(0x11A)
        b.state.delivered = 1
        rec = [Incoming(0, 53, "Stone & Metal Object")]
        for _ in range(3):
            b.tick(rec)
        self.assertTrue(self.gate())
        self.game.mem[FLAGS + 0x22D] &= ~0x08 & 0xFF                   # the drawn object is taken...
        self.game.mem[FLAGS + 0x304] |= 0x01
        b.tick(rec)
        self.game.set_slot(3, 53, 1)                                   # ...and lands in the inventory
        for _ in range(3):
            b.tick(rec)
        self.assertEqual(self.game.slot(3), (0, 0))
        self.assertTrue(self.gate())

    def test_players_own_object_is_theirs_to_take(self):
        b = self.bridge()
        self.set_room(0x11A)
        self.game.mem[FLAGS + 0x22D] |= 0x08                            # the player put it in
        self.game.mem[FLAGS + 0x326] |= 0x02
        for _ in range(3):
            b.tick([])
        self.game.mem[FLAGS + 0x22D] &= ~0x08 & 0xFF                   # and takes it back for the Altar
        self.game.mem[FLAGS + 0x326] &= ~0x02 & 0xFF
        self.game.mem[FLAGS + 0x304] |= 0x01
        b.tick([])
        self.game.set_slot(3, 53, 1)
        for _ in range(3):
            b.tick([])
        self.assertEqual(self.game.slot(3), (53, 1))                   # kept
        self.assertTrue(self.gate())                                   # and the gate stays open


class RoomLockLogTest(WrongDoorTest):
    """2026-11-14: locked door sides are logged once per room entry, with their flag's state."""

    def test_locks_logged_once(self):
        b = self.bridge()
        self.set_room(0x10B)
        self.set_doors([0x117])
        struct.pack_into("<i", self.game.mem, RECS + 0x44, 39)
        self.game.mem[RECS + 0x43] = 22
        b.room_since = 0.0
        with self.assertLogs("RE1HDClient", "INFO") as cm:
            for _ in range(4):
                b.tick([])
                b.room_since = 0.0
        lines = [l for l in cm.output if "Locks in 0x10b" in l]
        self.assertEqual(len(lines), 1)
        self.assertIn("->0x117 type 22 flag 39 locked", lines[0])


class InstantShortcutTest(WrongDoorTest):
    """2026-11-15 (TessarionAM): shortcuts are instant, like the random start room (room jump)."""

    def setUp(self):
        super().setUp()
        from .test_client import FakeJumper
        from ..client import game_bridge as gb
        gb.RoomJumper = FakeJumper
        self.game.pid = 99

    def unlocked(self, b, name="Dining Room"):
        b.shortcuts_on = True
        b.shortcuts_unlocked = frozenset({name})

    def test_jump_then_arrival(self):
        from .test_client import FakeJumper
        b = self.bridge()
        b.tick([])
        self.set_room(0x107)
        b.tick([])
        self.unlocked(b)
        msg = b.request_shortcut("Dining Room")
        self.assertIn("taking Jill to the Dining Room", msg)
        self.assertEqual(FakeJumper.last.armed, [0x105])
        self.assertIsNone(b.shortcut.target_name)                    # no door was changed
        FakeJumper.last.state = 2                                     # the stub fired
        self.set_room(0x105)
        b.tick([])
        self.assertIsNone(b.shortcut_jump)

    def test_pressed_again_cancels(self):
        from .test_client import FakeJumper
        b = self.bridge()
        b.tick([])
        self.set_room(0x107)
        b.tick([])
        self.unlocked(b)
        b.request_shortcut("Dining Room")
        self.assertIn("cancelled", b.request_shortcut("Dining Room"))
        self.assertEqual(FakeJumper.last.state, 0)
        self.assertIsNone(b.shortcut_jump)
