# Development tools

Not needed to play. These are the research tools used to map Resident Evil HD Remaster's memory
(pickup flags, the item box, doors, locks, Jill's position) and to test new features against the
running game. Their findings are built into `worlds/re1hd`.

## Setup

- Windows and Python 3.10 or newer. The tools use only the standard library, except
  `tools/key_map_preview.py` (Pillow).
- Run a tool with its launcher in `launchers/`, or from this folder: `python hd_inventory.py`.
  The launchers use a `.venv` in this folder or the repository root if one exists, otherwise
  `python` from the PATH.
- Each tool writes its results to `<tool>_output.txt` (and sometimes `.jsonl`) in this folder.
  These output files are not tracked in the repository.

The tools share the Archipelago client's own memory code: the `client` package here loads
`worlds/re1hd/client` without needing Archipelago installed.

## Tools

**Read-only (they only read the game's memory)**

| Tool | Purpose |
|---|---|
| `hd_inventory.py` | Identify the game build; show the inventory (`--box`: and the item box) live. |
| `hd_event_recorder.py` | Record flag changes while playing, with labels, to map new location types. |
| `hd_door_scanner.py` | Log every door record (lock and unlock flag) in each room entered. |
| `hd_jill_position_finder.py` | Find pointer paths to Jill's position after a game update. |
| `hd_scene_flag_finder.py` | Find a cutscene's "seen" flag. |
| `hd_health_watch.py` | Show Jill's health live; record poison and death states. |
| `hd_equip_watch.py` | Record the equipped and held weapon fields. |
| `hd_button_finder.py` | Find the controller button state. |
| `hd_death_load_watch.py` | Record the game's screens after a death and during loads. |
| `hd_death_memory_test.py` | What changes in memory on a death or load; door-unlock flags live (test plan 01). |
| `hd_load_menu_watch.py` | The save/load menu object and its state, for autoload (test plan 02; F10 is one optional write). |
| `hd_boss_watch.py` | Boss kill / story flags live, for the Boss Rush goal (test plan 04). |
| `hd_code_dump.py` | Save the game's program memory for disassembly. |

**Writing (they change the game's memory; use a spare save)**

| Tool | Purpose |
|---|---|
| `hd_door_shuffle_lab.py` | Test redirected doors, ladders and lifts (the door randomiser's method). |
| `hd_lock_lab.py` | Test changing door locks (the door lock randomiser's method). |
| `hd_wrong_door_test.py` | Test the Wrong Door trap's door redirection. |
| `hd_door_teleport.py` | Testing helper: every door in the room leads to a chosen room. |
| `hd_room_jump_test.py` | Move Jill to a room without a door (BhdTool's method), for the random start room (test plan 03). |
| `hd_scanner_tour.py` | Testing helper: visit rooms in turn for the door scanner. |
| `hd_flag_poke.py` | Testing helper: set a candidate flag. |
| `hd_door_skip.py` | Door skip on its own (the same patches as the client). |
| `hd_stack_test.py` | Put stacks of an item into the box to test stacking limits. |

**Data tools (`tools/`)**

| Tool | Purpose |
|---|---|
| `build_door_table.py` | Rebuild `worlds/re1hd/door_table.py` from the door scanner's data in `client/`. |
| `key_map_preview.py` | Render every Key Map floor to PNG, exactly as the client draws it. |
| `door_lock_batch.py` | Generate many seeds with the lock randomiser (run inside an Archipelago checkout). |
| `full_game_data.py`, `export_catalogue.py` | Turn a mapping run into world data (inside an Archipelago checkout). |
| `crash_info.bat` | Save Windows' error records from the last two hours to `crash_info.txt`. |

`client/*.json` holds research data the tools use: BhdTool's room list, the door animation
table pairs, scanned door locks, room names and the pickup catalogue.

## Test plans

`test_plans/` holds the in-game sessions Claude needs next, in order, each with its tool, steps,
what to send back and what it decides. Start with `test_plans/README.md`.

## Tests

```
python -m pytest dev/tests
```

The world and client tests run inside an Archipelago checkout:
`python -m pytest worlds/re1hd/test`.
