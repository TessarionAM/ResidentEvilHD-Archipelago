# Resident Evil HD Remaster for Archipelago

An [Archipelago](https://archipelago.gg) multiworld randomiser for **Resident Evil HD Remaster**
(Steam, Windows). Every item pickup in the game is shuffled across the multiworld, and items found
for you by other players are delivered straight into the game while you play. No other tools or
mods are needed.

Supports Jill on Normal difficulty, for the whole game.

## Features

**Locations**
- Every item pickup in the game: keys, quest items, weapons, ammo, herbs and more.
- Optional: the 8 maps, the 22 files and notes, and the first visit to each of the 112 rooms.

**Goals**
- Escape on the helicopter at the end of the game, or a shorter game ending in the Courtyard.

**Randomisers**
- Door lock randomiser: which key opens which door (Mansion only, per area, or across the whole
  game), with a configurable number of locked doors.
- Door randomiser (experimental, still being tested): where doors, ladders and lifts lead,
  coupled or decoupled.
- Random starting inventory.
- Every seed is checked to be beatable, with a way back from every reachable room.

**Traps and specials**
- Traps: Damage, Poison, Critical Damage and Ammo Leak.
- Fun traps: harmless pranks (fake crash, "To Be Continued...", fake item, fake Death Link,
  window shake, fake self-destruct, danger flash, and the Wrong Door to the Laboratory Cell).
  Their Archipelago message appears once the prank is over.
- Special items: Infinite Ammo and the Defence Bundle.
- Death Link.

**Quality of life**
- Received items go to the item box, so nothing is lost when the inventory is full.
- Open the item box from save rooms or anywhere (F7, a controller button or `/itembox`), with
  automatic sorting.
- Autosave in save rooms without Ink Ribbons, and skipping of door animations.
- A Key Map of every floor in the client: doors coloured by key, Jill's room from her actual
  position, hover details and shortcut buttons.
- A Tracker of reachable locations, borderless fullscreen with on-screen messages, and a
  resolution setting.

## Installation

1. Install [Archipelago](https://github.com/ArchipelagoMW/Archipelago/releases) 0.6.7 or newer.
2. Download `re1hd.apworld` from the releases page and put it in Archipelago's `custom_worlds`
   folder.
3. Copy `yamls/Resident Evil HD Remaster.yaml` into Archipelago's `Players` folder, set `name`
   and choose your options.

The full setup and play guide, including every client command, is in
[worlds/re1hd/docs/setup_en.md](worlds/re1hd/docs/setup_en.md).

## Reporting problems

Open an issue with your Archipelago client log (in Archipelago's `logs` folder), your YAML and,
for logic problems, the seed.

## Repository layout

| Path | Contents | Needed to play? |
|---|---|---|
| `worlds/re1hd/` | The Archipelago world and client (built into `re1hd.apworld`) | Yes, as the `.apworld` |
| `worlds/re1hd/docs/` | Game page and setup guide shown by Archipelago | Read online |
| `worlds/re1hd/test/` | World and client tests | No |
| `yamls/` | Player settings template | Yes |
| `dev/` | Research tools used to map the game's memory (see `dev/README.md`) | No |

## Building from source

Copy `worlds/re1hd` into an Archipelago source checkout's `worlds` folder, then either run the
**Build APWorlds** component from the Archipelago Launcher, or run the tests:

```
python -m pytest worlds/re1hd/test
```

## Credits

- **Benn Powell**, whose RE HD Remaster randomiser inspired this project and served as its
  design reference.
- **eleval**, for BhdTool: game builds, memory addresses, the item table and door skip.
- **Evil Resource**, for the room, item and door data and the maps the Key Map is traced from.
- **The Archipelago team and community.**

Full details are in [THIRD_PARTY.md](THIRD_PARTY.md).

## Licence

GPL-3.0. See [LICENSE](LICENSE).
