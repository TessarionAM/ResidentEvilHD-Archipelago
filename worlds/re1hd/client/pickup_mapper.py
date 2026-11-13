"""
Pickup mapper: learns which flag bit belongs to which pickup, just by watching
normal play. READ-ONLY - it never changes the game.

The idea
  Picking something up does two things at the same instant: the item arrives in
  Jill's inventory, and that pickup's "already taken" bit turns on. So:
    * a new bit + a Book of Curses arriving -> there is only one Book of Curses
      pickup in the mansion, so that bit IS "Crypt - Book of Curses";
    * a new bit + a Green Herb arriving -> one of 19 herb pickups. We keep the
      observation and solve it later by elimination (when all other herb
      pickups are known, the last bit must be the last herb).

Some things never enter the inventory. For those the game's "item just picked
up" value (inventory struct +0x50F4, see hd_versions) is used: if a new bit
turns on with NO inventory change, but that value has just switched to an item
id, that id counts as the arriving item. NOTE (2026-11-10): taking the 1F map
did NOT change that value, so maps can't be learned this way - they need the
room checker (or manual confirmation, as was done for the 1F map).

Safety rules
  * Only learn when EXACTLY ONE new bit turns on close in time (POLL_MATCH
    seconds) to EXACTLY ONE kind of item arriving. Anything messier is logged
    and skipped.
  * A bit we already know (or learned) is never reused for another pickup.
  * Nothing learned here becomes a real check by itself: Claude folds the
    learned file into the world (worlds/re1hd/game_data.py) and rebuilds it,
    so everyone's world and client always agree.

Learned results are saved as JSON (see LearnedFile) after every change.
"""

import json
import time
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ZONE = (0x2C0, 0x33C)      # every pickup bit found so far is inside this range;
                           # +0x33C on holds the "room visited" flags (2026-11-10)
POLL_MATCH = 0.5           # seconds: how close a bit and an item must be to pair them

Bit = Tuple[int, int]      # (offset, bit)


def inventory_gains(before, after) -> Dict[int, int]:
    """{item_id: increase} for items whose total count went up (ammo stacks count by amount)."""
    def totals(slots):
        c = Counter()
        for iid, qty in slots or []:
            if iid > 0:
                c[iid] += max(qty, 1)
        return c
    b, a = totals(before), totals(after)
    return {i: a[i] - b[i] for i in a if a[i] > b[i]}


def virtual_slots(defense_counts: Dict[int, int]):
    """Defensive items aren't in inventory slots, only counts ({112: daggers, 121: batteries}).
    Turn them into slot-like (id, count) entries so a count going up looks like an item arriving."""
    return [(iid, n) if n > 0 else (0, 0) for iid, n in sorted(defense_counts.items())]


def new_bits(old: bytes, new: bytes, start: int = ZONE[0]) -> List[Bit]:
    out = []
    for i, (x, y) in enumerate(zip(old, new)):
        turned_on = (x ^ y) & y
        for bit in range(8):
            if turned_on >> bit & 1:
                out.append((start + i, bit))
    return out


class LearnedFile:
    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> dict:
        if self.path.exists():
            return json.loads(self.path.read_text(encoding="utf-8"))
        return {"mappings": {}, "observations": [], "unmatched": []}

    def save(self, data: dict):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        tmp.replace(self.path)


class PickupMapper:
    def __init__(self, catalogue: dict, learned: LearnedFile, log=print, raw_log=None):
        """catalogue: {location name: {"room", "item", "item_id", "known": [off, bit] or None}}"""
        self.cat = catalogue
        self.file = learned
        self.data = learned.load()
        self.log = log
        self.raw_log = raw_log          # if set: every raw observation is reported (for diagnosis)
        self.recent_bits: List[Tuple[float, Bit]] = []
        self.recent_gains: List[Tuple[float, Dict[int, int]]] = []
        self.last_zone: Optional[bytes] = None
        self.last_inv = None
        self.last_picked: Optional[int] = None
        self.recent_picks: List[Tuple[float, int]] = []
        self.rooms: set = set()          # world room name(s) Jill is in, when known
        self._all_gain_times: List[Tuple[float, Dict[int, int]]] = []

    # -- what is already taken
    def known_bits(self) -> Dict[Bit, str]:
        out = {tuple(v["known"]): n for n, v in self.cat.items() if v["known"]}
        out.update({(m["offset"], m["bit"]): n for n, m in self.data["mappings"].items()})
        return out

    def unmapped_locations_for(self, item_id: int) -> List[str]:
        taken = set(self.known_bits().values())
        return [n for n, v in self.cat.items() if v["item_id"] == item_id and n not in taken]

    # -- feed one reading of the game (call ~10x per second)
    def update(self, zone: bytes, inventory, now: Optional[float] = None,
               picked: Optional[int] = None, rooms: Optional[set] = None) -> List[str]:
        """zone = bytes ZONE[0]..ZONE[1] of the flags structure; inventory = 9 (id, qty) slots,
        plus virtual_slots(...) for daggers / battery packs.
        picked = the "item just picked up" value (inventory struct +0x50F4), if available.
        rooms = the world room name(s) Jill is in (from the current-room value), if known.
        Returns names of pickups learned during this call."""
        now = time.time() if now is None else now
        learned = []
        if rooms is not None:
            self.rooms = set(rooms)
        if picked is not None:
            if self.last_picked is not None and picked != self.last_picked:
                if self.raw_log:
                    self.raw_log(f"[raw] 'just picked up' value: {self.last_picked} -> {picked}")
                if picked > 0:
                    self.recent_picks.append((now, picked))
            self.last_picked = picked
        if self.last_zone is not None and len(zone) == len(self.last_zone):
            all_new = new_bits(self.last_zone, zone)
            if self.raw_log and all_new and len(all_new) <= 40:
                known = self.known_bits()
                self.raw_log("[raw] bit(s) turned on: " + ", ".join(
                    f"+{o:#x} bit {b}" + (f" (= {known[(o, b)]})" if (o, b) in known else "")
                    for o, b in all_new))
            bits = [b for b in all_new if b not in self.known_bits()]
            if len(bits) > 40:                      # a load / new game, not a pickup
                bits = []
            self.recent_bits += [(now, b) for b in bits]
            gains = inventory_gains(self.last_inv, inventory) if self.last_inv is not None else {}
            if gains:
                if self.raw_log:
                    self.raw_log(f"[raw] inventory gained: {gains}" + (f" in {sorted(self.rooms)}" if self.rooms else ""))
                self.recent_gains.append((now, gains, set(self.rooms)))
                self._all_gain_times.append((now, gains))
        self.last_zone, self.last_inv = zone, inventory

        # Pair up once both sides have had time to arrive
        still = []
        for t, gains, at_rooms in self.recent_gains:
            if now - t < POLL_MATCH:
                still.append((t, gains, at_rooms))
                continue
            bits = sorted({b for tb, b in self.recent_bits if abs(tb - t) <= POLL_MATCH})
            learned += self._pair(bits, gains, t, at_rooms)
        self.recent_gains = still

        # Things that never enter the inventory (maps): a fresh "just picked up" id
        # with a new bit and NO inventory gain around it.
        still_picks = []
        for t, item in self.recent_picks:
            if now - t < POLL_MATCH:
                still_picks.append((t, item))
                continue
            if any(abs(tg - t) <= POLL_MATCH for tg, _ in self._all_gain_times):
                continue                           # an inventory item - handled above
            bits = sorted({b for tb, b in self.recent_bits if abs(tb - t) <= POLL_MATCH})
            if bits:
                learned += self._pair(bits, {item: 1}, t, set(self.rooms))
        self.recent_picks = still_picks
        self._all_gain_times = [(tg, g) for tg, g in self._all_gain_times if now - tg < 3 * POLL_MATCH]
        self.recent_bits = [(tb, b) for tb, b in self.recent_bits if now - tb < 3 * POLL_MATCH]
        return learned

    def _pair(self, bits: List[Bit], gains: Dict[int, int], t: float, rooms: set = frozenset()) -> List[str]:
        items = list(gains)
        if len(items) != 1 or len(bits) != 1:
            if bits:            # item(s) with no new bit = taken out of the box, etc. - ignore quietly
                self.data["unmatched"].append({"time": t, "bits": bits, "items": items})
                self.file.save(self.data)
                self.log(f"(skipped: {len(bits)} new bit(s) and {len(items)} kind(s) of item at the same moment)")
            return []
        bit, item = bits[0], items[0]
        candidates = self.unmapped_locations_for(item)
        if not candidates:
            self.log(f"(item {item} arrived with new bit +{bit[0]:#x} bit {bit[1]}, "
                     "but no unmapped mansion pickup gives that item - noted)")
            self.data["unmatched"].append({"time": t, "bits": [bit], "items": [item]})
            self.file.save(self.data)
            return []
        if rooms:
            here = [c for c in candidates if self.cat[c]["room"] in rooms]
            if here:
                # Identical items in the same room are interchangeable (same item, same
                # room, same logic), so the first unmapped one is correct either way.
                return self._learn(here[0], bit, f"room + item ({sorted(rooms)[0]})")
        self.data["observations"].append({"offset": bit[0], "bit": bit[1], "item_id": item, "time": t})
        self.file.save(self.data)
        if len(candidates) == 1:
            return self._learn(candidates[0], bit, "only pickup with this item")
        self.log(f"Saw a {self.cat[candidates[0]]['item']} pickup (+{bit[0]:#x} bit {bit[1]}): "
                 f"{len(candidates)} possible spots, will solve by elimination.")
        return self._eliminate()

    def _learn(self, name: str, bit: Bit, how: str) -> List[str]:
        self.data["mappings"][name] = {"offset": bit[0], "bit": bit[1],
                                       "item_id": self.cat[name]["item_id"], "how": how}
        self.data["observations"] = [o for o in self.data["observations"]
                                     if (o["offset"], o["bit"]) != bit]
        self.file.save(self.data)
        self.log(f"LEARNED: {name}  ->  +{bit[0]:#x} bit {bit[1]}  ({how})")
        return [name] + self._eliminate()

    def _eliminate(self) -> List[str]:
        """If, for some item, the unsolved bits seen == the unmapped spots left (exactly 1), solve it."""
        by_item: Dict[int, set] = {}
        for o in self.data["observations"]:
            by_item.setdefault(o["item_id"], set()).add((o["offset"], o["bit"]))
        for item, bits in by_item.items():
            spots = self.unmapped_locations_for(item)
            if len(spots) == 1 and len(bits) == 1:
                return self._learn(spots[0], next(iter(bits)), "last unsolved spot for this item")
        return []
