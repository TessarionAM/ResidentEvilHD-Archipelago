"""Client side of the door lock randomiser (fake game memory): locks written into the live door
records, key quantities, the Sword Key fix-up, and the tracker using the seed's doors."""
import random
import struct

from .. import door_locks as dl
from ..client.game_bridge import Incoming
from .test_wrong_door import RECS, WrongDoorTest


class LockClientTest(WrongDoorTest):
    def layout(self):
        # Main Hall -> Dining Room (open in vanilla) gets the Helmet Key, Art Room door opened
        return {"105-106": {"kind": "key", "sides": {"105->106": [6, 200], "106->105": [6, 200]}},
                "106-107": {"kind": "one_sided", "sides": {"106->107": [22, 201], "107->106": [21, 201]}}}

    def test_locks_written_and_kept(self):
        b = self.bridge()
        b.set_door_locks(self.layout(), {"Helmet Key": 5, "Book of Curses": 3})
        b.tick([])
        b.tick([])
        mem = self.game.mem
        self.assertEqual(mem[RECS + 0x43], 0x83 & 0x80 | 6)                  # high bit kept, Helmet
        self.assertEqual(struct.unpack_from("<i", mem, RECS + 0x44)[0], 200)
        self.assertEqual(mem[RECS + 0x100 + 0x43], 0x80 | 22)                 # Art Room door: locked from here
        mem[RECS + 0x43] = 0x83                                               # the game rebuilt the record
        b.tick([])
        self.assertEqual(mem[RECS + 0x43], 0x86)

    def test_key_quantity_is_the_door_count(self):
        b = self.bridge()
        b.set_door_locks(self.layout(), {"Helmet Key": 5})
        b.tick([Incoming(0, 48, "Helmet Key from Friend")])
        b.tick([Incoming(0, 48, "Helmet Key from Friend")])
        self.assertIn((48, 5), [self.game.box(i) for i in range(4)])

    def test_sword_key_gets_its_uses_once(self):
        b = self.bridge()
        b.set_door_locks(self.layout(), {"Book of Curses": 3})
        self.game.set_slot(2, 45, 4)          # the Sword Key came out of the book with the game's quantity
        b.tick([])
        b.tick([])
        self.assertEqual(self.game.slot(2), (45, 3))
        self.game.set_slot(2, 45, 2)          # used on a door: not set back
        b.tick([])
        self.assertEqual(self.game.slot(2), (45, 2))

    def test_disabled_writes_nothing(self):
        b = self.bridge()
        b.set_door_locks({}, {})
        before = bytes(self.game.mem)
        b.tick([])
        self.assertEqual(self.game.mem[RECS + 0x43], before[RECS + 0x43])


class TrackerLayoutTest(WrongDoorTest):
    def test_tracker_uses_the_seed_doors(self):
        from .. import logic_tracker, tracker
        from ..data import DOORS
        lay = dl._random_layout(dl.MANSION_ONLY, 30, dl.candidate_doors(dl.MANSION_ONLY), random.Random(3))
        try:
            dl.apply_to_tracker(lay)
            self.assertEqual(logic_tracker.DOORS, dl.effective_doors(lay))
            self.assertEqual(tracker.DOORS, logic_tracker.DOORS)
        finally:
            dl.apply_to_tracker({})
        self.assertEqual(logic_tracker.DOORS, list(DOORS))
