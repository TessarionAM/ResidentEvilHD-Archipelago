"""
Archipelago world for Resident Evil HD Remaster (Steam), Jill, Normal.

The whole game (Mansion, Courtyard, Residence, Caves, Altar, Laboratory).
Goal: complete the game (default) or just escape the mansion.
Data: Evil Resource; item IDs: BhdTool. See THIRD_PARTY.md for credits.
Licence: GPL-3.0.
"""

import logging
from collections import Counter
from typing import Any, Dict, Iterable

from BaseClasses import Item, ItemClassification, Region, Tutorial
from worlds.AutoWorld import WebWorld, World
from worlds.LauncherComponents import Component, Type, components, launch as launch_component

from .data import BOSSES, BOSS_RUSH_ITEM, BOSS_RUSH_LOCATION, BOX_ROOMS, DIRECT_ITEMS, DOORS, EITHER_ROOM, EVENTS, EVENT_NAMES, KEEP_VANILLA, MISSABLE, MISSABLE_POOL_ITEMS, FINAL_REQUIRES, FINAL_ROOM, GOAL_ROOM, ROOMS, START
from .data import GATE_SIDE_STARTS, START_ROOM_MISSABLE, START_ROOMS_ALL, START_ROOMS_MANSION
from .data import FLAMETHROWER_LOCATIONS
from .game_data import DELIVERY_QUANTITY, DETECTED_PICKUPS, ROOM_NUMBERS, START_BOX_RIBBONS
from .items import RE1HDItem, item_name_groups, item_table
from .locations import BOSS_RUSH_LOCATION_ID, RE1HDLocation, all_location_ids, extra_location_table, location_name_groups, location_table
from .options import NOT_YET_IMPLEMENTED, OPTION_GROUPS, RE1HDOptions
from . import door_locks, door_shuffle

WORLD_VERSION = "0.9.33"
LOCK_REROLLS = 12         # door randomiser: lock layouts tried before giving up
# random_start_room: a start needs at least this many locations reachable with nothing (sphere 0).
# 2026-11-15: a door-randomiser seed starting in the East Wing Storeroom had 1 and Archipelago's
# fill failed although our simulated fill had passed (it fails 3 times in 20 there); the plain
# doors' smallest working start, the Mining Area, has 5. Also the start check runs 3 simulated fills.
# 0.9.32: raised from 4 to 5 - with Barry's lift now one-way, two door-randomiser seeds in 60 with
# exactly 4 failed Archipelago's fill (our simulated fill passed them 38-39 times in 40).
MIN_START_LOCATIONS = 5
START_CHECK_RUNS = 3
# 2026-11-15: 1 seed in 60 (door randomiser coupled) found no start room on the first pass; the
# rooms are tried again with new door layouts before giving up.
START_ROUNDS = 3
VICTORY_LOCATION = "Escape the Mansion"
FINAL_VICTORY_LOCATION = "Escape on the Helicopter"
# Random starting inventory choices (2026-11-10): weapons and supplies that fit in a slot.
START_GUNS = ("Handgun", "Shotgun", "Grenade Launcher", "Magnum")
START_ITEM_CHOICES = ("Handgun", "Combat Knife", "Shotgun", "Grenade Launcher", "Magnum",
                      "First Aid Spray", "Green Herb", "Blue Herb", "Handgun Magazine", "Shotgun Shells")
# Junk weights (TessarionAM, 2026-11-11: e.g. handgun ammo more common than magnum ammo).
FILLER_WEIGHTS = {"Handgun Magazine": 25, "Green Herb": 20, "Shotgun Shells": 14, "Red Herb": 8,
                  "Blue Herb": 8, "First Aid Spray": 6, "Grenade Shells": 6, "Acid Shells": 4,
                  "Incendiary Shells": 4, "Magnum Rounds": 5}
FILLER_ITEMS = ("Green Herb", "Red Herb", "Blue Herb", "First Aid Spray", "Handgun Magazine",
                "Shotgun Shells", "Magnum Rounds", "Grenade Shells", "Acid Shells", "Incendiary Shells")
VICTORY_ITEM = "Victory"

log = logging.getLogger("RE1HD")


def launch_client(*args: str):
    from .client.RE1HDClient import launch
    launch_component(launch, name="RE1HDClient", args=args)


components.append(Component("Resident Evil HD Remaster Client", func=launch_client,
                            component_type=Type.CLIENT, description="Connects RE HD Remaster to Archipelago."))


BOX_ACCESS = "Item Box Access"        # event: you have reached an item box
# Items the client hands to Jill directly, not via the item box: the Lock Pick (her hidden
# slot) and the Book of Curses (inventory - every item box needs the Sword Key to reach).
# Starting items also go straight to the inventory.
# DIRECT_ITEMS (data.py) mirrors game_data.DIRECT_INVENTORY_ITEMS + the Lock Pick.


def _rule(requires: Iterable[str], player: int, box_gate: bool = False, direct=DIRECT_ITEMS):
    """Turn a list of required item names into an access rule (None = always open).
    box_gate: received items wait in the item box, so any requirement on an item that isn't
    handed over directly also needs an item box to have been reached."""
    requires = tuple(requires)
    if not requires:
        return None
    if box_gate and any(r not in direct and r not in EVENT_NAMES for r in requires):
        requires = requires + (BOX_ACCESS,)
    return lambda state: state.has_all(requires, player)


class RE1HDWeb(WebWorld):
    theme = "stone"
    option_groups = OPTION_GROUPS
    tutorials = [Tutorial(
        "Multiworld Setup Guide",
        "How to set up Resident Evil HD Remaster for Archipelago.",
        "English", "setup_en.md", "setup/en", ["TessarionAM"],
    )]


class RE1HDWorld(World):
    """
    Resident Evil HD Remaster: survive the Spencer Mansion as Jill Valentine.
    Every item pickup is shuffled into the multiworld.
    """
    game = "Resident Evil HD Remaster"
    web = RE1HDWeb()
    options_dataclass = RE1HDOptions
    options: RE1HDOptions
    topology_present = True

    item_name_to_id = {name: data.code for name, data in item_table.items()}
    location_name_to_id = dict(all_location_ids)
    item_name_groups = item_name_groups
    location_name_groups = location_name_groups

    def generate_early(self) -> None:
        self.extra_checks_made = 0
        # Starting item box (TessarionAM, 2026-11-11): the First Aid Spray becomes a random item, the
        # 3 Ink Ribbons become 99 - or another random item when autosave is on.
        spray = self.get_filler_item_name()
        ribbon = self.get_filler_item_name() if self.options.autosave.value else None
        as_box = lambda name: [item_table[name].game_id, DELIVERY_QUANTITY.get(item_table[name].game_id, 1)]
        self.start_box = [as_box(spray), as_box(ribbon) if ribbon else [68, START_BOX_RIBBONS]]
        # Boss Rush (2026-11-14) locks the Signal Rockets, so it only means something with the
        # helicopter ending.
        self.boss_rush = bool(self.options.boss_rush.value)
        if self.boss_rush and self.options.goal.value != self.options.goal.option_complete_game:
            log.warning("%s (%s): boss_rush needs goal complete_game - ignored.", self.player_name, self.game)
            self.boss_rush = False
        self.door_layout = {}
        self.door_shuffle = {}
        self._pick_start_room()
        for name in NOT_YET_IMPLEMENTED:
            if getattr(self.options, name).value:
                log.warning("%s (%s): option '%s' isn't implemented yet and will be ignored.",
                            self.player_name, self.game, name)

    def _pick_start_room(self) -> None:
        """random_start_room (2026-11-15): try the allowed save rooms in a random order; a room is
        used only if the doors (and the lock / door randomisers, built for that start) pass the
        same simulated fill and softlock checks as the door randomiser. Off: the Main Hall."""
        from Options import OptionError
        mode = self.options.random_start_room.value
        self.start_room = START
        self.missable = dict(MISSABLE)
        if not mode:
            self._make_doors()
            return
        self.missable.update({name: "Lock Pick" for name in START_ROOM_MISSABLE})
        rooms = list(START_ROOMS_MANSION if mode == self.options.random_start_room.option_mansion_save_rooms
                     else START_ROOMS_ALL)
        problems = []
        for _round in range(START_ROUNDS):       # each round: fresh door layouts for every room
            self.random.shuffle(rooms)
            problems = []
            for room in rooms:
                self.start_room = room
                self.door_layout, self.door_shuffle = {}, {}
                try:
                    self._make_doors()
                except OptionError as exc:
                    problems.append(f"{room}: {exc}")
                    continue
                reason = self._check_start()
                if reason is None:
                    return
                problems.append(f"{room}: {reason}")
        raise OptionError(f"{self.player_name} ({self.game}): random_start_room: no start room works with "
                          f"these options ({'; '.join(problems)})")

    def _validation_inputs(self):
        items, locs = door_locks.simple_progression()
        locs = [loc for loc in locs if loc[0] not in self.missable]
        goal = self.options.goal.value == self.options.goal.option_complete_game
        box_gate = (self.options.received_item_destination.value
                    == self.options.received_item_destination.option_item_box)
        everything = self.options.accessibility.value != self.options.accessibility.option_minimal
        return items, locs, goal, box_gate, everything

    def _check_start(self):
        """The finished doors, measured from self.start_room, with the same check each door mode
        uses from the Main Hall: the door randomiser's (assumed fill + softlock), the lock
        randomiser's (assumed fill), and for the plain doors the full one (assumed fill + softlock -
        it's what rules out e.g. the Mansion Drug Room, left behind a one-way door)."""
        import random as _random
        items, locs, goal, box_gate, everything = self._validation_inputs()
        base = door_locks.effective_doors(self.door_layout)
        doors = door_shuffle.connections(self.door_shuffle, base)
        n = door_locks.start_locations(doors, locs, box_gate, self.start_room)
        if n < MIN_START_LOCATIONS:
            return f"only {n} checks reachable at the start"
        for _ in range(START_CHECK_RUNS):
            sim = _random.Random(self.random.getrandbits(64))
            if self.door_layout and not self.door_shuffle:
                reason = door_locks.check_layout(self.door_layout, items, locs, goal, box_gate, sim,
                                                 everything=everything, origin=self.start_room)
            else:
                reason = door_shuffle.check(self.door_shuffle, base, items, locs, goal, box_gate, sim,
                                            everything=everything, origin=self.start_room)
            if reason:
                return reason
        return None

    def _make_doors(self) -> None:
        """Door locks, then where the doors lead (door randomiser, 2026-11-12). Both are checked
        with a simulated fill before they're accepted; if no door layout fits a lock layout, the
        locks are rolled again (up to LOCK_REROLLS times)."""
        import random as _random
        from Options import OptionError
        items, locs, goal, box_gate, everything = self._validation_inputs()
        origin = self.start_room
        sim = _random.Random(self.random.getrandbits(64))
        self._start_ok = lambda doors: (origin == START or door_locks.start_locations(
            doors, locs, box_gate, origin) >= MIN_START_LOCATIONS)
        shuffle_mode = self.options.door_randomisation.value
        last = None
        for _ in range(LOCK_REROLLS if shuffle_mode else 1):
            self._make_locks(items, locs, goal, box_gate, everything, sim)
            if not shuffle_mode:
                return
            base = door_locks.effective_doors(self.door_layout)
            try:
                self.door_shuffle = door_shuffle.make_layout(
                    shuffle_mode, self.random, base_doors=base, origin=origin,
                    validate=lambda lay: (
                        None if self._start_ok(door_shuffle.connections(lay, base)) else "too few checks at the start")
                    or door_shuffle.check(lay, base, items, locs, goal, box_gate, sim,
                                          everything=everything, origin=origin))
                return
            except door_shuffle.ShuffleError as exc:
                last = exc
        raise OptionError(f"{self.player_name} ({self.game}): door_randomisation: {last}")

    def _make_locks(self, items, locs, goal, box_gate, everything, sim) -> None:
        mode = self.options.door_lock_randomisation.value
        if mode:
            # Door lock randomiser (2026-11-12): build the layout now (regions need it) and check
            # it with a simulated fill before accepting it (door_locks.check_layout).
            from Options import OptionError
            try:
                count = door_locks.resolve_count(mode, self.options.locked_door_count.value)
                origin = self.start_room
                # the same check as from the Main Hall, measured from the start room
                validate = lambda lay: (
                    None if self._start_ok(door_locks.effective_doors(lay)) else "too few checks at the start"
                ) or door_locks.check_layout(lay, items, locs, goal, box_gate, sim, everything=everything,
                                             origin=origin)
                self.door_layout = door_locks.make_layout(mode, count, self.random, validate=validate,
                                                          origin=origin)
            except door_locks.LayoutError as exc:
                raise OptionError(f"{self.player_name} ({self.game}): {exc}") from exc

    def _rule(self, requires):
        box_gate = self.options.received_item_destination.value == self.options.received_item_destination.option_item_box
        return _rule(requires, self.player, box_gate, DIRECT_ITEMS)

    def create_regions(self) -> None:
        menu = Region("Menu", self.player, self.multiworld)
        regions = {name: Region(name, self.player, self.multiworld) for name in ROOMS}
        self.multiworld.regions += [menu, *regions.values()]

        menu.connect(regions[self.start_room], "New Game")

        names = Counter()
        def name(a, b):
            names[(a, b)] += 1
            n = names[(a, b)]
            return f"{a} -> {b}" + (f" ({n})" if n > 1 else "")
        doors = door_shuffle.connections(self.door_shuffle, door_locks.effective_doors(self.door_layout))
        doors = door_locks.with_start(doors, self.start_room)
        for a, b, requires, one_way in doors:
            rule = self._rule(requires)
            regions[a].connect(regions[b], name(a, b), rule)
            if not one_way:
                regions[b].connect(regions[a], name(b, a), rule)

        for name, data in location_table.items():
            region = regions[data.room]
            if self.is_check(name) and name in self.missable:
                # missable: a real check (sent when it happens) that always gives junk
                loc = RE1HDLocation(self.player, name, data.code, region)
                loc.place_locked_item(self.create_item(self.get_filler_item_name()))
            elif self.is_check(name):
                loc = RE1HDLocation(self.player, name, data.code, region)
            else:
                # Not detectable by the client yet: stays vanilla. An event location
                # holding its normal item, so logic knows the player will have it.
                loc = RE1HDLocation(self.player, name, None, region)
                v = item_table[data.vanilla_item]
                loc.place_locked_item(RE1HDItem(data.vanilla_item, v.kind, None, self.player))
            rule = self._rule(data.requires)
            if rule:
                loc.access_rule = rule
            region.locations.append(loc)

        # Extra checks (maps, ...): no vanilla item for logic, so if one isn't a check
        # in this seed it simply isn't created.
        for name, data in extra_location_table.items():
            if not self.extra_is_check(name, data.category):
                continue
            rule = self._rule(data.requires)
            if name in EITHER_ROOM:
                # reachable from any one of several rooms: hang it off Menu and ask for any of them
                region = menu
                rooms, player, base = EITHER_ROOM[name], self.player, rule
                rule = lambda state, rooms=rooms, player=player, base=base: (
                    any(state.can_reach_region(r, player) for r in rooms) and (base is None or base(state)))
            else:
                region = regions[data.room]
            loc = RE1HDLocation(self.player, name, data.code, region)
            if rule:
                loc.access_rule = rule
            region.locations.append(loc)
            self.extra_checks_made += 1

        # World events (e.g. the Armor Key spot has been used).
        for room, name, requires in EVENTS:
            ev = RE1HDLocation(self.player, name, None, regions[room])
            ev.place_locked_item(Item(name, ItemClassification.progression, None, self.player))
            rule = self._rule(requires)
            if rule:
                ev.access_rule = rule
            regions[room].locations.append(ev)

        # Boss Rush: one event per boss, and the check the client sends once all seven are dead.
        # It holds this world's Signal Rockets (locked), so they can only come from the bosses.
        if self.boss_rush:
            for name, room, _bit, requires in BOSSES:
                ev = RE1HDLocation(self.player, name, None, regions[room])
                ev.place_locked_item(Item(name, ItemClassification.progression, None, self.player))
                rule = self._rule(requires)
                if rule:
                    ev.access_rule = rule
                regions[room].locations.append(ev)
            loc = RE1HDLocation(self.player, BOSS_RUSH_LOCATION, BOSS_RUSH_LOCATION_ID, menu)
            names, player = [b[0] for b in BOSSES], self.player
            loc.access_rule = lambda state, names=names, player=player: state.has_all(names, player)
            loc.place_locked_item(self.create_item(BOSS_RUSH_ITEM))
            menu.locations.append(loc)

        # Reaching any item box gives "Item Box Access" (received items are waiting there).
        for room in BOX_ROOMS:
            box = RE1HDLocation(self.player, f"{room} - Item Box", None, regions[room])
            box.place_locked_item(Item(BOX_ACCESS, ItemClassification.progression, None, self.player))
            regions[room].locations.append(box)

        if self.options.goal.value == self.options.goal.option_complete_game:
            goal = regions[FINAL_ROOM]
            victory = RE1HDLocation(self.player, FINAL_VICTORY_LOCATION, None, goal)
            victory.access_rule = self._rule(FINAL_REQUIRES)
        else:
            goal = regions[GOAL_ROOM]
            victory = RE1HDLocation(self.player, VICTORY_LOCATION, None, goal)
        victory.place_locked_item(Item(VICTORY_ITEM, ItemClassification.progression, None, self.player))
        goal.locations.append(victory)

    def create_item(self, name: str) -> RE1HDItem:
        data = item_table[name]
        return RE1HDItem(name, data.kind, data.code, self.player)

    def is_check(self, location_name: str) -> bool:
        if location_name in KEEP_VANILLA:
            return False
        return not self.options.only_detected_pickups.value or location_name in DETECTED_PICKUPS

    def extra_is_check(self, location_name: str, category: str) -> bool:
        if category == "room":
            # The client knows the current room, so room entries never need mapping.
            # With goal mansion_escape the Garden Shed is the goal itself, not a check.
            if (location_name == f"{GOAL_ROOM} - First Visit"
                    and self.options.goal.value == self.options.goal.option_mansion_escape):
                return False
            return bool(self.options.first_room_entries.value)
        enabled = {"map": self.options.map_checks.value,
                   "file": self.options.files_and_notes.value}.get(category, False)
        return bool(enabled) and self.is_check(location_name)

    def create_items(self) -> None:
        # The pool is exactly the vanilla contents of every location that is a check, plus one
        # junk item for every extra check (maps, room entries: they have no vanilla item).
        pool = [self.create_item(d.vanilla_item) for name, d in location_table.items() if self.is_check(name)]
        pool += [self.create_item(self.get_filler_item_name()) for _ in range(self.extra_checks_made)]

        def swap_junk(new_name: str) -> bool:
            """Replace one junk item with new_name. False if there's no junk left (never
            replaces a key or weapon, so a seed can't become unbeatable)."""
            junk = [i for i, it in enumerate(pool) if it.name in FILLER_ITEMS]
            if not junk:
                return False
            pool[self.random.choice(junk)] = self.create_item(new_name)
            return True

        # Missable checks (2026-11-12): the location holds locked junk (create_regions), its real
        # item stays in the pool - so one junk item leaves the pool to keep the counts equal.
        for name in self.missable:
            if name in location_table and self.is_check(name):
                for i, item in enumerate(pool):
                    if item.name in FILLER_ITEMS:
                        del pool[i]
                        break
        for name in MISSABLE_POOL_ITEMS:
            swap_junk(name)
        # The Broken Flamethrower goes below Barry's cave lift, before Lisa's door (data.DOORS):
        # the lift doesn't go back up, so it must be found down there (TessarionAM, 2026-11-15).
        spots = [n for n in FLAMETHROWER_LOCATIONS if self.is_check(n) and n not in self.missable]
        flame = next((i for i, it in enumerate(pool) if it.name == "Broken Flamethrower"), None)
        if flame is not None and spots:
            del pool[flame]
            spot = self.multiworld.get_location(self.random.choice(spots), self.player)
            spot.place_locked_item(self.create_item("Broken Flamethrower"))
        if self.boss_rush:
            # the Signal Rockets are on the Boss Rush check (create_regions): the Heliport's own
            # pickup gets a junk item in their place
            for i, item in enumerate(pool):
                if item.name == BOSS_RUSH_ITEM:
                    pool[i] = self.create_item(self.get_filler_item_name())
                    break

        if self.options.start_with_sword_key.value:
            self.multiworld.push_precollected(self.create_item("Book of Curses"))
            for i, item in enumerate(pool):
                if item.name == "Book of Curses":
                    pool[i] = self.create_item(self.get_filler_item_name())
                    break
        if self.options.random_starting_inventory.value:
            # Jill's Handgun and Combat Knife go into the pool (replacing junk) and she starts
            # with two random items instead. With no junk to replace she simply keeps the weapon.
            for weapon in ("Handgun", "Combat Knife"):
                if not swap_junk(weapon):
                    self.multiworld.push_precollected(self.create_item(weapon))
            if self.options.random_start_guaranteed_gun.value:
                # Seed test 3 started with a First Aid Spray + Handgun Magazine: nothing to fight with.
                first = self.random.choice(START_GUNS)
                second = self.random.choice([c for c in START_ITEM_CHOICES if c != first])
                picks = [first, second]
            else:
                picks = self.random.sample(START_ITEM_CHOICES, 2)
            for name in picks:
                self.multiworld.push_precollected(self.create_item(name))
        # Traps replace a share of the junk (after everything else, so they count all junk).
        traps = self.options.trap_percentage.value
        o = self.options
        weights = {"Damage Trap": o.damage_trap_weight.value,
                   "Poison Trap": o.poison_trap_weight.value,
                   "Critical Damage Trap": o.critical_damage_trap_weight.value,
                   "Ammo Leak Trap": o.ammo_leak_trap_weight.value}
        self._replace_junk(pool, traps, weights)
        # Fun traps (2026-11-12): their own small share; the Fake Crash at most once per seed.
        self._replace_junk(pool, o.fun_trap_percentage.value,
                           {"Fake Crash Trap": o.fake_crash_trap_weight.value,
                            "To Be Continued Trap": o.to_be_continued_trap_weight.value,
                            "Fake Item Trap": o.fake_item_trap_weight.value,
                            "Fake Death Link Trap": o.fake_death_link_trap_weight.value,
                            "Window Shake Trap": o.window_shake_trap_weight.value,
                            "Self-Destruct Trap": o.self_destruct_trap_weight.value,
                            "Danger Flash Trap": o.danger_flash_trap_weight.value,
                            "Wrong Door Trap": o.wrong_door_trap_weight.value},
                           limits={"Fake Crash Trap": 1})
        # Special items (2026-11-12) take a share of the junk that's left after the traps.
        self._replace_junk(pool, o.special_item_percentage.value,
                           {"Infinite Ammo (20s)": o.infinite_ammo_weight.value,
                            "Defence Bundle": o.defence_bundle_weight.value})
        self.multiworld.itempool += pool

    def _replace_junk(self, pool, percent: int, weights: Dict[str, int],
                      limits: Dict[str, int] = None) -> None:
        """Replace percent % of the junk in pool with items picked by weight. limits: most copies
        of a name per seed (once reached, it isn't picked again)."""
        weights = dict(weights)
        if not percent or not sum(weights.values()):
            return
        junk = [i for i, it in enumerate(pool) if it.name in FILLER_ITEMS]
        used: Dict[str, int] = {}
        for i in self.random.sample(junk, len(junk) * percent // 100):
            names = [n for n in weights if weights[n] > 0]
            if not names:
                break
            name = self.random.choices(names, [weights[n] for n in names])[0]
            pool[i] = self.create_item(name)
            used[name] = used.get(name, 0) + 1
            if limits and used[name] >= limits.get(name, 1 << 30):
                weights[name] = 0

    def write_spoiler_header(self, spoiler_handle) -> None:
        if self.options.random_start_room.value:
            spoiler_handle.write(f"Start Room ({self.player_name}): {self.start_room}\n")

    def set_rules(self) -> None:
        self.multiworld.completion_condition[self.player] = lambda state: state.has(VICTORY_ITEM, self.player)

    def get_filler_item_name(self) -> str:
        # TessarionAM's list (2026-11-10), weighted (2026-11-11): healing and ammo.
        names = list(FILLER_WEIGHTS)
        return self.random.choices(names, weights=[FILLER_WEIGHTS[n] for n in names])[0]

    def fill_slot_data(self) -> Dict[str, Any]:
        return {
            "world_version": WORLD_VERSION,
            **self.options.as_dict("character", "difficulty", "goal", "item_pickups",
                                   "only_detected_pickups", "map_checks", "first_room_entries",
                                   "received_item_destination", "start_with_sword_key",
                                   "random_starting_inventory",
                                   "damage_trap_amount", "damage_trap_can_kill", "death_link",
                                   "death_link_effect", "door_skip", "autosave", "autosave_slot", "autoload_after_death", "item_box_auto_sort", "key_map_shortcuts", "item_box_anywhere", "item_box_button", "game_resolution",
                                   "borderless_fullscreen"),
            "start_box": self.start_box,
            "door_lock_randomisation": self.options.door_lock_randomisation.value,
            "door_locks": self.door_layout,
            "key_uses": door_locks.key_uses(self.door_layout),
            "door_randomisation": self.options.door_randomisation.value,
            "door_shuffle": self.door_shuffle,
            "boss_rush": int(self.boss_rush),
            # random_start_room: 0 = start in the Main Hall as usual, else stage*0x100 + room
            "start_room": ROOM_NUMBERS[self.start_room] if self.start_room != START else 0,
            "start_room_name": self.start_room,
            # beyond the Stone & Metal gate: the client keeps the gate open from the start
            # (data.GATE_SIDE_STARTS)
            "gate_open": int(self.start_room in GATE_SIDE_STARTS),
        }
