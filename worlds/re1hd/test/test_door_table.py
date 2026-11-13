"""Integrity of the door table (door_table.py, generated from the game) against the world's logic."""
import unittest

from ..data import DOORS
from ..door_table import DOOR_TABLE, KEY_ITEMS, ONE_SIDED_LOCKED, ONE_SIDED_OPENER
from ..game_data import ROOM_NUMBERS

# World requirements that are NOT the door's lock (documented in door-lock-randomiser-decisions.md):
# item chains / events / over-constraints the world keeps on purpose.
NOT_A_LOCK = {
    ("Dark Corridor", "Courtyard Study"): {"Helmet Key"},            # over-constraint; door = Emblem Key
    ("Lab Entrance", "Passage to Heliport"): {"Power Key"},           # escape sequence (GUESS)
    ("Lab Elevator Entry", "Elevator to Main Laboratory"): {"Power Key"},
    ("Gallery", "Plant 42 Room"): {"003 Key", "Control Room Key"},   # event door (GUESS)
}


def door_of(a, b):
    na, nb = ROOM_NUMBERS[a], ROOM_NUMBERS[b]
    return DOOR_TABLE.get(f"{min(na, nb):x}-{max(na, nb):x}")


class DoorTableTest(unittest.TestCase):
    def test_flags_and_one_sided(self):
        for did, d in DOOR_TABLE.items():
            recs = [r for side in d["sides"].values() if side for r in side]
            for key, flag in recs:
                self.assertTrue(0 <= flag < 256, did)
            if d["kind"] == "one_sided":
                types = {k & 0x7F for k, _ in recs}
                self.assertEqual(types, {ONE_SIDED_LOCKED, ONE_SIDED_OPENER}, did)
                self.assertEqual(len({f for _, f in recs}), 1, did)
            if d["kind"] in ("key", "lockpick"):
                flags = {f for k, f in recs if k & 0x7F}
                self.assertEqual(len(flags), 1, f"{did}: locked sides must share one unlock flag")

    def test_world_keys_match_the_game(self):
        """Every key a world link needs is the lock the game has on that door (or a documented exception)."""
        for a, b, req, _one in DOORS:
            keys = {r for r in req if r in KEY_ITEMS.values()} - NOT_A_LOCK.get((a, b), set())
            if not keys:
                continue
            d = door_of(a, b)
            self.assertIsNotNone(d, f"{a} -> {b}: not a real door")
            types = {k & 0x7F for side in d["sides"].values() if side for k, _ in side}
            game_keys = {KEY_ITEMS[t] for t in types if t in KEY_ITEMS}
            self.assertEqual(keys, game_keys, f"{a} -> {b}")

    def test_game_locks_are_in_the_world(self):
        """Every shuffle-eligible door's vanilla lock is what the world requires."""
        for did, d in DOOR_TABLE.items():
            if not d["shuffle"]:
                continue
            self.assertTrue(d["world"], did)
            types = {k & 0x7F for side in d["sides"].values() if side for k, _ in side}
            if d["kind"] == "one_sided":
                self.assertTrue(all(w[3] for w in d["world"]), f"{did}: one-sided must be one-way in the world")
                continue
            want = {KEY_ITEMS[t] for t in types if t in KEY_ITEMS}
            got = {r for w in d["world"] for r in w[2] if r in KEY_ITEMS.values()}
            self.assertEqual(want, got, did)

    def test_counts(self):
        shuffle = [d for d in DOOR_TABLE.values() if d["shuffle"]]
        self.assertEqual(sum(d["kind"] == "key" for d in shuffle), 21)   # + Attic, Library (TessarionAM 11:28)
        self.assertEqual(sum(d["kind"] == "lockpick" for d in shuffle), 4)
        self.assertEqual(sum(d["kind"] == "one_sided" for d in shuffle), 5)
