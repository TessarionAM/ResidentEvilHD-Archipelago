"""Door randomiser (2026-11-12): layouts, logic, softlock check and real Archipelago seeds."""
import random
import unittest
from collections import Counter

from . import RE1HDTestBase
from .test_door_locks import generate
from .. import door_locks as dl
from .. import door_shuffle as ds
from ..client.door_data import ARRIVALS
from ..data import ROOMS, START
from ..door_table import DOOR_TABLE


class EndTests(unittest.TestCase):
    def test_what_is_and_isnt_shuffled(self):
        dids = {e[0] for e in ds.ends()}
        for did in ds.ESCAPE:
            self.assertNotIn(did, dids)                       # the escape route stays
        for did in ("103-103", "109-109"):
            self.assertNotIn(did, dids)                       # doors inside one game room
        for did, d in DOOR_TABLE.items():
            if d["kind"] in ("event", "special", "inactive", "electronic") or not d["world"]:
                self.assertNotIn(did, dids, did)
        types = Counter(DOOR_TABLE[d]["door_type"] for d in dids)
        self.assertTrue(types[3] and types[4])                # ladders and lifts are in (TessarionAM)

    def test_every_end_has_an_arrival_spot(self):
        for did, room in ds.ends():
            other = ds.other_side((did, room))[1]
            self.assertTrue(any(s[0] == other and any(s[1:4]) for s in ARRIVALS[room]), (did, hex(room)))


class LayoutTests(unittest.TestCase):
    base = dl.effective_doors({})

    def test_coupled_is_symmetric_and_matches_needs(self):
        need = ds.needs(self.base)
        for seed in range(15):
            try:
                lay = ds.build_layout(ds.COUPLED, random.Random(seed), self.base)
            except ds.ShuffleError:
                continue
            for k, t in lay["targets"].items():
                e, f = ds.unkey(k), (t[0], int(t[1], 16))
                back = lay["targets"].get(ds.key(f))
                if back is None or ds.unkey(f"{back[0]}@{back[1]}") != e:
                    self.assertEqual(f, ds.other_side(e))         # the odd one out: vanilla
                    continue
                self.assertEqual(need[e], need[f], (e, f))        # same door kind both ways
                self.assertNotEqual(e[1], f[1])                   # never into its own room

    def test_decoupled_is_a_permutation_without_traps(self):
        need = ds.needs(self.base)
        group, of, start = ds._groups(self.base, ds.pinned(need))
        group_of = {e: g for g, es in of.items() for e in es}
        for seed in range(15):
            try:
                lay = ds.build_layout(ds.DECOUPLED, random.Random(seed), self.base)
            except ds.ShuffleError:
                continue
            arrivals = [tuple(t) for t in lay["targets"].values()]
            self.assertEqual(len(arrivals), len(set(arrivals)))   # every spot used once
            for k, t in lay["targets"].items():
                e, f = ds.unkey(k), (t[0], int(t[1], 16))
                self.assertNotEqual(e[1], f[1])
                if need[e] is not None:                            # can leave where it drops her
                    exits = [need[x] for x in of[group_of[f]] if need[x] is not None]
                    self.assertTrue(any(set(x) <= set(need[e]) for x in exits), (e, f))

    def test_built_layouts_pass_often_enough(self):
        items, locs = dl.simple_progression()
        # 40 tries each (2026-11-13: 20 was too few to measure coupled's ~15% per-try pass rate
        # with normal locks; generation itself makes up to 400 tries per lock layout)
        for mode, at_least in ((ds.COUPLED, 3), (ds.DECOUPLED, 16)):
            ok = 0
            for seed in range(40):
                rng = random.Random(seed)
                try:
                    lay = ds.build_layout(mode, rng, self.base)
                except ds.ShuffleError:
                    continue
                ok += ds.check(lay, self.base, items, locs, False, True, rng) is None
            self.assertGreaterEqual(ok, at_least, ds.MODE_NAMES[mode])

    def test_connections_follow_the_layout(self):
        lay = ds.make_layout(ds.COUPLED, random.Random(1), base_doors=self.base)
        doors = ds.connections(lay, self.base)
        e = next(ds.unkey(k) for k in lay["targets"])
        here, there = ds.logic_room(e), ds.logic_room(ds.target(lay, e))
        self.assertIn(here, ROOMS)
        self.assertTrue(any(a == here and b == there for a, b, _r, _o in doors))
        self.assertEqual(ds.connections({}, self.base), self.base)


class SoftlockTests(unittest.TestCase):
    def test_a_room_with_no_way_back_is_caught(self):
        base = dl.effective_doors({})
        doors = [d for d in base if START not in (d[0], d[1])]
        # the start leads one way into the Bar, whose only door needs the Armor Key
        doors += [(START, "Bar", (), True), ("Bar", START, ("Armor Key",), True)]
        self.assertIn("Bar", ds.stuck_rooms(doors, Counter(), True))
        self.assertNotIn("Bar", ds.stuck_rooms(doors, Counter(["Armor Key"]), False))


class RealSeedTests(unittest.TestCase):
    def test_coupled_and_decoupled_seeds_generate_and_are_beatable(self):
        for mode in ("coupled", "decoupled"):
            for seed in (1, 2):
                mw, problem = generate({"door_randomisation": mode}, seed)
                self.assertIsNone(problem, (mode, seed, problem))
                sd = mw.worlds[1].fill_slot_data()
                self.assertEqual(sd["door_shuffle"]["mode"], mode)
                self.assertTrue(sd["door_shuffle"]["targets"])

    def test_with_the_lock_randomiser_too(self):
        mw, problem = generate({"door_randomisation": "decoupled", "door_lock_randomisation": "full"}, 3)
        self.assertIsNone(problem, problem)
        sd = mw.worlds[1].fill_slot_data()
        self.assertTrue(sd["door_locks"] and sd["door_shuffle"])

    def test_off_is_vanilla(self):
        mw, problem = generate({}, 4)
        self.assertIsNone(problem)
        self.assertEqual(mw.worlds[1].fill_slot_data()["door_shuffle"], {})


class TestCoupledDefaults(RE1HDTestBase):
    options = {"door_randomisation": "coupled"}


class TestDecoupledDefaults(RE1HDTestBase):
    options = {"door_randomisation": "decoupled"}


class SealedRoomTests(unittest.TestCase):
    """Dead ends whose only door is locked from the inside (2026-11-12 batch failures)."""

    def test_way_back_only_for_the_only_door_in(self):
        door = next(d for d in ds.DOOR_TABLE.values() if d["world"])
        a, b = door["world"][0][:2]
        alone = ds._ways_back([(a, b, (), True)])
        self.assertIn((b, a, (), True), alone)            # only way in: she can walk back out
        other = ds._ways_back([(a, b, (), True), ("Somewhere Else", b, (), True)])
        self.assertNotIn((b, a, (), True), other)         # another way in: not guaranteed open

    def test_not_for_links_that_are_not_doors(self):
        self.assertEqual(ds._ways_back([("Nowhere A", "Nowhere B", (), True)]),
                         [("Nowhere A", "Nowhere B", (), True)])

    def test_every_lock_option_generates_in_both_modes(self):
        for lock in ("disabled", "regional", "full"):
            for mode in ("coupled", "decoupled"):
                with self.subTest(lock=lock, mode=mode):
                    _mw, problem = generate({"door_randomisation": mode,
                                             "door_lock_randomisation": lock}, 7)
                    self.assertIsNone(problem, problem)


class CeilingTrapDoorsTest(unittest.TestCase):
    """2026-11-13: the Marble Room (ceiling trap) keeps both its doors."""

    def test_marble_room_doors_never_shuffled(self):
        from ..door_shuffle import shufflable
        self.assertFalse(shufflable("109-115"))
        self.assertFalse(shufflable("115-116"))
