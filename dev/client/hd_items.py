"""
Resident Evil HD Remaster item IDs -> names.

SOURCE: generated from BhdTool by eleval (GPL-3.0), REmakeHook/src/Game/Items.h
(commit dated 2026-09-30): https://github.com/eleval/BhdTool

IMPORTANT: these are UNVERIFIED for our purposes until we see each ID in the
running game. VERIFIED_IDS lists the ones we have confirmed ourselves.
"""

ITEM_NAMES = {
    0: 'Nothing',
    1: "Jill's Knife",
    2: "Chris' Knife",
    3: 'Pistol',
    4: 'Self defense gun',
    5: 'Unlimited Samurai Edge',
    6: 'Shotgun',
    7: 'Grenade Launcher (explosive)',
    8: 'Grenade Launcher (acid)',
    9: 'Grenade Launcher (incendiary)',
    10: 'Rocket Launcher',
    11: 'Magnum',
    12: 'Flame Thrower',
    13: 'Assault Shotgun',
    14: 'Unlimited Rocket Launcher',
    15: "Barry's Magnum",
    16: 'Grenade Shells',
    17: 'Handgun Magazine',
    18: 'Shotgun Shells',
    19: 'Acid Shells',
    20: 'Incendiary Shells',
    21: 'Golden Arrow',
    22: 'Book of Curses',
    23: 'Coin',
    24: 'Collar',
    25: 'Magnum Rounds',
    26: 'Broach',
    27: 'Fuel Canteen',
    28: 'Arrowhead',
    29: 'Imitation of a key',
    30: 'Gallery Key',
    31: 'Fuel Capsule (armed)',
    32: 'Musical Score',
    33: 'First Aid Spray',
    34: 'Green Herb',
    35: 'Red Herb',
    36: 'Blue Herb',
    37: '2 Green Herbs Mix',
    38: '3 Green Herbs Mix',
    39: 'Green & Red Herbs Mix',
    40: 'Green, Red & Blue Herbs Mix',
    41: 'Green & Blue Herbs Mix',
    42: '2 Green & Blue Herbs Mix',
    43: 'Lockpick',
    44: 'Small Key',
    45: 'Sword Key',
    46: 'Armor Key',
    47: 'Shield Key',
    48: 'Helmet Key',
    49: '001 Key',
    50: '003 Key',
    51: 'Medal of Eagle',
    52: 'Medal of Wolf',
    53: 'Stone & Metal Object',
    54: 'Power Key',
    55: 'Master Key',
    56: 'Star Crest',
    57: 'Wind Crest',
    58: 'Sun Crest',
    59: 'Moon Crest',
    60: 'Square Crank',
    61: 'Hexagonal Crank',
    62: 'Closet Key',
    63: 'Emblem Key',
    64: 'Stone Ring',
    65: 'Metal Object',
    66: 'Knife (Black Tiger)',
    67: 'Battery',
    68: 'Ink Ribbon',
    69: 'Wooden Emblem',
    70: 'Golden Emblem',
    71: 'Sheet Music',
    72: 'Red Jewel',
    73: 'Blue Jewel',
    74: 'Yellow Jewel',
    75: 'Broken Shotgun',
    76: 'Chemical',
    77: 'Lighter',
    78: 'Serum',
    79: 'Transceiver',
    80: 'Empty Bottle',
    81: 'Water',
    82: 'UMB No. 3',
    83: 'NP-004',
    84: 'Yellow-6',
    85: 'UMB No. 7',
    86: 'UMB No. 10',
    87: 'VP-017',
    88: 'V-JOLT',
    89: 'Unused Grenade Shells',
    90: 'Red Book',
    91: 'Last Book Vol. 1',
    92: 'Last Book Vol. 2',
    93: 'MO Disk 1',
    94: 'MO Disk 2',
    95: 'MO Disk 3',
    96: 'Dog Whistle',
    97: 'Fuse Unit',
    98: 'Capsule (empty)',
    99: 'Jewelry Box (Stone Ring)',
    100: 'Insecticide Spray',
    101: 'First Aid Box (Spray)',
    102: 'Jewelry Box (Broach)',
    103: 'Jewerly Box (Mask)',
    104: 'First Aid Box (Green Herb)',
    105: 'First Aid Box (Blue Herb)',
    106: 'Signal Rockets',
    107: 'Broken Flamethrower',
    108: 'Wooden Mount',
    109: 'Slide Filter',
    110: 'Control Room Key',
    111: 'Fuel Capsule (empty)',
    112: 'Dagger',
    113: 'Flash Grenade',
    114: 'Stun Gun',
    115: 'Bee Specimen',
    116: 'Lure of a bee',
    117: 'Fishhook',
    118: 'Lure of a bee (with fishhook)',
    119: 'X-Ray 1',
    120: 'X-Ray 2',
    121: 'Battery Pack',
    122: 'Shaft',
    123: 'Cylinder',
    124: 'Cylinder Shaft',
    125: 'Death Mask (EMN)',
    126: 'Death Mask (Eyes)',
    127: 'Death Mask (Nose)',
    128: 'Death Mask (Mouth)',
    129: 'Musical Score',
    130: 'Map',
    131: 'First Aid Box (Green + Blue)',
    132: 'First Aid Box (Green x2)',
}

# Item IDs confirmed on TessarionAM's PC (add as we see them in-game).
VERIFIED_IDS: set = {
    # seen in-game on TessarionAM's PC, 2026-11-09 (in-game name in brackets where it differs)
    21,   # Golden Arrow (picked up in the flag-watch run)
    22,   # Book of Curses (Crypt)
    28,   # Arrowhead (made by examining the Golden Arrow)
    45,   # Sword Key (from examining the Book of Curses; arrived as x4 - probably uses left)
    69,   # Wooden Emblem (Dining Room, new game)
    112,  # Dagger (count at inventory struct +0x5088)
    121,  # Battery Pack (count at inventory struct +0x508C)
    1,    # Jill's Knife ("Survival Knife")
    3,    # Pistol ("Handgun"); quantity = rounds loaded
    4,    # Self defense gun
    6,    # Shotgun
    7,    # Grenade Launcher (explosive); quantity = shells loaded
    15,   # Barry's Magnum
    17,   # Handgun Magazine
    18,   # Shotgun Shells
    19,   # Acid Shells
    33,   # First Aid Spray
    35,   # Red Herb
    46,   # Armor Key (x4 seen - probably uses left)
    47,   # Shield Key (shown as a "Mansion Key" until examined)
    53,   # Stone & Metal Object
    68,   # Ink Ribbon
    73,   # Blue Jewel ("Blue Gemstone")
    74,   # Yellow Jewel ("Yellow Gemstone")
    76,   # Chemical = HERBICIDE (shown as a chemical until examined)
    77,   # Lighter
    94,   # MO Disk 2 ("MO Disk")
    111,  # Fuel Capsule (empty) ("Fuel Supply Capsule")
    117,  # Fishhook
    1,    # also seen in the item box as "Survival Knife"
    25,   # Magnum Rounds
    34,   # Green Herb
    43,   # Lockpick - kept in a HIDDEN slot after the inventory, qty 0
    54,   # Power Key ("Key for the Power Area" after examining; shown as "Laboratory Key" before)
    60,   # Square Crank (shown as "Crank")
    61,   # Hexagonal Crank (shown as "Crank")
    126,  # Death Mask (Eyes) = the "Mask without eyes"
    129,  # Musical Score (BhdTool "MusicalScore2")
}

# Note: many items show a generic name (e.g. "Mansion Key", a chemical) until
# examined in-game, then get their real name. Confirm names after examining.



def item_name(item_id: int) -> str:
    return ITEM_NAMES.get(item_id, f'Unknown item {item_id}')
