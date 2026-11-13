"""
Logic tests. WorldTestBase also runs Archipelago's standard checks
(everything reachable with all items, the game is beatable, etc.).
"""

import unittest
from . import RE1HDTestBase
from ..data import DOORS, PICKUPS, ROOMS
from ..items import item_table


class TestData(RE1HDTestBase):
    def test_every_room_and_door_is_known(self):
        for a, b, *_ in DOORS:
            self.assertIn(a, ROOMS)
            self.assertIn(b, ROOMS)

    def test_every_item_named_in_data_exists(self):
        from ..data import EVENT_NAMES
        names = set(item_table) | EVENT_NAMES
        for room, loc, item, req in PICKUPS:
            self.assertIn(room, ROOMS, loc)
            self.assertIn(item, names, loc)
            for r in req:
                self.assertIn(r, names, f"{loc} requires unknown item {r}")
        for *_, req, _ in DOORS:
            for r in req:
                self.assertIn(r, names)

    def test_unique_location_names(self):
        names = [p[1] for p in PICKUPS]
        self.assertEqual(len(names), len(set(names)))

    def test_requirements_are_progression(self):
        from BaseClasses import ItemClassification
        from ..data import EVENT_NAMES
        needed = {r for *_, req in PICKUPS for r in req} | {r for *_, req, _ in DOORS for r in req}
        for name in needed - EVENT_NAMES:
            self.assertTrue(item_table[name].kind & ItemClassification.progression,
                            f"{name} gates something but isn't progression")


class TestKeyChain(RE1HDTestBase):
    # key-chain tests on their own: items usable straight away (no item-box gate)
    options = {"goal": "mansion_escape", "received_item_destination": "inventory_then_box"}

    def test_start_area_open(self):
        self.assertTrue(self.can_reach_location("Main Hall - Lock Pick (Barry)"))
        self.assertTrue(self.can_reach_location("Mirror Corridor - Golden Arrow"))

    def test_crypt_needs_golden_arrow(self):
        self.assertFalse(self.can_reach_location("Crypt - Book of Curses"))
        self.collect_by_name(["Golden Arrow"])
        self.assertTrue(self.can_reach_location("Crypt - Book of Curses"))

    def test_armor_key_needs_collar(self):
        self.assertFalse(self.can_reach_location("'Death' Passage - Armor Key"))
        self.collect_by_name(["Collar"])
        self.assertTrue(self.can_reach_location("'Death' Passage - Armor Key"))

    def test_stone_and_metal_needs_all_masks(self):
        base = ["Golden Arrow"]
        masks = ["Mask without eyes", "Mask without a mouth", "Mask without a nose",
                 "Mask without eyes, nose, or mouth"]
        self.collect_by_name(base + masks[:3])
        self.assertFalse(self.can_reach_location("Crypt - Stone & Metal Object"))
        self.collect_by_name(masks[3:])
        self.assertTrue(self.can_reach_location("Crypt - Stone & Metal Object"))

    def test_goal_needs_stone_and_metal(self):
        # The Roofed Passage is in the east wing: reached via the Sword Key door
        # (Art Room -> 'L' Corridor), so the Book of Curses is needed too.
        self.collect_by_name(["Book of Curses"])
        self.assertBeatable(False)
        self.collect_by_name(["Stone & Metal Object"])
        self.assertBeatable(True)


class TestOnlyDetectedPickups(RE1HDTestBase):
    options = {"only_detected_pickups": True, "files_and_notes": True}

    def test_only_detected_pickups_are_checks(self):
        from ..game_data import DETECTED_PICKUPS
        real = {loc.name for loc in self.multiworld.get_locations(self.player) if loc.address is not None}
        self.assertEqual(real, set(DETECTED_PICKUPS))

    def test_pool_matches_checks(self):
        from collections import Counter
        from ..game_data import DETECTED_PICKUPS
        from ..locations import location_table
        from ..data import MISSABLE, MISSABLE_POOL_ITEMS
        from .. import FILLER_ITEMS
        pool = Counter(i.name for i in self.multiworld.itempool if i.player == self.player)
        checks = [n for n in DETECTED_PICKUPS]
        missable_checks = sum(1 for n in MISSABLE if n in DETECTED_PICKUPS and n in location_table)
        # one item per check, minus one per missable check (that location holds locked junk)
        self.assertEqual(sum(pool.values()), len(checks) - missable_checks)
        for name in MISSABLE_POOL_ITEMS:                       # swapped in for junk
            self.assertEqual(pool[name], 1)
        expected = Counter(location_table[n].vanilla_item for n in DETECTED_PICKUPS if n in location_table)
        for name, count in expected.items():                  # every non-junk vanilla item is there
            if name not in FILLER_ITEMS:
                self.assertGreaterEqual(pool[name], count, name)
        extra = set(pool) - set(expected) - set(FILLER_ITEMS) - set(MISSABLE_POOL_ITEMS)
        self.assertEqual(extra, set())                         # nothing else (traps are off here)

    def test_detected_names_exist_and_items_match(self):
        from ..game_data import DETECTED_PICKUPS
        from ..items import item_table
        from ..locations import location_table
        from ..data import EXTRA_CATEGORY_GAME_ID
        from ..locations import extra_location_table
        for name, (_, _, game_id) in DETECTED_PICKUPS.items():
            if name in extra_location_table:
                self.assertEqual(EXTRA_CATEGORY_GAME_ID[extra_location_table[name].category], game_id, name)
                continue
            self.assertIn(name, location_table)
            vanilla = location_table[name].vanilla_item
            if vanilla == "First Aid Box":          # the game has several First Aid Box ids
                self.assertIn(game_id, {101, 104, 131, 132}, name)
            else:
                self.assertEqual(item_table[vanilla].game_id, game_id, name)


class TestMapChecks(RE1HDTestBase):
    """With every pickup a check, the two mansion maps exist with their own IDs and rules."""
    options = {"only_detected_pickups": False, "map_checks": True}

    def test_maps_exist_in_extra_id_range(self):
        from ..locations import EXTRA_BASE_ID
        loc = self.multiworld.get_location("Art Room - Map of the Mansion 1F", self.player)
        self.assertEqual(loc.address, EXTRA_BASE_ID)

    def test_2f_map_needs_lighter_and_wooden_mount(self):
        name = "Resting Room - Map of the Mansion 2F"
        self.collect_all_but(["Lighter", "Wooden Mount"])
        self.assertFalse(self.can_reach_location(name))
        self.collect_by_name(["Lighter", "Wooden Mount"])
        self.assertTrue(self.can_reach_location(name))


class TestMapChecksOff(RE1HDTestBase):
    options = {"only_detected_pickups": False, "map_checks": False}

    def test_no_maps(self):
        names = {loc.name for loc in self.multiworld.get_locations(self.player)}
        self.assertNotIn("Art Room - Map of the Mansion 1F", names)


class TestRoomEntries(RE1HDTestBase):
    options = {"first_room_entries": True}

    def test_room_entries_exist_with_ids_after_maps(self):
        from ..data import ROOM_ENTRY_ROOMS
        from ..locations import EXTRA_BASE_ID, extra_location_table
        names = {loc.name for loc in self.multiworld.get_locations(self.player)}
        for room in ROOM_ENTRY_ROOMS:
            self.assertIn(f"{room} - First Visit", names)
        self.assertEqual(extra_location_table["Main Hall - First Visit"].code, EXTRA_BASE_ID + 2)
        self.assertEqual(ROOM_ENTRY_ROOMS[41], "Concrete Passage 1")   # the Mansion's 42 come first
        self.assertGreater(len(ROOM_ENTRY_ROOMS), 42)

    def test_every_room_entry_has_a_game_room_number(self):
        from ..data import ROOM_ENTRY_ROOMS
        from ..game_data import ROOM_NUMBERS
        numbers = [ROOM_NUMBERS[r] for r in ROOM_ENTRY_ROOMS]
        self.assertNotIn(None, numbers)
        self.assertEqual(len(numbers), len(set(numbers)))      # one check per game room

    def test_room_entry_needs_access_to_the_room(self):
        self.assertFalse(self.can_reach_location("Graveyard - First Visit") is None)


class TestRoomEntriesOff(RE1HDTestBase):
    options = {"first_room_entries": False}

    def test_none(self):
        self.assertFalse([l for l in self.multiworld.get_locations(self.player) if l.name.endswith("First Visit")])


class TestCompleteGame(RE1HDTestBase):
    """The whole game (2026-11-10): default goal is the helicopter ending."""

    def test_default_goal_is_the_helicopter(self):
        names = {loc.name for loc in self.multiworld.get_locations(self.player)}
        self.assertIn("Escape on the Helicopter", names)
        self.assertNotIn("Escape the Mansion", names)

    def test_helicopter_needs_signal_rockets_and_fuse(self):
        from .. import VICTORY_ITEM
        self.collect_all_but(["Signal Rockets", VICTORY_ITEM])
        self.assertBeatable(False)
        self.collect_by_name(["Signal Rockets"])
        self.assertBeatable(True)

    def test_lab_needs_both_medal_books(self):
        self.collect_all_but(["Last Book, vol. 2"])
        self.assertFalse(self.can_reach_region("Lab Entrance"))

    def test_residence_needs_square_crank(self):
        self.collect_all_but(["Square Crank"])
        self.assertFalse(self.can_reach_region("Residence Entry Corridor"))
        self.collect_by_name(["Square Crank"])
        self.assertTrue(self.can_reach_region("Residence Entry Corridor"))

    def test_helmet_key_rooms(self):
        self.collect_all_but(["Helmet Key"])
        self.assertFalse(self.can_reach_location("Trophy Room - Red Jewel"))
        self.collect_by_name(["Helmet Key"])
        self.assertTrue(self.can_reach_location("Trophy Room - Red Jewel"))


class TestAllMaps(RE1HDTestBase):
    """All 8 maps are checks with the default settings (2026-11-10)."""
    options = {"map_checks": True}

    def test_eight_maps(self):
        names = {loc.name for loc in self.multiworld.get_locations(self.player)}
        maps = {n for n in names if " - Map of the " in n}
        self.assertEqual(len(maps), 8)
        self.assertIn("Visual Data Room - Map of the Laboratory", maps)


class TestStartWithSwordKey(RE1HDTestBase):
    options = {"start_with_sword_key": True}

    def test_book_of_curses_is_precollected_not_in_pool(self):
        pre = [i.name for i in self.multiworld.precollected_items[self.player]]
        self.assertIn("Book of Curses", pre)
        self.assertNotIn("Book of Curses", [i.name for i in self.multiworld.itempool])


class TestFillerVariety(RE1HDTestBase):
    options = {"first_room_entries": True}

    def test_extra_checks_get_mixed_filler(self):
        from .. import FILLER_ITEMS
        world = self.multiworld.worlds[self.player]
        picks = {world.get_filler_item_name() for _ in range(200)}
        self.assertEqual(picks, set(FILLER_ITEMS))


class TestItemBoxGate(RE1HDTestBase):
    """Default delivery = item box: received items can only be used after reaching a box."""

    def test_keys_need_an_item_box_first(self):
        self.collect_by_name(["Armor Key"])                 # waits in the box...
        self.assertFalse(self.can_reach_region("Bar"))      # ...so no Armor Key doors yet
        self.collect_by_name(["Book of Curses"])            # handed straight to Jill...
        self.assertTrue(self.can_reach_region("East Wing Storeroom"))   # ...and reaches a box
        self.multiworld.state.sweep_for_advancements()      # picks up the "Item Box Access" event
        self.assertTrue(self.can_reach_region("Bar"))

    def test_lock_pick_works_without_a_box(self):
        # (Large Gallery used to be reachable this way through the Graveyard, but that door is
        # "locked from the other side" - door scanner 2026-11-11.)
        self.collect_by_name(["Lock Pick", "Book of Curses"])
        self.assertTrue(self.can_reach_region("Outside Boiler"))


class TestSwordKeyStartIsDirect(RE1HDTestBase):
    options = {"start_with_sword_key": True}

    def test_starting_sword_key_needs_no_box(self):
        self.assertTrue(self.can_reach_region("'L' Corridor"))


class TestRandomStartingInventory(RE1HDTestBase):
    options = {"random_starting_inventory": True, "map_checks": True}

    def test_two_starting_items_and_weapons_in_pool(self):
        from .. import START_ITEM_CHOICES
        pre = [i.name for i in self.multiworld.precollected_items[self.player]]
        self.assertEqual(len(pre), 2)
        self.assertTrue(all(n in START_ITEM_CHOICES for n in pre))
        pool = [i.name for i in self.multiworld.itempool]
        self.assertIn("Handgun", pool)
        self.assertIn("Combat Knife", pool)


class TestTraps(RE1HDTestBase):
    options = {"trap_percentage": 50, "damage_trap_weight": 50, "poison_trap_weight": 50, "death_link": True}

    def test_traps_replace_junk_only(self):
        names = [i.name for i in self.multiworld.itempool if i.player == self.player]
        traps = [n for n in names if n.endswith("Trap")]
        self.assertTrue(traps)
        self.assertIn("Signal Rockets", names)          # progression untouched
        sd = self.world.fill_slot_data()
        self.assertTrue(sd["death_link"])
        self.assertEqual(sd["damage_trap_amount"], 25)


class TestFillerWeights(RE1HDTestBase):
    def test_handgun_ammo_more_common_than_magnum(self):
        picks = [self.world.get_filler_item_name() for _ in range(2000)]
        self.assertGreater(picks.count("Handgun Magazine"), picks.count("Magnum Rounds") * 2)


class TestGardenShedEntryCompleteGame(RE1HDTestBase):
    options = {"first_room_entries": True, "goal": "complete_game"}

    def test_garden_shed_is_a_check(self):
        self.assertIn("Garden Shed - First Visit", [l.name for l in self.multiworld.get_locations(self.player)])
        self.assertIn("Secret Passage - First Visit", [l.name for l in self.multiworld.get_locations(self.player)])


class TestGardenShedEntryMansionEscape(RE1HDTestBase):
    options = {"first_room_entries": True, "goal": "mansion_escape"}

    def test_garden_shed_is_the_goal_not_a_check(self):
        self.assertNotIn("Garden Shed - First Visit", [l.name for l in self.multiworld.get_locations(self.player)])


class TestPoolNeverLosesProgression(RE1HDTestBase):
    options = {"random_starting_inventory": True, "trap_percentage": 100, "start_with_sword_key": True}

    def test_progression_items_all_present(self):
        from ..data import PICKUPS
        names = [i.name for i in self.multiworld.itempool if i.player == self.player]
        for must in ("Signal Rockets", "Fuse Unit", "Armor Key", "Handgun", "Combat Knife"):
            self.assertIn(must, names)
        self.assertNotIn("Book of Curses", names)                # precollected instead


class TestStartBoxRibbons(RE1HDTestBase):
    def test_99_ribbons_without_autosave(self):
        sd = self.world.fill_slot_data()
        self.assertEqual(sd["start_box"][1], [68, 99])
        self.assertNotEqual(sd["start_box"][0][0], 0)


class TestStartBoxAutosave(RE1HDTestBase):
    options = {"autosave": True, "autosave_slot": 5}

    def test_ribbons_become_a_random_item(self):
        sd = self.world.fill_slot_data()
        self.assertNotEqual(sd["start_box"][1][0], 68)
        self.assertEqual(sd["autosave_slot"], 5)


class TestTrackerMatchesGeneratorLogic(RE1HDTestBase):
    """logic_tracker (used by the client's /inlogic) must agree with the generator's rules."""
    options = {"first_room_entries": True, "map_checks": True}

    def test_same_reachable_locations_for_growing_item_sets(self):
        from ..logic_tracker import in_logic
        progression = [i.name for i in self.multiworld.itempool
                       if i.player == self.player and i.advancement]
        rnd = self.multiworld.random
        rnd.shuffle(progression)
        active = {l.name for l in self.multiworld.get_locations(self.player) if l.address is not None}
        for cut in (0, 3, 8, 15, 25, len(progression)):
            names = progression[:cut]
            from BaseClasses import CollectionState
            state = CollectionState(self.multiworld)
            for n in names:
                state.collect(self.world.create_item(n), True)
            state.sweep_for_advancements(locations=[l for l in self.multiworld.get_locations(self.player)
                                                    if l.address is None])
            expected = sorted(l.name for l in self.multiworld.get_locations(self.player)
                              if l.address is not None and l.can_reach(state))
            got = sorted(in_logic(names, active, set(), live=False))
            self.assertEqual(got, expected, f"after {cut} items")


class TestDoorScannerCorrections(RE1HDTestBase):
    """Seed test 3 (2026-11-11): the Kitchen -> Concrete Passage 2 door is locked from the other
    side, so B1 needs the Helmet Key (Resting Room -> Sliding Trap Room)."""
    options = {"received_item_destination": "inventory_then_box"}

    def test_kitchen_does_not_lead_to_the_basement(self):
        self.collect_by_name(["Book of Curses", "Armor Key", "Lock Pick"])
        self.assertTrue(self.can_reach_region("Kitchen"))
        self.assertFalse(self.can_reach_region("Concrete Passage 2"))

    def test_helmet_key_opens_the_basement_from_the_resting_room(self):
        self.collect_by_name(["Book of Curses", "Armor Key", "Lock Pick", "Helmet Key"])
        self.assertTrue(self.can_reach_region("Secret Passage"))
        self.assertTrue(self.can_reach_region("Concrete Passage 2"))

    def test_barry_items_need_the_armor_key_spot_not_an_armor_key(self):
        self.collect_by_name(["Book of Curses", "Armor Key", "Lock Pick"])
        self.assertFalse(self.can_reach_location("East Wing Storeroom - First Aid Spray (Barry)"))


class TestRandomStartHasAGun(RE1HDTestBase):
    options = {"random_starting_inventory": True}

    def test_a_gun_is_always_among_the_starting_items(self):
        from .. import START_GUNS
        start = [i.name for i in self.multiworld.precollected_items[self.player]]
        self.assertTrue(any(n in START_GUNS for n in start), start)


class TestTrackerText(RE1HDTestBase):
    def test_tracker_and_key_map_render(self):
        from ..tracker import key_map_text, tracker_text
        active = {l.name for l in self.multiworld.get_locations(self.player) if l.address is not None}
        t = tracker_text(["Book of Curses"], active, set(), True)
        self.assertIn("Checks you can do now", t)
        self.assertIn("Book of Curses", t)
        k = key_map_text(["Book of Curses"], True)
        self.assertIn("Armor Key", k)
        self.assertIn("<->", k)


class KeyMapTests(unittest.TestCase):
    def test_every_drawn_room_is_ours_or_map_only(self):
        from ..data import ROOMS
        from ..map_geometry import logic_room
        from ..map_layout import FLOORS
        for _t, _w, _h, rooms, _d in FLOORS:
            for name in rooms:
                lr = logic_room(name)
                self.assertTrue(lr is None or lr in ROOMS, name)
                if lr is None:
                    self.assertNotIn(name, ROOMS, name)     # a real room must never be greyed out

    def test_mirror_room_is_drawn_apart_but_counted_with_the_large_art_room(self):
        from ..map_geometry import floor, logic_room
        f = floor(0)
        self.assertIn("Large Art Room", f.names)
        self.assertIn("Mirror Room", f.names)
        self.assertEqual(logic_room("Mirror Room"), "Large Art & Mirror Rooms")
        walls = f.outline_of("Mirror Room")
        self.assertTrue(any(not outer for *_xy, outer in walls))   # a wall between the two rooms

    def test_locked_doors_get_their_key_and_open_once_you_have_it(self):
        from ..map_layout import FLOORS
        from ..tracker import map_state
        f = [t for t, *_ in FLOORS].index("Mansion 1F")
        _c, doors, _e = map_state([], set(), set(), True)
        sword = [d for d in doors[f] if d["key"] == "Book of Curses"]
        self.assertTrue(sword)
        self.assertFalse(any(d["ok"] for d in sword))
        helmet = [d for d in doors[f] if {d["a"], d["b"]} == {"Large Art Room", "Main Hall"}]
        self.assertEqual([d["key"] for d in helmet], ["Helmet Key"])
        _c, doors, _e = map_state(["Book of Curses"], set(), set(), True)
        self.assertTrue(all(d["ok"] for d in doors[f] if d["key"] == "Book of Curses"))

    def test_room_status(self):
        from ..tracker import CAN_GET, DONE, LATER, room_status
        active = {"Dining Room - Ink Ribbons", "Dining Room - Wooden Emblem", "Main Hall - Lock Pick (Barry)",
                  "Armor Room - Mask without eyes, nose, or mouth"} & set(self.names())
        st = room_status([], active, {"Main Hall - Lock Pick (Barry)"}, True)
        self.assertEqual(st.get("Main Hall"), DONE)
        self.assertEqual(st.get("Dining Room"), CAN_GET)
        if "Armor Room - Mask without eyes, nose, or mouth" in active:
            self.assertEqual(st["Armor Room"], LATER)

    def test_room_counts(self):
        from ..tracker import map_state
        active = {"Dining Room - Ink Ribbons", "Dining Room - Wooden Emblem", "Main Hall - Lock Pick (Barry)"} & set(self.names())
        counts, _d, _e = map_state([], active, {"Main Hall - Lock Pick (Barry)"}, True)
        self.assertEqual(counts["Main Hall"], [0, 0, 1])
        self.assertEqual(counts["Dining Room"][0], len(active) - 1)

    def names(self):
        from ..data import PICKUPS
        return {n for _r, n, _i, _q in PICKUPS}

    def test_floor_lookup(self):
        from ..tracker import floor_of
        self.assertEqual(floor_of("Main Hall"), 0)
        self.assertEqual(floor_of("Large Art & Mirror Rooms"), 0)     # logic name of two drawn rooms
        self.assertEqual(floor_of("Secret Passage"), 1)               # the 2F one, not the 1F strip
        self.assertEqual(floor_of("Nowhere"), -1)


class KeyMapGeometryTests(unittest.TestCase):
    def test_traced_gaps_are_closed(self):
        """Every room on a floor touches another room or is one piece (no 1-cell slits left where
        the source map had wall lines or door markers)."""
        from ..map_geometry import floor
        from ..map_layout import FLOORS
        for i in range(len(FLOORS)):
            f = floor(i)
            for name in f.names:
                self.assertTrue(f.rects[name], (f.title, name))
            # door markers sit on their room's wall (within 2 cells), never out in nothing
            for x, y, _hz, a, _b in f.doors:
                near = {f.room_at(x + dx, y + dy) for dx in (-2, -1, 0, 1, 2) for dy in (-2, -1, 0, 1, 2)}
                self.assertIn(a, near, (f.title, a, x, y))

    def test_mansion_2f_rooms_join_up(self):
        """Seed test 6: rooms on Mansion 2F looked cut off. Every door's two rooms now share a wall."""
        from ..map_geometry import floor
        f = floor(1)
        for x, y, _hz, a, b in f.doors:
            if not b:
                continue
            near = {f.room_at(x + dx, y + dy) for dx in (-1.5, 0, 1.5) for dy in (-1.5, 0, 1.5)}
            self.assertTrue({a, b} <= near, (a, b, x, y))


class KeyMapDrawingTests(unittest.TestCase):
    @staticmethod
    def measure(text, size, bold=False):
        return len(text) * size * 0.55, size * 1.25

    def scene(self, floor=0, received=(), room="Main Hall", w=1100, h=640, highlight=None):
        from ..data import PICKUPS
        from ..map_render import build
        from ..tracker import map_state
        active = {n for _r, n, _i, _q in PICKUPS}
        return build(floor, map_state(list(received), active, set(), True), w, h, room, self.measure, highlight)

    def test_every_floor_draws_inside_the_widget(self):
        from ..map_layout import FLOORS
        for i in range(len(FLOORS)):
            for w, h in ((1100, 640), (500, 700)):
                sc = self.scene(i, w=w, h=h)
                for op in sc.ops:
                    if op[0] == "rect":
                        _k, _c, x, y, rw, rh = op
                        self.assertTrue(-4 <= x and x + rw <= w + 4 and -4 <= y and y + rh <= h + 4,
                                        (FLOORS[i][0], op))

    def test_no_room_names_on_the_map(self):
        from ..map_layout import FLOORS
        sc = self.scene(0)
        texts = {op[2] for op in sc.ops if op[0] == "text"}
        self.assertFalse(texts & set(FLOORS[0][3]))

    def test_doors_hollow_until_you_have_the_key(self):
        from ..map_render import HOLLOW
        sc = self.scene(0)
        sword = [d for _b, d in sc.door_hits if d["key"] == "Book of Curses"]
        self.assertTrue(sword and not sword[0]["ok"])
        self.assertIn(HOLLOW, [op[1] for op in sc.ops if op[0] == "rect"])
        sc = self.scene(0, received=["Book of Curses"])
        self.assertTrue(all(d["ok"] for _b, d in sc.door_hits if d["key"] == "Book of Curses"))

    def test_legend_lists_the_keys_on_this_floor(self):
        """v0.9.3: a key is listed once you have it (its doors show in its colour); before that its
        doors are red, under "can't open yet"."""
        sc = self.scene(0)
        lids = [lid for _b, lid in sc.legend_hits]
        self.assertNotIn("key:Book of Curses", lids)
        self.assertIn("cant", lids)
        sc = self.scene(0, received=["Book of Curses"])
        self.assertIn("key:Book of Curses", [lid for _b, lid in sc.legend_hits])
        self.assertIn("Sword Key", [op[2] for op in sc.ops if op[0] == "text"])

    def test_hover_tooltips(self):
        from ..map_render import overlay, tooltip_lines
        sc = self.scene(0)
        (x, y, w, h), d = next((b, d) for b, d in sc.door_hits if d["key"] == "Book of Curses")
        lines, door, _room, _lid = tooltip_lines(sc, x + w / 2, y + h / 2)
        self.assertEqual(lines[0], "Sword Key door")
        self.assertIs(door, d)
        cx, cy = sc.floor.label_at["Dining Room"]
        lines, _d, room, _lid = tooltip_lines(sc, sc.ox + cx * sc.s, sc.oy + cy * sc.s)
        self.assertEqual(room, "Dining Room")
        self.assertEqual(lines[0], "Dining Room")
        (x, y, w, h), lid = sc.legend_hits[1]
        ops, got = overlay(sc, x + 5, y + h / 2, 1100, 640, self.measure)
        self.assertEqual(got, lid)

    def test_highlighting_a_key_fades_the_other_doors(self):
        from ..map_render import FADE
        sc = self.scene(0, highlight="key:Book of Curses")
        alphas = {op[1][3] for op in sc.ops if op[0] == "rect"}
        self.assertIn(FADE, alphas)

    def test_jill_marks_both_drawn_rooms_of_the_large_art_room(self):
        sc = self.scene(0, room="Large Art & Mirror Rooms")
        self.assertEqual(set(sc.here), {"Large Art Room", "Mirror Room"})

    # ---- v0.9.2 (TessarionAM: "a map, not a tracker"; polished, even lines)
    def test_no_badges_only_rects_and_text(self):
        from ..map_layout import FLOORS
        for i in range(len(FLOORS)):
            kinds = {op[0] for op in self.scene(i).ops}
            self.assertLessEqual(kinds, {"rect", "pulse", "ring_rect", "text"}, FLOORS[i][0])

    def test_every_wall_is_the_same_whole_pixel_thickness(self):
        from ..map_layout import FLOORS
        from ..map_render import WALL, WALL_PX
        for i in range(len(FLOORS)):
            for size in ((1106, 620), (1400, 900), (700, 500)):
                sc = self.scene(i, w=size[0], h=size[1])
                for op in sc.ops:
                    if op[0] == "rect" and op[1] == WALL and op[2] >= sc.map_box[0] - 5:
                        _k, _c, x, y, w, h = op
                        self.assertTrue(all(isinstance(v, int) for v in (x, y, w, h)), op)
                        self.assertEqual(min(w, h), WALL_PX, (FLOORS[i][0], op))

    def test_jill_room_glows_and_nothing_else_does(self):
        from ..map_render import PULSE_HIGH, PULSE_LOW, PULSE_SECONDS, ROOM, pulse_colour
        sc = self.scene(0, room="Dining Room")
        pulsing = [op for op in sc.ops if op[0] == "pulse" and op[2] < sc.map_box[0] + sc.map_box[2]]
        self.assertTrue(pulsing)
        for _k, _c, x, y, w, h in pulsing:
            self.assertEqual(sc.floor.room_at(*sc.to_grid(x + w / 2, y + h / 2)), "Dining Room")
        # v0.9.3 (TessarionAM): 50% brighter at the top, 25% darker at the bottom
        self.assertEqual((PULSE_LOW, PULSE_HIGH), (0.75, 1.5))
        top = pulse_colour(ROOM, PULSE_SECONDS / 4)
        low = pulse_colour(ROOM, PULSE_SECONDS * 3 / 4)
        self.assertAlmostEqual(top[0], ROOM[0] * 1.5, places=6)
        self.assertAlmostEqual(low[0], ROOM[0] * 0.75, places=6)

    def test_tea_room_and_northern_corridor_glow_together(self):
        """Seed test 6: standing in the Tea Room, the map put Jill in the Northern Corridor. The game
        has one room number (0x103) for both, so both glow."""
        for room in ("Tea Room", "Northern Corridor"):
            sc = self.scene(0, room=room)
            self.assertEqual(set(sc.here), {"Tea Room", "Northern Corridor"})

    def test_alfies_door_colours(self):
        from ..map_render import CANT_OPEN, ONE_WAY, rgba
        from ..tracker import KEY_COLOURS
        self.assertEqual(KEY_COLOURS["Book of Curses"], "ffe600")   # bright yellow
        self.assertEqual(KEY_COLOURS["Shield Key"], "d9620b")       # dark orange
        self.assertEqual(KEY_COLOURS["Helmet Key"], "9b4dff")       # purple
        self.assertEqual(KEY_COLOURS["Armor Key"], "7cc8ff")        # light blue
        self.assertEqual(KEY_COLOURS["Lock Pick"], "ffb3d1")        # baby pink
        self.assertEqual(ONE_WAY, rgba("1e7a3c"))                   # dark green
        self.assertEqual(CANT_OPEN, rgba("e02424"))                 # red
        self.assertEqual(len(set(KEY_COLOURS.values())), len(KEY_COLOURS))

    def door_colours(self, sc):
        out = {}
        for (x, y, w, h), d in sc.door_hits:
            cols = [op[1] for op in sc.ops if op[0] == "rect" and op[2] == x + 3 and op[3] == y + 3]
            out.setdefault((d["a"], d["b"]), []).append((d, cols[-1] if cols else None))
        return out

    def test_ordinary_doors_dark_blue_and_cant_open_fully_red(self):
        from ..map_render import CANT_OPEN, ORDINARY, key_rgba
        sc = self.scene(0)
        for pairs in self.door_colours(sc).values():
            for d, col in pairs:
                if d["kind"] == "open":
                    self.assertEqual(col, ORDINARY)
                elif d["kind"] in ("key", "item") and not d["ok"]:
                    self.assertEqual(col, CANT_OPEN, (d["a"], d["b"]))
        sc = self.scene(0, received=["Book of Curses"])
        sword = [col for pairs in self.door_colours(sc).values() for d, col in pairs if d["key"] == "Book of Curses"]
        self.assertTrue(sword)
        self.assertTrue(all(c == key_rgba("Book of Curses") for c in sword))

    def test_unlocked_doors_become_ordinary(self):
        from ..data import PICKUPS
        from ..map_render import ORDINARY, build
        from ..tracker import map_state, unlock_flags
        active = {n for _r, n, _i, _q in PICKUPS}
        state = map_state([], active, set(), True)
        sword = next(d for d in state[1][0] if d["key"] == "Book of Curses")
        flags = unlock_flags()[frozenset((sword["a"], sword["b"]))]
        self.assertTrue(flags)
        state = map_state([], active, set(), True, unlocked=flags)
        now = next(d for d in state[1][0] if (d["a"], d["b"]) == (sword["a"], sword["b"]))
        self.assertEqual(now["kind"], "unlocked")
        sc = build(0, state, 1100, 640, "Main Hall", self.measure)
        col = [c for d, c in self.door_colours(sc)[(sword["a"], sword["b"])]]
        self.assertEqual(col, [ORDINARY])

    def test_dark_corridor_winding_corridor_wall_is_straight(self):
        """Seed test 6 picture: the wall jogged by a cell at the Winding Corridor door, leaving short
        stray lines. It's now one straight wall with the door on it."""
        from ..map_geometry import floor
        f = floor(0)
        xs = {x for x, y, x2, y2, _o in f.walls if x == x2 and 53 <= y < 59
              and {f.room_at(x - 0.5, y + 0.5), f.room_at(x + 0.5, y + 0.5)} == {"Dark Corridor", "Winding Corridor"}}
        self.assertEqual(len(xs), 1, xs)
        door = next(d for d in f.snapped if {d[3], d[4]} == {"Winding Corridor", "Dark Corridor"})
        self.assertEqual(door[0], xs.pop())

    def test_doors_sit_on_the_wall_between_their_rooms(self):
        """Seed test 6: doors didn't line up with the walls in places."""
        from ..map_geometry import floor
        from ..map_layout import FLOORS
        for i in range(len(FLOORS)):
            f = floor(i)
            for x, y, hz, a, b in f.snapped:
                if hz:
                    self.assertEqual(y, int(y), (f.title, a, b))
                    sides = {f.room_at(x, y - 0.5), f.room_at(x, y + 0.5)}
                else:
                    self.assertEqual(x, int(x), (f.title, a, b))
                    sides = {f.room_at(x - 0.5, y), f.room_at(x + 0.5, y)}
                self.assertIn(a, sides, (f.title, a, b, x, y))
                if b:
                    self.assertIn(b, sides, (f.title, a, b, x, y))


class JillPositionTests(unittest.TestCase):
    """v0.9.4: Jill's position (not just the game's room number) says which map room she's in."""

    def test_calibration_is_tight_on_the_mansion(self):
        from ..map_position import fit
        fl = fit()
        self.assertIn(0, fl.scale)
        self.assertIn(1, fl.scale)
        for fi in (0, 1):
            self.assertAlmostEqual(1 / fl.scale[fi], 49.5, delta=1.5)

    def test_every_door_spot_of_a_shared_room_lands_in_the_right_map_room(self):
        """Each arrival spot of a game room that is two map rooms must land in the map room whose
        door it is next to (both sides of the door between them included)."""
        from ..client.door_data import ARRIVALS
        from ..map_geometry import floor
        from ..map_position import locate, room_number
        for number in (0x103, 0x109, 0x111):
            for src, x, y, z, _ang, _cut in ARRIVALS[number]:
                if not (x or y or z):
                    continue
                where = locate(number, (x, y, z))
                f = floor(where.floor)        # the Kitchen lift spot in 0x103 is at the B1 lift bottom
                self.assertEqual(where.floor, 3 if (number, src) == (0x103, 0x21C) else 0)
                self.assertEqual(len(where.rooms), 1)
                if src != number:                       # a door from another room: that door's map room
                    doors = [d for d in f.snapped if room_number(d[3]) == number and room_number(d[4]) == src
                             or room_number(d[4]) == number and room_number(d[3]) == src]
                    sides = {d[3] if room_number(d[3]) == number else d[4] for d in doors}
                    if sides:
                        self.assertIn(where.rooms[0], sides, (hex(number), hex(src)))

    def test_tea_room_and_northern_corridor_told_apart(self):
        from ..client.door_data import ARRIVALS
        from ..map_position import locate
        spots = {src: (x, y, z) for src, x, y, z, *_ in ARRIVALS[0x103] if src != 0x103}
        self.assertEqual(locate(0x103, spots[0x105]).rooms, ["Tea Room"])          # from the Dining Room
        self.assertEqual(locate(0x103, spots[0x101]).rooms, ["Northern Corridor"])  # from the West Wing
        self.assertEqual(locate(0x103, spots[0x10e]).rooms, ["Northern Corridor"])  # from the bedroom

    def test_height_picks_the_floor(self):
        from ..client.door_data import ARRIVALS
        from ..map_position import locate
        spots = {src: (x, y, z) for src, x, y, z, *_ in ARRIVALS[0x106]}
        self.assertEqual(locate(0x106, spots[0x105]).floor, 0)     # Main Hall 1F (from the Dining Room)
        self.assertEqual(locate(0x106, spots[0x202]).floor, 1)     # Main Hall 2F (from Dining Room 2F)
        spots = {src: (x, y, z) for src, x, y, z, *_ in ARRIVALS[0x101]}
        self.assertEqual(locate(0x101, spots[0x103]).floor, 0)
        self.assertEqual(locate(0x101, spots[0x214]).floor, 1)

    def test_doorway_keeps_the_room_she_was_in(self):
        from ..map_position import fit, locate
        fl = fit()
        s = fl.scale[0]
        tx, ty = fl.offset[(0, 0x103)]
        # just past the Tea Room / Northern Corridor door (map y 72.5) on the Tea Room side
        x, z = (39.0 - tx) / s, (72.9 - ty) / s
        self.assertEqual(locate(0x103, (x, 400, z), previous="Northern Corridor").rooms, ["Northern Corridor"])
        x, z = (39.0 - tx) / s, (75.0 - ty) / s
        self.assertEqual(locate(0x103, (x, 400, z), previous="Northern Corridor").rooms, ["Tea Room"])

    def test_without_a_position_every_map_room_of_the_number_glows(self):
        from ..map_position import locate
        self.assertEqual(sorted(locate(0x103).rooms), ["Northern Corridor", "Tea Room"])
        self.assertIsNone(locate(None))

    def test_map_only_rooms_have_numbers(self):
        from ..map_position import locate
        self.assertEqual(locate(0x11C).rooms, ["Hidden Wardrobe"])

    def test_render_uses_the_located_room(self):
        from ..data import PICKUPS
        from ..map_render import build
        from ..tracker import map_state
        state = map_state([], {n for _r, n, _i, _q in PICKUPS}, set(), True)
        sc = build(0, state, 1100, 640, "Northern Corridor", KeyMapDrawingTests.measure, here=["Tea Room"])
        self.assertEqual(sc.here, ["Tea Room"])

    def test_item_doors_not_in_the_map_key(self):
        from ..data import PICKUPS
        from ..map_render import build
        from ..tracker import map_state
        state = map_state([], {n for _r, n, _i, _q in PICKUPS}, set(), True)
        for fi in range(4):
            sc = build(fi, state, 1100, 640, "Main Hall", KeyMapDrawingTests.measure)
            texts = [op[2] for op in sc.ops if op[0] == "text"]
            self.assertFalse(any("item" in t.lower() for t in texts), texts)
            self.assertNotIn("Graveyard - Crypt", texts)
            self.assertNotIn("item", [lid for _b, lid in sc.legend_hits])


class TestSpotEventsInTracker(unittest.TestCase):
    """Seed test 5: Barry's East Wing Storeroom items only show once the Armor Key spot is used."""
    def test_barry_items_wait_for_the_armor_key_check(self):
        from ..logic_tracker import in_logic
        from ..data import PICKUPS
        barry = "East Wing Storeroom - Incendiary Shells (Barry)"
        armor = "'Death' Passage - Armor Key"
        active = {n for _, n, _, _ in PICKUPS}
        names = ["Book of Curses", "Collar", "Helmet Key", "Armor Key", "Shield Key"]
        self.assertNotIn(barry, in_logic(names, active, set()))
        self.assertIn(barry, in_logic(names, active, {armor}))

    def test_boulder_passage_needs_the_hexagonal_crank(self):
        from collections import Counter
        from ..logic_tracker import reachable_rooms
        from ..items import item_table
        have = Counter(n for n, d in item_table.items() if n != "Hexagonal Crank")
        rooms = reachable_rooms(have, True, True)
        self.assertIn("Mining Area", rooms)
        for room in ("Boulder Passage 1", "Spider Room", "Straight Passage", "Boulder Passage 2",
                     "Underground Statue Room"):
            self.assertNotIn(room, rooms)
        have["Hexagonal Crank"] = 1
        self.assertIn("Underground Statue Room", reachable_rooms(have, True, True))


class TestMissable(RE1HDTestBase):
    """TessarionAM (2026-11-12): missable checks always give junk; their item is in the pool."""
    def test_barrys_magnum_check_gives_junk_and_the_gun_is_in_the_pool(self):
        from .. import FILLER_ITEMS
        loc = self.multiworld.get_location("Jessica's Tomb - Barry's Magnum", self.player)
        self.assertIn(loc.item.name, FILLER_ITEMS)
        self.assertTrue(loc.locked)
        pool = [i.name for i in self.multiworld.itempool if i.player == self.player]
        self.assertIn("Barry's Magnum", pool)
        self.assertIn("Assault Shotgun", pool)

    def test_master_key_acid_and_greenhouse_herbs_are_missable(self):
        from .. import FILLER_ITEMS
        for name in ("Main Laboratory - Master Key", "Greenhouse - Green Herb 1"):
            loc = self.multiworld.get_location(name, self.player)
            self.assertTrue(loc.locked and loc.item.name in FILLER_ITEMS, name)
        pool = [i.name for i in self.multiworld.itempool if i.player == self.player]
        self.assertIn("Master Key", pool)

    def test_magnum_needs_all_three_crests(self):
        from ..data import PICKUPS
        req = {n: r for _, n, _, r in PICKUPS}["Small Headstone Area - Magnum"]
        self.assertTrue({"Moon Crest", "Star Crest", "Sun Crest"} <= set(req))
