"""random_start_room (2026-11-15): the world side. Real seeds of every option mix are generated in
test_door_locks.generate runs (see the project doc); here: the start room, its logic and slot data."""
import random
from collections import Counter

from . import RE1HDTestBase
from .. import door_locks as dl, door_shuffle as ds
from ..data import START, START_ROOM_MISSABLE, START_ROOMS_ALL, START_ROOMS_MANSION
from ..game_data import ROOM_NUMBERS


class TestStartRoomOff(RE1HDTestBase):
    def test_main_hall_as_before(self):
        w = self.world
        self.assertEqual(w.start_room, START)
        self.assertEqual(w.fill_slot_data()["start_room"], 0)
        lock = self.multiworld.get_location("Main Hall - Lock Pick (Barry)", self.player)
        self.assertIsNone(lock.item if lock.locked else None)       # a normal check
        menu = self.multiworld.get_region("Menu", self.player)
        self.assertEqual([e.connected_region.name for e in menu.exits], [START])


class TestStartRoomSaveRooms(RE1HDTestBase):
    options = {"only_detected_pickups": False, "random_start_room": "save_rooms"}

    def test_starts_in_an_allowed_room(self):
        w = self.world
        self.assertIn(w.start_room, START_ROOMS_ALL)
        menu = self.multiworld.get_region("Menu", self.player)
        self.assertEqual([e.connected_region.name for e in menu.exits], [w.start_room])
        sd = w.fill_slot_data()
        self.assertEqual(sd["start_room"], ROOM_NUMBERS[w.start_room])
        self.assertEqual(sd["start_room_name"], w.start_room)

    def test_barrys_lock_pick_is_missable(self):
        for name in START_ROOM_MISSABLE:
            loc = self.multiworld.get_location(name, self.player)
            self.assertTrue(loc.locked)
            self.assertNotEqual(loc.item.name, "Lock Pick")
        pool = [i.name for i in self.multiworld.itempool]
        self.assertIn("Lock Pick", pool)                             # the real one is still placed

    def test_start_room_is_reachable_with_nothing(self):
        state = self.multiworld.state.copy()
        self.assertTrue(state.can_reach_region(self.world.start_room, self.player))


class TestStartRoomMansion(RE1HDTestBase):
    options = {"only_detected_pickups": False, "random_start_room": "mansion_save_rooms"}

    def test_mansion_only(self):
        self.assertIn(self.world.start_room, START_ROOMS_MANSION)


class TestStartRoomWithLocksAndDoors(RE1HDTestBase):
    options = {"only_detected_pickups": False, "random_start_room": "save_rooms",
               "door_lock_randomisation": 1, "door_randomisation": 2, "goal": "complete_game"}

    def test_doors_were_built_from_the_start_room(self):
        w = self.world
        self.assertIn(w.start_room, START_ROOMS_ALL)
        self.assertIsNone(w._check_start())


class TestStartRoomValidation(RE1HDTestBase):
    """The validators measure from the start room they're given."""

    def test_reachable_from_origin(self):
        doors = dl.effective_doors({})
        rooms, _h, _b = dl.reachable(doors, Counter(), False, origin="Residence Storeroom")
        self.assertIn("Residence Storeroom", rooms)
        self.assertNotIn("Residence Storeroom", dl.reachable(doors, Counter(), False)[0])   # default: Main Hall

    def test_rooms_that_can_never_work_are_rejected(self):
        items, locs = dl.simple_progression()
        locs = [l for l in locs if l[0] not in START_ROOM_MISSABLE]
        base = dl.effective_doors({})
        for room in ("Room 003", "Garbage Compactor Room"):
            reason = ds.check({}, base, items, locs, False, False, random.Random(1), origin=room)
            self.assertIsNotNone(reason, room)
        for room in ("Dining Room", "East Wing Storeroom", "Residence Storeroom"):
            self.assertIsNone(ds.check({}, base, items, locs, False, False, random.Random(1), origin=room), room)

    def test_start_needs_enough_checks_in_reach(self):
        from .. import MIN_START_LOCATIONS
        items, locs = dl.simple_progression()
        doors = dl.effective_doors({})
        for room in ("Dining Room", "East Wing Storeroom", "Residence Storeroom", "Mining Area"):
            self.assertGreaterEqual(dl.start_locations(doors, locs, False, room), MIN_START_LOCATIONS, room)
        # a start cut off by its doors has (almost) nothing in reach
        cut = [d for d in doors if "East Wing Storeroom" not in d[:2]]
        self.assertLess(dl.start_locations(cut, locs, False, "East Wing Storeroom"), MIN_START_LOCATIONS)

    def test_gate_side_start_has_the_gate_open(self):
        """2026-11-15 (TessarionAM, 19:15): starting beyond the Stone & Metal gate, the client puts
        the object in the gate for you, so both ways through it are open in the logic."""
        doors = dl.effective_doors({})
        rooms = dl.reachable(doors, Counter(["Battery"]), False, origin="Residence Storeroom")[0]
        self.assertIn("Roofed Passage", rooms)
        start = dl.with_start(doors, "Residence Storeroom")
        gate = [d for d in start if (d[0], d[1]) == ("Roofed Passage", "Garden Shed")]
        self.assertEqual([tuple(d[2]) for d in gate], [()])
        self.assertEqual(dl.with_start(doors, "Dining Room"), doors)          # Mansion starts: unchanged


class TestGateSideStartWorld(RE1HDTestBase):
    options = {"only_detected_pickups": False, "random_start_room": "save_rooms"}

    def test_world_and_slot_data_agree(self):
        from ..data import GATE_SIDE_STARTS
        w = self.world
        sd = w.fill_slot_data()
        self.assertEqual(sd["gate_open"], int(w.start_room in GATE_SIDE_STARTS))
        ent = self.multiworld.get_entrance("Roofed Passage -> Garden Shed", self.player)
        state = self.multiworld.state.copy()
        # beyond the gate it needs nothing; otherwise the object
        self.assertEqual(ent.access_rule(state), w.start_room in GATE_SIDE_STARTS)
