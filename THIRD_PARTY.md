# Credits and third-party work

Anyone whose work this project uses (code, data, memory addresses, item tables, logic or
research) is credited here. Files that use such work also carry a `SOURCE:` note at the top.

## Benn Powell: RE Randomizer for Resident Evil HD Remaster

https://ko-fi.com/bennpowell (@bennpowell)

Benn Powell's randomiser for the Steam HD Remaster was the inspiration for moving this project
to the HD Remaster, and the design reference for it: it showed that randomising this game at
runtime works, and its feature set (items, keys, enemies, doors and locks) and win condition
shaped ours. It is closed source; none of its code or data is included in this project.

## BhdTool by eleval (GPL-3.0)

https://github.com/eleval/BhdTool

Used for the Steam version:

- `worlds/re1hd/client/hd_versions.py`: bhd.exe SHA-256 hashes, Steam build IDs, the inventory
  pointer and the inventory layout.
- `worlds/re1hd/client/door_skip.py`: the Door Skip code patches and their addresses. BhdTool
  credits the lab elevator sound fix to FluffyQuack's door skip mod.
- `dev/client/hd_items.py`: the item ID table (generated from `REmakeHook/src/Game/Items.h`).
- `dev/client/bhdtool_rooms.json`: BhdTool's room list with door positions, used by the research
  tools.

BhdTool is GPL-3.0, and so is this project (see `LICENSE`).

## Evil Resource (evilresource.com)

https://www.evilresource.com/resident-evil-remake

- The world's room, item and door data (`worlds/re1hd/data.py`) for Jill on Normal: which items
  are in each room, how rooms connect and which keys open which doors. Facts were read from each
  room page and restated in our own words.
- The Key Map's room shapes (`worlds/re1hd/map_layout.py`) were traced from Evil Resource's maps
  into our own grid data. No images are included.

## Archipelago (MIT)

https://github.com/ArchipelagoMW/Archipelago

The multiworld framework this world is built for. The client
(`worlds/re1hd/client/RE1HDClient.py`) is built on Archipelago's `CommonClient` and registers
with `worlds.LauncherComponents`. Archipelago's Kingdom Hearts 2 client was a reference for the
overall shape of a memory-reading client; no code was copied from it.

## Research references

- The REmake SRT tools (speedrun.com community): their notes on how the inventory table behaves
  informed the delivery design.
- BioRand by IntelOrca and team (MIT), https://github.com/biorand/classic: a reference for
  Resident Evil key-item placement logic. No code used.
