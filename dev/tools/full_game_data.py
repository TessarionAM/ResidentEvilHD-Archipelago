"""
One-off generator (2026-11-10): turns the full mapping run (pickups paired with their
flag bits, /tmp/pickups_full.json made from hd_event_recorder_events.jsonl) into
world data for the WHOLE game. Prints Python to paste into data.py / game_data.py.
Kept so the derivation can be re-run and checked.
"""
import json
import sys
from collections import defaultdict

sys.path.insert(0, "/home/claude/re_archipelago")
from client.hd_items import item_name  # noqa: E402

P = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "/tmp/pickups_full.json"))

# Not real pickups: made by combining / refilling (they still flip a bit).
CRAFTED = {(0x50A, 0x2FB, 0), (0x11A, 0x304, 0)}   # Fuel Capsule (armed), 2nd Stone & Metal Object

# Our world's item names for game ids (existing names kept; new ones added).
WORLD_ITEM = {
    4: "Self-Defence Gun", 6: "Shotgun", 7: "Grenade Launcher", 11: "Magnum", 15: "Barry's Magnum",
    16: "Grenade Shells", 17: "Handgun Magazine", 18: "Shotgun Shells", 19: "Acid Shells",
    20: "Incendiary Shells", 21: "Golden Arrow", 22: "Book of Curses", 24: "Collar", 25: "Magnum Rounds",
    27: "Fuel Canteen", 30: "Gallery Key", 32: "Missing Music", 33: "First Aid Spray", 34: "Green Herb",
    35: "Red Herb", 36: "Blue Herb", 43: "Lock Pick", 46: "Armor Key", 47: "Shield Key", 48: "Helmet Key",
    49: "001 Key", 50: "003 Key", 53: "Stone & Metal Object", 54: "Power Key", 55: "Master Key",
    56: "Star Crest", 57: "Wind Crest", 58: "Sun Crest", 59: "Moon Crest", 60: "Square Crank",
    61: "Hexagonal Crank", 65: "Metal Object", 66: "Knife", 67: "Battery", 68: "Ink Ribbon",
    69: "Wooden Emblem", 70: "Gold Emblem", 72: "Red Jewel", 73: "Blue Gemstone", 74: "Yellow Jewel",
    75: "Broken Shotgun", 76: "Herbicide", 77: "Lighter", 78: "Serum", 90: "Red Book",
    91: "Last Book, vol. 1", 92: "Last Book, vol. 2", 93: "MO Disk 1", 94: "MO Disk 2", 95: "MO Disk 3",
    96: "Dog Whistle", 97: "Fuse Unit", 99: "Jewelry Box (Stone Ring)", 100: "Insecticide Spray",
    101: "First Aid Box", 102: "Jewelry Box (Broach)", 103: "Mask without eyes, nose, or mouth",
    104: "First Aid Box", 106: "Signal Rockets", 107: "Broken Flamethrower", 108: "Wooden Mount",
    109: "Slide Filter", 110: "Control Room Key", 111: "Fuel Capsule", 112: "Dagger",
    115: "Bee Specimen", 116: "Lure without a hook", 117: "Fishhook", 119: "X-Ray 1", 120: "X-Ray 2",
    121: "Battery Pack", 122: "Shaft", 123: "Cylinder", 126: "Mask without eyes",
    127: "Mask without a nose", 128: "Mask without a mouth", 129: "Music, mid-pages",
    131: "First Aid Box", 132: "First Aid Box",
}

# Game room number -> our region name, for rooms NEW to the world (Mansion extras + Part 2).
NEW_ROOMS = {
    0x111: "Large Art & Mirror Rooms", 0x215: "Trophy Room", 0x216: "Library", 0x213: "Elevator Corridor",
    0x219: "Materials Room", 0x119: "Courtyard Study",
    0x300: "Main Garden", 0x301: "Water Pool", 0x302: "Falls Area", 0x304: "Zigzag Path",
    0x311: "Muddy Path", 0x312: "Small Headstone Area", 0x313: "Forest Pathway", 0x314: "Cabin",
    0x307: "Cave Entrance Passage", 0x308: "Forked Passage", 0x309: "Generator Room", 0x30A: "Enrico Room",
    0x30B: "Boulder Passage 1", 0x30C: "Spider Room", 0x30D: "Straight Passage", 0x30F: "Boulder Passage 2",
    0x306: "Underground Statue Room", 0x316: "Garbage Compactor Room", 0x317: "Winding Underground",
    0x318: "Underground Storage Room", 0x319: "Lisa's Room",
    0x31A: "Altar Stairway Passage", 0x315: "Jessica's Tomb", 0x305: "Fountain",
    0x400: "Residence Entry Corridor", 0x401: "Room 001", 0x402: "Room 001 Bathroom",
    0x403: "Residence Storeroom", 0x404: "Rec Room", 0x405: "Residence Central Corridor",
    0x406: "Room 002", 0x407: "Room 002 Bathroom", 0x408: "Gallery", 0x40A: "Room 003",
    0x40C: "Plant 42 Room", 0x40D: "Aqua Ring Entry", 0x410: "Aqua Ring Storage", 0x411: "Control Room",
    0x412: "Aqua Ring Water Tank",
    0x500: "Lab Entrance", 0x501: "Passage to Heliport", 0x502: "Lab Item Box Room", 0x503: "Lab Stairway",
    0x504: "Visual Data Room", 0x505: "'O' Room", 0x506: "Operating Room", 0x507: "Morgue",
    0x508: "Pass Code Corridor", 0x509: "X-Ray Room B", 0x50A: "X-Ray Room A", 0x50B: "Cell Entrance",
    0x50C: "Lab Elevator Entry", 0x50D: "Heliport Elevator", 0x50E: "Lounge Room", 0x50F: "Power Maze A",
    0x510: "Power Maze B", 0x511: "Power Control Room", 0x512: "Cell", 0x513: "Main Laboratory",
    0x514: "Main Laboratory Entrance", 0x515: "Elevator to Main Laboratory", 0x303: "Heliport",
    # existing world rooms that gained NEW pickups (not in the Evil Resource Part 1 list)
    0x11B: "Garden Shed", 0x10D: "Tiger Statue Room", 0x20C: "Secret Passage",
}


def main():
    import os
    sys.path.insert(0, os.getcwd())                # run from the Archipelago folder
    from worlds.re1hd.data import PICKUPS
    from worlds.re1hd.game_data import ROOM_NUMBERS
    from worlds.re1hd.items import item_table
    # existing world pickups -> claim matching log entries (same room number + game item id)
    pool = defaultdict(list)
    for p in sorted(P, key=lambda p: (p["off"], p["bit"])):
        if (p["room"], p["off"], p["bit"]) not in CRAFTED:
            pool[(p["room"], p["item"])].append(p)
    fixed_gid = {"Missing Music": 32, "Music, mid-pages": 129, "Mask without eyes, nose, or mouth": 103,
                 "First Aid Box": 101}
    detected = {}
    for room, name, item, _ in PICKUPS:
        nb = ROOM_NUMBERS.get(room)
        gid = fixed_gid.get(item, item_table[item].game_id)
        cands = pool.get((nb, gid)) or ([] if item != "First Aid Box" else
                                         [c for k, v in pool.items() if k[0] == nb and k[1] in (101, 104, 131, 132) for c in v])
        if cands:
            c = cands.pop(0)
            for k, v in pool.items():
                if c in v:
                    v.remove(c)
            detected[name] = (c["off"], c["bit"], c["item"])
    print("# existing pickups detected:", len(detected), "of", len(PICKUPS))
    # leftovers = new pickups
    new = defaultdict(list)
    left_old_rooms = []
    for (nb, gid), lst in pool.items():
        for c in lst:
            if nb in NEW_ROOMS:
                new[nb].append(c)
            else:
                left_old_rooms.append(c)
    print("# leftovers in old rooms:", [(hex(c['room']), item_name(c['item']), hex(c['off']), c['bit'])
                                      for c in left_old_rooms])
    lines, det_new = [], {}
    for nb in sorted(new):
        room = NEW_ROOMS[nb]
        counts = defaultdict(int)
        items = sorted(new[nb], key=lambda c: (c["off"], c["bit"]))
        totals = defaultdict(int)
        for c in items:
            totals[WORLD_ITEM[c["item"]]] += 1
        for c in items:
            it = WORLD_ITEM[c["item"]]
            counts[it] += 1
            nm = f"{room} - {it}" + (f" {counts[it]}" if totals[it] > 1 else "")
            lines.append(f'    ("{room}", "{nm}", "{it}", ()),') if "'" not in room else \
                lines.append(f'    ("{room}", "{nm}", "{it}", ()),')
            det_new[nm] = (c["off"], c["bit"], c["item"])
    json.dump({"existing": detected, "new": det_new, "lines": lines}, open("/tmp/fullgame_gen.json", "w"), indent=1)
    print("\n".join(lines))
    print("# new:", len(det_new))


if __name__ == "__main__":
    main()
