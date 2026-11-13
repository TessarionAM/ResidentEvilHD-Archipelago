"""
Items for Resident Evil HD Remaster.

* `code`   - Archipelago item ID. NEVER change or reuse once released; only append.
* `kind`   - progression (logic needs it), useful (strong but optional), filler.
* `game_id`- the game's own item number, from BhdTool's item table
             (eleval, GPL-3.0; see THIRD_PARTY.md). None = not yet matched.
             All are UNVERIFIED until seen in-game.
"""

from typing import Dict, NamedTuple, Optional

from BaseClasses import Item, ItemClassification as IC

BASE_ID = 1_302_000_000   # arbitrary unique-looking range for this game


class RE1HDItem(Item):
    game = "Resident Evil HD Remaster"


class ItemData(NamedTuple):
    code: int
    kind: IC
    game_id: Optional[int]
    group: str


P, U, F, T = IC.progression, IC.useful, IC.filler, IC.trap

# (name, classification, game_id, group) - order defines the ID, APPEND ONLY.
_ITEMS = [
    # Keys and quest items
    ("Lock Pick", P, 43, "Keys"),
    ("Book of Curses", P, 22, "Keys"),            # holds the Sword Key
    ("Armor Key", P, 46, "Keys"),
    ("Shield Key", P, 47, "Keys"),
    ("Golden Arrow", P, 21, "Quest"),             # holds the Arrowhead
    ("Collar", P, 24, "Quest"),                   # holds Coin -> Imitation of a key
    ("Dog Whistle", P, 96, "Quest"),
    ("Wooden Emblem", P, 69, "Quest"),
    ("Gold Emblem", P, 70, "Quest"),
    ("Missing Music", P, 32, "Quest"),            # seen in-game (Bar) 2026-11-10
    ("Music, mid-pages", P, 129, "Quest"),       # seen in-game (Small Dining Room) 2026-11-10
    ("Lighter", P, 77, "Quest"),
    ("Herbicide", P, 76, "Quest"),                # "Chemical" (76) - confirmed in-game 2026-11-09
    ("Blue Gemstone", P, 73, "Quest"),
    ("Mask without eyes", P, 126, "Masks"),       # "Death Mask (Eyes)" - confirmed in-game 2026-11-09
    ("Mask without a mouth", P, 128, "Masks"),    # BhdTool DeathMaskMouth - same naming pattern, unverified
    ("Mask without a nose", P, 127, "Masks"),     # BhdTool DeathMaskNose - unverified
    ("Mask without eyes, nose, or mouth", P, 103, "Masks"),  # seen in-game 2026-11-10 (BhdTool: "Jewelry Box (Mask)")
    ("Stone & Metal Object", P, 53, "Quest"),
    ("Fishhook", P, 117, "Quest"),
    ("Bee Specimen", P, 115, "Quest"),
    ("Lure without a hook", P, 116, "Quest"),
    ("Wind Crest", P, 57, "Quest"),               # opens the Small Headstone puzzle (Courtyard)
    ("Last Book, vol. 1", P, 91, "Quest"),        # holds the Medal of Eagle (Lab door)
    ("Wooden Mount", P, 108, "Quest"),            # progression: needed for the 2F map check
    ("Fuel Canteen", U, 27, "Quest"),
    ("Serum", U, 78, "Quest"),
    ("Broken Shotgun", F, 75, "Quest"),
    # Weapons
    ("Shotgun", U, 6, "Weapons"),
    ("Grenade Launcher", U, 7, "Weapons"),
    # Ammo
    ("Handgun Magazine", F, 17, "Ammo"),
    ("Shotgun Shells", F, 18, "Ammo"),
    ("Acid Shells", F, 19, "Ammo"),
    ("Incendiary Shells", F, 20, "Ammo"),
    # Healing / defence / saves
    ("Green Herb", F, 34, "Healing"),
    ("Red Herb", F, 35, "Healing"),
    ("Blue Herb", F, 36, "Healing"),
    ("First Aid Spray", U, 33, "Healing"),
    ("First Aid Box", U, 101, "Healing"),         # several box IDs exist (101/104/131/132); we deliver 101
    ("Dagger", F, 112, "Defence"),
    ("Battery Pack", F, 121, "Defence"),
    ("Ink Ribbon", F, 68, "Saves"),
    # --- The rest of the game (2026-11-10). Game ids all SEEN in TessarionAM's full run. ---
    ("Helmet Key", P, 48, "Keys"),
    ("Red Jewel", P, 72, "Quest"),
    ("Yellow Jewel", P, 74, "Quest"),
    ("Jewelry Box (Broach)", P, 102, "Quest"),
    ("Metal Object", P, 65, "Quest"),
    ("Battery", P, 67, "Quest"),
    ("Last Book, vol. 2", P, 92, "Quest"),        # holds the Medal of Wolf (Lab door)
    ("MO Disk 1", P, 93, "Quest"),
    ("MO Disk 2", P, 94, "Quest"),
    ("MO Disk 3", P, 95, "Quest"),
    ("Square Crank", P, 60, "Quest"),
    ("Moon Crest", P, 59, "Quest"),
    ("Star Crest", P, 56, "Quest"),
    ("Sun Crest", P, 58, "Quest"),
    ("Shaft", P, 122, "Quest"),
    ("Hexagonal Crank", P, 61, "Quest"),
    ("Cylinder", P, 123, "Quest"),
    ("Broken Flamethrower", P, 107, "Quest"),
    ("Jewelry Box (Stone Ring)", P, 99, "Quest"),
    ("001 Key", P, 49, "Keys"),
    ("003 Key", P, 50, "Keys"),
    ("Control Room Key", P, 110, "Keys"),
    ("Gallery Key", P, 30, "Keys"),
    ("Red Book", P, 90, "Quest"),
    ("Insecticide Spray", P, 100, "Quest"),
    ("X-Ray 1", P, 119, "Quest"),
    ("X-Ray 2", P, 120, "Quest"),
    ("Slide Filter", P, 109, "Quest"),
    ("Power Key", P, 54, "Keys"),
    ("Fuel Capsule", P, 111, "Quest"),
    ("Master Key", P, 55, "Keys"),
    ("Fuse Unit", P, 97, "Quest"),
    ("Signal Rockets", P, 106, "Quest"),
    ("Magnum", U, 11, "Weapons"),
    ("Barry's Magnum", U, 15, "Weapons"),
    ("Self-Defence Gun", U, 4, "Weapons"),
    ("Knife", F, 66, "Weapons"),
    ("Grenade Shells", F, 16, "Ammo"),
    ("Magnum Rounds", F, 25, "Ammo"),
    # Random starting inventory (2026-11-10): Jill's own starting weapons become items.
    ("Handgun", U, 3, "Weapons"),                 # new game: inventory slot 1 = {3, 15}
    ("Combat Knife", U, 1, "Weapons"),            # new game: inventory slot 2 = {1, 1}
    # Traps (2026-11-11): no game item - the client applies the effect to Jill directly.
    ("Damage Trap", T, None, "Traps"),
    ("Poison Trap", T, None, "Traps"),
    # Seed test 5 requests (TessarionAM, 2026-11-12). Specials replace junk like traps do.
    ("Infinite Ammo (20s)", U, None, "Specials"),   # effect: no game item
    ("Defence Bundle", U, 9002, "Specials"),        # pseudo id: +1 Dagger and +1 Battery Pack
    ("Critical Damage Trap", T, None, "Traps"),
    ("Ammo Leak Trap", T, None, "Traps"),
    # Fun traps (TessarionAM, 2026-11-12): harmless pranks, rare. Jumpscare dropped (game sounds don't
    # play outside their own areas).
    ("Fake Crash Trap", T, None, "Fun Traps"),
    ("To Be Continued Trap", T, None, "Fun Traps"),
    ("Fake Item Trap", T, None, "Fun Traps"),
    ("Fake Death Link Trap", T, None, "Fun Traps"),
    ("Window Shake Trap", T, None, "Fun Traps"),
    # Missable (TessarionAM, 2026-11-12): Richard drops it in the Attic only if you saved him.
    ("Assault Shotgun", U, 13, "Weapons"),        # BhdTool id 13, comes loaded with 10 shells
    ("Self-Destruct Trap", T, None, "Fun Traps"),
    ("Danger Flash Trap", T, None, "Fun Traps"),
    # Missable: Brad drops it at the Heliport only if the Tyrant shows up (Barry alive).
    ("Rocket Launcher", U, 10, "Weapons"),        # BhdTool id 10
    # Fun trap (TessarionAM, 2026-11-12): the next door Jill opens takes her somewhere far away.
    ("Wrong Door Trap", T, None, "Fun Traps"),
]

item_table: Dict[str, ItemData] = {
    name: ItemData(BASE_ID + i, kind, game_id, group)
    for i, (name, kind, game_id, group) in enumerate(_ITEMS)
}

item_name_groups = {}
for _name, _data in item_table.items():
    item_name_groups.setdefault(_data.group, set()).add(_name)
