"""Door lock randomiser tests (2026-11-12): layouts, logic, and real seeds generated with
Archipelago's own fill (every accepted seed must be beatable)."""
import random
import unittest
from argparse import Namespace
from collections import Counter

from . import RE1HDTestBase
from .. import door_locks as dl
from ..data import DOORS
from ..door_table import DOOR_TABLE, KEY_ITEMS

GAME = "Resident Evil HD Remaster"


def generate(options: dict, seed: int):
    """One single-player seed with Archipelago's real generation + fill. Returns (multiworld, problem)."""
    from BaseClasses import CollectionState, MultiWorld
    from Fill import distribute_items_restrictive
    from worlds import AutoWorld
    from worlds.AutoWorld import call_all
    from Options import OptionError
    mw = MultiWorld(1)
    mw.game[1] = GAME
    mw.player_name = {1: "Tester"}
    mw.set_seed(seed)
    args = Namespace()
    for name, option in AutoWorld.AutoWorldRegister.world_types[GAME].options_dataclass.type_hints.items():
        setattr(args, name, {1: option.from_any(options.get(name, option.default))})
    mw.set_options(args)
    mw.state = CollectionState(mw)
    try:
        for step in ("generate_early", "create_regions", "create_items", "set_rules", "connect_entrances",
                     "generate_basic", "pre_fill"):
            call_all(mw, step)
        distribute_items_restrictive(mw)
        call_all(mw, "post_fill")
    except OptionError as exc:
        return mw, f"option error: {exc}"
    except Exception as exc:            # FillError etc.
        return mw, f"{type(exc).__name__}: {exc}"
    if not mw.can_beat_game(CollectionState(mw)):
        return mw, "not beatable"
    return mw, None


class LayoutUnitTests(unittest.TestCase):
    def test_counts_and_limits(self):
        self.assertEqual(dl.limits(dl.MANSION_ONLY), (24, 42))
        self.assertEqual(dl.limits(dl.REGIONAL), (30, 65))
        self.assertEqual(dl.resolve_count(dl.REGIONAL, -1), 30)
        self.assertEqual(dl.resolve_count(dl.REGIONAL, -2), 22)
        self.assertEqual(dl.resolve_count(dl.REGIONAL, -4), 45)
        with self.assertRaises(dl.LayoutError):
            dl.resolve_count(dl.MANSION_ONLY, 43)       # more than the mode supports: an error, never a silent change

    def test_layout_rules(self):
        for mode in (dl.MANSION_ONLY, dl.REGIONAL, dl.FULL):
            for seed in range(25):
                count = random.Random(seed).randint(0, dl.limits(mode)[1])
                lay = dl._random_layout(mode, count, dl.candidate_doors(mode), random.Random(seed))
                locked = [d for d, e in lay.items() if e["kind"] != "open"]
                self.assertEqual(len(locked), count)
                flags = []
                for did, e in lay.items():
                    sides = list(e["sides"].values())
                    if e["kind"] in ("key", "lockpick"):
                        self.assertEqual(sides[0], sides[1], "both sides: same key, shared flag")
                        flags.append(sides[0][1])
                    if e["kind"] == "one_sided":
                        self.assertEqual(sorted(t for t, _ in sides), [21, 22])
                        self.assertEqual(sides[0][1], sides[1][1])
                        flags.append(sides[0][1])
                    if e["kind"] == "key" and mode != dl.FULL:
                        t = sides[0][0]
                        self.assertIn(t, dl.AREA_KEYS[DOOR_TABLE[did]["area"]], "regional keys stay in their area")
                    if e["kind"] == "lockpick" and mode != dl.FULL:
                        self.assertEqual(DOOR_TABLE[did]["area"], "Mansion")
                    for t, f in sides:
                        self.assertTrue(0 <= f < 255)
                self.assertEqual(len(flags), len(set(flags)), "every locked door has its own unlock flag")
                uses = dl.key_uses(lay)
                if mode != dl.FULL:
                    for area in dl.mode_areas(mode):
                        vals = [uses[KEY_ITEMS[k]] for k in dl.AREA_KEYS[area]]
                        self.assertLessEqual(max(vals) - min(vals), dl.BALANCE_RANGE, (mode, area, uses))

    def test_key_uses_equal_doors(self):
        lay = dl._random_layout(dl.FULL, 50, dl.candidate_doors(dl.FULL), random.Random(4))
        counted = Counter()
        for did, e in lay.items():
            t = list(e["sides"].values())[0][0]
            if e["kind"] == "key":
                counted[KEY_ITEMS[t]] += 1
        uses = dl.key_uses(lay)
        fixed = dl._fixed_uses()
        for name, n in counted.items():
            t = [k for k, v in KEY_ITEMS.items() if v == name][0]
            self.assertEqual(uses[name], n + fixed[t])

    def test_disabled_is_vanilla(self):
        self.assertEqual(dl.effective_doors({}), list(DOORS))
        self.assertEqual(dl.key_uses({}), {})

    def test_effective_doors_follow_the_layout(self):
        lay = dl._random_layout(dl.MANSION_ONLY, 30, dl.candidate_doors(dl.MANSION_ONLY), random.Random(9))
        eff = dl.effective_doors(lay)
        for did, e in lay.items():
            for a, b, req, one in DOOR_TABLE[did]["world"]:
                there = [x for x in eff if {x[0], x[1]} == {a, b}]
                keys = {r for x in there for r in x[2] if r in KEY_ITEMS.values()}
                t = list(e["sides"].values())[0][0]
                if e["kind"] == "key":
                    self.assertEqual(keys, {KEY_ITEMS[t]})
                elif e["kind"] == "open":
                    self.assertEqual(keys, set())
                elif e["kind"] == "one_sided":
                    self.assertEqual(len(there), 1, "a one-sided door can only be used from its opening side")


class RealSeedTests(unittest.TestCase):
    """Real Archipelago generation + fill for every mode and several counts (a smaller batch than
    Tools/door_lock_batch.py, which runs hundreds)."""
    def run_batch(self, options, seeds):
        bad = []
        for seed in seeds:
            mw, problem = generate(options, seed)
            if problem:
                bad.append((seed, problem))
            else:
                world = mw.worlds[1]
                # every key arrives with as many uses as it has doors
                for name, n in world.fill_slot_data()["key_uses"].items():
                    self.assertGreaterEqual(n, 1)
        self.assertEqual(bad, [], f"{options}: failed seeds")

    def test_mansion_only(self):
        for count in ("fewer", "vanilla", "more", "many", 42):
            self.run_batch({"door_lock_randomisation": "mansion_only", "locked_door_count": count}, range(4))

    def test_regional(self):
        for count in ("fewer", "vanilla", "many", 65):
            self.run_batch({"door_lock_randomisation": "regional", "locked_door_count": count}, range(4))

    def test_full(self):
        for count in (0, "vanilla", "many", 65):
            self.run_batch({"door_lock_randomisation": "full", "locked_door_count": count}, range(4))

    def test_mansion_escape_goal(self):
        self.run_batch({"door_lock_randomisation": "full", "locked_door_count": "many",
                        "goal": "mansion_escape"}, range(4))

    def test_too_many_is_an_error(self):
        _mw, problem = generate({"door_lock_randomisation": "mansion_only", "locked_door_count": 60}, 1)
        self.assertIsNotNone(problem)
        self.assertIn("at most 42", problem)

    def test_disabled_generates_the_same_seed_as_before(self):
        a, _ = generate({}, 77)
        b, _ = generate({"door_lock_randomisation": "disabled", "locked_door_count": 50}, 77)
        place = lambda mw: [(l.name, l.item.name if l.item else None) for l in mw.get_locations()]
        self.assertEqual(place(a), place(b))


class TestRegionalDefaults(RE1HDTestBase):
    """Archipelago's standard world checks (all reachable, beatable, fill) with locks shuffled."""
    options = {"only_detected_pickups": False, "door_lock_randomisation": "regional", "locked_door_count": "more"}


class TestFullDefaults(RE1HDTestBase):
    options = {"door_lock_randomisation": "full", "locked_door_count": 60}
