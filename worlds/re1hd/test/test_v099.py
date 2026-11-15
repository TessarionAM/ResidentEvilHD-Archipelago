"""v0.9.9 fixes (TessarionAM's play notes, 2026-11-13)."""
import unittest
from collections import Counter

from .. import door_locks as dl
from ..client.held_traps import HOLD_LIMIT, HeldTraps
from ..data import DOORS, MISSABLE
from ..map_render import door_text
from . import RE1HDTestBase


class SecretPassageTests(unittest.TestCase):
    def test_hole_is_one_way_down(self):
        self.assertIn(("Secret Passage", "Concrete Passage 1", (), True), DOORS)
        self.assertFalse(any({a, b} == {"Secret Passage", "Concrete Passage 1"} and not one
                             for a, b, _r, one in DOORS))

    def test_secret_passage_only_from_the_resting_room(self):
        items, _locs = dl.simple_progression()
        have = Counter(i for i in items if i != "Helmet Key")
        rooms, _h, _b = dl.reachable(dl.effective_doors({}), have, True)
        self.assertNotIn("Secret Passage", rooms)
        self.assertNotIn("Concrete Passage 1", rooms)
        self.assertIn("Resting Room", rooms)


class LisaPassageTests(unittest.TestCase):
    """2026-11-15 (TessarionAM): Barry's cave lift only goes down, so the Broken Flamethrower is
    always placed below it, before Lisa's door - the area needs nothing more in the logic."""

    def test_area_below_the_lift(self):
        items, _locs = dl.simple_progression()
        have = Counter(i for i in items if i != "Broken Flamethrower")
        rooms, _h, _b = dl.reachable(dl.effective_doors({}), have, True)
        for room in ("Garbage Compactor Room", "Winding Underground Passage", "Underground Storage Room",
                     "Lisa's Room"):
            self.assertIn(room, rooms)

    def test_the_lift_is_one_way(self):
        lift = [d for d in dl.effective_doors({}) if {d[0], d[1]} == {"Generator Room", "Garbage Compactor Room"}]
        self.assertEqual(lift, [("Generator Room", "Garbage Compactor Room",
                                 ("Shaft", "Cylinder", "Hexagonal Crank"), True)])


class SprayTests(unittest.TestCase):
    def test_gallery_spray_is_missable(self):
        self.assertEqual(MISSABLE["Gallery - Insecticide Spray"], "Insecticide Spray")


class SprayWorldTest(RE1HDTestBase):
    def test_spray_check_holds_junk(self):
        loc = self.multiworld.get_location("Gallery - Insecticide Spray", self.player)
        self.assertTrue(loc.locked)
        self.assertNotEqual(loc.item.name, "Insecticide Spray")


class TooltipTests(unittest.TestCase):
    def test_key_door_lists_everything_missing(self):
        d = dict(kind="key", key="Helmet Key", needs=["Helmet Key", "Jewelry Box (Broach)", "Red Jewel"],
                 ok=False, missing=["Jewelry Box (Broach)"], a="Dark Corridor", b="Courtyard Study")
        lines = door_text(d)
        self.assertIn("Also needs: Jewelry Box (Broach), Red Jewel", lines)
        self.assertIn("Can't open yet - you still need: Jewelry Box (Broach)", lines)
        self.assertFalse(any("haven't got the Helmet Key" in l for l in lines))


class HeldTrapTests(unittest.TestCase):
    def setUp(self):
        self.out = []
        self.h = HeldTraps(lambda a: a.get("trap"), self.out.append)

    def test_held_until_released(self):
        self.assertTrue(self.h.hold({"trap": "To Be Continued Trap"}, now=0))
        self.assertFalse(self.h.hold({"text": "normal"}, now=0))
        self.assertEqual(self.out, [])
        self.h.release("To Be Continued Trap")
        self.assertEqual(self.out, [{"trap": "To Be Continued Trap"}])

    def test_prank_over_before_the_message(self):
        self.h.release("Window Shake Trap")
        self.assertFalse(self.h.hold({"trap": "Window Shake Trap"}, now=0))     # printed straight away

    def test_never_lost(self):
        self.h.hold({"trap": "Fake Crash Trap"}, now=0)
        self.h.expire(now=HOLD_LIMIT + 1)
        self.assertEqual(len(self.out), 1)


from .test_client import BridgeTest, FLAGS           # noqa: E402
from ..client import hd_versions as hv                # noqa: E402
import struct                                         # noqa: E402


class SprayAndFlamethrowerClientTest(BridgeTest):
    def test_using_a_spray_sends_the_gallery_spray_check(self):
        b = self.bridge()
        self.game.set_slot(3, 100, 1)                 # Insecticide Spray in the inventory
        b.tick([])
        b.tick([])
        self.game.set_slot(3, 0, 0)                   # used on the beehive
        checked = b.tick([])
        self.assertIn("Gallery - Insecticide Spray", checked)

    def test_no_flamethrower_warning_any_more(self):
        """2026-11-15 (TessarionAM): the Broken Flamethrower is always found below the cave lift now,
        so the old 'carry it' warning is gone."""
        b = self.bridge()
        b.tick([])
        struct.pack_into("<ii", self.game.mem, FLAGS + hv.CURRENT_ROOM_OFFSET, 3, 0x16)   # 0x316
        b.tick([])
        b.room_since -= 2
        b.tick([])
        self.assertFalse(any("Broken Flamethrower" in (n[0] if isinstance(n, tuple) else n) for n in b.notices))


class StudyDoorTest(unittest.TestCase):
    def test_insignia_only(self):
        req = next(r for a, b, r, _o in DOORS if {a, b} == {"Dark Corridor", "Courtyard Study"})
        self.assertNotIn("Helmet Key", req)
        self.assertIn("Jewelry Box (Broach)", req)


class DoorShuffleMapTest(unittest.TestCase):
    def tearDown(self):
        from .. import tracker
        tracker.SHUFFLE = {}

    def test_tooltip_says_where_a_used_door_leads(self):
        from .. import tracker
        from .. import door_shuffle as ds
        e = next(x for x in ds.ends() if ds.logic_room(x) == "Main Hall")
        f = next(x for x in ds.ends() if ds.logic_room(x) == "Bar")
        tracker.SHUFFLE = {"mode": "decoupled", "targets": {ds.key(e): [f[0], f"{f[1]:x}"]}}
        pair = frozenset((ds.logic_room(e), ds.logic_room(ds.other_side(e))))
        self.assertEqual(tracker._shuffle_lines(pair, {}), ["From Main Hall: leads somewhere new (not used yet)"])
        self.assertEqual(tracker._shuffle_lines(pair, {ds.key(e): f[1]}), ["From Main Hall: leads to Bar"])
        d = dict(kind="open", a="Main Hall", b="X", leads=["From Main Hall: leads to Bar"])
        self.assertIn("From Main Hall: leads to Bar", door_text(d))
