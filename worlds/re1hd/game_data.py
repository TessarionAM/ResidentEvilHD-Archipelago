"""
Game-memory facts shared by the world (generation) and the client.

Everything here was found by us in-game on TessarionAM's PC (Steam build
6699874012183562949, Jill, Normal, 2026-11-09). See the project notes
claude/pickup-flags.md and claude/milestone-7-replace-pickups.md.

DETECTED_PICKUPS: location name -> (flag offset, bit, vanilla game item id)
  The flag offset is relative to the structure the pointer at bhd.exe
  0x00CF2FC8 points to; the bit turns on when the pickup is taken.
  Only CONFIRMED inventory pickups are listed. When a pickup is added here it
  becomes a randomised check (with the "only_detected_pickups" option on).

DELIVERY_QUANTITY: game item id -> quantity written into the item box.
  Values seen in-game where known; everything else defaults to 1.
"""

DETECTED_PICKUPS = {
    # --- Mansion (Evil Resource list). Bits from the full mapping run 2026-11-10 (and the
    #     first 11, confirmed one by one on 2026-11-09). ---
    "Main Hall - Lock Pick (Barry)": (0x2DC, 1, 43),
    "Dining Room - Ink Ribbons": (0x2F2, 1, 68),
    "Dining Room - Wooden Emblem": (0x2EC, 4, 69),
    "Dining Room - Blue Gemstone": (0x2EC, 2, 73),
    "Dining Room - Shield Key": (0x2EC, 3, 47),
    "Dining Room 2F - Dagger": (0x2F0, 7, 112),
    "Bar - Missing Music": (0x2EC, 5, 32),
    "Bar - Gold Emblem": (0x2EC, 7, 70),
    "Art Room - Dagger": (0x2E6, 2, 112),
    "'L' Corridor - Dagger": (0x2F4, 1, 112),
    "'L' Corridor - Handgun Magazine": (0x2F4, 0, 17),
    "Bathroom - Dagger": (0x2E9, 4, 112),
    "Living Room - Dagger": (0x2F6, 1, 112),
    "Living Room - Ink Ribbons": (0x2F6, 3, 68),
    "Living Room - Shotgun": (0x2F5, 7, 6),
    "Outside Boiler - Herbicide": (0x2ED, 0, 76),
    "Outside Boiler - Green Herb 1": (0x2F2, 3, 34),
    "Outside Boiler - Green Herb 2": (0x2F2, 4, 34),
    "Outside Boiler - Red Herb": (0x2F2, 5, 35),
    "Large Gallery - Mask without a mouth": (0x304, 3, 128),
    "Graveyard - Shotgun Shells": (0x315, 6, 18),
    "Crypt - Book of Curses": (0x2E9, 2, 22),
    "Crypt - Shotgun Shells": (0x315, 7, 18),
    "Crypt - Stone & Metal Object": (0x2E9, 3, 53),
    "East Wing Storeroom - Fuel Canteen": (0x2E4, 4, 27),
    "East Wing Storeroom - First Aid Spray (Barry)": (0x2E7, 2, 33),
    "East Wing Storeroom - Incendiary Shells (Barry)": (0x2E7, 1, 20),
    "West Wing Outer Stairway - Handgun Magazine": (0x307, 5, 17),
    "West Wing Outer Stairway - Green Herb 1": (0x307, 6, 34),
    # "Mansion Drug Room - Serum": (0x2EC, 0, 78) - KEPT VANILLA (data.KEEP_VANILLA), so the
    # client neither sends it nor takes the Serum back.
    "Small Storeroom - Battery Pack": (0x2E4, 2, 121),
    "Small Storeroom - Broken Shotgun": (0x2E4, 0, 75),
    "Small Storeroom - Ink Ribbons": (0x2E4, 3, 68),
    "Northern Corridor - Battery Pack": (0x2E0, 0, 121),
    "Researcher's Bedroom - Handgun Magazine": (0x305, 2, 17),
    "Researcher's Bedroom - Battery Pack": (0x309, 7, 121),
    "Tiger Statue Room - Shotgun Shells": (0x304, 1, 18),
    "Greenhouse - Green Herb 1": (0x2F4, 2, 34),
    "Greenhouse - Green Herb 2": (0x2F4, 3, 34),
    "Greenhouse - Green Herb 3": (0x2F4, 4, 34),
    "Greenhouse - Green Herb 4": (0x2F4, 5, 34),
    "Greenhouse - Green Herb 5": (0x2F4, 6, 34),
    "Greenhouse - Mask without eyes": (0x2F4, 7, 126),
    "Mirror Corridor - Golden Arrow": (0x2E9, 1, 21),
    "Mirror Corridor - Green Herb": (0x2E6, 4, 34),
    "Mirror Corridor - Handgun Magazine": (0x2E8, 3, 17),
    "'Death' Passage - Armor Key": (0x306, 5, 46),
    "Outside Balcony - Collar (Cerberus)": (0x2F6, 7, 24),
    "Outside Patio - Dagger": (0x305, 0, 112),
    "Outside Patio - Grenade Launcher": (0x305, 6, 7),
    "Outside Patio - Green Herb 1": (0x304, 6, 34),
    "Outside Patio - Green Herb 2": (0x304, 7, 34),
    "'C' Corridor - Wooden Mount": (0x2E0, 6, 108),
    "Small Library - Dog Whistle": (0x2EB, 4, 96),
    "Small Library - Handgun Magazine": (0x2E7, 7, 17),
    "Small Library - Lighter": (0x2E6, 1, 77),
    "Armor Room - Mask without eyes, nose, or mouth": (0x304, 2, 103),
    "Pillar Room - Green Herb 1": (0x2F7, 1, 34),
    "Pillar Room - Green Herb 2": (0x2F7, 2, 34),
    "Attic - Mask without a nose": (0x2DE, 1, 127),
    "Small Dining Room - Handgun Magazine (Table)": (0x2E6, 5, 17),
    "Small Dining Room - Handgun Magazine (Cabinet)": (0x2E8, 2, 17),
    "Small Dining Room - Music, mid-pages": (0x2E4, 1, 129),
    "Resting Room - Green Herb": (0x305, 3, 34),
    "Deer Room - Red Herb": (0x309, 1, 35),
    "Bedroom - First Aid Box": (0x2F3, 2, 101),
    "Bedroom - Ink Ribbons": (0x2F3, 3, 68),
    "Bedroom - Green Herb": (0x2F3, 4, 34),
    "Fish Tank Room - Fishhook": (0x2ED, 5, 117),
    "Fish Tank Room - Bee Specimen": (0x2ED, 3, 115),
    "Fish Tank Room - Lure without a hook": (0x2ED, 4, 116),
    "Fish Tank Room - Wind Crest": (0x2ED, 2, 57),
    "Kitchen - Dagger": (0x2E6, 3, 112),
    "Concrete Passage 2 - Red Herb": (0x2E8, 5, 35),
    "Concrete Passage 2 - Blue Herb": (0x2E8, 6, 36),
    "Concrete Passage 2 - Dagger": (0x2E6, 7, 112),
    "Concrete Passage 2 - Handgun Magazine": (0x2E6, 6, 17),
    "Concrete Passage 1 - Shotgun Shells": (0x2F7, 4, 18),
    "Secret Passage - Last Book Vol. 1": (0x2E0, 2, 91),
    "West Wing Outer Stairway - Green Herb 2": (0x307, 7, 34),
    # --- The rest of the game, seen in TessarionAM's full run 2026-11-10 (tools/full_game_data.py) ---
    "Tiger Statue Room - MO Disk 1": (0x307, 1, 93),
    "Large Art & Mirror Rooms - Dagger": (0x2F5, 0, 112),
    "Large Art & Mirror Rooms - Ink Ribbon": (0x2F5, 1, 68),
    "Large Art & Mirror Rooms - Green Herb": (0x2F5, 2, 34),
    "Large Art & Mirror Rooms - Jewelry Box (Broach)": (0x2F5, 6, 102),
    "Courtyard Study - Metal Object": (0x2ED, 1, 65),
    "Courtyard Study - Shotgun Shells": (0x2F3, 0, 18),
    "Courtyard Study - Battery Pack": (0x2F3, 1, 121),
    "Garden Shed - Shotgun Shells": (0x2E5, 7, 18),
    "Garden Shed - First Aid Spray 1": (0x2E6, 0, 33),
    "Garden Shed - Battery Pack 1": (0x2E8, 7, 121),
    "Garden Shed - Battery Pack 2": (0x2EA, 7, 121),
    "Garden Shed - Grenade Shells": (0x2EB, 0, 16),
    "Garden Shed - First Aid Spray 2": (0x2EB, 1, 33),
    "Secret Passage - Dagger": (0x2E0, 1, 112),
    "Elevator Corridor - Green Herb 1": (0x2E0, 3, 34),
    "Elevator Corridor - Red Herb": (0x2E0, 4, 35),
    "Elevator Corridor - Green Herb 2": (0x2E0, 5, 34),
    "Trophy Room - Yellow Jewel": (0x2ED, 6, 74),
    "Trophy Room - Red Jewel": (0x2ED, 7, 72),
    "Trophy Room - Dagger": (0x2F3, 6, 112),
    "Trophy Room - Grenade Shells": (0x2F3, 7, 16),
    "Library - Green Herb 1": (0x304, 4, 34),
    "Library - Green Herb 2": (0x305, 1, 34),
    "Library - Last Book, vol. 2": (0x309, 4, 92),
    "Materials Room - Shotgun Shells": (0x2DF, 0, 18),
    "Materials Room - Acid Shells": (0x2DF, 1, 19),
    "Materials Room - Battery Pack": (0x2DF, 2, 121),
    "Materials Room - Battery": (0x2DF, 6, 67),
    "Main Garden - Green Herb": (0x307, 2, 34),
    "Main Garden - Blue Herb": (0x307, 4, 36),   # client log 2026-11-11 03:24 and 11-12 04:01: Blue Herb + this bit
    "Heliport - Signal Rockets": (0x304, 5, 106),
    "Zigzag Path - Red Herb": (0x2F0, 6, 35),
    "Underground Statue Room - Cylinder": (0x30C, 7, 123),
    "Mining Area - Green Herb": (0x2EA, 4, 34),
    "Mining Area - Ink Ribbon": (0x2EB, 5, 68),
    "Generator Room - Handgun Magazine 1": (0x305, 4, 17),
    "Generator Room - Shaft": (0x306, 7, 122),
    "Generator Room - Handgun Magazine 2": (0x30A, 5, 17),
    "Enrico Room - Hexagonal Crank": (0x2F8, 0, 61),
    "Boulder Passage 1 - Shotgun Shells": (0x2F1, 0, 18),
    "Spider Room - Knife": (0x30C, 3, 66),
    "Straight Passage - Blue Herb 1": (0x2F0, 3, 36),
    "Straight Passage - Blue Herb 2": (0x2F0, 4, 36),
    "Boulder Passage 2 - First Aid Box": (0x2F1, 1, 101),
    "Small Headstone Area - Magnum": (0x2E9, 5, 11),
    "Small Headstone Area - Star Crest": (0x2E9, 6, 56),
    "Small Headstone Area - Moon Crest": (0x2E9, 7, 59),
    "Small Headstone Area - Sun Crest": (0x2EA, 0, 58),
    "Cabin - Square Crank": (0x2E8, 0, 60),
    "Jessica's Tomb - Barry's Magnum": (0x2EB, 3, 15),
    "Garbage Compactor Room - Broken Flamethrower": (0x306, 2, 107),
    "Winding Underground Passage - Green Herb": (0x2FC, 3, 34),
    "Winding Underground Passage - Red Herb": (0x2FC, 4, 35),
    "Underground Storage Room - Handgun Magazine": (0x30A, 7, 17),
    "Underground Storage Room - Magnum Rounds": (0x30B, 0, 25),
    "Underground Storage Room - Battery Pack": (0x30B, 2, 121),
    "Lisa's Room - Jewelry Box (Stone Ring)": (0x30C, 4, 99),
    "Lisa's Room - Green Herb": (0x30E, 2, 34),
    "Lisa's Room - Blue Herb": (0x30E, 3, 36),
    "Residence Entry Corridor - Blue Herb 1": (0x2F8, 1, 36),
    "Residence Entry Corridor - Blue Herb 2": (0x2F8, 2, 36),
    "Residence Entry Corridor - Blue Herb 3": (0x2F8, 3, 36),
    "Room 001 - Handgun Magazine": (0x2FC, 0, 17),
    "Room 001 - Self-Defence Gun": (0x306, 3, 4),
    "Room 001 Bathroom - Control Room Key": (0x306, 4, 110),
    "Residence Storeroom - Battery Pack": (0x2F8, 4, 121),
    "Residence Storeroom - Ink Ribbon": (0x2F8, 5, 68),
    "Rec Room - Green Herb 1": (0x2F8, 7, 34),
    "Rec Room - Green Herb 2": (0x2F9, 0, 34),
    "Rec Room - First Aid Box": (0x2F9, 1, 131),
    "Rec Room - Shotgun Shells": (0x2F9, 2, 18),
    "Rec Room - Red Book": (0x2F9, 3, 90),
    "Room 002 Bathroom - 001 Key": (0x309, 6, 49),
    "Gallery - Insecticide Spray": (0x308, 2, 100),
    "Gallery - 003 Key": (0x308, 3, 50),
    "Gallery - Red Herb": (0x30B, 3, 35),
    "Gallery - Handgun Magazine": (0x30B, 5, 17),
    "Plant 42 Room - Helmet Key": (0x2E4, 5, 48),
    "Aqua Ring Entry - Green Herb": (0x30C, 5, 34),
    "Aqua Ring Exit - Magnum Rounds": (0x30C, 6, 25),
    "Aqua Ring Storage - Shotgun Shells": (0x308, 6, 18),
    "Control Room - First Aid Box": (0x2FB, 1, 132),
    "Aqua Ring Water Tank - Gallery Key": (0x30C, 0, 30),
    "Passage to Heliport - Fuse Unit": (0x2FA, 1, 97),
    "Passage to Heliport - Shotgun Shells": (0x2FA, 2, 18),
    "Passage to Heliport - First Aid Box": (0x2FA, 3, 104),
    "Lab Item Box Room - Ink Ribbon": (0x2FC, 2, 68),
    "Lab Stairway - MO Disk 2": (0x30C, 1, 94),
    "Lab Stairway - Green Herb 1": (0x30D, 3, 34),
    "Lab Stairway - Green Herb 2": (0x30D, 4, 34),
    "Visual Data Room - First Aid Spray": (0x2EA, 5, 33),
    "Visual Data Room - Power Key": (0x30E, 0, 54),
    "Visual Data Room - MO Disk 3": (0x30E, 6, 95),
    "Visual Data Room - Shotgun Shells": (0x30F, 0, 18),
    "'O' Room - Dagger": (0x2EA, 6, 112),
    "Operating Room - First Aid Box": (0x2F0, 2, 104),
    "Operating Room - Battery Pack": (0x2F1, 3, 121),
    "Operating Room - Magnum Rounds": (0x2F1, 4, 25),
    "Morgue - Battery Pack": (0x2F9, 4, 121),
    "Morgue - Shotgun Shells": (0x2FB, 3, 18),
    "Pass Code Corridor - First Aid Box": (0x2EB, 7, 132),
    "X-Ray Room B - X-Ray 2": (0x30C, 2, 120),
    "X-Ray Room B - X-Ray 1": (0x30E, 7, 119),
    "X-Ray Room A - Incendiary Shells": (0x2F1, 6, 20),
    "X-Ray Room A - Slide Filter": (0x2FA, 7, 109),
    "Lounge Room - Grenade Shells": (0x2F9, 5, 16),
    "Lounge Room - Ink Ribbon": (0x2F9, 7, 68),
    "Lounge Room - First Aid Spray": (0x2FA, 0, 33),
    "Power Maze A - Fuel Capsule": (0x2EA, 2, 111),
    "Power Maze B - Battery Pack": (0x2F1, 7, 121),
    "Main Laboratory - Master Key": (0x30E, 5, 55),
    "Main Laboratory Entrance - Shotgun Shells": (0x30F, 3, 18),
    "Cell - Shotgun Shells": (0x2FB, 4, 18),        # 2026-11-14: seen twice in the Cell (see data.py)
    # Maps (extra checks, map_checks option). The player keeps the map.
    "Art Room - Map of the Mansion 1F": (0x316, 0, 130),   # confirmed 2026-11-10 (only bit, clean run)
    # Found in the full mapping run 2026-11-10: one bit, no item gained, in the map's room.
    "Resting Room - Map of the Mansion 2F": (0x316, 2, 130),
    "Concrete Passage 1 - Map of the Mansion B1": (0x316, 3, 130),
    "Cabin - Map of the Courtyard": (0x316, 4, 130),
    "Straight Passage - Map of the Caves": (0x316, 5, 130),
    "Residence Central Corridor - Map of the Residence": (0x316, 7, 130),
    "Control Room - Map of the Aqua Ring": (0x317, 0, 130),
    "Visual Data Room - Map of the Laboratory": (0x317, 1, 130),
}
# Files (data.FILE_CHECKS): flag bit, FILE_MARKER = "a file" (our marker, no real item; nothing is
# taken back). It was 131 until v0.7.6 - but 131 is a real First Aid Box, so the Rec Room one was
# never taken back (seed test 5).
FILE_MARKER = 9001
from .data import FILE_CHECKS as _FILE_CHECKS
DETECTED_PICKUPS.update({name: (off, bit, FILE_MARKER) for _room, name, off, bit in _FILE_CHECKS})

DELIVERY_QUANTITY = {
    17: 15,     # Handgun Magazine: pickups gave 15 rounds (seen 2026-11-09)
    18: 6,      # Shotgun Shells: the Graveyard pickup gave 6 (seen 2026-11-10)
    43: 0,      # Lock Pick: the game stores it with quantity 0
    3: 15,      # Handgun: a new game starts with {3, 15} (loaded)
    # Seen in the full mapping run 2026-11-10 (quantity the pickup gave):
    6: 6, 7: 6, 11: 6, 15: 6,          # Shotgun / Grenade Launcher / Magnum / Barry's Magnum come loaded
    13: 10,                            # Assault Shotgun: "comes loaded with 10 shells" (Evil Resource)
    10: 1,                             # Rocket Launcher: quantity to be checked in-game
    16: 6, 19: 6, 20: 6, 25: 6,        # Grenade / Acid / Incendiary shells, Magnum Rounds
    68: 3,                             # Ink Ribbons
    46: 7, 48: 4, 54: 2, 55: 2,        # Armor / Helmet / Power / Master Key: number of doors they open
}

# Lock Pick (43) normally lives in hidden slot 1, not the inventory, so the
# client puts a received Lock Pick there instead of the item box.
HIDDEN_SLOT_ITEMS = {43}

# The LAST item box slot (256, index 255) keeps {0, number of received items delivered}. The
# box is saved with the game, so after loading an older save (e.g. after dying) the client
# knows exactly which received items that save is missing and delivers them again.
SAVE_MARKER_SLOT = 255
SEED_TAG_SLOT = 254           # box slot 255: {0, seed tag} - which seed this save belongs to

# Items that STACK when sent to the item box (TessarionAM, 2026-11-11): added onto an existing box
# stack of the same item instead of taking a new slot. Ammo and ink ribbons; the limit is the
# largest stack seen in-game (Handgun Magazine reached 255 in TessarionAM's full run).
# Max stack per box slot. Ammo: 255 (TessarionAM's stack test, 2026-11-11). Ink Ribbons go past 255
# (he reached 340), TessarionAM chose 250 for them.
# 13 Assault Shotgun comes loaded with 10 shells (Evil Resource, Attic).
STACK_LIMITS = {16: 255, 17: 255, 18: 255, 19: 255, 20: 255, 25: 255, 68: 250}

# The item box of a NEW game holds a First Aid Spray and 3 Ink Ribbons (TessarionAM, 2026-11-11).
# TessarionAM's change: the spray becomes a random item; the ribbons become 99, or (with autosave on)
# another random item. The client does this once it sees that exact vanilla box.
VANILLA_BOX_SPRAY, VANILLA_BOX_RIBBON = 33, (68, 3)
START_BOX_RIBBONS = 99

# Handed straight to Jill's INVENTORY even when received items go to the item box: every item
# box needs the Sword Key (Book of Curses, 22) to reach, so it must never wait in a box
# (seed test 1, 2026-11-10). If her inventory is full the client waits and asks for room.
DIRECT_INVENTORY_ITEMS = {22, 107}     # Book of Curses, Broken Flamethrower (no item box below the cave lift)


def delivery_quantity(game_id: int) -> int:
    return DELIVERY_QUANTITY.get(game_id, 1)


# ---------------------------------------------------------------------------
# ROOMS. The game keeps the current room as two int32s (stage, room) at
# flags structure -0x3E0 (found by us 2026-11-10, room finder + live watcher;
# the copy at -0x404 changes ~1 s earlier = the room a door is leading to).
# Room number = stage * 0x100 + room, numbering and names from BhdTool's
# rooms.json by eleval (GPL-3.0, credited in THIRD_PARTY.md).
# Our world uses Evil Resource's names; this maps them to the game's numbers.
# None = not in BhdTool's list (probably one of the unlisted numbers) - to be
# found by visiting with the room watcher.
ROOM_NUMBERS = {
    "Main Hall": 0x106, "Dining Room": 0x105, "Tea Room": 0x103, "Bar": 0x10F,
    "Art Room": 0x107, "'L' Corridor": 0x108, "Winding Corridor": 0x109, "Bathroom": 0x109,
    "Marble Room": 0x115, "Living Room": 0x116, "Outside Boiler": 0x114, "Dark Corridor": 0x10A,
    "Roofed Passage": 0x11A, "Large Gallery": 0x117, "Graveyard": 0x10B,
    "East Wing Stairway": 0x207, "East Wing Storeroom": 0x118, "West Wing Outer Stairway": 0x112,
    "West Wing Inner Stairway": 0x101, "Mansion Drug Room": 0x100, "Small Storeroom": 0x102,
    "Northern Corridor": 0x103, "Greenhouse": 0x10C, "Researcher's Bedroom": 0x10E,
    "Tiger Statue Room": 0x10D,
    "Dining Room 2F": 0x202, "Mirror Corridor": 0x214, "'Death' Passage": 0x217,
    "Outside Balcony": 0x203, "Outside Patio": 0x212, "'C' Corridor": 0x204, "Small Library": 0x206,
    "Armor Room": 0x205, "Pillar Room": 0x20D, "Attic Entry": 0x20E, "Attic": 0x210,
    "Small Dining Room": 0x20F, "Resting Room": 0x20B, "Deer Room": 0x208, "Bedroom": 0x209,
    "Fish Tank Room": 0x20A,
    "Crypt": 0x10B, "Kitchen": 0x21C, "Concrete Passage 2": 0x21B, "Concrete Passage 1": 0x21A,
    "Secret Passage": 0x20C,
    "Garden Shed": 0x11B,
    # The rest of the game (2026-11-10; numbers from BhdTool, all visited in TessarionAM's run)
    "Large Art & Mirror Rooms": 0x111,
    "Courtyard Study": 0x119,
    "Elevator Corridor": 0x213,
    "Trophy Room": 0x215,
    "Library": 0x216,
    "Materials Room": 0x219,
    "Main Garden": 0x300,
    "Water Pool": 0x301,
    "Falls Area": 0x302,
    "Heliport": 0x303,
    "Zigzag Path": 0x304,
    "Fountain": 0x305,
    "Underground Statue Room": 0x306,
    "Mining Area": 0x307,
    "Forked Passage": 0x308,
    "Generator Room": 0x309,
    "Enrico Room": 0x30A,
    "Boulder Passage 1": 0x30B,
    "Spider Room": 0x30C,
    "Straight Passage": 0x30D,
    "Boulder Passage 2": 0x30F,
    "Muddy Path": 0x311,
    "Small Headstone Area": 0x312,
    "Forest Pathway": 0x313,
    "Cabin": 0x314,
    "Jessica's Tomb": 0x315,
    "Garbage Compactor Room": 0x316,
    "Winding Underground Passage": 0x317,
    "Underground Storage Room": 0x318,
    "Lisa's Room": 0x319,
    "Altar Stairway Passage": 0x31A,
    "Residence Entry Corridor": 0x400,
    "Room 001": 0x401,
    "Room 001 Bathroom": 0x402,
    "Residence Storeroom": 0x403,
    "Rec Room": 0x404,
    "Residence Central Corridor": 0x405,
    "Room 002": 0x406,
    "Room 002 Bathroom": 0x407,
    "Gallery": 0x408,
    "Room 003": 0x40A,
    "Plant 42 Room": 0x40C,
    "Aqua Ring Entry": 0x40D, "Aqua Ring Walkway": 0x40E, "Guard Room": 0x40F,
    "Aqua Ring Storage": 0x410,
    "Control Room": 0x411,
    "Aqua Ring Water Tank": 0x412,
    "Lab Entrance": 0x500,
    "Passage to Heliport": 0x501,
    "Lab Item Box Room": 0x502,
    "Lab Stairway": 0x503,
    "Visual Data Room": 0x504,
    "'O' Room": 0x505,
    "Operating Room": 0x506,
    "Morgue": 0x507,
    "Pass Code Corridor": 0x508,
    "X-Ray Room B": 0x509,
    "X-Ray Room A": 0x50A,
    "Cell Entrance": 0x50B,
    "Lab Elevator Entry": 0x50C,
    "Heliport Elevator": 0x50D,
    "Lounge Room": 0x50E,
    "Power Maze A": 0x50F,
    "Power Maze B": 0x510,
    "Power Control Room": 0x511,
    "Cell": 0x512,
    "Main Laboratory": 0x513,
    "Main Laboratory Entrance": 0x514,
    "Elevator to Main Laboratory": 0x515,
}
# Tea Room and Northern Corridor are ONE room in the game (0x103); both our names map to it.

# "Room visited" flags (found 2026-11-10 from the full mapping run): the game keeps one
# saved bit per room, set ~5 s after you first enter it. Bit index = stage start + room
# index, counted from flags +0x33C. 80 rooms across all 5 stages were seen at exactly
# the predicted bit (ROOM_VISITED_VERIFIED); the rest are predicted only, so the client
# uses the live room number for those and logs whether the predicted flag agrees.
ROOM_VISITED_BASE = 0x33C
ROOM_VISITED_STAGE_START = {1: 0, 2: 37, 3: 72, 4: 104, 5: 129}
ROOM_VISITED_VERIFIED = frozenset({
    0x100, 0x103, 0x108, 0x109, 0x10a, 0x10b, 0x10c, 0x10d, 0x10e, 0x111, 0x112, 0x114, 0x115, 0x116, 0x118, 0x119, 0x11a, 0x200, 0x202, 0x203, 0x204, 0x205, 0x206, 0x208, 0x20a, 0x20b, 0x20c, 0x20d, 0x20e, 0x210, 0x212, 0x215, 0x217, 0x219, 0x21a, 0x21b, 0x21c, 0x302, 0x304, 0x306, 0x307, 0x30a, 0x30b, 0x30f, 0x311, 0x312, 0x313, 0x314, 0x317, 0x318, 0x319, 0x400, 0x401, 0x403, 0x405, 0x408, 0x40a, 0x40c, 0x40d, 0x410, 0x500, 0x501, 0x502, 0x503, 0x504, 0x505, 0x506, 0x507, 0x50a, 0x50b, 0x50c, 0x50d, 0x50e, 0x50f, 0x510, 0x511, 0x512, 0x513, 0x514, 0x515})


def room_visited_flag(number: int):
    """(flags offset, bit) of the game's "room visited" flag for a room number, or None."""
    if number is None or (number >> 8) not in ROOM_VISITED_STAGE_START:
        return None
    index = ROOM_VISITED_STAGE_START[number >> 8] + (number & 0xFF)
    return ROOM_VISITED_BASE + index // 8, index % 8
GOAL_ROOM_NUMBER = 0x11B      # Garden Shed: reaching it completes goal mansion_escape


# Random starting inventory (option random_starting_inventory). A NEW game starts with
# exactly these two inventory slots filled (seen 2026-11-10 on a new game: {3,15}, {1,1}).
VANILLA_START = [(3, 15), (1, 1)]
EQUIPPED_SLOT_OFFSET = 0x80     # hidden slot 2: the equipped weapon (Handgun in a new game)
START_ROOM_NUMBER = 0x106       # Main Hall


# Special items (TessarionAM's picks, 2026-11-12) ----------------------------------------------
# Defence Bundle: a pseudo item id (no such item in the game, like FILE_MARKER 9001). The client
# adds these to Jill's defensive-item counters. Claude's choice: one of each (the vanilla game
# has few daggers, so a bundle of 2+2 felt too strong; change here if TessarionAM wants more).
DEFENCE_BUNDLE = 9002
DEFENCE_BUNDLE_CONTENTS = {112: 1, 121: 1}       # Dagger, Battery Pack
# Ammo Leak Trap: the ammo items it can take one stack of.
AMMO_IDS = {16, 17, 18, 19, 20, 25}             # Grenade, Handgun, Shotgun, Acid, Incendiary, Magnum
# Infinite Ammo: guns whose loaded ammo (equipped slot +0x84) is topped up, and the round count
# used when the gun is empty at the start. Knives (1, 66) have no ammo. Loaded Grenade Launcher
# ids 7/8/9 (explosive/acid/incendiary, BhdTool's table). Capacities are Claude's estimates
# (Handgun 15 = the vanilla start; the rest a safe 6); only used when the gun starts empty.
GUN_CAPACITY = {3: 15, 4: 2, 6: 6, 7: 6, 8: 6, 9: 6, 11: 6, 15: 6}
INFINITE_AMMO_SECONDS = 20
