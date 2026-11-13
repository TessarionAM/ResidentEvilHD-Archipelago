"""Offline tests for the pickup mapper (synthetic game readings)."""
import json
import tempfile
import unittest
from pathlib import Path

from client.pickup_mapper import ZONE, LearnedFile, PickupMapper, inventory_gains, new_bits

REAL_CAT_FILE = Path(__file__).resolve().parent.parent / "client" / "pickup_catalogue.json"
# The mapper tests use the Mansion catalogue as it was before the full mapping run
# (2026-11-09: 12 known), so learning/elimination still has unknown spots to work on.
CAT_FILE = Path(__file__).resolve().parent / "fixtures" / "catalogue_mansion_2026-11-09.json"
EMPTY = [(0, 0)] * 9


def zone_with(*bits):
    z = bytearray(ZONE[1] - ZONE[0])
    for off, bit in bits:
        z[off - ZONE[0]] |= 1 << bit
    return bytes(z)


def inv_with(*items):
    slots = list(items) + [(0, 0)] * (9 - len(items))
    return slots


class MapperTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cat = json.loads(CAT_FILE.read_text(encoding="utf-8"))
        self.logs = []
        self.m = PickupMapper(self.cat, LearnedFile(Path(self.tmp.name) / "l.json"), log=self.logs.append)

    def tearDown(self):
        self.tmp.cleanup()

    def play(self, steps):
        """steps: list of (zone bytes, inventory[, picked id]); 0.1 s apart. Returns everything learned."""
        learned, t = [], 1000.0
        for step in steps:
            picked = step[2] if len(step) > 2 else None
            learned += self.m.update(step[0], step[1], now=t, picked=picked)
            t += 0.1
        last = steps[-1]
        for _ in range(10):                 # let pairing windows close
            learned += self.m.update(last[0], last[1], now=t, picked=last[2] if len(last) > 2 else None)
            t += 0.1
        return learned

    def test_unique_item_learned_at_once(self):
        shield = "Dining Room - Shield Key"
        self.assertIsNone(self.cat[shield]["known"])
        got = self.play([(zone_with(), inv_with((3, 15))),
                         (zone_with((0x2F4, 3)), inv_with((3, 15), (47, 1)))])
        self.assertEqual(got, [shield])
        saved = json.loads((Path(self.tmp.name) / "l.json").read_text())
        self.assertEqual(saved["mappings"][shield]["offset"], 0x2F4)

    def test_known_bits_never_relearned(self):
        # Golden Arrow is already known (+0x2E9 bit 1)
        got = self.play([(zone_with(), EMPTY), (zone_with((0x2E9, 1)), inv_with((21, 1)))])
        self.assertEqual(got, [])

    def test_common_item_waits_for_elimination(self):
        got = self.play([(zone_with(), EMPTY), (zone_with((0x2F8, 0)), inv_with((34, 1)))])
        self.assertEqual(got, [])
        saved = json.loads((Path(self.tmp.name) / "l.json").read_text())
        self.assertEqual(len(saved["observations"]), 1)

    def test_two_bits_at_once_is_skipped(self):
        got = self.play([(zone_with(), EMPTY),
                         (zone_with((0x2F4, 3), (0x2F5, 0)), inv_with((47, 1)))])
        self.assertEqual(got, [])

    def test_box_withdrawal_without_bit_is_ignored_quietly(self):
        got = self.play([(zone_with(), EMPTY), (zone_with(), inv_with((47, 1)))])
        self.assertEqual(got, [])
        self.assertEqual(self.logs, [])

    def test_elimination_solves_last_spot(self):
        # Make every Red Herb spot but one already mapped, then observe a red herb pickup
        reds = [n for n, v in self.cat.items() if v["item"] == "Red Herb"]
        for i, n in enumerate(reds[:-1]):
            self.m.data["mappings"][n] = {"offset": 0x330, "bit": i, "item_id": 35, "how": "test"}
        got = self.play([(zone_with(), EMPTY), (zone_with((0x2FA, 6)), inv_with((35, 1)))])
        self.assertEqual(got, [reds[-1]])

    def test_ammo_stack_counts_as_a_gain(self):
        self.assertEqual(inventory_gains(inv_with((17, 10)), inv_with((17, 25))), {17: 15})

    def test_new_bits(self):
        self.assertEqual(new_bits(bytes([0b0001]), bytes([0b0011]), 0x100), [(0x100, 1)])


class MapTests(MapperTest):
    """Maps never enter the inventory: the 'just picked up' value (+0x50F4) identifies them."""

    def test_map_learned_from_picked_value(self):
        # 2F map = only other map, so make the 1F one known first -> the 2F map is the only spot
        self.m.data["mappings"]["Art Room - Map of the Mansion 1F"] = {"offset": 0x316, "bit": 0,
                                                                      "item_id": 130, "how": "test"}
        got = self.play([(zone_with(), EMPTY, 0), (zone_with((0x317, 2)), EMPTY, 130)])
        self.assertEqual(got, ["Resting Room - Map of the Mansion 2F"])

    def test_stale_picked_value_with_a_door_bit_is_ignored(self):
        # 'just picked up' still shows an old dagger (112) - a door bit must NOT pair with it
        got = self.play([(zone_with(), EMPTY, 112), (zone_with((0x31E, 2)), EMPTY, 112)])
        self.assertEqual(got, [])

    def test_inventory_item_with_picked_value_is_not_double_counted(self):
        got = self.play([(zone_with(), inv_with((3, 15)), 0),
                         (zone_with((0x2F4, 3)), inv_with((3, 15), (47, 1)), 47)])
        self.assertEqual(got, ["Dining Room - Shield Key"])


class CatalogueTests(unittest.TestCase):
    def test_catalogue_shape(self):
        cat = json.loads(CAT_FILE.read_text(encoding="utf-8"))
        self.assertEqual(len(cat), 85)                      # 83 Mansion pickups + 2 maps (fixture)
        self.assertEqual(sum(1 for v in cat.values() if v["known"]), 12)

    def test_real_catalogue_covers_the_whole_game(self):
        cat = json.loads(REAL_CAT_FILE.read_text(encoding="utf-8"))
        self.assertEqual(len(cat), 203)                     # 195 pickups + 8 maps (2026-11-10)
        self.assertGreaterEqual(sum(1 for v in cat.values() if v["known"]), 190)
        self.assertEqual(cat["Art Room - Map of the Mansion 1F"]["item_id"], 130)


if __name__ == "__main__":
    unittest.main()


class RoomAwareTests(MapperTest):
    def test_herb_learned_at_once_when_room_known(self):
        got = []
        t = 1000.0
        for zone, inv in [(zone_with(), EMPTY), (zone_with((0x30C, 4)), inv_with((34, 1)))]:
            got += self.m.update(zone, inv, now=t, rooms={"Resting Room"})
            t += 0.1
        for _ in range(10):
            got += self.m.update(zone_with((0x30C, 4)), inv_with((34, 1)), now=t, rooms={"Resting Room"})
            t += 0.1
        self.assertEqual(got, ["Resting Room - Green Herb"])

    def test_room_unknown_falls_back_to_elimination(self):
        got = self.play([(zone_with(), EMPTY), (zone_with((0x30C, 4)), inv_with((34, 1)))])
        self.assertEqual(got, [])
