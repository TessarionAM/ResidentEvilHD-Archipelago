"""
Item box sort (TessarionAM, 2026-11-11: "scrolling through the box takes a lot of time").

Keys first, then quest items, weapons, ammo, healing, defence, ink ribbons, anything else.
Ammo and ink ribbons are merged into full stacks. Empty slots go to the end. The last box
slot (256) holds the client's delivery record and is never touched.
"""
from typing import Dict, List, Optional, Tuple

GROUP_ORDER = ["Keys", "Masks", "Quest", "Weapons", "Ammo", "Healing", "Defence", "Saves"]


# Game items that aren't in our item list (seed test 5: the loaded Grenade Launcher, the Stone
# Ring, herb mixes... always ended up at the bottom). Ids from BhdTool's item table (dinput8.dll);
# anything else 1-140 counts as a quest item rather than "unknown".
OTHER_GROUPS = {
    "Weapons": list(range(1, 16)),               # knives, guns, loaded Grenade Launchers, ...
    "Ammo": list(range(16, 21)) + [89],          # 89 = unused Grenade Shells
    "Healing": list(range(33, 43)) + [101, 104, 105, 130, 131, 132],   # sprays, herbs, mixes, boxes
    "Keys": [43, 44, 45, 46, 47, 48, 49, 50, 54, 55, 62, 63, 110],
    "Masks": [103, 124, 125, 126, 127, 128],
    "Defence": [112, 113, 114, 121],
    "Saves": [68],
}


# Top of the Healing group (TessarionAM, v0.9.2): First Aid Sprays, then First Aid Boxes (sprays in a box).
FIRST_AID_SPRAY, FIRST_AID_BOX = 33, 101
HEALING_FIRST = [FIRST_AID_SPRAY, FIRST_AID_BOX]


def sort_key_table() -> Dict[int, Tuple[int, int]]:
    """game item id -> (group rank, position in the item list)."""
    from ..items import _ITEMS
    out = {}
    for pos, (_name, _kind, gid, group) in enumerate(_ITEMS):
        if gid is not None and gid not in out:
            rank = GROUP_ORDER.index(group) if group in GROUP_ORDER else len(GROUP_ORDER)
            out[gid] = (rank, pos)
    for group, ids in OTHER_GROUPS.items():
        for gid in ids:
            out.setdefault(gid, (GROUP_ORDER.index(group), 1000 + gid))
    for gid in range(1, 141):
        out.setdefault(gid, (GROUP_ORDER.index("Quest"), 1000 + gid))
    healing = GROUP_ORDER.index("Healing")
    for n, gid in enumerate(HEALING_FIRST):
        out[gid] = (healing, -len(HEALING_FIRST) + n)
    return out


def sorted_box(slots: List[Tuple[int, int]], stack_limits: Dict[int, int],
               table: Optional[Dict[int, Tuple[int, int]]] = None) -> List[Tuple[int, int]]:
    """New box contents (same length): sorted, stacks merged, empties last. Nothing is lost:
    the total quantity of every item is the same before and after."""
    table = table if table is not None else sort_key_table()
    items = [(i, q) for i, q in slots if i != 0]
    merged: List[Tuple[int, int]] = []
    totals: Dict[int, int] = {}
    for iid, qty in items:
        if iid in stack_limits and qty > 0:
            totals[iid] = totals.get(iid, 0) + qty
        else:
            merged.append((iid, qty))
    for iid, total in totals.items():
        limit = stack_limits[iid]
        while total > 0:
            merged.append((iid, min(limit, total)))
            total -= limit
    unknown = (len(GROUP_ORDER) + 1, 10_000)
    merged.sort(key=lambda s: (table.get(s[0], unknown), s[0], -s[1]))
    if len(merged) > len(slots):          # can't happen (merging never adds slots), but never lose items
        return list(slots)
    return merged + [(0, 0)] * (len(slots) - len(merged))
