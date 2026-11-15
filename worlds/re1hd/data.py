"""
Game data for Resident Evil HD Remaster, Jill, Normal.

The Steam release is ONE continuous game (no Disc 1 / Disc 2 split - that only
mattered for the GameCube version). This file covers the whole game: Mansion,
Courtyard, Residence, Caves, Altar and Laboratory, in the same lists.

SOURCE: Evil Resource (https://www.evilresource.com/resident-evil-remake/maps),
        one page per room, "Jill (Normal)" contents and door locks, read 2026-11-09.
        Facts are restated in our own words. Credited in THIRD_PARTY.md.

HOW TO READ THIS FILE
---------------------
* ROOMS: every room we model. Each room becomes an Archipelago "region".
* DOORS: (room A, room B, requirements, one_way)
    - requirements = items the player must have (ALL of them).
    - one_way=True means you can only go A -> B (e.g. a door that
      "unlocks from the other side": once opened it gives no new access).
* PICKUPS: (room, location name, vanilla item, requirements)
    - each becomes an Archipelago location; its vanilla item goes into the pool.

Requirements always name the PHYSICAL item you pick up, e.g. "Golden Arrow"
(you examine it to get the Arrowhead), "Book of Curses" (holds the Sword Key),
"Collar" (holds the Coin -> Imitation of a key).

Anything marked CONFIRMED was reasoned from game knowledge (not stated on Evil
Resource) and then confirmed in-game by TessarionAM on 2026-11-09. Where unsure we
OVER-constrain: an extra requirement can only make seeds a little less
random, never impossible.

NOT MODELLED YET: Hidden Wardrobe (bonus Closet Key), files, Kerosene refills and
event-only rewards (Richard's Radio, Assault Shotgun). Locks outside the Mansion are
marked GUESS until the door scanner confirms them.
"""

START = "Main Hall"
# random_start_room (2026-11-15): the save rooms a seed can start in (logic room names; the client
# gets the room number from game_data.ROOM_NUMBERS). The Laboratory's two are left out: its doors
# depend on power and story events, and Barry / Wesker's Lab scenes weren't tested with a jump.
# The Mansion Drug Room was dropped after the 2026-11-15 generation runs: with the plain doors it
# never passes (going out leaves it behind a one-way door), and with door locks / door shuffle the
# seeds that passed our check then failed Archipelago's own fill (every failure in 480 seeds).
START_ROOMS_MANSION = ("Dining Room", "East Wing Storeroom")
# Also left out after checking every save room with the generator's own validation (2026-11-15): the
# Garbage Compactor Room and Room 003 can't reach the goal even with every item (their way out is a
# locked door), and the Altar Stairway Passage has too few checks within reach to start a fill.
# Every start is still validated per seed (World._pick_start_room); a room that fails is skipped.
START_ROOMS_ALL = START_ROOMS_MANSION + ("Mining Area", "Cabin", "Residence Storeroom")
# With a random start room, Barry's Lock Pick scene happens when Jill first walks back into the Main
# Hall (the intro replays) - not proven yet, so the check is treated as missable (locked junk; the
# real Lock Pick stays in the pool).
START_ROOM_MISSABLE = frozenset({"Main Hall - Lock Pick (Barry)"})
# Starts on the far side of the Stone & Metal gate (2026-11-15, TessarionAM's seed: from the
# Residence he walked Garden Shed -> Roofed Passage, which is free one way, and couldn't get back -
# the gate is the only way back to the Courtyard, Residence and Caves). TessarionAM (19:15): with
# these starts the client puts the object in the gate for you from the start (the gate holder,
# client._gate_tick: the drawn object is a copy, taken away again if picked up, so there are never
# more than the game's two), so the gate is open both ways and the logic needs nothing there.
GATE_SIDE_STARTS = frozenset({"Mining Area", "Cabin", "Residence Storeroom"})
GATE_LINK = ("Garden Shed", "Roofed Passage")
GATE_ITEM = "Stone & Metal Object"
GOAL_ROOM = "Garden Shed"   # reaching it = escaping the mansion (goal mansion_escape)

ROOMS = [
    # Mansion 1F
    "Main Hall", "Dining Room", "Tea Room", "Bar", "Art Room", "'L' Corridor",
    "Winding Corridor", "Bathroom", "Marble Room", "Living Room", "Outside Boiler",
    "Dark Corridor", "Roofed Passage", "Large Gallery", "Graveyard",
    "East Wing Stairway", "East Wing Storeroom", "West Wing Outer Stairway",
    "West Wing Inner Stairway", "Mansion Drug Room", "Small Storeroom",
    "Northern Corridor", "Greenhouse", "Researcher's Bedroom", "Tiger Statue Room",
    # Mansion 2F / 3F
    "Dining Room 2F", "Mirror Corridor", "'Death' Passage", "Outside Balcony",
    "Outside Patio", "'C' Corridor", "Small Library", "Armor Room", "Pillar Room",
    "Attic Entry", "Attic", "Small Dining Room", "Resting Room", "Deer Room",
    "Bedroom", "Fish Tank Room",
    # Mansion B1
    "Crypt", "Kitchen", "Concrete Passage 2", "Concrete Passage 1", "Secret Passage",
    # Goal
    "Garden Shed",
]

LOCKPICK = ("Lock Pick",)
SWORD = ("Book of Curses",)        # Sword Key is attached to the Book of Curses
ARMOR = ("Armor Key",)
ARMOR_SPOT = "Armor Key Spot Used"   # event, see EVENTS
ELEVATOR_POWER = "Kitchen Elevator Powered"   # event, see EVENTS
HELMET_SPOT = "Helmet Key Spot Used"   # event: the Plant 42 Room Helmet Key pickup (vanilla spot)
POOL_DRAINED = "Water Pool Drained"          # event: the Square Crank used in the Water Pool
BATTERY_LIFT = "Falls Area Lift Powered"     # event: the Battery put in the Falls Area lift
SHIELD = ("Shield Key",)
MASKS = ("Mask without eyes", "Mask without a mouth", "Mask without a nose",
         "Mask without eyes, nose, or mouth")

DOORS = [
    # --- Mansion 1F ---
    ("Main Hall", "Dining Room", (), False),
    ("Main Hall", "Art Room", (), False),
    ("Main Hall", "Graveyard", (), False),            # CONFIRMED by TessarionAM: no key needed
    ("Main Hall", "Dining Room 2F", (), False),           # via the main staircase
    ("Main Hall", "'C' Corridor", SWORD, False),
    ("Main Hall", "Outside Patio", ARMOR, False),
    ("Outside Balcony", "Main Hall", (), True),            # unlocks from balcony side
    ("Dining Room", "Tea Room", (), False),
    ("Dining Room 2F", "West Wing Inner Stairway", SWORD, False),
    ("Tea Room", "Bar", ARMOR, False),
    ("Tea Room", "West Wing Outer Stairway", (), False),
    ("Tea Room", "Kitchen", SWORD, False),
    ("Northern Corridor", "Tea Room", (), True),           # unlocks from corridor side
    ("Art Room", "'L' Corridor", SWORD, False),
    ("'L' Corridor", "Winding Corridor", (), False),
    ("Winding Corridor", "Bathroom", (), False),
    ("Winding Corridor", "Marble Room", (), False),
    ("Winding Corridor", "Dark Corridor", (), False),
    ("Winding Corridor", "Outside Boiler", LOCKPICK, False),
    ("Marble Room", "Living Room", (), False),
    ("Dark Corridor", "East Wing Stairway", (), False),
    ("Dark Corridor", "Roofed Passage", (), False),
    ("Dark Corridor", "Large Gallery", ARMOR, False),
    # Door scanner: Large Gallery side = Lock Pick, Graveyard side = lock 22 ("locked from the other
    # side"). The Graveyard is also open from the Main Hall, so this must be one-way.
    ("Large Gallery", "Graveyard", LOCKPICK, True),
    ("Graveyard", "Crypt", ("Golden Arrow",), False),      # CONFIRMED by TessarionAM: Arrowhead opens the crypt
    ("East Wing Stairway", "East Wing Storeroom", (), False),
    ("East Wing Stairway", "Deer Room", ARMOR, False),
    ("East Wing Stairway", "Resting Room", (), False),
    # Door scanner: the 'C' Corridor side is lock 22 ("locked from the other side"), the stairway
    # side is lock 21 (opens from this side). Was the wrong way round before 2026-11-11.
    ("East Wing Stairway", "'C' Corridor", (), True),
    ("Small Library", "East Wing Stairway", (), True),     # impassable from stairway side
    ("West Wing Outer Stairway", "Mirror Corridor", (), False),
    ("West Wing Inner Stairway", "Mansion Drug Room", (), False),
    ("West Wing Inner Stairway", "Small Storeroom", LOCKPICK, False),
    ("West Wing Inner Stairway", "Northern Corridor", ARMOR, False),
    ("West Wing Inner Stairway", "Outside Balcony", LOCKPICK, False),
    ("West Wing Inner Stairway", "Mirror Corridor", (), True),   # unlocks from inner side
    ("Northern Corridor", "Greenhouse", (), False),
    ("Northern Corridor", "Researcher's Bedroom", (), False),
    ("Northern Corridor", "Tiger Statue Room", (), False),
    # --- Mansion 2F / 3F ---
    ("Mirror Corridor", "Dining Room 2F", (), True),       # unlocks from mirror side
    ("Mirror Corridor", "'Death' Passage", (), False),
    ("'C' Corridor", "Small Library", (), False),
    ("'C' Corridor", "Armor Room", ARMOR, False),
    ("'C' Corridor", "Pillar Room", ARMOR, False),
    ("Pillar Room", "Attic Entry", (), False),
    ("Attic Entry", "Attic", SHIELD, False),
    ("Attic Entry", "Small Dining Room", (), False),
    ("Deer Room", "Bedroom", (), False),
    ("Deer Room", "Fish Tank Room", LOCKPICK, False),
    # --- Mansion B1 ---
    # Kitchen -> Concrete Passage 2 is "locked from the other side" (door scanner: lock 22 on the
    # Kitchen side; TessarionAM, seed test 3). B1 is entered from the Resting Room (Helmet Key, below).
    ("Concrete Passage 2", "Kitchen", (), True),
    ("Concrete Passage 2", "Concrete Passage 1", (), False),
    # The Secret Passage (Sliding Trap Room) drops down a hole into B1 and Jill can't climb back up
    # (TessarionAM, 2026-11-13: logic sent him to the Resting Room's herb "through" the Secret Passage
    # from B1). So it's one-way down: the Secret Passage, its Dagger and the Resting Room are only
    # reached through the Resting Room's own doors.
    ("Secret Passage", "Concrete Passage 1", (), True),
    # --- Goal ---
    # The gate only takes the Stone & Metal Object from the Roofed Passage side (TessarionAM,
    # 2026-11-14). Test 07 (17:35): from the Garden Shed the door to the Roofed Passage opens
    # without it; the way from the Roofed Passage into the Garden Shed needs the gate open. Since
    # 0.9.25 the client keeps it open once the object has been received (or taken back off the
    # gate for the Altar), so the rule is simply "have the object".
    ("Roofed Passage", "Garden Shed", ("Stone & Metal Object",), True),
    ("Garden Shed", "Roofed Passage", (), True),
]

PICKUPS = [
    # Main Hall
    ("Main Hall", "Main Hall - Lock Pick (Barry)", "Lock Pick", ()),
    ("Main Hall", "Main Hall - Acid Shells (Barry)", "Acid Shells", ()),
    # Dining Room
    ("Dining Room", "Dining Room - Ink Ribbons", "Ink Ribbon", ()),
    ("Dining Room", "Dining Room - Wooden Emblem", "Wooden Emblem", ()),
    ("Dining Room", "Dining Room - Blue Gemstone", "Blue Gemstone", ()),   # push statue from 2F (free)
    ("Dining Room", "Dining Room - Shield Key", "Shield Key", ("Gold Emblem",)),
    # Dining Room 2F
    ("Dining Room 2F", "Dining Room 2F - Dagger", "Dagger", ()),
    # Bar (piano puzzle: both music pieces; an emblem must be swapped in or you're trapped -
    # CONFIRMED by TessarionAM. The Wooden Emblem is the emblem you swap in.)
    ("Bar", "Bar - Missing Music", "Missing Music", ()),
    ("Bar", "Bar - Gold Emblem", "Gold Emblem", ("Missing Music", "Music, mid-pages", "Wooden Emblem")),
    # Art Room
    ("Art Room", "Art Room - Dagger", "Dagger", ()),
    # 'L' Corridor
    ("'L' Corridor", "'L' Corridor - Dagger", "Dagger", ()),
    ("'L' Corridor", "'L' Corridor - Handgun Magazine", "Handgun Magazine", ()),
    # Bathroom - nothing collectable for Jill (Normal) besides a Dagger
    ("Bathroom", "Bathroom - Dagger", "Dagger", ()),
    # Living Room
    ("Living Room", "Living Room - Dagger", "Dagger", ()),
    ("Living Room", "Living Room - Ink Ribbons", "Ink Ribbon", ()),
    ("Living Room", "Living Room - Shotgun", "Shotgun", ()),
    # Outside Boiler
    ("Outside Boiler", "Outside Boiler - Herbicide", "Herbicide", ()),
    ("Outside Boiler", "Outside Boiler - Green Herb 1", "Green Herb", ()),
    ("Outside Boiler", "Outside Boiler - Green Herb 2", "Green Herb", ()),
    ("Outside Boiler", "Outside Boiler - Red Herb", "Red Herb", ()),
    # Large Gallery
    ("Large Gallery", "Large Gallery - Mask without a mouth", "Mask without a mouth", ()),
    # Graveyard / Crypt
    ("Graveyard", "Graveyard - Shotgun Shells", "Shotgun Shells", ()),
    ("Crypt", "Crypt - Book of Curses", "Book of Curses", ()),
    ("Crypt", "Crypt - Shotgun Shells", "Shotgun Shells", MASKS),
    ("Crypt", "Crypt - Stone & Metal Object", "Stone & Metal Object", MASKS),
    # East Wing Storeroom
    # (East Wing Storeroom - Handgun Magazine deleted 2026-11-12: Easy/Hard only, not Jill Normal)
    ("East Wing Storeroom", "East Wing Storeroom - Fuel Canteen", "Fuel Canteen", ()),
    # Barry leaves these after the Armor Key SPOT in the 'Death' Passage has been used (TessarionAM,
    # seed test 3) - not when you hold an Armor Key from the multiworld.
    ("East Wing Storeroom", "East Wing Storeroom - First Aid Spray (Barry)", "First Aid Spray", (ARMOR_SPOT,)),
    ("East Wing Storeroom", "East Wing Storeroom - Incendiary Shells (Barry)", "Incendiary Shells", (ARMOR_SPOT,)),
    # West Wing Outer Stairway
    ("West Wing Outer Stairway", "West Wing Outer Stairway - Handgun Magazine", "Handgun Magazine", ()),
    ("West Wing Outer Stairway", "West Wing Outer Stairway - Green Herb 1", "Green Herb", ()),
    ("West Wing Outer Stairway", "West Wing Outer Stairway - Green Herb 2", "Green Herb", ()),
    # Mansion Drug Room / Small Storeroom
    ("Mansion Drug Room", "Mansion Drug Room - Serum", "Serum", ()),
    ("Small Storeroom", "Small Storeroom - Battery Pack", "Battery Pack", ()),
    ("Small Storeroom", "Small Storeroom - Broken Shotgun", "Broken Shotgun", ()),
    ("Small Storeroom", "Small Storeroom - Ink Ribbons", "Ink Ribbon", ()),
    # Northern Corridor and its rooms
    ("Northern Corridor", "Northern Corridor - Battery Pack", "Battery Pack", ()),
    # (Northern Corridor - Dagger deleted 2026-11-12: not in Jill (Normal); only the Battery Pack is)
    ("Researcher's Bedroom", "Researcher's Bedroom - Handgun Magazine", "Handgun Magazine", ()),
    ("Researcher's Bedroom", "Researcher's Bedroom - Battery Pack", "Battery Pack", ()),
    ("Tiger Statue Room", "Tiger Statue Room - Shotgun Shells", "Shotgun Shells", ("Blue Gemstone",)),
    # the herbs can be killed with the Herbicide (handle on "Green"), so they're MISSABLE (TessarionAM,
    # 2026-11-12): each check always gives junk. 2026-11-15 (TessarionAM): they can't be reached
    # until the Herbicide has killed the plant, so the tracker only shows them with it.
    *[("Greenhouse", f"Greenhouse - Green Herb {i}", "Green Herb", ("Herbicide",)) for i in range(1, 6)],
    ("Greenhouse", "Greenhouse - Mask without eyes", "Mask without eyes", ("Herbicide",)),
    # Mirror Corridor / 'Death' Passage
    ("Mirror Corridor", "Mirror Corridor - Golden Arrow", "Golden Arrow", ()),
    ("Mirror Corridor", "Mirror Corridor - Green Herb", "Green Herb", ()),
    ("Mirror Corridor", "Mirror Corridor - Handgun Magazine", "Handgun Magazine", ()),
    ("'Death' Passage", "'Death' Passage - Armor Key", "Armor Key", ("Collar",)),   # Imitation of a key from the Collar
    # Outside Balcony (Dog Whistle summons the Cerberus with the Collar - CONFIRMED by TessarionAM)
    # (The 3 Outside Balcony Green Herbs on Evil Resource's list are NOT pickups in this
    # version: using them changed neither the inventory nor any pickup flag - tested 2026-11-10.)
    # 2026-11-15 (TessarionAM): once Jill has a Collar the whistle can't be used any more, so this
    # check is missable (MISSABLE: junk) and leaves the tracker when a Collar is received (GONE_WHEN).
    ("Outside Balcony", "Outside Balcony - Collar (Cerberus)", "Collar", ("Dog Whistle",)),
    # Outside Patio
    ("Outside Patio", "Outside Patio - Dagger", "Dagger", ()),
    ("Outside Patio", "Outside Patio - Grenade Launcher", "Grenade Launcher", ()),
    ("Outside Patio", "Outside Patio - Green Herb 1", "Green Herb", ()),
    ("Outside Patio", "Outside Patio - Green Herb 2", "Green Herb", ()),
    # 'C' Corridor / Small Library / Armor Room / Pillar Room / Attic
    ("'C' Corridor", "'C' Corridor - Wooden Mount", "Wooden Mount", ()),
    ("Small Library", "Small Library - Dog Whistle", "Dog Whistle", ()),
    ("Small Library", "Small Library - Handgun Magazine", "Handgun Magazine", ()),
    ("Small Library", "Small Library - Lighter", "Lighter", ()),
    ("Armor Room", "Armor Room - Mask without eyes, nose, or mouth", "Mask without eyes, nose, or mouth", ()),
    ("Pillar Room", "Pillar Room - Green Herb 1", "Green Herb", ()),
    ("Pillar Room", "Pillar Room - Green Herb 2", "Green Herb", ()),
    ("Attic", "Attic - Mask without a nose", "Mask without a nose", ()),
    # Small Dining Room (candles need the Lighter)
    ("Small Dining Room", "Small Dining Room - Handgun Magazine (Table)", "Handgun Magazine", ()),
    ("Small Dining Room", "Small Dining Room - Handgun Magazine (Cabinet)", "Handgun Magazine", ("Lighter",)),
    ("Small Dining Room", "Small Dining Room - Music, mid-pages", "Music, mid-pages", ("Lighter",)),
    # East wing 2F
    ("Resting Room", "Resting Room - Green Herb", "Green Herb", ()),
    ("Deer Room", "Deer Room - Red Herb", "Red Herb", ()),
    ("Bedroom", "Bedroom - First Aid Box", "First Aid Box", ()),
    ("Bedroom", "Bedroom - Ink Ribbons", "Ink Ribbon", ()),
    ("Bedroom", "Bedroom - Green Herb", "Green Herb", ()),
    # Fish Tank Room (Wind Crest puzzle needs all three pieces - CONFIRMED by TessarionAM)
    ("Fish Tank Room", "Fish Tank Room - Fishhook", "Fishhook", ()),
    ("Fish Tank Room", "Fish Tank Room - Bee Specimen", "Bee Specimen", ()),
    ("Fish Tank Room", "Fish Tank Room - Lure without a hook", "Lure without a hook", ()),
    ("Fish Tank Room", "Fish Tank Room - Wind Crest", "Wind Crest",
     ("Fishhook", "Bee Specimen", "Lure without a hook")),
    # Mansion B1
    ("Kitchen", "Kitchen - Dagger", "Dagger", ()),
    # (No Handgun Magazine in the Kitchen, even on a new game - TessarionAM, 2026-11-10.)
    ("Concrete Passage 2", "Concrete Passage 2 - Red Herb", "Red Herb", ()),
    ("Concrete Passage 2", "Concrete Passage 2 - Blue Herb", "Blue Herb", ()),
    ("Concrete Passage 2", "Concrete Passage 2 - Dagger", "Dagger", ()),
    ("Concrete Passage 2", "Concrete Passage 2 - Handgun Magazine", "Handgun Magazine", ()),
    ("Concrete Passage 1", "Concrete Passage 1 - Shotgun Shells", "Shotgun Shells", ()),
    ("Secret Passage", "Secret Passage - Last Book Vol. 1", "Last Book, vol. 1", ()),
]

# Where each room's facts came from (for credit and re-checking).
ER = "https://www.evilresource.com/resident-evil-remake/maps/mansion/"
SOURCE_PAGES = {
    "1F": ER + "mansion-1f/", "2F": ER + "mansion-2f/", "3F": ER + "mansion-3f/", "B1": ER + "mansion-b1/",
}


# ===========================================================================
# THE REST OF THE GAME (added 2026-11-10): Mansion rooms behind the Helmet Key,
# Courtyard, Caves (Courtyard B1/B2), Residence + Aqua Ring, Altar, Laboratory.
#
# SOURCES
# * Pickups: TessarionAM's full play-through recorded with hd_event_recorder (2026-11-10),
#   every pickup paired with its flag bit (tools/full_game_data.py). So every pickup
#   below was SEEN in this version, Jill, Normal, and is detectable by the client.
# * Room connections: BhdTool's rooms.json (eleval, GPL-3.0) door list.
# * Locks: game knowledge + the order TessarionAM needed things in his run + a Jill
#   walkthrough (dtgre.com, read 2026-11-10, restated in our own words).
#   Where unsure we OVER-constrain (see the top of this file): a lock may list more
#   than the game strictly needs. That can only make seeds less random, never
#   impossible. Each such guess is marked GUESS so it can be relaxed after testing.
# * Not checks: the armed Fuel Capsule (refilled, not picked up) and taking the
#   Stone & Metal Object back off the Roofed Passage gate - both flip a bit but
#   give nothing new.
# ===========================================================================

HELMET = ("Helmet Key",)
CRESTS = ("Moon Crest", "Star Crest", "Sun Crest")
MEDALS = ("Last Book, vol. 1", "Last Book, vol. 2")       # the books hold the Eagle / Wolf medals
MO_DISKS = ("MO Disk 1", "MO Disk 2", "MO Disk 3")
# everything the vanilla route needs to reach Lisa's Room / the Main Laboratory (for GUESS locks
# that may depend on story progress rather than an item)
# The Broken Flamethrower is always found below Barry's cave lift (FLAMETHROWER_LOCATIONS), so the
# logic uses an event there instead of the item: generation and our own checks then agree on it.
FLAMETHROWER_FOUND = "Broken Flamethrower Found"
REACH_LISA = ("Square Crank", "Battery") + CRESTS + ("Shaft", "Cylinder", "Hexagonal Crank", FLAMETHROWER_FOUND)
REACH_MAIN_LAB = ("Power Key", "Fuel Capsule") + MO_DISKS

ROOMS += [r for r in ["Tiger Statue Room", "Large Art & Mirror Rooms", "Courtyard Study", "Garden Shed", "Secret Passage", "Elevator Corridor", "Trophy Room", "Library", "Materials Room", "Main Garden", "Heliport", "Zigzag Path", "Underground Statue Room", "Mining Area", "Generator Room", "Enrico Room", "Boulder Passage 1", "Spider Room", "Straight Passage", "Boulder Passage 2", "Small Headstone Area", "Cabin", "Jessica's Tomb", "Garbage Compactor Room", "Winding Underground Passage", "Underground Storage Room", "Lisa's Room", "Residence Entry Corridor", "Room 001", "Room 001 Bathroom", "Residence Storeroom", "Rec Room", "Room 002 Bathroom", "Gallery", "Plant 42 Room", "Aqua Ring Entry", "Aqua Ring Storage", "Control Room", "Aqua Ring Water Tank", "Passage to Heliport", "Lab Item Box Room", "Lab Stairway", "Visual Data Room", "'O' Room", "Operating Room", "Morgue", "Pass Code Corridor", "X-Ray Room B", "X-Ray Room A", "Lounge Room", "Power Maze A", "Power Maze B", "Main Laboratory", "Main Laboratory Entrance"] if r not in ROOMS] + [
    "Altar Stairway Passage", "Fountain", "Residence Central Corridor", "Room 002",
    "Lab Entrance", "Cell Entrance", "Lab Elevator Entry", "Heliport Elevator",
    "Power Control Room", "Cell", "Elevator to Main Laboratory", "Forked Passage",
]

DOORS += [
    # --- Mansion, Helmet Key doors (GUESS: every new Mansion room needs the Helmet Key) ---
    ("Main Hall", "Large Art & Mirror Rooms", HELMET, False),
    ("West Wing Inner Stairway", "Trophy Room", HELMET, False),
    # Door scanner (2026-11-11): Mirror Corridor -> Elevator Corridor is lock 22 = "locked from the
    # other side"; the Elevator Corridor is reached through the Library. It opens from that side.
    ("Elevator Corridor", "Mirror Corridor", (), True),
    # Resting Room -> Sliding Trap Room (our "Secret Passage", 0x20C) = lock 6 = Helmet Key.
    ("Resting Room", "Secret Passage", HELMET, False),
    # Kitchen Elevator (0x200) links the Kitchen and the Elevator Corridor. It has no power until
    # it's switched on in Concrete Passage 2 (TessarionAM, 2026-11-11).
    ("Elevator Corridor", "Kitchen", (ELEVATOR_POWER,), False),
    ("'Death' Passage", "Library", HELMET, False),
    # (no Elevator Corridor <-> Library door: Evil Resource links the Library only to the 'Death'
    # Passage, behind the Helmet Key - removed in the audit, 2026-11-12)
    ("Elevator Corridor", "Materials Room", (), False),
    # the door takes the Broach, which is inside the Jewelry Box - and the box only opens with the
    # Red Jewel (TessarionAM, seed test 5: had the box, not the gem, logic said Courtyard Study was open)
    # TessarionAM (2026-11-13): the door only needs the insignia (the Broach) - no Helmet Key
    ("Dark Corridor", "Courtyard Study", ("Jewelry Box (Broach)", "Red Jewel"), False),
    # (Secret Passage = BhdTool 0x20C "Sliding Trap Room"; one-way drop down to Concrete Passage 1.)
    # --- Courtyard ---
    ("Garden Shed", "Main Garden", (), False),
    ("Garden Shed", "Muddy Path", (), False),
    ("Main Garden", "Water Pool", (), False),
    # Courtyard water (TessarionAM, 2026-11-14 + mapping run 2026-11-10): the Square Crank only works in
    # the Water Pool (top side): draining it opens the walk across the pool to the lift down to the
    # Falls Area (game door 301-302). The Battery goes into the lift at the Falls Area end (inventory,
    # 17:22:29 in 0x302); that lift (300-302) then joins the Falls Area and the Main Garden. So the way
    # back up from the Falls Area needs the pool drained from the top OR the Battery - never the crank
    # in hand.
    ("Water Pool", "Falls Area", (POOL_DRAINED,), False),
    ("Main Garden", "Falls Area", (BATTERY_LIFT,), False),
    ("Falls Area", "Zigzag Path", (), False),
    ("Muddy Path", "Small Headstone Area", (), False),
    ("Small Headstone Area", "Forest Pathway", (), False),
    ("Forest Pathway", "Cabin", (), False),
    # --- Residence + Aqua Ring ---
    ("Zigzag Path", "Residence Entry Corridor", (), False),
    ("Residence Entry Corridor", "Residence Storeroom", (), False),
    ("Residence Entry Corridor", "Rec Room", (), False),
    ("Residence Entry Corridor", "Residence Central Corridor", (), False),
    ("Residence Entry Corridor", "Room 001", ("001 Key",), False),
    ("Room 001", "Room 001 Bathroom", (), False),
    ("Residence Central Corridor", "Room 002", (), False),
    ("Room 002", "Room 002 Bathroom", (), False),
    ("Room 002", "Aqua Ring Entry", (), False),
    # Aqua Ring re-modelled 2026-11-12 from Evil Resource + the door scanner (the old version put
    # the Control Room Key on three wrong doors and had no Walkway / Guard Room). The only key door
    # is Walkway -> Control Room (game: key type 13 = Control Room Key, flag 42).
    ("Aqua Ring Entry", "Aqua Ring Walkway", (), False),
    ("Aqua Ring Walkway", "Guard Room", (), False),                         # Plant 42's roots
    ("Aqua Ring Walkway", "Control Room", ("Control Room Key",), False),
    ("Control Room", "Aqua Ring Storage", (), False),                       # the Control Room spans B1/B2
    ("Aqua Ring Storage", "Aqua Ring Water Tank", (), False),               # drained from the Control Room
    # the Aqua Ring Exit door "needs to be unlocked from the other side" (game: one-sided 22/21, flag 44)
    ("Aqua Ring Storage", "Aqua Ring Entry", (), True),
    ("Residence Central Corridor", "Gallery", ("Gallery Key",), False),
    ("Gallery", "Room 003", ("003 Key",), False),
    ("Gallery", "Plant 42 Room", ("003 Key", "Red Book", "Insecticide Spray", "Control Room Key"), False),  # GUESS
    # --- Caves (Courtyard B1/B2) ---
    # TessarionAM (2026-11-12): the caves need the Battery (the S&M Object, Square Crank and Sword Key
    # are already on the way here). The three crests were a wrong guess.
    # The ladder down is behind the waterfall, which only stops when the pool is full again: refilled
    # with the crank at the top, then back down by the Battery lift (mapping run 17:28:25 -> 17:29:12).
    ("Falls Area", "Mining Area", ("Square Crank", BATTERY_LIFT), False),
    ("Mining Area", "Forked Passage", (), False),
    ("Forked Passage", "Generator Room", (), False),
    ("Generator Room", "Enrico Room", (), False),
    # the Mining Area corridor must be turned with the Hexagonal Crank first (TessarionAM, seed test 5:
    # Boulder Passages, Spider Room, Straight Passage and Underground Statue Room were in logic
    # without it; Evil Resource: the Mining Area Green Herb also needs the corridor turned)
    ("Mining Area", "Boulder Passage 1", ("Hexagonal Crank",), False),
    ("Boulder Passage 1", "Spider Room", (), False),
    ("Spider Room", "Straight Passage", (), False),
    ("Straight Passage", "Boulder Passage 2", (), False),
    ("Boulder Passage 2", "Underground Statue Room", (), False),
    # Barry's cave lift only goes down: the game won't let Jill ride it back up (TessarionAM,
    # 2026-11-15), and the only way out is Lisa's door, which the Broken Flamethrower opens. So the
    # Broken Flamethrower is always placed down here, before that door (FLAMETHROWER_LOCATIONS,
    # World.create_items), and handed straight to Jill (DIRECT_ITEMS) - there's no item box below.
    # With it guaranteed here, Lisa's door needs nothing more in the logic.
    ("Generator Room", "Garbage Compactor Room", ("Shaft", "Cylinder", "Hexagonal Crank"), True),
    ("Garbage Compactor Room", "Winding Underground Passage", (), False),
    ("Winding Underground Passage", "Underground Storage Room", (), False),
    ("Winding Underground Passage", "Lisa's Room", (), False),
    ("Lisa's Room", "Cabin", (), True),
    # --- Altar ---
    # Two Stone & Metal Objects (the 2nd = Stone Ring + Metal Object). GUESS: the passage may
    # only open after the caves story, so we also require everything that reaches Lisa's Room.
    ("Main Hall", "Altar Stairway Passage",
     ("Stone & Metal Object", "Jewelry Box (Stone Ring)", "Metal Object") + REACH_LISA, False),
    ("Altar Stairway Passage", "Jessica's Tomb", (), False),
    ("Jessica's Tomb", "Fountain", (), False),
    # --- Laboratory ---
    ("Fountain", "Lab Entrance", MEDALS, False),
    ("Lab Entrance", "Lab Item Box Room", (), False),
    ("Lab Item Box Room", "Lab Stairway", (), False),
    ("Lab Stairway", "Visual Data Room", ("Slide Filter", "X-Ray 1", "X-Ray 2"), False),   # GUESS
    ("Lab Stairway", "'O' Room", (), False),
    ("'O' Room", "Operating Room", (), False),
    ("'O' Room", "Morgue", ("Power Key",), False),     # Evil Resource: needs the Key for the Power Area
    ("'O' Room", "Pass Code Corridor", (), False),
    ("Pass Code Corridor", "X-Ray Room A", (), False),
    ("Pass Code Corridor", "X-Ray Room B", (), False),
    ("Pass Code Corridor", "Cell Entrance", (), False),
    ("'O' Room", "Lab Elevator Entry", ("Power Key",), False),                     # GUESS
    ("Lab Elevator Entry", "Lounge Room", (), False),
    ("Lab Elevator Entry", "Power Maze A", (), False),
    ("Power Maze A", "Power Maze B", (), False),
    ("Power Maze B", "Power Control Room", (), False),
    ("Lab Elevator Entry", "Elevator to Main Laboratory", REACH_MAIN_LAB, False),  # GUESS
    ("Elevator to Main Laboratory", "Main Laboratory Entrance", (), False),
    ("Main Laboratory Entrance", "Main Laboratory", (), False),
    ("Cell Entrance", "Cell", ("Master Key",), False),
    ("Lab Entrance", "Passage to Heliport", ("Master Key",) + REACH_MAIN_LAB, False),  # GUESS: opens in the escape
    ("Passage to Heliport", "Heliport Elevator", (), False),
    ("Heliport Elevator", "Heliport", (), False),
]

# every room a door leads to is a room (some new rooms have no pickups)
for _a, _b, _req, _one in DOORS:
    for _r in (_a, _b):
        if _r not in ROOMS:
            ROOMS.append(_r)

PICKUPS += [
    ("Tiger Statue Room", "Tiger Statue Room - MO Disk 1", "MO Disk 1", ("Yellow Jewel",)),
    ("Large Art & Mirror Rooms", "Large Art & Mirror Rooms - Dagger", "Dagger", ()),
    ("Large Art & Mirror Rooms", "Large Art & Mirror Rooms - Ink Ribbon", "Ink Ribbon", ()),
    ("Large Art & Mirror Rooms", "Large Art & Mirror Rooms - Green Herb", "Green Herb", ()),
    # the box can be taken without the Red Jewel (TessarionAM, seed test 5); the jewel opens it, which
    # the Courtyard Study door asks for
    ("Large Art & Mirror Rooms", "Large Art & Mirror Rooms - Jewelry Box (Broach)", "Jewelry Box (Broach)", ()),
    ("Courtyard Study", "Courtyard Study - Metal Object", "Metal Object", ()),
    ("Courtyard Study", "Courtyard Study - Shotgun Shells", "Shotgun Shells", ()),
    ("Courtyard Study", "Courtyard Study - Battery Pack", "Battery Pack", ()),
    # Shells, Battery Pack 1 and the shelf First Aid Spray are there on the first visit; the
    # other three appear after the Helmet Key is picked up in the Plant 42 Room (TessarionAM, seed test 4)
    ("Garden Shed", "Garden Shed - Shotgun Shells", "Shotgun Shells", ()),
    ("Garden Shed", "Garden Shed - First Aid Spray 1", "First Aid Spray", ()),
    ("Garden Shed", "Garden Shed - Battery Pack 1", "Battery Pack", ()),
    ("Garden Shed", "Garden Shed - Battery Pack 2", "Battery Pack", (HELMET_SPOT,)),
    ("Garden Shed", "Garden Shed - Grenade Shells", "Grenade Shells", (HELMET_SPOT,)),
    ("Garden Shed", "Garden Shed - First Aid Spray 2", "First Aid Spray", (HELMET_SPOT,)),
    ("Secret Passage", "Secret Passage - Dagger", "Dagger", ()),
    ("Elevator Corridor", "Elevator Corridor - Green Herb 1", "Green Herb", ()),
    ("Elevator Corridor", "Elevator Corridor - Red Herb", "Red Herb", ()),
    ("Elevator Corridor", "Elevator Corridor - Green Herb 2", "Green Herb", ()),
    ("Trophy Room", "Trophy Room - Yellow Jewel", "Yellow Jewel", ()),
    ("Trophy Room", "Trophy Room - Red Jewel", "Red Jewel", ()),
    ("Trophy Room", "Trophy Room - Dagger", "Dagger", ()),
    ("Trophy Room", "Trophy Room - Grenade Shells", "Grenade Shells", ()),
    ("Library", "Library - Green Herb 1", "Green Herb", ()),
    ("Library", "Library - Green Herb 2", "Green Herb", ()),
    ("Library", "Library - Last Book, vol. 2", "Last Book, vol. 2", ()),
    ("Materials Room", "Materials Room - Shotgun Shells", "Shotgun Shells", ()),
    ("Materials Room", "Materials Room - Acid Shells", "Acid Shells", ()),
    ("Materials Room", "Materials Room - Battery Pack", "Battery Pack", ()),
    ("Materials Room", "Materials Room - Battery", "Battery", ()),
    ("Main Garden", "Main Garden - Green Herb", "Green Herb", ()),
    ("Main Garden", "Main Garden - Blue Herb", "Blue Herb", ()),   # missed until seed test 5 (TessarionAM)
    ("Heliport", "Heliport - Signal Rockets", "Signal Rockets", ()),
    ("Zigzag Path", "Zigzag Path - Red Herb", "Red Herb", ()),
    ("Underground Statue Room", "Underground Statue Room - Cylinder", "Cylinder", ("Hexagonal Crank",)),
    ("Mining Area", "Mining Area - Green Herb", "Green Herb", ("Hexagonal Crank",)),
    ("Mining Area", "Mining Area - Ink Ribbon", "Ink Ribbon", ()),
    ("Generator Room", "Generator Room - Handgun Magazine 1", "Handgun Magazine", ()),
    ("Generator Room", "Generator Room - Shaft", "Shaft", ()),
    ("Generator Room", "Generator Room - Handgun Magazine 2", "Handgun Magazine", ()),
    ("Enrico Room", "Enrico Room - Hexagonal Crank", "Hexagonal Crank", ()),
    ("Boulder Passage 1", "Boulder Passage 1 - Shotgun Shells", "Shotgun Shells", ()),
    ("Spider Room", "Spider Room - Knife", "Knife", ()),
    ("Straight Passage", "Straight Passage - Blue Herb 1", "Blue Herb", ()),
    ("Straight Passage", "Straight Passage - Blue Herb 2", "Blue Herb", ()),
    ("Boulder Passage 2", "Boulder Passage 2 - First Aid Box", "First Aid Box", ()),
    # Evil Resource (Jill Normal): the Magnum is revealed with the Moon, Star and Sun Crests
    ("Small Headstone Area", "Small Headstone Area - Magnum", "Magnum", ("Wind Crest", "Moon Crest", "Star Crest", "Sun Crest")),
    ("Small Headstone Area", "Small Headstone Area - Star Crest", "Star Crest", ("Wind Crest",)),
    ("Small Headstone Area", "Small Headstone Area - Moon Crest", "Moon Crest", ("Wind Crest",)),
    ("Small Headstone Area", "Small Headstone Area - Sun Crest", "Sun Crest", ("Wind Crest",)),
    ("Cabin", "Cabin - Square Crank", "Square Crank", ()),
    ("Jessica's Tomb", "Jessica's Tomb - Barry's Magnum", "Barry's Magnum", ()),
    # the crate it's in is pushed down from the Underground Storage Room (TessarionAM's 2026-11-15
    # run: Storage Room 17:33, back in the Compactor Room 17:36, check 17:37)
    ("Garbage Compactor Room", "Garbage Compactor Room - Broken Flamethrower", "Broken Flamethrower", ()),
    ("Winding Underground Passage", "Winding Underground Passage - Green Herb", "Green Herb", ()),
    ("Winding Underground Passage", "Winding Underground Passage - Red Herb", "Red Herb", ()),
    ("Underground Storage Room", "Underground Storage Room - Handgun Magazine", "Handgun Magazine", ()),
    ("Underground Storage Room", "Underground Storage Room - Magnum Rounds", "Magnum Rounds", ()),
    ("Underground Storage Room", "Underground Storage Room - Battery Pack", "Battery Pack", ()),
    ("Lisa's Room", "Lisa's Room - Jewelry Box (Stone Ring)", "Jewelry Box (Stone Ring)", ()),
    ("Lisa's Room", "Lisa's Room - Green Herb", "Green Herb", ()),
    ("Lisa's Room", "Lisa's Room - Blue Herb", "Blue Herb", ()),
    ("Residence Entry Corridor", "Residence Entry Corridor - Blue Herb 1", "Blue Herb", ()),
    ("Residence Entry Corridor", "Residence Entry Corridor - Blue Herb 2", "Blue Herb", ()),
    ("Residence Entry Corridor", "Residence Entry Corridor - Blue Herb 3", "Blue Herb", ()),
    ("Room 001", "Room 001 - Handgun Magazine", "Handgun Magazine", ()),
    ("Room 001", "Room 001 - Self-Defence Gun", "Self-Defence Gun", ()),
    ("Room 001 Bathroom", "Room 001 Bathroom - Control Room Key", "Control Room Key", ()),
    ("Residence Storeroom", "Residence Storeroom - Battery Pack", "Battery Pack", ()),
    ("Residence Storeroom", "Residence Storeroom - Ink Ribbon", "Ink Ribbon", ()),
    ("Rec Room", "Rec Room - Green Herb 1", "Green Herb", ()),
    ("Rec Room", "Rec Room - Green Herb 2", "Green Herb", ()),
    ("Rec Room", "Rec Room - First Aid Box", "First Aid Box", ()),
    ("Rec Room", "Rec Room - Shotgun Shells", "Shotgun Shells", ()),
    ("Rec Room", "Rec Room - Red Book", "Red Book", ()),
    ("Room 002 Bathroom", "Room 002 Bathroom - 001 Key", "001 Key", ()),
    ("Gallery", "Gallery - Insecticide Spray", "Insecticide Spray", ()),
    ("Gallery", "Gallery - 003 Key", "003 Key", ("Insecticide Spray",)),   # under the giant beehive
    ("Gallery", "Gallery - Red Herb", "Red Herb", ()),
    ("Gallery", "Gallery - Handgun Magazine", "Handgun Magazine", ()),
    ("Plant 42 Room", "Plant 42 Room - Helmet Key", "Helmet Key", ()),
    ("Aqua Ring Entry", "Aqua Ring Entry - Green Herb", "Green Herb", ()),
    # in the Aqua Ring Exit, behind the Control Room Key door (TessarionAM, seed test 5)
    ("Aqua Ring Entry", "Aqua Ring Exit - Magnum Rounds", "Magnum Rounds", ("Control Room Key",)),
    ("Aqua Ring Storage", "Aqua Ring Storage - Shotgun Shells", "Shotgun Shells", ()),
    ("Control Room", "Control Room - First Aid Box", "First Aid Box", ()),
    ("Aqua Ring Water Tank", "Aqua Ring Water Tank - Gallery Key", "Gallery Key", ()),
    ("Passage to Heliport", "Passage to Heliport - Fuse Unit", "Fuse Unit", ()),
    ("Passage to Heliport", "Passage to Heliport - Shotgun Shells", "Shotgun Shells", ()),
    ("Passage to Heliport", "Passage to Heliport - First Aid Box", "First Aid Box", ()),
    ("Lab Item Box Room", "Lab Item Box Room - Ink Ribbon", "Ink Ribbon", ()),
    ("Lab Stairway", "Lab Stairway - MO Disk 2", "MO Disk 2", ()),
    ("Lab Stairway", "Lab Stairway - Green Herb 1", "Green Herb", ()),
    ("Lab Stairway", "Lab Stairway - Green Herb 2", "Green Herb", ()),
    ("Visual Data Room", "Visual Data Room - First Aid Spray", "First Aid Spray", ()),
    ("Visual Data Room", "Visual Data Room - Power Key", "Power Key", ()),
    ("Visual Data Room", "Visual Data Room - MO Disk 3", "MO Disk 3", ()),
    ("Visual Data Room", "Visual Data Room - Shotgun Shells", "Shotgun Shells", ()),
    ("'O' Room", "'O' Room - Dagger", "Dagger", ()),
    ("Operating Room", "Operating Room - First Aid Box", "First Aid Box", ()),
    ("Operating Room", "Operating Room - Battery Pack", "Battery Pack", ()),
    ("Operating Room", "Operating Room - Magnum Rounds", "Magnum Rounds", ()),
    ("Morgue", "Morgue - Battery Pack", "Battery Pack", ()),
    ("Morgue", "Morgue - Shotgun Shells", "Shotgun Shells", ()),
    ("Pass Code Corridor", "Pass Code Corridor - First Aid Box", "First Aid Box", ()),
    ("X-Ray Room B", "X-Ray Room B - X-Ray 2", "X-Ray 2", ()),
    ("X-Ray Room B", "X-Ray Room B - X-Ray 1", "X-Ray 1", ()),
    ("X-Ray Room A", "X-Ray Room A - Incendiary Shells", "Incendiary Shells", ()),
    ("X-Ray Room A", "X-Ray Room A - Slide Filter", "Slide Filter", ()),
    ("Lounge Room", "Lounge Room - Grenade Shells", "Grenade Shells", ()),
    ("Lounge Room", "Lounge Room - Ink Ribbon", "Ink Ribbon", ()),
    ("Lounge Room", "Lounge Room - First Aid Spray", "First Aid Spray", ()),
    ("Power Maze A", "Power Maze A - Fuel Capsule", "Fuel Capsule", ()),
    ("Power Maze B", "Power Maze B - Battery Pack", "Battery Pack", ()),
    ("Main Laboratory", "Main Laboratory - Master Key", "Master Key", ()),
    ("Main Laboratory Entrance", "Main Laboratory Entrance - Shotgun Shells", "Shotgun Shells", ()),
    # --- appended after the public release (IDs above never move) ---
    # 2026-11-14: Cell Shotgun Shells, flag +0x2FB bit 4. The client noted "item 18 arrived with new
    # bit +0x2fb bit 4" twice, both times with Jill in the Cell (0x512): 2026-11-13 13:51:37 and
    # 2026-11-14 00:53:05 (TessarionAM's logs).
    ("Cell", "Cell - Shotgun Shells", "Shotgun Shells", ()),
]

# Rooms with an ITEM BOX (2026-11-10, from where TessarionAM took items out of the box in his run,
# matching the typewriter rooms). Received items go to the item box, so they can only be USED
# after reaching one of these - the logic models that (see BOX_ACCESS in __init__.py).
BOX_ROOMS = ["Mansion Drug Room", "East Wing Storeroom", "Residence Storeroom", "Mining Area",
             "Cabin", "Altar Stairway Passage", "Lab Item Box Room", "Lounge Room"]

# Goal "complete_game": the helicopter ending. Fire the Signal Rockets at the Heliport
# (the Fuse Unit restores the power on the way) and beat the Tyrant.
# EVENTS: things that happen in the game world, not items you receive.
# (room, event name, requirements). The event is "had" once its room is reachable with them.
EVENTS = [
    ("'Death' Passage", ARMOR_SPOT, ("Collar",)),   # same as the 'Death' Passage - Armor Key pickup
    ("Concrete Passage 2", ELEVATOR_POWER, ()),       # the power switch for the Kitchen Elevator
    ("Plant 42 Room", HELMET_SPOT, ()),               # same as the Plant 42 Room - Helmet Key pickup
    # 2026-11-14 (TessarionAM: these only work from one side; flags from the mapping run 2026-11-10):
    ("Water Pool", POOL_DRAINED, ("Square Crank",)),                # +0x221.4
    ("Falls Area", BATTERY_LIFT, ("Battery",)),                     # +0x22A.6
    # 2026-11-15: the Broken Flamethrower is always placed below the cave lift, before Lisa's door
    ("Garbage Compactor Room", FLAMETHROWER_FOUND, ()),
]
EVENT_NAMES = frozenset(name for _, name, _ in EVENTS)

# MISSABLE checks (TessarionAM, 2026-11-12): a story choice decides whether you ever get them, so the
# check itself always holds a junk item, and its real item goes into the pool to be found
# elsewhere. Missable items that aren't a check yet (no flag mapped) still go into the pool.
MISSABLE = {
    "Jessica's Tomb - Barry's Magnum": "Barry's Magnum",   # keeping it gets Barry killed
    # Evil Resource: "If Barry got killed in the altar, this key will be on the body of Wesker"
    "Main Laboratory - Master Key": "Master Key",
    "Main Hall - Acid Shells (Barry)": "Acid Shells",      # only if Barry is there and you have room
    **{f"Greenhouse - Green Herb {i}": "Green Herb" for i in range(1, 6)},   # the Herbicide can kill them
    # using an Insecticide Spray (e.g. one received from the multiworld) removes the Gallery's own
    # spray from the game (TessarionAM, 2026-11-13); the client sends this check when a spray is used
    "Gallery - Insecticide Spray": "Insecticide Spray",
    "Outside Balcony - Collar (Cerberus)": "Collar",       # the whistle stops working once you have one
}
# Checks that can't be done any more once an item has been received: the tracker drops them.
GONE_WHEN = {"Outside Balcony - Collar (Cerberus)": "Collar"}
# The Broken Flamethrower is always placed at one of these (the area below Barry's cave lift, before
# Lisa's door - see DOORS). Picked at random among those that are checks in the seed.
FLAMETHROWER_LOCATIONS = ("Garbage Compactor Room - Broken Flamethrower",
                          "Winding Underground Passage - Green Herb", "Winding Underground Passage - Red Herb",
                          "Underground Storage Room - Handgun Magazine", "Underground Storage Room - Magnum Rounds",
                          "Underground Storage Room - Battery Pack")
# Bonus weapons that are never a location (TessarionAM, 2026-11-14): the Attic Assault Shotgun
# doesn't spawn for Jill at all, and Brad only drops the Heliport Rocket Launcher if both Barry and
# Chris were saved, which players can't be made to do. Both are delivered to the item box fine
# (logs 2026-11-12/13/14), so they stay in the pool as found items.
MISSABLE_POOL_ITEMS = ("Assault Shotgun", "Rocket Launcher")
# Spot events that happen when a pickup is taken from its vanilla spot. The live tracker only
# counts them once that pickup's check has really been collected (seed test 5, 2026-11-12).
EVENT_SPOT_CHECK = {ARMOR_SPOT: "'Death' Passage - Armor Key", HELMET_SPOT: "Plant 42 Room - Helmet Key"}

# Pickups that always stay vanilla, even when the client can see them (TessarionAM, seed test 3):
# the Serum is needed for Richard's story moment, which is on a timer.
KEEP_VANILLA = frozenset({"Mansion Drug Room - Serum"})

# Items the client hands to Jill directly, not via the item box (the Lock Pick goes to her hidden
# slot, the Book of Curses to her inventory - every item box needs the Sword Key to reach).
DIRECT_ITEMS = frozenset({"Lock Pick", "Book of Curses", "Broken Flamethrower"})

FINAL_ROOM = "Heliport"
FINAL_REQUIRES = ("Signal Rockets", "Fuse Unit")

# BOSS RUSH (TessarionAM, 2026-11-14): the Signal Rockets are locked behind these seven bosses. The
# client sends BOSS_RUSH_LOCATION once every kill bit is on; that location holds the Signal Rockets.
# (event name, region, kill bit in the per-enemy kill table, extra requirements)
# Kill bits: mapping run 2026-11-10, ONE sample each (test plan 04 confirms): EXPERIMENTAL.
BOSSES = [
    ("Crypt Crimson Head Defeated", "Crypt", (0x270, 6), MASKS),      # it wakes when the masks are in
    ("Plant 42 Defeated", "Plant 42 Room", (0x270, 3), ()),
    ("Yawn Defeated", "Library", (0x2A5, 0), ()),
    ("Black Tiger Defeated", "Spider Room", (0x2AD, 0), ()),
    ("Neptune Defeated", "Aqua Ring Water Tank", (0x2AC, 0), ()),    # confirmed by TessarionAM 2026-11-15
    ("Lisa Trevor Defeated", "Jessica's Tomb", (0x272, 0), ()),      # the Altar fight
    ("Tyrant Defeated", "Main Laboratory", (0x2AE, 1), ()),
]
BOSS_RUSH_LOCATION = "Boss Rush - All Bosses Defeated"
BOSS_RUSH_ITEM = "Signal Rockets"


# ---------------------------------------------------------------------------
# EXTRA CHECKS - things that are checks but don't give an inventory item.
# (category, room, location name, requirements). Each category has a YAML
# option to switch it on. They get their own ID range (see locations.py), so
# adding pickups later never shifts them. Append only after release.
#
# Maps - SOURCE: Evil Resource map object pages and a community map location
# guide (2015), read 2026-11-10, restated in our own words:
#   * Mansion 1F map: Art Room, inside the urn of the statue (push the wooden
#     chest over to climb up). No item needed.
#   * Mansion 2F map: Resting Room. Light the fire with the Lighter and put the
#     Wooden Mount in the frame above the fireplace; the map burns onto it.
#   The other 6 maps are appended further down (found 2026-11-10).
# Room entries (first_room_entries option): entering a room for the first time.
# One per GAME room: Tea Room shares 0x103 with Northern Corridor, so only
# "Northern Corridor" has one. Rooms found later are in LATE_ROOM_ENTRIES (appended at the
# END of EXTRA_CHECKS so existing IDs never shift).
ROOM_ENTRY_ROOMS = [
    "Main Hall", "Dining Room", "Bar", "Art Room", "'L' Corridor", "Winding Corridor",
    "Marble Room", "Living Room", "Outside Boiler", "Dark Corridor", "Roofed Passage",
    "Large Gallery", "Graveyard", "East Wing Stairway", "East Wing Storeroom",
    "West Wing Outer Stairway", "West Wing Inner Stairway", "Mansion Drug Room",
    "Small Storeroom", "Northern Corridor", "Greenhouse", "Researcher's Bedroom",
    "Tiger Statue Room", "Dining Room 2F", "Mirror Corridor", "'Death' Passage",
    "Outside Balcony", "Outside Patio", "'C' Corridor", "Small Library", "Armor Room",
    "Pillar Room", "Attic Entry", "Attic", "Small Dining Room", "Resting Room", "Deer Room",
    "Bedroom", "Fish Tank Room", "Kitchen", "Concrete Passage 2", "Concrete Passage 1",
]

# Rooms of the rest of the game (2026-11-10), appended so earlier IDs never shift.
ROOM_ENTRY_ROOMS += ['Large Art & Mirror Rooms', 'Courtyard Study', 'Elevator Corridor', 'Trophy Room', 'Library', 'Materials Room', 'Main Garden', 'Heliport', 'Zigzag Path', 'Underground Statue Room', 'Mining Area', 'Generator Room', 'Enrico Room', 'Boulder Passage 1', 'Spider Room', 'Straight Passage', 'Boulder Passage 2', 'Small Headstone Area', 'Cabin', "Jessica's Tomb", 'Garbage Compactor Room', 'Winding Underground Passage', 'Underground Storage Room', "Lisa's Room", 'Residence Entry Corridor', 'Room 001', 'Room 001 Bathroom', 'Residence Storeroom', 'Rec Room', 'Room 002 Bathroom', 'Gallery', 'Plant 42 Room', 'Aqua Ring Entry', 'Aqua Ring Storage', 'Control Room', 'Aqua Ring Water Tank', 'Passage to Heliport', 'Lab Item Box Room', 'Lab Stairway', 'Visual Data Room', "'O' Room", 'Operating Room', 'Morgue', 'Pass Code Corridor', 'X-Ray Room B', 'X-Ray Room A', 'Lounge Room', 'Power Maze A', 'Power Maze B', 'Main Laboratory', 'Main Laboratory Entrance', 'Altar Stairway Passage', 'Fountain', 'Residence Central Corridor', 'Room 002', 'Lab Entrance', 'Cell Entrance', 'Lab Elevator Entry', 'Heliport Elevator', 'Power Control Room', 'Cell', 'Elevator to Main Laboratory', 'Forked Passage']

# Rooms that were missing a First Visit check (code review 2026-11-11). Appended so no ID shifts.
# Bathroom and Crypt share their room number with Winding Corridor / Graveyard, so they can't
# have their own. Garden Shed only counts with goal complete_game (with mansion_escape it IS the goal).
LATE_ROOM_ENTRIES = ["Secret Passage", "Water Pool", "Falls Area", "Muddy Path", "Forest Pathway",
                     "Room 003", "Garden Shed"]

EXTRA_CHECKS = [
    ("map", "Art Room", "Art Room - Map of the Mansion 1F", ()),
    ("map", "Resting Room", "Resting Room - Map of the Mansion 2F", ("Lighter", "Wooden Mount")),
] + [("room", room, f"{room} - First Visit", ()) for room in ROOM_ENTRY_ROOMS] + [
    # The other maps (2026-11-10): each one turned on a single flag at +0x316/+0x317, with nothing
    # entering the inventory, while TessarionAM was in the room. Appended so earlier IDs never shift.
    ("map", "Concrete Passage 1", "Concrete Passage 1 - Map of the Mansion B1", ()),
    ("map", "Cabin", "Cabin - Map of the Courtyard", ()),
    ("map", "Straight Passage", "Straight Passage - Map of the Caves", ()),
    ("map", "Residence Central Corridor", "Residence Central Corridor - Map of the Residence", ()),
    ("map", "Control Room", "Control Room - Map of the Aqua Ring", ()),
    ("map", "Visual Data Room", "Visual Data Room - Map of the Laboratory", ()),
] + [("room", room, f"{room} - First Visit", ()) for room in LATE_ROOM_ENTRIES]

# FILES (2026-11-11): each document sets one bit at flags +0x318..+0x31B the moment it's read
# (event recorder runs 2026-11-10/11, matched to TessarionAM's "file" key presses and to rooms; the bits
# are saved and restored with the game). +0x319 bit 4 is NOT here: it turns on at every new game.
# Appended so no existing ID shifts. Option: files_and_notes.
SAVE_ROOM_NOTE = "Save Room Note (Drug Room or East Wing Storeroom)"
# Checks you can do from any one of several rooms: name -> the rooms.
EITHER_ROOM = {SAVE_ROOM_NOTE: ("Mansion Drug Room", "East Wing Storeroom")}
FILE_CHECKS = [
    ("Researcher's Bedroom", "Researcher's Bedroom - File", 0x318, 0),
    ("Small Library", "Small Library - File 1", 0x318, 1),
    ("Northern Corridor", "Northern Corridor - File", 0x318, 3),   # Tea Room / Northern Corridor (one game room)
    ("Room 002", "Room 002 - File", 0x318, 4),
    ("Room 003", "Room 003 - File", 0x318, 5),
    ("Trophy Room", "Trophy Room - File", 0x318, 6),
    ("Visual Data Room", "Visual Data Room - File", 0x318, 7),
    ("X-Ray Room A", "X-Ray Room A - File", 0x319, 1),
    ("Fish Tank Room", "Fish Tank Room - File", 0x319, 2),
    ("Room 001", "Room 001 - File", 0x319, 3),
    ("Dining Room", "Dining Room - File", 0x319, 5),   # GUESS: seen in the Dining Room and once in the Mirror Corridor
    ("Dining Room 2F", "Dining Room 2F - File", 0x319, 6),
    ("Jessica's Tomb", "Jessica's Tomb - File 1", 0x31a, 1),
    ("Main Laboratory", "Main Laboratory - File", 0x31a, 2),
    ("Bar", "Bar - File", 0x31a, 3),   # next to the Gold Emblem (TessarionAM)
    ("Secret Passage", "Secret Passage - File", 0x31a, 4),   # Sliding Trap Room
    ("Large Art & Mirror Rooms", "Large Art & Mirror Rooms - File", 0x31a, 5),
    ("Cabin", "Cabin - File", 0x31a, 6),
    ("Jessica's Tomb", "Jessica's Tomb - File 2", 0x31b, 2),
    ("Operating Room", "Operating Room - File", 0x31b, 4),
    # One note, two spots: it appears in whichever of the Mansion Drug Room / East Wing Storeroom you
    # enter first, and the other copy is deleted (TessarionAM, seed test 5). One check, reachable from
    # either room (EITHER_ROOM below). Flag from the event recorder (picked up in the East Wing
    # Storeroom, 2026-11-11 20:01). The old Drug Room guess (0x31a bit 0) is dropped.
    ("East Wing Storeroom", SAVE_ROOM_NOTE, 0x31b, 5),
    ("Small Library", "Small Library - File 2", 0x31b, 6),
]
# Files you can only reach after a puzzle (TessarionAM, seed test 4)
FILE_REQUIRES = {"Bar - File": ("Missing Music", "Music, mid-pages")}   # behind the piano wall: Moonlight Sonata
EXTRA_CHECKS += [("file", room, name, FILE_REQUIRES.get(name, ())) for room, name, _, _ in FILE_CHECKS]

# In-game item id each category's pickup shows (BhdTool's item table has a single
# "Map" = 130). Used by the client/mapper; the multiworld gets filler instead.
EXTRA_CATEGORY_GAME_ID = {"map": 130, "file": 9001}   # 9001 = our own marker for "a file" (no item)
