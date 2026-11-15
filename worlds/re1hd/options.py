"""
Player options. Options that are fixed or not implemented yet are hidden (Visibility.none), so they
never appear on the website or in templates; YAMLs that still set them keep working.
"""

from dataclasses import dataclass

from Options import (Choice, DeathLink, DefaultOnToggle, NamedRange, OptionGroup, PerGameCommonOptions, Range,
                     Toggle, Visibility)


class Character(Choice):
    """The playable character. Only Jill is supported."""
    visibility = Visibility.none     # hidden: fixed, or not implemented
    display_name = "Character"
    option_jill = 0
    default = 0


class Difficulty(Choice):
    """The game difficulty. Only Normal is supported (item placements differ between difficulties)."""
    visibility = Visibility.none     # hidden: fixed, or not implemented
    display_name = "Difficulty"
    option_normal = 2
    default = 2


class Goal(Choice):
    """The victory condition.
    complete_game: Escape on the helicopter at the end of the game.
    mansion_escape: Leave the Mansion for the Courtyard by using the Stone & Metal Object on the
    gate in the Roofed Passage. A shorter game."""
    display_name = "Goal"
    option_mansion_escape = 0
    option_complete_game = 1
    default = 1


class BossRush(Toggle):
    """EXPERIMENTAL. The Signal Rockets are locked behind the seven bosses: the Crypt Crimson Head,
    Plant 42, Yawn (Library), Black Tiger, Neptune, Lisa Trevor (Altar) and the Tyrant (Lab).
    When all seven are dead the Signal Rockets go straight into Jill's inventory. Defeat the
    other six before the Lab Tyrant: after it the Laboratory self-destructs and there's no way
    back. Only with goal complete_game."""
    display_name = "Boss Rush"


class ItemPickups(DefaultOnToggle):
    """Every item pickup is a location. Always on."""
    visibility = Visibility.none     # no effect: pickups are always locations
    display_name = "Item Pickups"


class OnlyDetectedPickups(DefaultOnToggle):
    """Only pickups the client can detect become locations; any other pickup keeps its normal
    item. Always on."""
    visibility = Visibility.none     # hidden: fixed, or not implemented
    display_name = "Only Detected Pickups"


class MapChecks(DefaultOnToggle):
    """Picking up a map is a location. You still receive the map."""
    display_name = "Maps Are Checks"


class BossDefeats(Toggle):
    """Defeating a boss is a location. Not implemented."""
    visibility = Visibility.none     # hidden: fixed, or not implemented
    display_name = "Boss Defeats (not yet implemented)"


class FirstRoomEntries(Toggle):
    """Entering each room for the first time is a location."""
    display_name = "First Room Entries"


class EnemyChecks(Choice):
    """Killing enemies is a location. Not implemented.
    off: Enemy kills are not locations.
    species: The first kill of each enemy type is a location.
    every_enemy: Every enemy is a location."""
    visibility = Visibility.none     # hidden: fixed, or not implemented
    display_name = "Enemy Checks (not yet implemented)"
    option_off = 0
    option_species = 1
    option_every_enemy = 2
    default = 0


class FilesAndNotes(Toggle):
    """Reading each file or note for the first time is a location. You keep the file."""
    display_name = "Files and Notes"


class ReceivedItemDestination(Choice):
    """Where items received from the multiworld are placed.
    item_box: In the item box. Ammo and Ink Ribbons stack onto matching stacks.
    inventory_then_box: In Jill's inventory when there is space, otherwise in the item box.
    The Lock Pick and the Book of Curses (Sword Key) always go straight to Jill's inventory."""
    display_name = "Received Item Destination"
    option_item_box = 0
    option_inventory_then_box = 1
    default = 0


class StartWithSwordKey(Toggle):
    """Start the game holding the Book of Curses, which contains the Sword Key."""
    display_name = "Start With Sword Key"


class RandomStartingInventory(Toggle):
    """Start a new game with two random items instead of the Handgun and Combat Knife, which are
    added to the item pool."""
    display_name = "Random Starting Inventory"


class RandomStartGuaranteedGun(DefaultOnToggle):
    """When random_starting_inventory is on, one of the two starting items is always a gun
    (Handgun, Shotgun, Grenade Launcher or Magnum)."""
    display_name = "Random Start: Guaranteed Gun"


class RandomStartRoom(Choice):
    """EXPERIMENTAL. Start a new game in a random save room instead of the Main Hall. A new game
    begins in the Main Hall as usual; about ten seconds in, the client moves Jill to the start room.
    The intro replays the first time you walk back into the Main Hall.
    mansion_save_rooms: the Dining Room or the East Wing Storeroom.
    save_rooms: also the Mining Area, the Cabin or the Residence Storeroom.
    Seeds are only made with a start room they can be finished from."""
    display_name = "Random Start Room"
    option_off = 0
    option_mansion_save_rooms = 1
    option_save_rooms = 2
    default = 0


class TrapPercentage(Range):
    """Percentage of filler items (herbs, ammo, sprays) replaced by traps."""
    display_name = "Trap Percentage"
    range_start = 0
    range_end = 100
    default = 0


class DamageTrapWeight(Range):
    """Relative weight of the Damage Trap among traps."""
    display_name = "Damage Trap Weight"
    range_start = 0
    range_end = 100
    default = 50


class PoisonTrapWeight(Range):
    """Relative weight of the Poison Trap among traps. Jill is poisoned until cured with a Blue Herb."""
    display_name = "Poison Trap Weight"
    range_start = 0
    range_end = 100
    default = 50


class CriticalDamageTrapWeight(Range):
    """Relative weight of the Critical Damage Trap among traps. Jill drops to 1 health; it never kills."""
    display_name = "Critical Damage Trap Weight"
    range_start = 0
    range_end = 100
    default = 5


class AmmoLeakTrapWeight(Range):
    """Relative weight of the Ammo Leak Trap among traps. One stack of ammo in the inventory or item box is lost."""
    display_name = "Ammo Leak Trap Weight"
    range_start = 0
    range_end = 100
    default = 25


class FunTrapPercentage(Range):
    """Percentage of the remaining filler items replaced by fun traps: harmless pranks that do not
    affect the game."""
    display_name = "Fun Trap Percentage"
    range_start = 0
    range_end = 100
    default = 0


class FakeCrashTrapWeight(Range):
    """Relative weight of the Fake Crash fun trap: a fake error message. At most one per seed."""
    display_name = "Fake Crash Trap Weight"
    range_start = 0
    range_end = 100
    default = 5


class ToBeContinuedTrapWeight(Range):
    """Relative weight of the To Be Continued fun trap: the screen fades to "To Be Continued..."."""
    display_name = "To Be Continued Trap Weight"
    range_start = 0
    range_end = 100
    default = 25


class FakeItemTrapWeight(Range):
    """Relative weight of the Fake Item fun trap: a message announcing a key item that does not arrive."""
    display_name = "Fake Item Trap Weight"
    range_start = 0
    range_end = 100
    default = 30


class FakeDeathLinkTrapWeight(Range):
    """Relative weight of the Fake Death Link fun trap: a Death Link message with no effect."""
    display_name = "Fake Death Link Trap Weight"
    range_start = 0
    range_end = 100
    default = 25


class WindowShakeTrapWeight(Range):
    """Relative weight of the Window Shake fun trap: the game window shakes briefly (windowed or borderless only)."""
    display_name = "Window Shake Trap Weight"
    range_start = 0
    range_end = 100
    default = 25


class SelfDestructTrapWeight(Range):
    """Relative weight of the Self-Destruct fun trap: a fake self-destruct announcement."""
    display_name = "Self-Destruct Trap Weight"
    range_start = 0
    range_end = 100
    default = 25


class DangerFlashTrapWeight(Range):
    """Relative weight of the Danger Flash fun trap: the screen edges pulse red. No damage."""
    display_name = "Danger Flash Trap Weight"
    range_start = 0
    range_end = 100
    default = 25


class DoorLockRandomisation(Choice):
    """Shuffles which key opens which door. Each key arrives with as many uses as it has doors.
    disabled: Normal locks.
    mansion_only: Mansion doors with Mansion keys (Sword, Armor, Shield, Helmet, Lock Pick).
    regional: Mansion, Residence and Laboratory doors, each area keeping its own keys.
    full: Any key on any of those doors.
    Electronic doors, lifts, ladders and the doors of save rooms and boss rooms are never changed."""
    display_name = "Door Lock Randomisation"
    option_disabled = 0
    option_mansion_only = 1
    option_regional = 2
    option_full = 3
    default = 0


class DoorRandomisation(Choice):
    """EXPERIMENTAL: still being tested. A story event that doesn't expect a changed door can
    trap Jill, so keep a spare save.
    Shuffles where doors, ladders and lifts lead. Locks stay on their doors. Every seed is
    beatable, and every reachable room has a way back. Story doors, one-way drops and the
    final escape route are never changed.
    off: Normal doors.
    coupled: Going back through the door you arrived by returns you to where you came from.
    decoupled: Every door always leads to the same place, but not necessarily back."""
    display_name = "Door Randomisation (Experimental)"
    option_off = 0
    option_coupled = 1
    option_decoupled = 2
    default = 0


class LockedDoorCount(NamedRange):
    """The number of locked doors when door_lock_randomisation is on.
    vanilla: The normal number (24 for mansion_only, 30 otherwise).
    fewer: 25% fewer. more: 25% more. many: 50% more.
    Or an exact number. Maximum 42 for mansion_only and 65 for regional or full."""
    display_name = "Locked Door Count"
    range_start = 0
    range_end = 65
    default = -1
    special_range_names = {"vanilla": -1, "fewer": -2, "more": -3, "many": -4}


class WrongDoorTrapWeight(Range):
    """Relative weight of the Wrong Door fun trap: the next door leads to the Laboratory Cell,
    locked for 15 seconds, then back to where Jill was."""
    display_name = "Wrong Door Trap Weight"
    range_start = 0
    range_end = 100
    default = 25


class SpecialItemPercentage(Range):
    """Percentage of the remaining filler items replaced by special items."""
    display_name = "Special Item Percentage"
    range_start = 0
    range_end = 100
    default = 0


class InfiniteAmmoWeight(Range):
    """Relative weight of Infinite Ammo among special items: the equipped gun uses no ammo for 20 seconds."""
    display_name = "Infinite Ammo Weight"
    range_start = 0
    range_end = 100
    default = 50


class DefenceBundleWeight(Range):
    """Relative weight of the Defence Bundle among special items: one Dagger and one Battery Pack."""
    display_name = "Defence Bundle Weight"
    range_start = 0
    range_end = 100
    default = 50


class DamageTrapAmount(Range):
    """Health taken by a Damage Trap, as a percentage of Jill's maximum health. Always at least one health state."""
    display_name = "Damage Trap Amount"
    range_start = 5
    range_end = 100
    default = 25


class DamageTrapCanKill(Toggle):
    """Whether a Damage Trap can kill Jill. When off, it never takes her below 1 health."""
    display_name = "Damage Trap Can Kill"


class DoorSkip(Toggle):
    """Skip the door-opening animations. Can be toggled in the client with /doorskip."""
    display_name = "Door Skip"


class ItemBoxAutoSort(DefaultOnToggle):
    """Sort the item box when entering an item box room: keys first, then quest items, weapons,
    ammo and healing items, with stacks merged. /sortbox sorts it at any time."""
    display_name = "Item Box Auto Sort"


class KeyMapShortcuts(DefaultOnToggle):
    """Shortcut buttons on the client's Key Map, one for each typewriter room. The next door Jill
    goes through leads to that room. Each unlocks once that room has been visited."""
    display_name = "Key Map Shortcuts"


class ItemBoxAnywhere(Choice):
    """Open the item box away from item boxes with F7, the item_box_button, or /itembox.
    off: Item boxes only.
    save_rooms: In rooms with a typewriter.
    anywhere: In any room."""
    display_name = "Item Box Anywhere"
    option_off = 0
    option_save_rooms = 1
    option_anywhere = 2
    default = 1


class GameResolution(Choice):
    """The game's rendering resolution, written to the game's config.ini and applied the next time
    the game starts. Resolutions above the monitor's are skipped.
    keep: Leave config.ini unchanged."""
    display_name = "Game Resolution"
    option_keep = 0
    option_1080p = 1
    option_1440p = 2
    option_4k = 3
    default = 0


class ItemBoxButton(Choice):
    """The controller button that opens the item box when item_box_anywhere is on.
    back_plus_lb: Hold Back/Select and press LB/L1."""
    display_name = "Item Box Button"
    option_off = 0
    option_lb_l1 = 1
    option_rb_r1 = 2
    option_lt_l2 = 3
    option_rt_r2 = 4
    option_l3 = 5
    option_r3 = 6
    option_back_select = 7
    option_back_plus_lb = 8
    default = 1


class BorderlessFullscreen(Toggle):
    """Run the game borderless fullscreen so Archipelago messages appear over it. Set the game to
    windowed mode. Can be toggled in the client with /borderless."""
    display_name = "Borderless Fullscreen"


class Autosave(Toggle):
    """Save automatically, without an Ink Ribbon, when entering a save room. The starting item box's
    Ink Ribbons are replaced by a random item."""
    display_name = "Autosave in Save Rooms"


class AutosaveSlot(Range):
    """The save slot used by autosave. Saving to this slot manually will be overwritten."""
    display_name = "Autosave Slot"
    range_start = 1
    range_end = 8
    default = 8


class AutoloadAfterDeath(Toggle):
    """EXPERIMENTAL. Needs Autosave. After Jill dies, the client loads your autosave slot by itself as
    soon as the title screen's menu is up, putting you back in the last save room you walked into.
    Only after the client has autosaved at least once in this seed."""
    display_name = "Autoload After Death"


class DeathLinkEffect(Choice):
    """What happens to Jill when a Death Link is received.
    kill: Jill dies.
    lose_health_state: Jill loses one health state."""
    display_name = "Death Link Effect"
    option_lose_health_state = 0
    option_kill = 1
    default = 1


@dataclass
class RE1HDOptions(PerGameCommonOptions):
    character: Character
    difficulty: Difficulty
    goal: Goal
    boss_rush: BossRush
    item_pickups: ItemPickups
    only_detected_pickups: OnlyDetectedPickups
    map_checks: MapChecks
    boss_defeats: BossDefeats
    first_room_entries: FirstRoomEntries
    enemy_checks: EnemyChecks
    files_and_notes: FilesAndNotes
    received_item_destination: ReceivedItemDestination
    start_with_sword_key: StartWithSwordKey
    random_starting_inventory: RandomStartingInventory
    random_start_guaranteed_gun: RandomStartGuaranteedGun
    random_start_room: RandomStartRoom
    trap_percentage: TrapPercentage
    damage_trap_weight: DamageTrapWeight
    poison_trap_weight: PoisonTrapWeight
    critical_damage_trap_weight: CriticalDamageTrapWeight
    ammo_leak_trap_weight: AmmoLeakTrapWeight
    fun_trap_percentage: FunTrapPercentage
    fake_crash_trap_weight: FakeCrashTrapWeight
    to_be_continued_trap_weight: ToBeContinuedTrapWeight
    fake_item_trap_weight: FakeItemTrapWeight
    fake_death_link_trap_weight: FakeDeathLinkTrapWeight
    window_shake_trap_weight: WindowShakeTrapWeight
    self_destruct_trap_weight: SelfDestructTrapWeight
    danger_flash_trap_weight: DangerFlashTrapWeight
    wrong_door_trap_weight: WrongDoorTrapWeight
    door_lock_randomisation: DoorLockRandomisation
    locked_door_count: LockedDoorCount
    door_randomisation: DoorRandomisation
    special_item_percentage: SpecialItemPercentage
    infinite_ammo_weight: InfiniteAmmoWeight
    defence_bundle_weight: DefenceBundleWeight
    damage_trap_amount: DamageTrapAmount
    damage_trap_can_kill: DamageTrapCanKill
    death_link: DeathLink
    death_link_effect: DeathLinkEffect
    door_skip: DoorSkip
    item_box_auto_sort: ItemBoxAutoSort
    key_map_shortcuts: KeyMapShortcuts
    item_box_anywhere: ItemBoxAnywhere
    item_box_button: ItemBoxButton
    game_resolution: GameResolution
    borderless_fullscreen: BorderlessFullscreen
    autosave: Autosave
    autosave_slot: AutosaveSlot
    autoload_after_death: AutoloadAfterDeath


# Planned check types (hidden options; the world warns if a YAML turns them on).
NOT_YET_IMPLEMENTED = ("boss_defeats", "enemy_checks")


# Order of the options on the website and in generated templates.
OPTION_GROUPS = [
    OptionGroup("Victory Conditions", [Goal, BossRush]),
    OptionGroup("Features", [MapChecks, FirstRoomEntries, FilesAndNotes,
                             ReceivedItemDestination, StartWithSwordKey, RandomStartingInventory,
                             RandomStartGuaranteedGun, RandomStartRoom, DoorLockRandomisation, LockedDoorCount,
                             DoorRandomisation,
                             SpecialItemPercentage, InfiniteAmmoWeight, DefenceBundleWeight,
                             DeathLink, DeathLinkEffect]),
    OptionGroup("Quality of Life", [ItemBoxAutoSort, ItemBoxAnywhere, ItemBoxButton, KeyMapShortcuts,
                                    DoorSkip, Autosave, AutosaveSlot, AutoloadAfterDeath, BorderlessFullscreen,
                                    GameResolution]),
    OptionGroup("Traps", [TrapPercentage, DamageTrapWeight, PoisonTrapWeight, CriticalDamageTrapWeight,
                          AmmoLeakTrapWeight, DamageTrapAmount, DamageTrapCanKill, FunTrapPercentage,
                          FakeCrashTrapWeight, ToBeContinuedTrapWeight, FakeItemTrapWeight,
                          FakeDeathLinkTrapWeight, WindowShakeTrapWeight, SelfDestructTrapWeight,
                          DangerFlashTrapWeight, WrongDoorTrapWeight]),
]
