"""
Offline tests for the client's game bridge (Milestone 8), using a fake game memory.
No game, no server needed.
"""

import struct
import time
import tempfile
import unittest
from pathlib import Path

from ..client import hd_versions as hv
from ..client.game_bridge import EFFECT_ITEMS, GameBridge, Incoming, StateFile, delivery_tag
from ..client.hd_delivery import Journal
from ..game_data import DEFENCE_BUNDLE, DETECTED_PICKUPS, EQUIPPED_SLOT_OFFSET, SEED_TAG_SLOT

INV_PTR, FLAGS_PTR = 0x1000, 0x1200
INV, FLAGS = 0x10000, 0x40000


class FakeGame:
    def __init__(self):
        self.mem = bytearray(0x80000)
        self.put32(INV_PTR, INV)
        self.put32(FLAGS_PTR, FLAGS)
        self.writes = 0

    def put32(self, a, v):
        struct.pack_into("<I", self.mem, a, v)

    def read_bytes(self, a, n):
        return bytes(self.mem[a:a + n])

    def write_bytes(self, a, data):
        self.mem[a:a + len(data)] = data
        self.writes += 1

    # helpers
    def slot(self, i):
        return struct.unpack_from("<ii", self.mem, INV + hv.INVENTORY_SLOTS_OFFSET + i * 8)

    def set_slot(self, i, iid, qty):
        struct.pack_into("<ii", self.mem, INV + hv.INVENTORY_SLOTS_OFFSET + i * 8, iid, qty)

    def box(self, i):
        return struct.unpack_from("<ii", self.mem, INV + hv.ITEM_BOX_OFFSET + i * 8)

    def set_box(self, i, iid, qty):
        struct.pack_into("<ii", self.mem, INV + hv.ITEM_BOX_OFFSET + i * 8, iid, qty)

    def flag(self, name, on=True):
        off, bit, _ = DETECTED_PICKUPS[name]
        if on:
            self.mem[FLAGS + off] |= 1 << bit
        else:
            self.mem[FLAGS + off] &= ~(1 << bit) & 0xFF


class BridgeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.game = FakeGame()
        self.game.set_slot(0, 3, 15)        # Handgun
        self.game.set_slot(1, 1, 1)         # Knife
        self.put_jill()                     # in the game (not the title screen) unless a test says so

    def put_jill(self, hp=960):
        """Fake Jill (verified character-manager path): manager at 0x3000, Jill at 0x4000."""
        mem = self.game.mem
        struct.pack_into("<I", mem, FLAGS_PTR - hv.CHARACTER_MANAGER_BEFORE_FLAGS, 0x3000)
        struct.pack_into("<II", mem, 0x3000 + 0x20, 7, 1 << 16)
        struct.pack_into("<II", mem, 0x3000 + 0x8B0 + 24, 0x4000, 7)
        struct.pack_into("<i", mem, 0x4000 + hv.JILL_HEALTH_OFFSET, hp)
        struct.pack_into("<i", mem, 0x4000 + hv.JILL_MAX_HEALTH_OFFSET, 960)

    def no_jill(self):
        """Title screen / loading: no character object."""
        struct.pack_into("<I", self.game.mem, FLAGS_PTR - hv.CHARACTER_MANAGER_BEFORE_FLAGS, 0)

    def tearDown(self):
        self.tmp.cleanup()

    def bridge(self):
        d = Path(self.tmp.name)
        return GameBridge(StateFile(d / "state.json"), Journal(d / "journal.jsonl"),
                          connect=lambda: (self.game, INV_PTR, FLAGS_PTR))


def items(*pairs):
    return [Incoming(i, gid, label) for i, (gid, label) in enumerate(pairs)]


class DeliveryTests(BridgeTest):
    def test_one_item_per_tick_into_first_empty_slots(self):
        self.game.set_box(0, 33, 1)                 # First Aid Spray already in slot 1
        b = self.bridge()
        rec = items((21, "Golden Arrow from Friend"), (17, "Handgun Magazine from Friend"))
        b.tick(rec)
        b.tick(rec)
        b.tick(rec)                                  # nothing left - no extra writes
        self.assertEqual(self.game.box(1), (21, 1))
        self.assertEqual(self.game.box(2), (17, 15))  # magazine = 15 rounds
        self.assertEqual(b.state.delivered, 2)

    def test_restart_never_delivers_twice(self):
        rec = items((34, "Green Herb from Friend"))
        self.bridge().tick(rec)
        writes = self.game.writes
        b2 = self.bridge()                           # client restarted
        b2.tick(rec)
        b2.tick(rec)
        self.assertEqual(self.game.writes, writes)
        self.assertEqual(self.game.box(1), (0, 0))

    def test_lock_pick_goes_to_hidden_slot(self):
        b = self.bridge()
        b.tick(items((43, "Lock Pick from Friend")))
        self.assertEqual(self.game.slot(8), (43, 0))      # hidden slot 1 right after the 8 slots
        self.assertEqual(self.game.box(0), (0, 0))

    def test_crash_after_write_is_not_redelivered(self):
        rec = items((34, "Green Herb from Friend"), (34, "Green Herb from Friend"))
        b = self.bridge()
        b.tick(rec)                                      # herb #0 delivered into box slot 1
        # simulate: herb #1 written into slot 2, then the client died before saving
        b.state.pending = {"index": 1, "address": None, "game_id": 34, "qty": 1, "tag": delivery_tag(rec[1])}
        b.state_file.save(b.state)
        b.journal.write(event="intent", item_id=34, quantity=1, slot_number=2,
                        address=INV + hv.ITEM_BOX_OFFSET + 8, reason=delivery_tag(rec[1]))
        self.game.set_box(1, 34, 1)
        b2 = self.bridge()
        b2.tick(rec)
        b2.tick(rec)
        self.assertEqual(b2.state.delivered, 2)
        self.assertEqual(self.game.box(2), (0, 0))       # no third herb

    def test_crash_before_write_is_redelivered(self):
        rec = items((34, "Green Herb from Friend"))
        b = self.bridge()
        b.state.pending = {"index": 0, "address": None, "game_id": 34, "qty": 1, "tag": delivery_tag(rec[0])}
        b.state_file.save(b.state)
        b2 = self.bridge()
        b2.tick(rec)
        b2.tick(rec)
        self.assertEqual(self.game.box(0), (34, 1))
        self.assertEqual(b2.state.delivered, 1)

    def test_full_box_keeps_item_waiting(self):
        for i in range(hv.ITEM_BOX_SLOTS):
            self.game.set_box(i, 34, 1)
        b = self.bridge()
        b.tick(items((21, "Golden Arrow from Friend")))
        self.assertEqual(b.state.delivered, 0)          # not lost: still owed

    def test_item_without_game_id_is_recorded_not_silently_dropped(self):
        b = self.bridge()
        b.tick(items((None, "Missing Music from Friend")))
        self.assertEqual(b.state.undeliverable[0]["label"], "Missing Music from Friend")

    def test_redeliver_after_loading_older_save(self):
        rec = items((21, "Golden Arrow from Friend"))
        b = self.bridge()
        b.tick(rec)
        self.game.set_box(0, 0, 0)                       # older save loaded: box lost it
        b.redeliver_from(0)
        b.tick(rec)
        self.assertEqual(self.game.box(0), (21, 1))

    def test_title_screen_does_nothing(self):
        self.game.put32(INV_PTR, 0)
        b = self.bridge()
        self.assertIsNone(b.tick(items((21, "x"))))
        self.assertEqual(b.state.delivered, 0)

    def test_main_menu_with_memory_but_no_jill_delivers_nothing(self):
        """Seed test 3: at the main menu the game's memory exists but isn't your game."""
        self.no_jill()
        b = self.bridge()
        self.assertIsNone(b.tick([Incoming(0, 18, "Shotgun Shells from Archipelago", starting=True)]))
        self.assertEqual(b.state.delivered, 0)
        self.assertEqual(self.game.writes, 0)

    def test_new_game_forgets_an_old_record_and_resends_everything(self):
        """Seed test 3: New Game left the old record {0,2} in box slot 256; starting items were lost."""
        struct.pack_into("<ii", self.game.mem, FLAGS + hv.CURRENT_ROOM_OFFSET, 1, 6)   # Main Hall
        self.game.set_box(0, 33, 1)
        self.game.set_box(1, 68, 3)
        self.game.set_box(255, 0, 2)                         # stale record
        b = self.bridge()
        b.state.delivered = 2
        rec = [Incoming(0, 18, "Shotgun Shells from Archipelago", starting=True),
               Incoming(1, 33, "First Aid Spray from Archipelago", starting=True)]
        b.tick(rec)
        b.tick(rec)
        self.assertEqual(b.state.delivered, 2)
        self.assertIn((18, 6), [self.game.slot(i) for i in range(8)])
        self.assertIn((33, 1), [self.game.slot(i) for i in range(8)])


class PickupTests(BridgeTest):
    def test_pickup_while_watching_is_checked_and_vanilla_removed(self):
        b = self.bridge()
        b.tick([])
        self.game.flag("Mirror Corridor - Golden Arrow")
        self.game.set_slot(2, 21, 1)                     # the game gave the vanilla arrow
        on = b.tick([])
        self.assertIn("Mirror Corridor - Golden Arrow", on)
        self.assertEqual(self.game.slot(2), (0, 0))

    def test_stacked_ammo_only_loses_the_pickup_amount(self):
        self.game.set_slot(2, 17, 10)
        b = self.bridge()
        b.tick([])
        self.game.flag("Mirror Corridor - Handgun Magazine")
        self.game.set_slot(2, 17, 25)
        b.tick([])
        self.assertEqual(self.game.slot(2), (17, 10))

    def test_pickup_made_while_client_closed_counts_but_is_not_touched(self):
        self.game.flag("Crypt - Book of Curses")
        self.game.set_slot(2, 22, 1)
        on = self.bridge().tick([])
        self.assertIn("Crypt - Book of Curses", on)
        self.assertEqual(self.game.slot(2), (22, 1))

    def test_emblem_put_back_and_retaken_is_kept(self):
        self.game.flag("Dining Room - Wooden Emblem")
        self.game.set_slot(2, 69, 1)                     # player owns an emblem
        b = self.bridge()
        b.tick([])
        self.game.flag("Dining Room - Wooden Emblem", on=False)    # placed on the fireplace
        self.game.set_slot(2, 0, 0)
        b.tick([])
        self.game.flag("Dining Room - Wooden Emblem")             # taken again
        self.game.set_slot(2, 69, 1)
        b.tick([])
        b.tick([])
        self.assertEqual(self.game.slot(2), (69, 1))     # still theirs


if __name__ == "__main__":
    unittest.main()


class MapperInClientTests(BridgeTest):
    def test_client_learns_unique_pickup_while_playing(self):
        from unittest import mock
        from .. import game_data
        undetected = {k: v for k, v in game_data.DETECTED_PICKUPS.items() if k not in ['Dining Room - Shield Key']}
        with mock.patch.dict(game_data.DETECTED_PICKUPS, undetected, clear=True):
            import json
            d = Path(self.tmp.name)
            b = GameBridge(StateFile(d / "s.json"), Journal(d / "j.jsonl"),
                           connect=lambda: (self.game, INV_PTR, FLAGS_PTR), learned_file=d / "learned.json")
            import time as _t
            b.tick([])
            self.game.mem[FLAGS + 0x33A] |= 1 << 3          # unknown bit turns on...
            self.game.set_slot(2, 47, 1)                     # ...as the Shield Key arrives
            b.tick([])
            _t.sleep(0.6)
            b.tick([])
            learned = json.loads((d / "learned.json").read_text())
            self.assertIn("Dining Room - Shield Key", learned["mappings"])
            self.assertEqual(self.game.slot(2), (47, 1))      # not a check yet -> item left alone

    def test_catalogue_covers_every_pickup_and_map(self):
        from ..client.game_bridge import pickup_catalogue
        from ..locations import extra_location_table, location_table
        maps = {n for n, d in extra_location_table.items() if d.category in ("map", "file")}
        self.assertEqual(set(pickup_catalogue()), set(location_table) | maps)

    def test_mapper_uses_the_room_for_herbs(self):
        from unittest import mock
        from .. import game_data
        undetected = {k: v for k, v in game_data.DETECTED_PICKUPS.items() if k not in ['Resting Room - Green Herb']}
        with mock.patch.dict(game_data.DETECTED_PICKUPS, undetected, clear=True):
            import json
            import time as _t
            d = Path(self.tmp.name)
            b = GameBridge(StateFile(d / "s.json"), Journal(d / "j.jsonl"),
                           connect=lambda: (self.game, INV_PTR, FLAGS_PTR), learned_file=d / "learned.json")
            struct.pack_into("<ii", self.game.mem, FLAGS + hv.CURRENT_ROOM_OFFSET, 2, 0x0B)  # Resting Room (0x20B)
            b.tick([])
            self.game.mem[FLAGS + 0x33A] |= 1 << 4          # unknown bit...
            self.game.set_slot(2, 34, 1)                     # ...as a Green Herb arrives in the Resting Room
            b.tick([])
            _t.sleep(0.6)
            b.tick([])
            learned = json.loads((d / "learned.json").read_text())
            self.assertIn("Resting Room - Green Herb", learned["mappings"])


class MapCheckClientTests(BridgeTest):
    def test_map_check_sent_but_map_not_taken_back(self):
        from unittest import mock
        from .. import game_data
        name = "Art Room - Map of the Mansion 1F"
        with mock.patch.dict(game_data.DETECTED_PICKUPS, {name: (0x316, 0, 130)}):
            b = self.bridge()
            b.tick([])
            self.game.mem[FLAGS + 0x316] |= 1
            writes = self.game.writes
            on = b.tick([])
            b.tick([])
            self.assertIn(name, on)
            self.assertEqual(self.game.writes, writes)      # nothing written: the player keeps the map
            self.assertFalse([e for e in b.journal.entries() if e.get("event") == "vanilla_not_removed"])


class RoomTests(BridgeTest):
    def set_room(self, number):
        struct.pack_into("<ii", self.game.mem, FLAGS + hv.CURRENT_ROOM_OFFSET, number >> 8, number & 0xFF)

    def test_first_visit_check_for_current_room(self):
        self.set_room(0x106)
        self.put_jill()
        b = self.bridge()
        self.assertIn("Main Hall - First Visit", b.tick([]))
        self.assertEqual(b.current_room, 0x106)

    def test_title_screen_main_hall_is_not_a_visit(self):
        self.set_room(0x106)                 # the title screen also reports the Main Hall...
        self.no_jill()                       # ...but Jill doesn't exist yet
        b = self.bridge()
        self.assertFalse(b.tick([]))

    def set_visited(self, number):
        from ..game_data import room_visited_flag
        off, bit = room_visited_flag(number)
        self.game.mem[FLAGS + off] |= 1 << bit

    def test_tea_room_and_northern_corridor_share_one_check(self):
        self.set_room(0x103)
        self.set_visited(0x103)
        on = self.bridge().tick([])
        self.assertIn("Northern Corridor - First Visit", on)
        self.assertNotIn("Tea Room - First Visit", on)

    def test_verified_room_uses_the_saved_visited_flag(self):
        self.set_room(0x106)                             # standing in the Main Hall...
        self.set_visited(0x10B)                          # ...but the Graveyard was visited earlier
        on = self.bridge().tick([])
        self.assertIn("Graveyard - First Visit", on)

    def test_verified_room_waits_for_its_flag(self):
        self.set_room(0x10B)                             # just walked in; game sets the flag ~5 s later
        self.assertNotIn("Graveyard - First Visit", self.bridge().tick([]))
        self.set_visited(0x10B)
        self.assertIn("Graveyard - First Visit", self.bridge().tick([]))

    def test_visited_flag_formula(self):
        from ..game_data import room_visited_flag, ROOM_VISITED_VERIFIED
        self.assertEqual(room_visited_flag(0x10B), (0x33D, 3))     # Graveyard (seen in-game)
        self.assertEqual(room_visited_flag(0x302), (0x345, 2))     # Courtyard Falls Area
        self.assertEqual(room_visited_flag(0x515), (0x34E, 6))     # Lab elevator
        self.assertIsNone(room_visited_flag(0x612))
        self.assertEqual(len(ROOM_VISITED_VERIFIED), 80)

    def test_goal_room_is_seen(self):
        from ..game_data import GOAL_ROOM_NUMBER
        self.set_room(GOAL_ROOM_NUMBER)
        b = self.bridge()
        b.tick([])
        self.assertEqual(b.current_room, 0x11B)

    def test_loading_junk_is_not_a_room(self):
        self.set_room(0x0012)                            # stage 0 = mid-transition junk
        b = self.bridge()
        on = b.tick([])
        self.assertIsNone(b.current_room)
        self.assertFalse([n for n in on if n.endswith("First Visit")])


class DefensiveItemTests(BridgeTest):
    """Daggers / battery packs are counts at inventory struct +0x5088 / +0x508C (found 2026-11-10)."""

    def count(self, iid):
        return struct.unpack_from("<i", self.game.mem, INV + hv.DEFENSE_COUNT_OFFSETS[iid])[0]

    def set_count(self, iid, n):
        struct.pack_into("<i", self.game.mem, INV + hv.DEFENSE_COUNT_OFFSETS[iid], n)

    def test_received_dagger_and_battery_raise_the_counts(self):
        self.set_count(112, 2)
        b = self.bridge()
        rec = items((112, "Dagger from Friend"), (121, "Battery Pack from Friend"))
        b.tick(rec)
        b.tick(rec)
        self.assertEqual(self.count(112), 3)
        self.assertEqual(self.count(121), 1)
        self.assertEqual(self.game.box(0), (0, 0))       # never into the box
        self.bridge().tick(rec)                           # restart: no duplicates
        self.assertEqual(self.count(112), 3)

    def test_crash_after_count_write_is_not_redelivered(self):
        rec = items((112, "Dagger from Friend"))
        b = self.bridge()
        b.state.pending = {"index": 0, "address": INV + hv.DAGGER_COUNT_OFFSET, "game_id": 112, "count": 1}
        b.state_file.save(b.state)
        self.set_count(112, 1)                            # the write had happened
        b2 = self.bridge()
        b2.tick(rec)
        b2.tick(rec)
        self.assertEqual(self.count(112), 1)
        self.assertEqual(b2.state.delivered, 1)

    def test_vanilla_dagger_taken_back_when_its_pickup_is_a_check(self):
        from unittest import mock
        from .. import game_data
        with mock.patch.dict(game_data.DETECTED_PICKUPS, {"Dining Room 2F - Dagger": (0x2F0, 7, 112)}):
            self.set_count(112, 3)
            b = self.bridge()
            b.tick([])
            self.game.flag("Dining Room 2F - Dagger")
            self.set_count(112, 4)                        # the game gave the vanilla dagger
            on = b.tick([])
            self.assertIn("Dining Room 2F - Dagger", on)
            self.assertEqual(self.count(112), 3)          # back to what the player had

    def test_mapper_learns_battery_pack_by_elimination(self):
        from unittest import mock
        from .. import game_data
        undetected = {k: v for k, v in game_data.DETECTED_PICKUPS.items() if k not in ['Small Storeroom - Battery Pack', 'Northern Corridor - Battery Pack', "Researcher's Bedroom - Battery Pack"]}
        with mock.patch.dict(game_data.DETECTED_PICKUPS, undetected, clear=True):
            import json
            import time as _t
            d = Path(self.tmp.name)
            b = GameBridge(StateFile(d / "s.json"), Journal(d / "j.jsonl"),
                           connect=lambda: (self.game, INV_PTR, FLAGS_PTR), learned_file=d / "learned.json")
            spots = ["Small Storeroom - Battery Pack", "Northern Corridor - Battery Pack",
                     "Researcher's Bedroom - Battery Pack"]
            b.mapper.data["mappings"] = {spots[0]: {"offset": 0x330, "bit": 0, "item_id": 121, "how": "test"},
                                         spots[1]: {"offset": 0x330, "bit": 1, "item_id": 121, "how": "test"}}
            b.tick([])
            self.game.mem[FLAGS + 0x30A] |= 1 << 2
            self.set_count(121, 1)
            b.tick([])
            _t.sleep(0.6)
            b.tick([])
            learned = json.loads((d / "learned.json").read_text())
            self.assertEqual(learned["mappings"][spots[2]]["offset"], 0x30A)


class TestOverlayMessages(unittest.TestCase):
    """On-screen text for item sends (2026-11-10)."""

    def msg(self, receiving, finder, item_name="Shotgun Shells", type_="ItemSend"):
        from ..client.overlay import message_for
        from ..client.RE1HDClient import item_quantity
        args = {"type": type_, "receiving": receiving, "item": (1, 2, finder, 0)}
        names = {1: "TessarionAM", 2: "Bob"}
        return message_for(args, 1, lambda i, s: item_name, lambda s: names[s], item_quantity)

    def test_own_find(self):
        self.assertEqual(self.msg(1, 1), ("found", "You found your Shotgun Shells (6)."))

    def test_sent_to_other(self):
        self.assertEqual(self.msg(2, 1, "Hookshot"), ("sent", "You sent Hookshot to Bob."))

    def test_received_from_other(self):
        self.assertEqual(self.msg(1, 2, "Green Herb"), ("received", "Bob sent you Green Herb."))

    def test_handgun_quantity(self):
        self.assertEqual(self.msg(1, 2, "Handgun Magazine")[1], "Bob sent you Handgun Magazine (15).")

    def test_not_ours(self):
        self.assertIsNone(self.msg(2, 2))

    def test_other_message_types_ignored(self):
        self.assertIsNone(self.msg(1, 1, type_="Chat"))

    def test_dict_item(self):
        from ..client.overlay import message_for
        args = {"type": "ItemSend", "receiving": 2, "item": {"item": 5, "player": 1}}
        self.assertEqual(message_for(args, 1, lambda i, s: "X", lambda s: "Bob", lambda n: None),
                         ("sent", "You sent X to Bob."))


class EndingWatcherTests(unittest.TestCase):
    """Goal complete_game: Heliport, then the game resets to an empty Main Hall (2026-11-10)."""

    def test_ending_after_heliport(self):
        from ..client.game_bridge import EndingWatcher
        w = EndingWatcher()
        self.assertFalse(w.update(0x303, False, 100.0))
        self.assertFalse(w.update(None, False, 150.0))          # credits / loading
        self.assertTrue(w.update(0x106, True, 160.0))

    def test_new_game_without_heliport_is_not_the_ending(self):
        from ..client.game_bridge import EndingWatcher
        self.assertFalse(EndingWatcher().update(0x106, True, 10.0))

    def test_reload_after_dying_at_heliport_is_not_the_ending(self):
        from ..client.game_bridge import EndingWatcher
        w = EndingWatcher()
        w.update(0x303, False, 100.0)
        self.assertFalse(w.update(0x502, False, 130.0))         # a save loads: items, other room
        self.assertFalse(w.update(0x106, False, 140.0))         # Main Hall but with items


class InventoryDeliveryTests(BridgeTest):
    """received_item_destination = inventory_then_box (default since 2026-11-10)."""

    def bridge(self):
        b = super().bridge()
        from ..client.game_bridge import INVENTORY_THEN_BOX
        b.destination = INVENTORY_THEN_BOX
        return b

    def test_goes_into_first_empty_inventory_slot(self):
        b = self.bridge()
        b.tick(items((22, "Book of Curses from Server")))
        self.assertEqual(self.game.slot(2), (22, 1))       # slots 0-1 hold the handgun and knife
        self.assertEqual(self.game.box(0), (0, 0))

    def test_full_inventory_falls_back_to_the_box_with_a_notice(self):
        for i in range(2, 8):
            self.game.set_slot(i, 34, 1)
        b = self.bridge()
        b.tick(items((46, "Armor Key from Server")))
        self.assertEqual(self.game.box(0), (46, 7))
        self.assertTrue(b.notices and "item box" in b.notices[0])

    def test_restart_mid_inventory_delivery_is_not_doubled(self):
        b = self.bridge()
        rec = items((22, "Book of Curses from Server"))
        b.state.pending = {"index": 0, "address": None, "game_id": 22, "qty": 1,
                           "tag": "AP item #0: Book of Curses from Server"}
        b.state_file.save(b.state)
        from ..client.game_bridge import delivery_tag
        from ..client.hd_delivery import deliver_to_inventory
        deliver_to_inventory(self.game, INV, 22, 1, b.journal, reason=delivery_tag(rec[0]))
        b2 = self.bridge()
        b2.tick(rec)
        b2.tick(rec)
        held = [self.game.slot(i) for i in range(8)].count((22, 1))
        self.assertEqual(held, 1)


class StartingItemTests(BridgeTest):
    def test_starting_item_goes_to_inventory_even_in_box_mode(self):
        from ..client.game_bridge import Incoming
        b = self.bridge()                                   # default destination = item box
        b.tick([Incoming(0, 22, "Book of Curses from Archipelago", starting=True)])
        self.assertEqual(self.game.slot(2), (22, 1))
        self.assertEqual(self.game.box(0), (0, 0))

    def test_normal_items_still_go_to_the_box(self):
        b = self.bridge()
        b.tick(items((46, "Armor Key from Bob")))
        self.assertEqual(self.game.box(0), (46, 7))


class DirectInventoryTests(BridgeTest):
    def test_book_of_curses_goes_to_inventory_in_box_mode(self):
        b = self.bridge()
        b.tick(items((22, "Book of Curses from Bob")))
        self.assertEqual(self.game.slot(2), (22, 1))
        self.assertEqual(self.game.box(0), (0, 0))

    def test_book_of_curses_waits_when_inventory_is_full(self):
        for i in range(2, 8):
            self.game.set_slot(i, 34, 1)
        b = self.bridge()
        b.tick(items((22, "Book of Curses from Bob")))
        self.assertEqual(self.game.box(0), (0, 0))          # NOT put in a box
        self.assertEqual(b.state.delivered, 0)               # still waiting
        self.assertTrue(b.notices and "Make room" in b.notices[0])
        self.game.set_slot(7, 0, 0)                          # player uses a herb
        b.next_delivery_try = 0
        b.tick(items((22, "Book of Curses from Bob")))
        self.assertEqual(self.game.slot(7), (22, 1))


class RandomStartTests(BridgeTest):
    """random_starting_inventory (2026-11-10, experimental)."""

    def setUp(self):
        super().setUp()
        self.game.set_slot(0, 3, 15)                         # a NEW game: Handgun 15 + Combat Knife
        self.game.set_slot(1, 1, 1)
        struct.pack_into("<ii", self.game.mem, FLAGS + hv.CURRENT_ROOM_OFFSET, 1, 0x06)   # Main Hall
        struct.pack_into("<ii", self.game.mem, INV + 0x80, 3, 15)                         # equipped

    def bridge(self):
        b = super().bridge()
        b.random_start = True
        return b

    def test_new_game_swaps_once_and_starting_items_arrive(self):
        from ..client.game_bridge import Incoming
        start = [Incoming(0, 6, "Shotgun from Archipelago", starting=True),
                 Incoming(1, 33, "First Aid Spray from Archipelago", starting=True)]
        b = self.bridge()
        b.tick(start)
        b.tick(start)
        held = [self.game.slot(i) for i in range(8)]
        self.assertNotIn((3, 15), held)
        self.assertNotIn((1, 1), held)
        self.assertIn((6, 6), held)
        self.assertIn((33, 1), held)
        self.assertEqual(struct.unpack_from("<ii", self.game.mem, INV + 0x80), (0, 0))
        self.assertTrue(b.state.start_swapped)
        # a later reload with a Handgun is never touched again
        self.game.set_slot(0, 3, 15)
        self.game.set_slot(1, 1, 1)
        self.bridge().tick(start)
        self.assertEqual(self.game.slot(0), (3, 15))

    def test_equipped_handgun_without_one_in_inventory_is_unequipped(self):
        b = self.bridge()
        b.tick([])                                           # swap done
        struct.pack_into("<ii", self.game.mem, INV + 0x80, 3, 0)      # game re-equips an empty Handgun
        b.tick([])
        self.assertEqual(struct.unpack_from("<ii", self.game.mem, INV + 0x80), (0, 0))

    def test_equipped_weapon_still_in_inventory_is_kept(self):
        b = self.bridge()
        b.tick([])
        self.game.set_slot(4, 11, 6)                         # Magnum in the inventory...
        struct.pack_into("<ii", self.game.mem, INV + 0x80, 11, 3)     # ...and equipped
        b.tick([])
        self.assertEqual(struct.unpack_from("<ii", self.game.mem, INV + 0x80), (11, 3))

    def test_not_a_new_game_is_left_alone(self):
        self.game.set_slot(2, 34, 1)                         # already picked something up
        b = self.bridge()
        b.tick([])
        self.assertEqual(self.game.slot(0), (3, 15))
        self.assertFalse(b.state.start_swapped)


class SeedNameTests(unittest.TestCase):
    """Seed test 2 (2026-11-11): every seed shared state_None_1.json because CommonContext
    0.6.7 never stores the seed name - a new seed's items looked 'already delivered'."""

    def test_room_info_sets_the_seed_name(self):
        import asyncio
        from ..client.RE1HDClient import RE1HDContext

        async def run():
            ctx = RE1HDContext(None, None)
            ctx.on_package("RoomInfo", {"seed_name": "12345678901234567890"})
            return ctx.seed_name
        self.assertEqual(asyncio.run(run()), "12345678901234567890")


class StackingTests(BridgeTest):
    """Box stacking (TessarionAM, 2026-11-11): ammo and ink ribbons add onto an existing stack."""

    def test_ammo_stacks_onto_existing_box_stack(self):
        self.game.set_box(3, 17, 15)
        b = self.bridge()
        b.tick(items((17, "Handgun Magazine from Bob")))
        self.assertEqual(self.game.box(3), (17, 30))
        self.assertEqual(self.game.box(0), (0, 0))

    def test_herbs_do_not_stack(self):
        self.game.set_box(3, 34, 1)
        b = self.bridge()
        b.tick(items((34, "Green Herb from Bob")))
        self.assertEqual(self.game.box(3), (34, 1))
        self.assertEqual(self.game.box(0), (34, 1))

    def test_full_stack_uses_a_new_slot(self):
        self.game.set_box(3, 17, 250)
        b = self.bridge()
        b.tick(items((17, "Handgun Magazine from Bob")))
        self.assertEqual(self.game.box(3), (17, 250))
        self.assertEqual(self.game.box(0), (17, 15))

    def test_restart_after_stack_write_is_not_doubled(self):
        from ..client.hd_delivery import deliver_to_box
        self.game.set_box(3, 17, 15)
        b = self.bridge()
        rec = items((17, "Handgun Magazine from Bob"))
        b.state.pending = {"index": 0, "address": None, "game_id": 17, "qty": 15, "tag": delivery_tag(rec[0])}
        b.state_file.save(b.state)
        deliver_to_box(self.game, INV, 17, 15, b.journal, reason=delivery_tag(rec[0]), stack_limit=255)
        b2 = self.bridge()
        b2.tick(rec)
        self.assertEqual(self.game.box(3), (17, 30))
        self.assertEqual(b2.state.delivered, 1)


class SaveMarkerTests(BridgeTest):
    """Seed test 2 (2026-11-11): dying / loading an older save lost every item delivered since
    that save. The client keeps the delivered count in item box slot 256 (saved with the game)."""

    def marker(self):
        return self.game.box(255)

    def test_marker_follows_deliveries(self):
        b = self.bridge()
        b.tick(items((21, "Golden Arrow from Bob"), (34, "Green Herb from Bob")))
        b.tick(items((21, "Golden Arrow from Bob"), (34, "Green Herb from Bob")))
        self.assertEqual(self.marker(), (0, 2))

    def test_loading_an_older_save_redelivers_what_it_lacks(self):
        rec = items((21, "Golden Arrow from Bob"), (34, "Green Herb from Bob"))
        struct.pack_into("<B", self.game.mem, FLAGS + 0x2E9, 0x80)   # not a new game (a pickup flag is on)
        b = self.bridge()
        b.tick(rec)
        b.tick(rec)
        # the player saved after the Golden Arrow, got the herb, died, and reloaded that save:
        self.game.set_box(0, 21, 1)
        self.game.set_box(1, 0, 0)
        self.game.set_box(255, 0, 1)
        b.tick(rec)
        b.tick(rec)
        self.assertEqual(self.game.box(1), (34, 1))                  # herb sent again
        self.assertEqual([self.game.box(i) for i in range(4)].count((21, 1)), 1)   # arrow not doubled
        self.assertEqual(self.marker(), (0, 2))

    def test_new_game_gets_everything_again(self):
        rec = items((21, "Golden Arrow from Bob"))
        b = self.bridge()
        b.tick(rec)
        for i in range(256):
            self.game.set_box(i, 0, 0)                               # brand-new game
        b.tick(rec)
        self.assertEqual(self.game.box(0), (21, 1))

    def test_save_without_marker_does_not_auto_redeliver(self):
        rec = items((21, "Golden Arrow from Bob"))
        struct.pack_into("<B", self.game.mem, FLAGS + 0x2E9, 0x80)
        b = self.bridge()
        b.tick(rec)
        self.game.set_box(255, 0, 0)                                 # an old save with no marker
        self.game.set_box(0, 0, 0)
        b.tick(rec)
        self.assertEqual(self.game.box(0), (0, 0))                   # not guessed...
        self.assertTrue(any("/redeliver" in n for n in b.notices))   # ...the player is told

    def test_item_in_slot_256_is_never_touched(self):
        self.game.set_box(255, 34, 1)
        b = self.bridge()
        b.tick(items((21, "Golden Arrow from Bob")))
        self.assertEqual(self.game.box(255), (34, 1))


class SeedTagTests(BridgeTest):
    """Seed test 4 (02:21): loading a save from another game sent 244 checks at once and then
    delivered items into it. Box slot 255 now holds {0, seed tag}."""

    def tagged_bridge(self):
        b = self.bridge()
        b.seed_tag = 12345
        return b

    def test_new_game_gets_the_tag(self):
        b = self.tagged_bridge()
        b.tick(items((21, "Golden Arrow from Bob")))
        self.assertEqual(self.game.box(254), (0, 12345))

    def test_other_seeds_save_does_nothing(self):
        self.game.set_box(254, 0, 999)                      # another seed's tag
        self.game.flag(next(iter(DETECTED_PICKUPS)))         # something picked up in that save
        b = self.tagged_bridge()
        self.assertIsNone(b.tick(items((21, "Golden Arrow from Bob"))))   # no checks sent
        self.assertEqual(b.state.delivered, 0)                             # nothing delivered
        self.assertTrue(any("isn't from this seed" in n for n in b.notices))
        b.adopt_save = True                                  # /adopt
        self.assertIsNotNone(b.tick(items((21, "Golden Arrow from Bob"))))
        self.assertEqual(self.game.box(254), (0, 12345))

    def test_untagged_save_with_pickups_and_no_record_is_foreign(self):
        self.game.flag(next(iter(DETECTED_PICKUPS)))
        b = self.tagged_bridge()
        self.assertIsNone(b.tick([]))

    def test_untagged_save_with_a_delivery_record_is_foreign(self):
        """2026-11-14 (TessarionAM): a save from an earlier seed (no tag, but a delivery record of
        124) was taken as this seed's and sent its 30 old pickups as checks."""
        self.game.flag(next(iter(DETECTED_PICKUPS)))
        self.game.set_box(255, 0, 124)                       # a record, but no tag
        b = self.tagged_bridge()
        self.assertIsNone(b.tick([]))                        # no checks sent
        self.assertEqual(self.game.box(254), (0, 0))         # not tagged
        self.assertTrue(any("isn't from this seed" in n for n in b.notices))
        b.adopt_save = True                                  # /adopt still works
        self.assertIsNotNone(b.tick([]))
        self.assertEqual(self.game.box(254), (0, 12345))

    def test_deliveries_never_use_the_last_two_slots(self):
        for i in range(254):
            self.game.set_box(i, 34, 1)                      # box full up to slot 254
        b = self.tagged_bridge()
        b.tick(items((21, "Golden Arrow from Bob")))
        self.assertEqual(self.game.box(254), (0, 12345))
        self.assertNotEqual(self.game.box(255)[0], 21)


class LoadBurstTests(BridgeTest):
    """A reload turns many pickup flags on at once - never take items back then."""

    def test_many_flags_at_once_take_nothing_back(self):
        b = self.bridge()
        b.tick([])
        self.game.set_slot(2, 70, 1)                                 # Gold Emblem in hand from the save
        for name in ("Bar - Gold Emblem", "Dining Room - Shield Key", "Mirror Corridor - Golden Arrow"):
            off, bit, _ = DETECTED_PICKUPS[name]
            self.game.mem[FLAGS + off] |= 1 << bit
        b.tick([])
        b.tick([])
        self.assertEqual(self.game.slot(2), (70, 1))


class TrapAndDeathLinkTests(RoomTests):
    def setUp(self):
        super().setUp()
        self.set_room(0x106)

    def jill(self, hp=960):
        self.put_jill(hp)
        struct.pack_into("<i", self.game.mem, 0x4000 + hv.JILL_MAX_HEALTH_OFFSET, 960)

    def hp(self):
        return struct.unpack_from("<i", self.game.mem, 0x4000 + hv.JILL_HEALTH_OFFSET)[0]

    def trap(self, name, i=0):
        return Incoming(i, None, f"{name} from Bob", trap=name)

    def test_damage_trap_takes_the_set_percentage(self):
        self.jill()
        b = self.bridge()
        b.tick([self.trap("Damage Trap")])
        self.assertEqual(self.hp(), 719)            # 25 % AND at least one state (seed test 3)
        self.assertEqual(b.state.delivered, 1)
        self.assertEqual(self.game.box(0), (0, 0))       # nothing goes in the box

    def test_damage_trap_leaves_one_hp_unless_it_can_kill(self):
        self.jill(100)
        b = self.bridge()
        b.tick([self.trap("Damage Trap")])
        self.assertEqual(self.hp(), 1)
        self.jill(100)
        b.trap_can_kill = True
        b.tick([self.trap("Damage Trap"), self.trap("Damage Trap", 1)])
        self.assertEqual(self.hp(), 0)

    def test_poison_trap_sets_the_poison_bit(self):
        self.jill()
        self.bridge().tick([self.trap("Poison Trap")])
        self.assertTrue(self.game.mem[0x4000 + hv.JILL_POISON_OFFSET] & (1 << hv.JILL_POISON_BIT))

    def test_trap_waits_until_jill_exists(self):
        self.no_jill()
        b = self.bridge()
        b.tick([self.trap("Damage Trap")])
        self.assertEqual(b.state.delivered, 0)

    def test_trap_is_not_reapplied_after_loading_a_save(self):
        self.jill()
        b = self.bridge()
        b.tick([self.trap("Damage Trap")])
        self.jill()                                       # loaded a save: full health again
        b.redeliver_from(0)
        b.tick([self.trap("Damage Trap")])
        self.assertEqual(self.hp(), 960)
        self.assertEqual(b.state.delivered, 1)

    def test_jill_dying_is_noticed(self):
        self.jill()
        b = self.bridge()
        b.tick([])
        self.assertFalse(b.jill_died)
        struct.pack_into("<i", self.game.mem, 0x4000 + hv.JILL_HEALTH_OFFSET, 0)
        b.tick([])
        self.assertTrue(b.jill_died)

    def test_received_death_link_takes_one_health_state(self):
        self.jill()
        b = self.bridge()
        b.deaths_to_apply = 1
        b.tick([])
        self.assertEqual(self.hp(), 719)            # one health state down (game's 75 % limit)
        self.assertEqual(b.deaths_to_apply, 0)

    def test_received_death_link_never_kills_by_default_and_isnt_echoed(self):
        self.jill(50)
        b = self.bridge()
        b.deaths_to_apply = 1
        b.tick([])
        self.assertEqual(self.hp(), 1)
        b.death_link_kill = True
        b.deaths_to_apply = 1
        b.tick([])
        self.assertEqual(self.hp(), 0)
        b.tick([])
        self.assertFalse(b.jill_died)                    # a death we caused isn't sent back


class DoorSkipTests(unittest.TestCase):
    """Door skip patches (client/door_skip.py) against a fake game holding the original code."""
    class Code:
        module_base = 0x00400000
        exe_path = "D:\\\\Game\\\\bhd.exe"

        def __init__(self):
            from ..client.door_skip import PATCHES
            self.mem = {}
            for a, orig, _, _ in PATCHES["hd_6699874012183562949"]:
                for i, b in enumerate(orig):
                    self.mem[a + i] = b

        def read_bytes(self, a, n):
            return bytes(self.mem.get(a + i, 0xCC) for i in range(n))

        def write_code(self, a, data):
            for i, b in enumerate(data):
                self.mem[a + i] = b

    def test_on_off_round_trip(self):
        from ..client.door_skip import set_door_skip, status
        g = self.Code()
        key = "hd_6699874012183562949"
        self.assertEqual(status(g, key), "off")
        self.assertEqual(set_door_skip(g, key, True), 5)
        self.assertEqual(status(g, key), "on")
        self.assertEqual(set_door_skip(g, key, True), 0)      # already on (e.g. BhdTool did it)
        set_door_skip(g, key, False)
        self.assertEqual(status(g, key), "off")

    def test_unexpected_code_writes_nothing(self):
        from ..client.door_skip import DoorSkipError, set_door_skip
        g = self.Code()
        g.mem[0x00668A9A] = 0x12                                # someone else changed this byte
        before = dict(g.mem)
        with self.assertRaises(DoorSkipError):
            set_door_skip(g, "hd_6699874012183562949", True)
        self.assertEqual(g.mem, before)


class StartBoxTests(RoomTests):
    def test_vanilla_box_gets_random_item_and_99_ribbons(self):
        self.set_room(0x106)
        self.game.set_box(0, 33, 1)
        self.game.set_box(1, 68, 3)
        b = self.bridge()
        b.start_box = [(17, 15), (68, 99)]
        b.tick([])
        self.assertEqual(self.game.box(0), (17, 15))
        self.assertEqual(self.game.box(1), (68, 99))
        b.tick([])                                         # not vanilla any more: untouched
        self.assertEqual(self.game.box(1), (68, 99))

    def test_box_with_anything_else_is_left_alone(self):
        self.set_room(0x106)
        self.game.set_box(0, 33, 1)
        self.game.set_box(1, 68, 3)
        self.game.set_box(2, 34, 1)
        b = self.bridge()
        b.start_box = [(17, 15), (68, 99)]
        b.tick([])
        self.assertEqual(self.game.box(0), (33, 1))

    def test_not_outside_the_main_hall(self):
        self.set_room(0x100)
        self.game.set_box(0, 33, 1)
        self.game.set_box(1, 68, 3)
        b = self.bridge()
        b.start_box = [(17, 15), (68, 99)]
        b.tick([])
        self.assertEqual(self.game.box(1), (68, 3))


class FakeSaver:
    def __init__(self, conn, key):
        self.requests, self.flag_done, self.result = [], False, 0
        FakeSaver.last = self

    def install(self):
        return 0x10000000

    def game_idle(self):
        return True

    def request(self, slot):
        self.requests.append(slot)

    def poll(self):
        return self.result if self.flag_done else None

    def waiting_for_control(self):
        return False

    def cancel(self):
        pass

    def call_ready(self):
        return True

    def request_call(self, name, this, args=(), in_control=False):
        self.calls = getattr(self, "calls", []) + [(name, this) + ((tuple(args),) if args else ())]
        self.in_control = getattr(self, "in_control", []) + [in_control]

    def call_result(self):
        r = getattr(self, "results", [])
        return r.pop(0) if r else 0

    def address(self, name):
        from ..client.autosave import ADDR
        return ADDR["hd_6699874012183562949"][name]

    def play_sound(self, bank, sound_id):
        self.sounds = getattr(self, "sounds", []) + [(bank, sound_id)]
        return True

    def open_item_box(self):
        self.calls = getattr(self, "calls", []) + [("open_item_box", 0)]
        self.box = 1

    def box_state(self):
        return getattr(self, "box", 0)

    def cancel_item_box(self):
        self.box = 0

    def clear_item_box_done(self):
        self.box = 0


class AutosaveTests(RoomTests):
    def bridge_with_autosave(self):
        b = self.bridge()
        b.autosave_slot = 7
        b.autosaver_factory = FakeSaver
        self.put_jill()
        return b

    def walk(self, b, room, wait=True):
        self.set_room(room)
        b.tick([])
        if wait:
            b.as_since -= 3                    # pretend 3 s passed in the room
            b.tick([])

    def test_walking_into_a_save_room_autosaves_once(self):
        b = self.bridge_with_autosave()
        self.walk(b, 0x106)                     # Main Hall
        self.walk(b, 0x100)                     # into the Mansion Drug Room (save room)
        saver = FakeSaver.last
        self.assertEqual(saver.requests, [7])
        saver.flag_done = True
        b.tick([])
        self.assertIn("Autosaved (slot 8).", b.notices)
        b.as_since -= 10
        b.tick([])
        self.assertEqual(saver.requests, [7])   # once per entry

    def test_loading_a_save_in_a_save_room_does_not_autosave(self):
        b = self.bridge_with_autosave()
        self.walk(b, 0x100)                     # first room seen = a load / client start
        self.assertEqual(FakeSaver.last.requests, [])

    def test_no_save_in_ordinary_rooms(self):
        b = self.bridge_with_autosave()
        self.walk(b, 0x106)
        self.walk(b, 0x105 + 2)                 # Art Room
        self.assertEqual(FakeSaver.last.requests, [])

    def test_deliveries_pause_while_saving(self):
        b = self.bridge_with_autosave()
        self.walk(b, 0x106)
        self.walk(b, 0x100)
        b.tick(items((34, "Green Herb from Bob")))
        self.assertEqual(b.state.delivered, 0)
        FakeSaver.last.flag_done = True
        b.tick(items((34, "Green Herb from Bob")))   # save finishes this tick
        b.tick(items((34, "Green Herb from Bob")))
        self.assertEqual(b.state.delivered, 1)


class ItemBoxAnywhereTests(AutosaveTests):
    def ready(self, on=2):
        b = self.bridge_with_autosave()
        b.box_anywhere = on
        self.walk(b, 0x106)
        b.room_since -= 5
        return b

    def test_off_in_the_yaml(self):
        b = self.ready(on=0)
        self.assertIn("off in your YAML", b.open_item_box())

    def test_save_rooms_only(self):
        b = self.ready(on=1)                                  # Main Hall: no typewriter
        self.assertIn("typewriter", b.open_item_box())
        self.walk(b, 0x105)                                   # Dining Room has one
        b.room_since -= 5
        b.as_deadline = None                                  # (its autosave finished)
        self.assertEqual(b.open_item_box(), "Opening the item box...")

    def test_opens_through_the_game_thread(self):
        b = self.ready()
        b.box_auto_sort = True
        self.game.set_box(0, 34, 1)
        self.game.set_box(1, 46, 7)
        self.assertEqual(b.open_item_box(), "Opening the item box...")
        self.assertEqual(self.game.box(0), (46, 7))           # sorted before it opens
        self.assertEqual(FakeSaver.last.calls, [("open_item_box", 0)])

    def test_not_right_after_a_door(self):
        b = self.ready()
        b.room_since = time.time()
        self.assertIn("Wait", b.open_item_box())

    def test_not_while_saving(self):
        b = self.ready()
        b.as_deadline = time.time() + 30
        self.assertIn("Busy", b.open_item_box())

    def test_request_the_game_never_takes_is_withdrawn(self):
        b = self.ready()
        b.open_item_box()
        b.box_open_deadline = time.time() - 1
        b.tick([])
        self.assertEqual(FakeSaver.last.box, 0)
        self.assertIn("The item box can't open right now.", b.notices)

    def test_game_side_l1_opens_the_box(self):
        b = self.ready()
        b.box_button = "lb_l1"
        mgr = 0x6000
        struct.pack_into("<I", self.game.mem, FLAGS_PTR - 0x00CF2FC8 + 0x00D599E4, mgr)
        self.assertFalse(b._game_button_down("lb_l1"))
        struct.pack_into("<I", self.game.mem, mgr + 0x198, 0x100)        # L1 held, as the game sees it
        self.assertTrue(b._game_button_down("lb_l1"))
        self.assertFalse(b._game_button_down("rb_r1"))
        self.assertFalse(b._game_button_down("back_plus_lb"))

    def test_opened_request_resets(self):
        b = self.ready()
        b.open_item_box()
        FakeSaver.last.box = 2
        b.tick([])
        self.assertIsNone(b.box_open_deadline)
        self.assertEqual(FakeSaver.last.box, 0)


class CaveCodeTests(unittest.TestCase):
    def test_box_stub_opens_the_item_box_menu_once_else_the_scan(self):
        from ..client.autosave import ADDR, box_stub_code, BOX_STUB, D_BOX_FLAG
        a = ADDR["hd_6699874012183562949"]
        base = 0x10000000
        code = box_stub_code(base, a)
        self.assertIn(b"\x83\x3D" + struct.pack("<I", base + D_BOX_FLAG) + b"\x01", code)   # after the v7 call check
        calls = [struct.unpack("<i", code[i + 1:i + 5])[0] + base + BOX_STUB + i + 5
                 for i in range(len(code) - 4) if code[i] == 0xE8]
        calls = [c for c in calls if 0x400000 <= c < 0x1000000]          # real calls into the game only
        # v9: the autosave start (SaveToSlot) comes first, then the item box's two calls
        self.assertEqual(calls, [a["save_to_slot"], a["set_state_bit"], a["open_menu"]])
        self.assertIn(b"\x6A\x01\x6A\x00\x6A\x00\x6A\x00\x6A\x00\x6A\x05", code)   # OpenMenu(5,0,0,0,0,1)
        self.assertIn(b"\x8B\x0D" + struct.pack("<I", a["menu_ptr"]), code)
        self.assertIn(b"\xC2\x04\x00", code)                                             # ret 4 like the scan
        self.assertEqual(code[-5], 0xE9)                                                  # else jmp scan
        self.assertEqual(struct.unpack("<i", code[-4:])[0] + base + BOX_STUB + len(code), a["examine"])

    def test_cave_calls_original_then_save_without_ribbon(self):
        from ..client.autosave import ADDR, cave_code
        a = ADDR["hd_6699874012183562949"]
        code = cave_code(0x10000000, a)
        self.assertEqual(code[:5], b"\xE8" + struct.pack("<i", a["late_update"] - 0x10000005))
        self.assertIn(b"\x6A\x03\xFF\x35", code)            # push 3 (no ribbon), push [slot]
        self.assertEqual(code[-3:], b"\x9D\x61\xC3")         # popfd, popad, ret
        self.assertLess(len(code), 0x200)


from ..client.autosave import ADDR as ADDR_


class AutosaverInstallTests(unittest.TestCase):
    class Mem:
        module_base = 0x00400000

        def __init__(self, call_target):
            self.mem = bytearray(0x1000)            # fake page for the hook site
            self.extra = {}
            hook = 0x0089151B
            self.hook = hook
            self.code = {hook + i: b for i, b in enumerate(
                b"\xE8" + struct.pack("<i", call_target - (hook + 5)))}
            self.next_alloc = 0x20000000

        def read_bytes(self, a, n):
            return bytes(self.code.get(a + i, self.extra.get(a + i, 0)) for i in range(n))

        def write_bytes(self, a, data):
            for i, b in enumerate(data):
                self.extra[a + i] = b

        def write_code(self, a, data):
            for i, b in enumerate(data):
                self.code[a + i] = b

        def alloc_code(self, size):
            a, self.next_alloc = self.next_alloc, self.next_alloc + 0x10000
            return a

    def test_installs_on_the_vanilla_call(self):
        from ..client.autosave import Autosaver
        m = self.Mem(0x007BEE70)
        s = Autosaver(m, "hd_6699874012183562949")
        base = s.install()
        self.assertIsNone(s.chained_to)
        self.assertEqual(s._call_target(), base)
        first = m.read_bytes(base, 5)
        self.assertEqual(struct.unpack("<i", first[1:])[0] + base + 5, 0x007BEE70)

    def test_chains_through_bhdtool(self):
        from ..client.autosave import Autosaver
        m = self.Mem(0x12345670)                     # BhdTool's hook
        s = Autosaver(m, "hd_6699874012183562949")
        base = s.install()
        self.assertEqual(s.chained_to, 0x12345670)
        first = m.read_bytes(base, 5)
        self.assertEqual(struct.unpack("<i", first[1:])[0] + base + 5, 0x12345670)

    def with_scan(self, m, detoured=False):
        from ..client.autosave import FIRST_BYTES
        for name, first in FIRST_BYTES.items():
            m.write_code(ADDR_["hd_6699874012183562949"][name], b"\xE9\0\0\0\0" if detoured else first)
        site = 0x004F2E97
        m.write_code(site, b"\xE8" + struct.pack("<i", 0x0047FE80 - (site + 5)))

    def test_item_box_hook_goes_on_the_trigger_scan_call(self):
        from ..client.autosave import Autosaver, BOX_STUB, D_BOX_FLAG
        m = self.Mem(0x007BEE70)
        self.with_scan(m, detoured=True)              # BhdTool's detour on the functions is fine
        s = Autosaver(m, "hd_6699874012183562949")
        base = s.install()
        self.assertIsNone(s.box_hook_error)
        self.assertEqual(s._call_target("examine_hook"), base + BOX_STUB)
        s.open_item_box()
        self.assertEqual(struct.unpack("<I", m.read_bytes(base + D_BOX_FLAG, 4))[0], 1)
        with self.assertRaises(Exception):
            s.open_item_box()                         # already waiting
        s.cancel_item_box()
        self.assertEqual(s.box_state(), 0)

    def test_no_item_box_hook_on_unknown_code(self):
        from ..client.autosave import Autosaver
        m = self.Mem(0x007BEE70)                      # trigger scan bytes not there
        s = Autosaver(m, "hd_6699874012183562949")
        s.install()
        self.assertIsNotNone(s.box_hook_error)
        with self.assertRaises(Exception):
            s.open_item_box()

    def test_client_restart_finds_its_own_hook(self):
        from ..client.autosave import Autosaver
        m = self.Mem(0x007BEE70)
        base = Autosaver(m, "hd_6699874012183562949").install()
        again = Autosaver(m, "hd_6699874012183562949")
        self.assertEqual(again.install(), base)


class BorderlessStyleTests(unittest.TestCase):
    def test_title_bar_and_borders_removed_other_bits_kept(self):
        from ..client.window_mode import borderless_style
        style, ex = borderless_style(0x14CF0000, 0x00040300)   # WS_OVERLAPPEDWINDOW|VISIBLE|CLIPSIBLINGS
        self.assertEqual(style & 0x00C40000, 0)                 # no caption / thick frame
        self.assertEqual(style & 0x10000000, 0x10000000)        # still visible
        self.assertEqual(ex & 0x300, 0)


class HealthStateTests(unittest.TestCase):
    def test_limits_from_the_game(self):
        from ..client.game_bridge import below_next_state
        self.assertEqual(below_next_state(960, 960), 719)   # Fine -> Caution
        self.assertEqual(below_next_state(720, 960), 719)   # 720 is still Fine (75 %)
        self.assertEqual(below_next_state(719, 960), 479)   # Caution -> orange Caution
        self.assertEqual(below_next_state(300, 960), 239)   # orange -> Danger
        self.assertEqual(below_next_state(100, 960), 1)     # Danger


class DamageTrapStateTests(RoomTests):
    def test_trap_from_full_health_drops_a_state(self):
        self.set_room(0x106)
        b = self.bridge()
        b.tick([Incoming(0, None, "Damage Trap from Bob", trap="Damage Trap")])
        hp = struct.unpack_from("<i", self.game.mem, 0x4000 + hv.JILL_HEALTH_OFFSET)[0]
        self.assertEqual(hp, 719)

    def test_death_link_drops_exactly_one_state(self):
        self.set_room(0x106)
        b = self.bridge()
        b.deaths_to_apply = 1
        b.tick([])
        hp = struct.unpack_from("<i", self.game.mem, 0x4000 + hv.JILL_HEALTH_OFFSET)[0]
        self.assertEqual(hp, 719)


class HeldWeaponTests(BridgeTest):
    """Seed test 3: Jill kept holding the removed Handgun (equip watch: Jill+0x15D0 = 2).
    Seed test 6: dropping the model left the Handgun pose (v0.9.6), and queueing the change alone
    crashed (v0.9.7: pl01_2w01 lives in arc\\wep\\wep11, not loaded). v0.9.8 does the menu's whole
    unequip: find the loader, switch the weapon archive, wait until loaded, then queue the change."""
    OBJ = 0x5000

    def setup_game(self, held=2, once=False):
        FakeSaver.last = None
        struct.pack_into("<ii", self.game.mem, FLAGS + hv.CURRENT_ROOM_OFFSET, 1, 5)   # Dining Room
        self.game.set_slot(0, 33, 1)                     # no Handgun in the inventory
        self.game.set_slot(1, 0, 0)
        struct.pack_into("<i", self.game.mem, 0x4000 + 0x15D0, held)
        struct.pack_into("<i", self.game.mem, 0x4000 + 0x1580, 1)          # Jill's column
        b = self.bridge()
        b.random_start, b.state.start_swapped = True, True
        b.unarmed_once = once
        b.autosaver_factory = FakeSaver
        self.game.mem_map = getattr(self.game, "mem_map", None)
        b.tick([])
        b.room_since -= 3
        return b

    def object_list(self, b):
        from ..client.autosave import ADDR
        return ADDR["hd_6699874012183562949"]["object_list"]

    def run_steps(self, b, ready=(1, 1)):
        """Tick through the steps; the fake saver answers find_object and the two ready polls."""
        b._u32 = (lambda orig: (lambda a: 0x7000 if a == self.object_list(b) else orig(a)))(b._u32)
        b.tick([])                                       # 1. find_object
        FakeSaver.last.results = [self.OBJ]
        b.tick([])                                       # 2. weapon_arc
        b.tick([])                                       # 3a. loader_ready +0x358
        FakeSaver.last.results = [ready[0]]
        b.tick([])                                       # 3b. loader_ready +0x390 (if 3a done)
        FakeSaver.last.results = [ready[1]]
        b.tick([])                                       # 4. queue_weapon
        b.tick([])                                       # done
        return FakeSaver.last.calls

    def test_put_away_like_the_inventory_menu(self):
        b = self.setup_game()
        calls = self.run_steps(b)
        self.assertEqual(calls, [("find_object", 0x7000, (0xCEDCC8,)),
                                 ("weapon_arc", self.OBJ + 0x50, (0, 1)),
                                 ("loader_ready", self.OBJ + 0x358),
                                 ("loader_ready", self.OBJ + 0x390),
                                 ("queue_weapon", 0x4000, (0, 0))])
        # the steps that change Jill run only once she can move
        self.assertEqual(FakeSaver.last.in_control, [True, True, False, False, True])
        self.assertTrue(b.unarmed_once)
        self.assertIsNone(b.unarm)

    def test_waits_until_the_weapon_archive_is_loaded(self):
        b = self.setup_game()
        calls = self.run_steps(b, ready=(0, 1))
        self.assertNotIn("queue_weapon", [c[0] for c in calls])     # not loaded: no change yet
        self.assertGreaterEqual([c[0] for c in calls].count("loader_ready"), 2)   # keeps polling

    def test_stuck_pose_with_no_weapon_is_fixed_once_per_run(self):
        b = self.setup_game(held=0)
        b.swapped_this_run = True                        # straight after the random start swap
        self.run_steps(b)
        n = len(FakeSaver.last.calls)
        b.next_drop_try = 0
        b.tick([])
        self.assertEqual(len(FakeSaver.last.calls), n)

    def test_nothing_to_fix_on_a_save_loaded_mid_game(self):
        # 2026-11-15: Jill T-posed for a second when the client connected to a mid-game save
        b = self.setup_game(held=0)                      # nothing held, no swap in this run
        b.tick([])
        b.tick([])
        self.assertFalse(getattr(FakeSaver.last, "calls", []))

    def test_nothing_happens_while_the_menu_is_open(self):
        b = self.setup_game()
        struct.pack_into("<i", self.game.mem, INV + 0x34, 3)
        b.tick([])
        self.assertFalse(getattr(FakeSaver.last, "calls", []))

    def test_held_weapon_that_is_in_the_inventory_is_kept_after_the_first_check(self):
        b = self.setup_game(held=14, once=True)
        self.game.set_slot(2, 15, 6)                     # Grenade Launcher (item 15 = type 14)
        b.tick([])
        self.assertFalse(getattr(FakeSaver.last, "calls", []))

    def test_menu_calls_are_whitelisted_with_the_dump_bytes(self):
        from ..client.autosave import ADDR, CALLABLE
        a = ADDR["hd_6699874012183562949"]
        self.assertEqual(a["queue_weapon"], 0x6AA710)
        self.assertEqual(CALLABLE["queue_weapon"].hex(), "8b4424048981401d00008b442408")
        self.assertEqual((a["weapon_arc"], CALLABLE["weapon_arc"].hex()), (0x48D190, "568bf18b0d842ecf00e8"))
        self.assertEqual((a["find_object"], CALLABLE["find_object"].hex()), (0x4D3040, "5356578bf98bb724380000"))
        self.assertEqual((a["loader_ready"], CALLABLE["loader_ready"].hex()), (0x482530, "51538bd9b001565733ff"))

    def test_in_control_calls_run_from_the_box_stub_and_keep_the_result(self):
        from ..client import autosave as a
        addrs = a.ADDR["hd_6699874012183562949"]
        stub = a.box_stub_code(0x10000000, addrs)
        flag = b"\x83\x3D" + struct.pack("<I", 0x10000000 + a.D_CALL_FLAG)
        self.assertIn(flag + bytes([a.IN_CONTROL]), stub)
        self.assertNotIn(flag + bytes([a.IN_CONTROL]), a.cave_code(0x10000000, addrs))
        store = b"\xA3" + struct.pack("<I", 0x10000000 + a.D_CALL_RESULT)
        self.assertIn(store, stub)
        self.assertIn(store, a.cave_code(0x10000000, addrs))


class AutosaveInControlTests(unittest.TestCase):
    """v9 (2026-11-14): the autosave starts only from the box stub (Jill can move), in place of
    that frame's trigger scan, and only when no save runs and storage is free."""

    def test_stub_starts_the_save_first_and_skips_the_scan_that_frame(self):
        from ..client import autosave as a
        addrs = a.ADDR["hd_6699874012183562949"]
        base = 0x10000000
        stub = a.box_stub_code(base, addrs)
        wait = b"\x83\x3D" + struct.pack("<I", base + a.D_FLAG) + bytes([a.WAIT_CONTROL])
        self.assertTrue(stub.startswith(wait))
        # flag -> RUNNING before the first SaveToSlot, so the late update carries it on
        running = b"\xC7\x05" + struct.pack("<I", base + a.D_FLAG) + struct.pack("<I", a.RUNNING)
        self.assertLess(stub.index(running), stub.index(b"\x6A\x03\xFF\x35"))
        # the save branch returns (ret 4) before the scan code
        self.assertLess(stub.index(b"\xC2\x04\x00"), stub.index(b"\x83\x3D" + struct.pack("<I", base + a.D_CALL_FLAG)))
        # busy checks: save state and storage busy, as in the late-update routine
        self.assertIn(b"\x83\xBE" + struct.pack("<I", a.SAVE_OBJECT + a.STATE) + b"\x00", stub)
        self.assertIn(b"\x83\x78" + bytes([a.STORAGE_BUSY]) + b"\x00", stub)

    def test_request_waits_for_control_when_the_box_stub_is_in(self):
        from ..client import autosave as a
        s = a.Autosaver.__new__(a.Autosaver)
        mem = {}
        s.cave = 0x2000
        s.box_hook_error = None
        s.conn = type("C", (), {"write_bytes": lambda _s, addr, data: mem.__setitem__(addr, data),
                                "read_bytes": lambda _s, addr, n: mem.get(addr, bytes(n))})()
        s.request(7)
        self.assertEqual(struct.unpack("<I", mem[0x2000 + a.D_FLAG])[0], a.WAIT_CONTROL)
        self.assertTrue(s.waiting_for_control())
        s.cancel()
        self.assertEqual(struct.unpack("<I", mem[0x2000 + a.D_FLAG])[0], a.IDLE)
        s.box_hook_error = "not installed"                    # no stub: as before
        s.request(7)
        self.assertEqual(struct.unpack("<I", mem[0x2000 + a.D_FLAG])[0], a.REQUESTED)


class BoxReminderTests(RoomTests):
    def test_entering_a_box_room_lists_new_box_items_once(self):
        self.set_room(0x106)
        b = self.bridge()
        b.tick(items((46, "Armor Key from Bob"), (18, "Shotgun Shells from Bob")))
        b.tick(items((46, "Armor Key from Bob"), (18, "Shotgun Shells from Bob")))
        self.assertEqual(b.state.box_unseen, ["Armor Key (7)", "Shotgun Shells (6)"])
        self.set_room(0x100)                                  # Mansion Drug Room (item box)
        b.tick(items((46, "Armor Key from Bob"), (18, "Shotgun Shells from Bob")))
        self.assertIn("In the item box: Armor Key (7), Shotgun Shells (6)", b.notices)
        self.assertEqual(b.state.box_unseen, [])

    def test_auto_sort_retries_until_the_game_lets_it(self):
        self.set_room(0x106)
        b = self.bridge()
        b.box_auto_sort = True
        self.game.set_box(0, 34, 1)
        self.game.set_box(1, 46, 7)
        b.tick([])
        self.set_room(0x100)
        struct.pack_into("<i", self.game.mem, INV + 0x34, 3) # menu (or door) still busy
        b.tick([])
        b.box_sort_due = time.time() - 1
        b.tick([])                                            # can't sort yet: retry later
        self.assertIsNotNone(b.box_sort_due)
        self.assertEqual(self.game.box(0), (34, 1))
        struct.pack_into("<i", self.game.mem, INV + 0x34, 0)
        b.box_sort_due = time.time() - 1
        b.tick([])
        self.assertIsNone(b.box_sort_due)
        self.assertEqual(self.game.box(0), (46, 7))           # key first

    def test_summary_groups_and_limits(self):
        from ..client.game_bridge import box_summary
        self.assertEqual(box_summary(["Green Herb", "Green Herb", "Key"]), "Green Herb x2, Key")
        self.assertTrue(box_summary([str(i) for i in range(9)]).endswith("and 3 more"))


class GamepadTests(unittest.TestCase):
    def test_off_and_unknown_never_down(self):
        from ..client.gamepad import button_down
        self.assertFalse(button_down("off"))
        self.assertFalse(button_down(None))
        self.assertFalse(button_down("lb_l1"))               # no XInput here

    def test_every_option_has_a_button(self):
        from ..client.gamepad import BUTTONS, TRIGGERS, COMBOS
        from ..options import ItemBoxButton
        for name in ItemBoxButton.name_lookup.values():
            self.assertTrue(name == "off" or name in BUTTONS or name in TRIGGERS or name in COMBOS, name)


class BoxSortTests(BridgeTest):
    def test_keys_first_stacks_merged_nothing_lost(self):
        from ..client.box_sort import sorted_box
        from ..game_data import STACK_LIMITS
        slots = [(34, 1), (0, 0), (17, 200), (46, 7), (17, 100), (0, 0), (68, 3), (22, 1)] + [(0, 0)] * 4
        new = sorted_box(slots, STACK_LIMITS)
        self.assertEqual(len(new), len(slots))
        self.assertEqual(new[0][0], 22)          # Book of Curses (Keys) first
        self.assertEqual(new[1], (46, 7))        # Armor Key
        self.assertIn((17, 255), new)
        self.assertIn((17, 45), new)             # 300 handgun rounds -> 255 + 45
        total = lambda ss, i: sum(q for g, q in ss if g == i)
        for iid in (34, 17, 46, 68, 22):
            self.assertEqual(total(new, iid), total(slots, iid))
        self.assertEqual(new[-1], (0, 0))

    def test_sort_in_game_writes_once_and_keeps_slot_256(self):
        b = self.bridge()
        self.game.set_box(0, 34, 1)
        self.game.set_box(1, 46, 7)
        self.game.set_box(255, 0, 9)              # delivery record
        b.tick([])
        self.assertEqual(b.sort_box(), "Item box sorted.")
        self.assertEqual(self.game.box(0), (46, 7))
        self.assertEqual(self.game.box(1), (34, 1))
        self.assertEqual(self.game.box(255), (0, 9))

    def test_no_sort_with_menu_open(self):
        b = self.bridge()
        self.game.set_box(0, 34, 1)
        self.game.set_box(1, 46, 7)
        b.tick([])
        struct.pack_into("<i", self.game.mem, INV + 0x34, 3)
        self.assertEqual(b.sort_box(), "Close the menu first.")


class GameConfigTests(unittest.TestCase):
    def test_resolution_line_is_replaced_in_display_only(self):
        from ..client.game_config import with_resolution
        text = "[SOUND]\r\nResolution=5\r\n[DISPLAY]\r\nAspect=16:9\r\nResolution=1920x1080\r\nFullScreen=ON\r\n"
        out = with_resolution(text, 3840, 2160)
        self.assertIn("Resolution=3840x2160\r\n", out)
        self.assertIn("[SOUND]\r\nResolution=5\r\n", out)
        self.assertIn("FullScreen=ON", out)

    def test_missing_line_or_section_is_added(self):
        from ..client.game_config import with_resolution
        self.assertIn("[DISPLAY]\nResolution=2560x1440\nAspect=16:9", with_resolution("[DISPLAY]\nAspect=16:9\n", 2560, 1440))
        self.assertIn("[DISPLAY]\nResolution=1920x1080", with_resolution("[SOUND]\nX=1\n", 1920, 1080))

    def test_odd_value_format_is_kept(self):
        from ..client.game_config import with_resolution
        self.assertIn("Resolution=3840 x 2160 60Hz", with_resolution("[DISPLAY]\nResolution=1280 x 720 60Hz\n", 3840, 2160))


class NoTakeBackTests(unittest.TestCase):
    def test_only_maps_and_files_are_never_taken_back(self):
        """Seed test 5: the file marker was 131, a real First Aid Box id, so the Rec Room box
        stayed in the inventory."""
        from ..client.game_bridge import NO_TAKE_BACK
        from ..data import EXTRA_CHECKS, MISSABLE
        extras = {name for _c, _r, name, _q in EXTRA_CHECKS} | set(MISSABLE)
        for name, (_off, _bit, gid) in DETECTED_PICKUPS.items():
            if gid in NO_TAKE_BACK:
                self.assertIn(name, extras, name)


class RecordSlotTests(BridgeTest):
    def open_box_ui(self, on=True):
        root, menu = 0x6800, 0x7000
        struct.pack_into("<I", self.game.mem, FLAGS_PTR - 0x00CF2FC8 + 0x00CF30D8, root)
        struct.pack_into("<I", self.game.mem, root + 0x40, menu)
        struct.pack_into("<I", self.game.mem, menu + 0x60A0, 5 if on else 0)

    def test_item_put_in_the_record_slots_is_moved_out_and_records_restored(self):
        b = self.bridge()
        b.seed_tag = 777
        b.tick([])                                          # tagged, known ours
        self.assertEqual(self.game.box(254), (0, 777))
        self.open_box_ui()
        self.game.set_box(254, 8, 6)                        # player drops the Grenade Launcher there
        self.game.set_box(255, 64, 1)                       # ...and the Stone Ring
        self.assertIsNotNone(b.tick([]))                    # box open: no "foreign save" panic
        self.open_box_ui(False)
        b.tick([])
        self.assertEqual(self.game.box(254), (0, 777))
        self.assertEqual(self.game.box(255)[0], 0)
        ids = [self.game.box(i)[0] for i in range(254)]
        self.assertIn(8, ids)
        self.assertIn(64, ids)

    def test_unknown_items_sort_into_groups(self):
        from ..client.box_sort import sorted_box, sort_key_table
        t = sort_key_table()
        self.assertLess(t[8], t[34])        # loaded Grenade Launcher (weapon) before herbs
        self.assertLess(t[64], t[17])       # Stone Ring (quest) before ammo
        new = sorted_box([(64, 1), (0, 0), (8, 6), (46, 1)], {})
        self.assertEqual([s[0] for s in new], [46, 64, 8, 0])


class NewTrapTests(TrapAndDeathLinkTests):
    """Seed test 5 picks (2026-11-12): Critical Damage, Ammo Leak, Jumpscare, Infinite Ammo."""

    def test_critical_damage_leaves_one_health(self):
        self.jill()
        b = self.bridge()
        b.tick([self.trap("Critical Damage Trap")])
        self.assertEqual(self.hp(), 1)
        self.assertEqual(b.state.delivered, 1)

    def test_ammo_leak_takes_one_ammo_stack(self):
        self.jill()
        self.game.set_slot(2, 17, 30)                    # Handgun Magazine in the inventory
        self.game.set_box(5, 18, 12)                     # Shotgun Shells in the box
        b = self.bridge()
        b.tick([self.trap("Ammo Leak Trap")])
        left = [self.game.slot(2), self.game.box(5)]
        self.assertEqual(left.count((0, 0)), 1)          # exactly one stack gone
        self.assertEqual(self.game.slot(0), (3, 15))     # the loaded Handgun is not ammo

    def test_ammo_leak_never_touches_the_record_slots(self):
        self.jill()
        self.game.set_slot(2, 0, 0)
        b = self.bridge()
        b.tick([])
        self.game.set_box(SEED_TAG_SLOT, 17, 5)          # pretend junk in a record slot
        b.rng.choice = lambda xs: xs[0]
        b._ammo_leak(INV, "Bob")
        self.assertEqual(self.game.box(SEED_TAG_SLOT), (17, 5))

    def test_ammo_leak_with_no_ammo_still_counts(self):
        self.jill()
        b = self.bridge()
        b.tick([self.trap("Ammo Leak Trap")])
        self.assertEqual(b.state.delivered, 1)

    def test_fake_item_trap_says_just_kidding_later(self):
        self.jill()
        b = self.bridge()
        b.tick([self.trap("Fake Item Trap")])
        self.assertEqual(b.state.delivered, 1)
        text, kind = b.notices[-1]
        self.assertTrue(text.startswith("Bob sent you ") and kind == "received")
        self.assertEqual(len(b.timed_notices), 1)
        b.timed_notices[0] = (0, b.timed_notices[0][1], "info")
        b.tick([self.trap("Fake Item Trap")])
        self.assertIn("Just kidding", b.notices[-1][0])

    def test_fake_death_link_does_nothing_to_jill(self):
        self.jill()
        b = self.bridge()
        b.tick([self.trap("Fake Death Link Trap")])
        self.assertEqual(self.hp(), 960)
        self.assertTrue(b.notices[-1][0].startswith("Death Link!"))

    def test_window_traps_go_to_the_client(self):
        self.jill()
        b = self.bridge()
        rec = [self.trap("Fake Crash Trap"), self.trap("Window Shake Trap", 1), self.trap("To Be Continued Trap", 2)]
        for _ in range(3):
            b.tick(rec)
        self.assertEqual([n for n, _ in b.fun_requests], ["Fake Crash Trap", "Window Shake Trap", "To Be Continued Trap"])

    def test_infinite_ammo_tops_up_the_equipped_gun(self):
        self.jill()
        struct.pack_into("<ii", self.game.mem, INV + EQUIPPED_SLOT_OFFSET, 3, 10)
        self.game.set_slot(0, 3, 10)
        b = self.bridge()
        b.tick([self.trap("Infinite Ammo (20s)")])
        struct.pack_into("<ii", self.game.mem, INV + EQUIPPED_SLOT_OFFSET, 3, 4)   # fired 6
        self.game.set_slot(0, 3, 4)
        b.tick([self.trap("Infinite Ammo (20s)")])
        self.assertEqual(struct.unpack_from("<ii", self.game.mem, INV + EQUIPPED_SLOT_OFFSET), (3, 10))
        self.assertEqual(self.game.slot(0), (3, 10))
        b.infinite_until = time.time() - 1                # 20 s later
        struct.pack_into("<ii", self.game.mem, INV + EQUIPPED_SLOT_OFFSET, 3, 4)
        b.tick([self.trap("Infinite Ammo (20s)")])
        self.assertEqual(struct.unpack_from("<ii", self.game.mem, INV + EQUIPPED_SLOT_OFFSET), (3, 4))

    def test_infinite_ammo_on_empty_gun_uses_capacity(self):
        self.jill()
        struct.pack_into("<ii", self.game.mem, INV + EQUIPPED_SLOT_OFFSET, 6, 0)  # empty Shotgun
        b = self.bridge()
        b.tick([self.trap("Infinite Ammo (20s)")])
        self.assertEqual(struct.unpack_from("<ii", self.game.mem, INV + EQUIPPED_SLOT_OFFSET), (6, 6))


class DefenceBundleTests(DefensiveItemTests):
    def test_bundle_adds_a_dagger_and_a_battery_pack_once(self):
        self.set_count(112, 2)
        rec = items((DEFENCE_BUNDLE, "Defence Bundle from Friend"))
        b = self.bridge()
        b.tick(rec)
        b.tick(rec)
        self.assertEqual((self.count(112), self.count(121)), (3, 1))
        self.bridge().tick(rec)
        self.assertEqual((self.count(112), self.count(121)), (3, 1))

    def test_half_done_bundle_is_finished_not_doubled(self):
        rec = items((DEFENCE_BUNDLE, "Defence Bundle from Friend"))
        b = self.bridge()
        b.state.pending = {"index": 0, "game_id": DEFENCE_BUNDLE,
                           "multi": [[INV + hv.DAGGER_COUNT_OFFSET, 0, 1], [INV + hv.BATTERY_COUNT_OFFSET, 0, 1]]}
        b.state_file.save(b.state)
        self.set_count(112, 1)                            # only the dagger had been written
        self.bridge().tick(rec)
        self.assertEqual((self.count(112), self.count(121)), (1, 1))


class EffectNameTests(unittest.TestCase):
    def test_every_trap_and_effect_item_is_handled_by_the_client(self):
        from ..items import item_table
        names = {n for n, d in item_table.items() if d.group in ("Traps", "Fun Traps")} | {"Infinite Ammo (20s)"}
        self.assertEqual(names, set(EFFECT_ITEMS))

    def test_cave_call_passes_three_arguments_and_restores_esp(self):
        from ..client.autosave import ADDR, D_CALL_ARGS, cave_code
        base = 0x10000000
        code = cave_code(base, ADDR["hd_6699874012183562949"])
        pushes = b"".join(b"\xFF\x35" + struct.pack("<I", base + D_CALL_ARGS + o) for o in (8, 4, 0))
        self.assertIn(b"\x89\xE5" + pushes, code)                 # mov ebp,esp; push arg3..arg1
        self.assertIn(b"\x89\xEC\xC7\x05", code)                 # mov esp,ebp right after the call


class FunEffectTests(unittest.TestCase):
    def test_shake_ends_where_it_started(self):
        from ..client.fun_effects import shake_offsets
        offs = shake_offsets(1.2, 16, seed=1)
        self.assertEqual(offs[-1], (0, 0))
        self.assertTrue(all(abs(dx) <= 16 and abs(dy) <= 16 for dx, dy in offs))

    def test_crash_text_looks_like_the_real_one(self):
        from ..client.fun_effects import crash_text
        text = crash_text(r"D:\Games\RE")
        self.assertTrue(text.startswith("Fatal error."))
        self.assertIn(r"Failed open file D:\Games\RE\nativePC\arc\itemv\v.arc 2", text)


class FunTrapGenerationTests(unittest.TestCase):
    def test_at_most_one_fake_crash_per_seed(self):
        from collections import Counter
        from .. import RE1HDWorld
        class Item:
            def __init__(self, name): self.name = name
        class Fake:
            create_item = staticmethod(Item)
            random = __import__("random").Random(3)
        pool = [Item("Green Herb") for _ in range(200)]
        RE1HDWorld._replace_junk(Fake(), pool, 50, {"Fake Crash Trap": 100, "Window Shake Trap": 1},
                                 limits={"Fake Crash Trap": 1})
        c = Counter(i.name for i in pool)
        self.assertEqual(c["Fake Crash Trap"], 1)
        self.assertEqual(c["Window Shake Trap"], 99)


class VignetteTests(unittest.TestCase):
    def test_glow_is_strongest_at_the_edge_and_clear_in_the_middle(self):
        from ..client.vignette import edge_alpha, vignette_rows
        a = edge_alpha(100, 30)
        self.assertEqual(a[0], max(a))
        self.assertEqual(a[50], 0)
        self.assertGreater(a[5], a[20])
        rows = list(vignette_rows(40, 20, margin=6))
        self.assertEqual(len(rows), 20)
        self.assertEqual(len(rows[0]), 160)
        mid = rows[10][20 * 4:20 * 4 + 4]
        self.assertEqual(mid, b"\0\0\0\0")               # centre fully transparent
        corner = rows[0][0:4]
        self.assertGreater(corner[3], 0)                  # corner opaque-ish (alpha byte)
        self.assertLessEqual(corner[2], corner[3])        # premultiplied red <= alpha

    def test_pulse_ends_clear(self):
        from ..client.vignette import pulse_levels
        p = pulse_levels(1.0, 2)
        self.assertEqual(p[-1], 0)
        self.assertEqual(max(p) > 200, True)


class BoxModeTests(unittest.TestCase):
    def test_old_seeds_on_switch_means_anywhere(self):
        import importlib
        try:
            mod = importlib.import_module("worlds.re1hd.client.RE1HDClient")
        except Exception:
            self.skipTest("client imports need the Archipelago runtime")
        f = mod.box_anywhere_mode
        self.assertEqual(f({"item_box_anywhere": 1, "world_version": "0.7.4"}), 2)
        self.assertEqual(f({"item_box_anywhere": 0, "world_version": "0.6.8"}), 0)
        self.assertEqual(f({"item_box_anywhere": 1, "world_version": "0.8.3"}), 1)
        self.assertEqual(f({"item_box_anywhere": 2, "world_version": "0.8.4"}), 2)


class EndingLiveInventoryTests(BridgeTest):
    def test_inventory_empty_now_reads_live_memory(self):
        b = self.bridge()
        b.tick([])
        self.assertFalse(b.inventory_empty_now())          # Handgun + Knife
        for i in range(8):
            self.game.set_slot(i, 0, 0)
        self.no_jill()                                      # credits: no Jill, normal tick stops
        b.tick([])
        self.assertTrue(b.inventory_empty_now())


class ResolutionCapTest(unittest.TestCase):
    """2026-11-12: 4k on a 1080p monitor came out cropped - never write above the monitor."""
    def test_too_big_is_skipped_and_undone(self):
        import tempfile
        from pathlib import Path
        from ..client import game_config as g
        d = Path(tempfile.mkdtemp())
        cfg, bak = d / "config.ini", d / "config.ini.bak"
        cfg.write_text("[DISPLAY]\nResolution=3840x2160\n")
        bak.write_text("[DISPLAY]\nResolution=1920x1080\n")
        old = g.find_config
        g.find_config = lambda: cfg
        try:
            msg = g.set_resolution(3, (1920, 1080))
            self.assertIn("bigger than your monitor", msg)
            self.assertIn("Resolution=1920x1080", cfg.read_text())
            g.set_resolution(2, (2560, 1440))
            self.assertIn("Resolution=2560x1440", cfg.read_text())
        finally:
            g.find_config = old


class FirstAidFirstTest(unittest.TestCase):
    def test_first_aid_sprays_top_the_healing_group(self):
        """TessarionAM (v0.9.3): First Aid Sprays at the top of the healing items in the box sort."""
        from ..client.box_sort import FIRST_AID_BOX, FIRST_AID_SPRAY, sort_key_table, sorted_box
        table = sort_key_table()
        healing = [gid for gid, (rank, _p) in table.items() if rank == table[FIRST_AID_SPRAY][0]]
        first = sorted(healing, key=lambda g: table[g])
        self.assertEqual(first[:2], [FIRST_AID_SPRAY, FIRST_AID_BOX])
        herb = 34
        box = sorted_box([(herb, 1), (FIRST_AID_SPRAY, 1), (0, 0)], {})
        self.assertEqual(box[0][0], FIRST_AID_SPRAY)


class JillPositionReadTest(unittest.TestCase):
    """v0.9.4: the bridge reads Jill's position through the paths the finder found."""

    def fake(self, mem, key="hd_6699874012183562949"):
        import types
        from ..client import hd_versions as hv

        class Conn:
            module_base = hv.DEFAULT_IMAGE_BASE
            build_key = key

            def read_bytes(self, a, n):
                for start, data in mem.items():
                    if start <= a and a + n <= start + len(data):
                        return bytes(data[a - start:a - start + n])
                raise OSError("unmapped")
        return types.SimpleNamespace(conn=Conn())

    def test_reads_the_first_path(self):
        from ..client.game_bridge import GameBridge
        obj = bytearray(0x100)
        struct.pack_into("<fff", obj, 0x40, -160.6, 0.0, 57.3)
        static = bytearray(0x200)
        struct.pack_into("<I", static, 0x14C, 0x2E000000)
        mem = {0x00D59380: struct.pack("<I", 0x10000000), 0x10000000: static, 0x2E000000: obj}
        x, y, z = GameBridge._jill_position(self.fake(mem))
        self.assertAlmostEqual(x, -160.6, places=3)
        self.assertAlmostEqual(z, 57.3, places=3)

    def test_falls_back_and_rejects_junk(self):
        from ..client.game_bridge import GameBridge
        self.assertIsNone(GameBridge._jill_position(self.fake({})))
        self.assertIsNone(GameBridge._jill_position(self.fake({}, key="unknown")))
        obj = bytearray(0x600)
        struct.pack_into("<fff", obj, 0x530, 1130.3, 1.8, -528.8)
        holder = bytearray(0x100)
        struct.pack_into("<I", holder, 0x5C, 0x2F000000)
        mem = {0x00D59380: struct.pack("<I", 0), 0x00CF3018: struct.pack("<I", 0x11000000),
               0x11000000: holder, 0x2F000000: obj}
        self.assertAlmostEqual(GameBridge._jill_position(self.fake(mem))[0], 1130.3, places=2)


class UnstickTests(BridgeTest):
    """/unstick (2026-11-14): the game still thinks a menu is open after a death / a bad save."""

    def test_stuck_menu_state_is_reset(self):
        from ..client.game_bridge import MENU_FLAGS, MENU_SCREEN
        b = self.bridge()
        b.tick([])
        struct.pack_into("<ii", self.game.mem, INV + MENU_FLAGS, 0x1020, 0)
        struct.pack_into("<i", self.game.mem, INV + MENU_SCREEN, 3)
        self.assertIn("reset", b.unstick())
        self.assertEqual(struct.unpack_from("<i", self.game.mem, INV + MENU_FLAGS)[0], 0x20)
        self.assertEqual(struct.unpack_from("<i", self.game.mem, INV + MENU_SCREEN)[0], 0)

    def test_nothing_stuck_writes_nothing(self):
        b = self.bridge()
        b.tick([])
        self.assertIn("No stuck menu", b.unstick())


class AutoloadBridgeTests(AutosaveTests):
    def bridge_with_autoload(self):
        self.game.module_base, self.game.pid = hv.DEFAULT_IMAGE_BASE, 1234
        self.game.readable_regions = lambda limit=0: []        # no title screen object yet
        b = self.bridge_with_autosave()
        b.autoload = True
        return b

    def die(self, b):
        b.tick([])
        struct.pack_into("<i", self.game.mem, 0x4000 + hv.JILL_HEALTH_OFFSET, 0)
        b.tick([])

    def test_a_successful_autosave_is_remembered(self):
        b = self.bridge_with_autoload()
        self.walk(b, 0x106)
        self.walk(b, 0x100)
        type(self).saver_done(b)
        self.assertTrue(b.state.autosave_made)
        self.assertTrue(self.bridge().state.autosave_made)     # kept in the state file

    @staticmethod
    def saver_done(b):
        FakeSaver.last.flag_done = True
        b.tick([])

    def test_death_arms_only_after_an_autosave(self):
        b = self.bridge_with_autoload()
        self.die(b)
        self.assertIsNone(b.autoloader)
        self.assertIn("No autosave yet in this seed - load your save yourself.", b.notices)
        b.state.autosave_made = True
        self.put_jill()
        self.die(b)
        self.assertTrue(b.autoloader.armed)
        self.assertEqual(b.autoloader.slot, 7)

    def test_off_by_default(self):
        b = self.bridge_with_autoload()
        b.autoload = False
        b.state.autosave_made = True
        self.die(b)
        self.assertIsNone(b.autoloader)

    def test_loading_yourself_disarms_it(self):
        b = self.bridge_with_autoload()
        b.state.autosave_made = True
        self.die(b)
        self.put_jill()                                        # back in the game, full health
        b.tick([])
        self.assertFalse(b.autoloader.armed)

    def test_status_always_says_on_or_off(self):
        b = self.bridge_with_autoload()
        b.autoload = False
        self.assertIn("OFF (from your YAML)", b.autoload_status())
        b.autosave_slot = None
        self.assertIn("needs the autosave option", b.autoload_status())

    def test_autoload_command_turns_it_on_and_is_kept_for_the_seed(self):
        b = self.bridge_with_autoload()
        b.autoload = False
        self.assertIn("ON (set with /autoload)", b.set_autoload(True))
        self.assertTrue(b.autoload)
        self.assertTrue(self.bridge().state.autoload_choice)       # kept in the state file
        b.state.autosave_made = True
        self.die(b)
        self.assertTrue(b.autoloader.armed)
        b.set_autoload(False)
        self.assertFalse(b.autoloader.armed)
        self.assertIs(self.bridge().state.autoload_choice, False)

    def test_autoload_command_needs_autosave(self):
        b = self.bridge_with_autoload()
        b.autosave_slot = None
        b.autoload = False
        b.set_autoload(True)
        self.assertFalse(b.autoload)


class FakeJumper:
    """Stands in for client.room_jump.RoomJumper (no code is written in tests)."""
    last = None

    def __init__(self, conn, log=None):
        self.armed, self.installs, self.state = [], 0, 0
        FakeJumper.last = self

    def install(self):
        self.installs += 1

    def arm(self, room, came_from=None):
        self.armed.append(room)
        self.state = 1
        return True

    def flag(self):
        return self.state

    def cancel(self):
        self.state = 0


class StartRoomTests(RoomTests):
    """random_start_room (2026-11-15): the client moves Jill once, on a new game."""
    def bridge_with_start(self, room=0x118):
        self.game.pid = 4321
        b = self.bridge()
        b.start_room, b.start_room_name = room, "East Wing Storeroom"
        b.jumper_factory = FakeJumper
        self.set_room(0x106)
        return b

    def test_new_game_arms_then_marks_done_on_arrival(self):
        b = self.bridge_with_start()
        b.tick([])
        self.assertEqual(FakeJumper.last.armed, [0x118])
        b.tick([])
        self.assertEqual(FakeJumper.last.armed, [0x118])           # armed once, not every tick
        FakeJumper.last.state = 2                                    # the stub fired
        self.set_room(0x118)
        b.tick([])
        self.assertTrue(b.state.start_room_done)
        self.assertTrue(self.bridge().state.start_room_done)       # kept in the state file
        self.assertIn("Your start room: East Wing Storeroom.", b.notices)
        self.assertTrue(b.as_armed)                                  # autosaves there next
        self.set_room(0x106)
        b.tick([])
        self.assertEqual(FakeJumper.last.armed, [0x118])           # never again in this run

    def test_off_does_nothing(self):
        b = self.bridge_with_start(room=0)
        b.tick([])
        self.assertIsNone(FakeJumper.last if FakeJumper.last and FakeJumper.last.armed else None)

    def test_not_after_something_was_picked_up(self):
        FakeJumper.last = None
        b = self.bridge_with_start()
        name = next(iter(DETECTED_PICKUPS))
        self.game.flag(name)
        b.tick([])
        self.assertIsNone(FakeJumper.last)

    def test_waits_for_the_random_starting_inventory(self):
        FakeJumper.last = None
        b = self.bridge_with_start()
        b.random_start = True
        b.state.start_swapped = False
        b._swap_start = lambda *a: None                              # swap not done yet
        b.tick([])
        self.assertIsNone(FakeJumper.last)

    def test_a_new_game_jumps_again(self):
        b = self.bridge_with_start()
        b.state.start_room_done = True
        mem = self.game.mem
        self.game.set_box(0, 33, 1)                                  # the untouched new-game box
        self.game.set_box(1, 68, 3)
        b.tick([])
        self.assertFalse(b.state.start_room_done)


class PlaytestLogTests(RoomTests):
    def test_kill_table_bits_are_logged_with_the_room(self):
        self.set_room(0x311)
        b = self.bridge()
        b.tick([])
        self.game.mem[FLAGS + 0x2AC] |= 1                           # the Neptune bit in data.BOSSES
        with self.assertLogs("RE1HDClient", "INFO") as cm:
            b.tick([])
        self.assertTrue(any("Kill table: +0x2ac.0 on in room 0x311 (Neptune Defeated)" in l for l in cm.output),
                        cm.output)

    def test_a_load_is_not_logged_as_kills(self):
        b = self.bridge()
        b.tick([])
        for off in range(0x26C, 0x27C):
            self.game.mem[FLAGS + off] = 0xFF
        with self.assertLogs("RE1HDClient", "INFO") as cm:
            b.tick([])
            import logging
            logging.getLogger("RE1HDClient").info("marker")
        self.assertFalse(any("Kill table" in l for l in cm.output))

    def test_real_death_is_snapshotted(self):
        b = self.bridge()
        b.tick([])
        struct.pack_into("<i", self.game.mem, 0x4000 + hv.JILL_HEALTH_OFFSET, 0)
        with self.assertLogs("RE1HDClient", "INFO") as cm:
            b.tick([])
        self.assertTrue(any("Death research real death t+0.0" in l for l in cm.output))
