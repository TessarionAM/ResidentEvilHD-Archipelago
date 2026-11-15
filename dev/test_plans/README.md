# Test plans

Each plan is one in-game session for TessarionAM, in the order Claude needs them. Every plan says
what to do, which tool to run (`../launchers/`), what to send back and what the result decides.
Use a spare save for anything marked WRITES.

| # | Plan | Tool | Decides |
|---|---|---|---|
| 01 | [Death and reload memory](01-death-and-reload-memory.md) | `run_hd_death_memory_test.bat` (read-only) | Why the Graveyard gate relocked; what the client must redo after a death or load |
| 02 | [Autoload after a death](02-autoload-load-menu.md) | `run_hd_load_menu_watch.bat` (read-only, one optional write) | Whether the client can load the autosave by itself |
| 03 | [Room jump (random start room)](03-room-jump.md) | `run_hd_room_jump_test.bat` (WRITES) | Whether `random_start_room` can move Jill without a door |
| 04 | [Boss flags (Boss Rush goal)](04-boss-flags.md) | `run_hd_boss_watch.bat` (read-only) | Which bits mean "boss defeated" |
| 05 | [One-sided gates](05-one-sided-gates.md) | `run_hd_door_teleport.bat` (WRITES) or a normal save | ANSWERED by TessarionAM: both one-sided (logic fixed in 0.9.22) |
| 06 | [Doorknob guard](06-doorknob-guard.md) | the client (v0.9.19+) | Whether the East Wing doorknob door stays usable |
| 07 | [Stone & Metal gate flags](07-stone-metal-gate.md) | `run_hd_flag_poke.bat` (WRITES) | Whether the client can open the gate (and keep it open) |
| 08 | [Courtyard lifts](08-courtyard-lifts.md) | the client (v0.9.23+) | Whether the lifts really wait on Jill's floor |

Plans 01 and 04 can run at the same time as the client. Plans 02, 03, 05 and 07 are best done with
the client closed, so its own hooks and door changes don't mix into the results.
