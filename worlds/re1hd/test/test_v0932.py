"""2026-11-15 play-test requests (TessarionAM): Greenhouse herbs, the Cerberus' Collar, Boss Rush
on the tracker and Key Map, coloured item names, the Broken Flamethrower below the cave lift."""
import unittest
from collections import Counter

from . import RE1HDTestBase
from .. import door_locks as dl
from ..data import FLAMETHROWER_LOCATIONS, GONE_WHEN, MISSABLE, PICKUPS


class GreenhouseHerbTests(unittest.TestCase):
    def test_herbs_need_the_herbicide(self):
        herbs = [p for p in PICKUPS if p[1].startswith("Greenhouse - Green Herb")]
        self.assertEqual(len(herbs), 5)
        for _room, name, _item, req in herbs:
            self.assertEqual(tuple(req), ("Herbicide",), name)
            self.assertIn(name, MISSABLE)                       # still junk

    def test_tracker_only_with_the_herbicide(self):
        from ..logic_tracker import in_logic
        herbs = {f"Greenhouse - Green Herb {i}" for i in range(1, 6)}
        active = herbs | {"Outside Boiler - Herbicide"}      # a check: not picked up on the way
        everything = [i for i in dl._everything().elements() if i != "Herbicide"]
        self.assertFalse(herbs & set(in_logic(everything, active, set(), False)))
        self.assertEqual(herbs & set(in_logic(everything + ["Herbicide"], active, set(), False)), herbs)


class CollarTests(unittest.TestCase):
    NAME = "Outside Balcony - Collar (Cerberus)"

    def test_missable_and_gone_once_a_collar_is_received(self):
        from ..tracker import drop_gone
        self.assertEqual(MISSABLE[self.NAME], "Collar")
        self.assertEqual(GONE_WHEN[self.NAME], "Collar")
        active = {self.NAME, "Small Library - Dog Whistle"}
        self.assertEqual(drop_gone(active, set(), ["Dog Whistle"]), active)
        self.assertEqual(drop_gone(active, set(), ["Collar"]), {"Small Library - Dog Whistle"})
        self.assertEqual(drop_gone(active, {self.NAME}, ["Collar"]), active)   # done before: kept


class FlamethrowerWorldTest(RE1HDTestBase):
    options = {"only_detected_pickups": False}

    def test_placed_below_the_lift(self):
        spots = [l.name for l in self.multiworld.get_locations(self.player)
                 if l.item is not None and l.item.name == "Broken Flamethrower"]
        self.assertEqual(len(spots), 1)
        self.assertIn(spots[0], FLAMETHROWER_LOCATIONS)
        self.assertTrue(self.multiworld.get_location(spots[0], self.player).locked)

    def test_handed_straight_to_jill(self):
        from ..data import DIRECT_ITEMS
        from ..game_data import DIRECT_INVENTORY_ITEMS
        self.assertIn("Broken Flamethrower", DIRECT_ITEMS)
        self.assertIn(107, DIRECT_INVENTORY_ITEMS)


class BossTrackerTests(unittest.TestCase):
    def test_off_shows_nothing(self):
        from ..tracker import boss_lines
        self.assertEqual(boss_lines(None), [])

    def test_dead_and_left(self):
        from ..tracker import boss_lines, tracker_text
        lines = boss_lines({"Neptune Defeated": True, "Yawn Defeated": False})
        self.assertIn("1 of 7 defeated", lines[0])
        self.assertTrue(any("Neptune: defeated" in l for l in lines))
        self.assertTrue(any("Yawn: left (Library)" in l for l in lines))
        text = tracker_text([], set(), set(), False, {"Neptune Defeated": True})
        self.assertIn("Boss Rush: 1 of 7", text)


class SkullTests(unittest.TestCase):
    def test_skull_on_the_boss_room_floor_only_with_boss_rush(self):
        from .. import map_render, tracker
        from ..map_layout import FLOORS
        measure = lambda text, size, bold=False: (len(text) * size * 0.6, size * 1.2)
        state = tracker.map_state([], set(), set(), False)
        crypt = next(i for i, f in enumerate(FLOORS) if f[0] == "Mansion B1")
        off = map_render.build(crypt, state, 900, 600, None, measure)
        on = map_render.build(crypt, state, 900, 600, None, measure, bosses={"Crypt Crimson Head Defeated": False})
        self.assertEqual(off.skulls, [])
        self.assertEqual(on.skulls, [("Crypt", "Crypt Crimson Head", False)])
        self.assertIn(map_render.SKULL_ALIVE, [op[1] for op in on.ops if op[0] == "rect"])
        dead = map_render.build(crypt, state, 900, 600, None, measure, bosses={"Crypt Crimson Head Defeated": True})
        self.assertEqual(dead.skulls, [])                       # gone once the boss is dead (19:15)
        self.assertNotIn(map_render.SKULL_ALIVE, [op[1] for op in dead.ops if op[0] == "rect"])


class ItemColourTests(unittest.TestCase):
    def parts(self, flags, receiving=1, finder=1):
        from ..client.overlay import message_parts
        args = {"type": "ItemSend", "receiving": receiving, "item": (1, 2, finder, flags)}
        return message_parts(args, 1, lambda i, s: "Shotgun Shells", lambda s: "Bob", lambda n: 6)

    def test_colours_like_archipelago(self):
        from ..client.overlay import ITEM_COLOUR
        self.assertEqual(self.parts(1)[1][1][1], ITEM_COLOUR["progression"])
        self.assertEqual(self.parts(2)[1][1][1], ITEM_COLOUR["useful"])
        self.assertEqual(self.parts(4)[1][1][1], ITEM_COLOUR["trap"])
        self.assertEqual(self.parts(0)[1][1][1], ITEM_COLOUR["filler"])
        self.assertEqual(self.parts(5)[1][1][1], ITEM_COLOUR["trap"])     # a trap first, like AP

    def test_rest_of_the_line_keeps_its_colour(self):
        kind, parts = self.parts(1)
        self.assertEqual(kind, "found")
        self.assertEqual(parts[0], ("You found your ", None))
        self.assertEqual("".join(t for t, _c in parts), "You found your Shotgun Shells (6).")
