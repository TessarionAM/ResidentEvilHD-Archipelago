# 03 - Room jump for the random start room (WRITES - spare save)

**Why.** `random_start_room` needs to move Jill into a room without walking through a door. BhdTool
does this by answering the game's per-frame trigger check (0x47D6E0, called from 0x48AF56) with a
filled "target room" buffer. The tool does the same with a small stub; the game's own room change
does the rest. It must be proven before anything is built on it.

**Tool.** `launchers/run_hd_room_jump_test.bat` (client closed; BhdTool may stay installed).

**Steps**
1. At the prompt press Enter for the default list (Dining Room 105, East Wing Storeroom 118, Cabin
   314, Residence Storeroom 403, Room 003 40a, Mining Area 307, Lab Item Box Room 502), or type your own.
2. Load a spare save in the Main Hall. Press **F10**. Jill should appear in the first room.
3. In each room check: crash, black screen, Jill inside a wall, camera, does a cutscene play that
   shouldn't (or not play), do the doors work, can you use the typewriter / item box. Then F10 again.
4. Do one jump from a brand-new game (straight after the opening, before the Dining Room) and
   report whether Barry's Lock Pick scene still happens when you go back to the Main Hall.

**Send.** `hd_room_jump_test_output.txt` and notes per room.

**Decides.** Jump method (no door) vs the proven door-redirect method; which rooms are safe starts.

## Results (2026-11-15, TessarionAM)
- All 7 default rooms: a slow fade to black, then Jill in the room. Items, camera and doors all
  normal; leaving by a door went to the right place. The jump method works (no door needed).
- Last check (new game): the tool was given `106`, which is the **Main Hall** (Claude's mistake in
  the steps: the Dining Room is `105`). So Jill jumped Main Hall -> Main Hall (the stub fired 10.1 s
  after F10, once the opening let her move), then walked into the Dining Room and back as normal and
  got the Lock Pick. That only proves the normal intro still works after a jump.
- The output file was overwritten by that last run, so the 7-room run's log is gone; every tool now
  adds runs to the end of its file instead.

## Last check, again (new game, client closed)
1. New Game. As soon as Jill can move in the Main Hall, run the tool with `107` (Art Room, one
   door from the Main Hall) and press F10. She skips the Dining Room completely.
2. Walk straight back into the Main Hall. Does Barry still give the Lock Pick? Then go to the
   Dining Room: does anything odd happen (a missing or repeated scene)?
