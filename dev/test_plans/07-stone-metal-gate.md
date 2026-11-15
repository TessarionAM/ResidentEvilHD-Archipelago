# 07 - Stone & Metal gate flags (WRITES - use a spare save, client closed)

**Why this is next.** It unblocks two things at once:
1. **A hole in today's logic.** The object is taken back off the gate for the Altar (both objects go
   into the Dining Room fireplace). If the gate closes again then, the Courtyard, Residence and
   Caves are cut off for the rest of the game, but the logic still counts on them.
2. **TessarionAM's idea:** once you have the object, the client opens the gate (and keeps it open).
   That also lets a Courtyard or Residence start walk back to the Mansion.

**What the recorded run shows (2026-11-10).**
- Placing the object (14:42:12, Roofed Passage): **+0x22D bit 3** and **+0x326 bit 1** turned on.
  Nothing else changed with it. Two other bits a few seconds later belong to entering the Garden
  Shed for the first time and were never cleared.
- Taking it back (17:53:21, Roofed Passage): those same two bits turned off, and **+0x304 bit 0**
  (the "take it back" pickup) turned on.
- The gate is not a door lock: the door scan shows the door itself as open. So the gate is a
  scripted object in the Roofed Passage that these bits switch.
- After taking it back, Jill never used the gate again in that run, so nobody knows yet whether
  it closes.

**Tools.** `launchers/run_hd_door_teleport.bat` (to get to the Garden Shed side) and
`launchers/run_hd_flag_poke.bat` (candidates 3 and 4). Close the Archipelago client.

## Part A - open it from the Garden Shed side (candidate 3)
Use any Mansion save from **before** the object has been put in the gate.
1. Door teleport: type `11b`, press **F10** in any room, walk through a door. Jill arrives in the
   Garden Shed at the door to the Roofed Passage.
2. Try that door. Write down what the game says.
3. Flag poke: type `3`, press **F9**. Try the door again.
   If it still refuses, go out to the Main Garden and back into the Garden Shed, then try again.
4. If it opens: in the Roofed Passage, is the object shown in the gate? Try to take it.
   Do you get a Stone & Metal Object? Does the gate still let you through afterwards?

## Part B - same, with the "already taken" bit (candidate 4)
Reload the same save. Repeat Part A with `4` instead of `3`.
Is the gate open with nothing to take?

## Part C - does the gate close after taking the object back? (no tools)
Use a save where the object IS in the gate (after reaching the Courtyard, before the Altar).
1. In the Roofed Passage, take the object back.
2. Try to go through to the Garden Shed. Open or closed?
3. If it's closed, put the object back, so the save isn't left stuck.

## Send
- What happened at each step, with the game's message if a door refused.
- `hd_flag_poke_output.txt` and `hd_door_teleport_output.txt` from the `dev` folder.

## What it decides
| Result | Build next |
|---|---|
| A works, no free object | Client sets the two bits once the object is received; logic becomes "have the object" from both sides |
| A works but gives a free object, B doesn't | Client uses candidate 4 (the three bits) |
| Neither opens it | The bits only change the visible object; look for the gate's own flag next (same bits, read with the room reloaded) |
| C: the gate closes | The client must keep the bits on after the take-back too; until then, the logic hole is real |
| C: the gate stays open | No hole today; the gate holder is only needed for random starts |

## Results so far
- **Part A (2026-11-14 17:35, candidate 3):** from the Garden Shed the door to the Roofed Passage
  opens even without the poke. Roofed Passage -> Garden Shed is what the gate blocks. With 3 the
  gate opens both ways and the object is shown; taking it closes the gate again (answers Part C).
- **Part B (17:45, candidate 4):** the object is shown, and picking it up CRASHES the game
  ("Failed open file ... nativePC\\arc\\itemv\\v.arc"). The "taken" bit removes the item from
  the pickup but not the object from the gate. Candidate 4 is out.

## Part D - which bit is the gate, which is the object? (candidates 5 and 6)
Same start as Part A (Mansion save before placing the object, teleport to `11b`, client closed).
1. Flag poke `5`, F9. Go out to the Main Garden and back in. Try Garden Shed -> Roofed Passage ->
   back into the Garden Shed. Does the gate let you back in? Is the object shown? **Don't pick it up.**
2. Reload, repeat with `6`.
3. Send what you saw for each, and `hd_flag_poke_output.txt`.

Hoped-for result: one bit opens the gate with NO object shown. The client then keeps only that
bit on, and nobody can get a free object or hit the crash.

- **Part D (17:50-17:52):** `5` (+0x22D.3 only) opens the gate both ways and the object is shown.
  `6` (+0x326.1 only) does nothing: the gate stays shut from the Roofed Passage.
  So +0x22D.3 is the gate (and the object's model); +0x326.1 is probably the pickup itself.

## Part E - candidate 5, then pick the object up
Same start, `5`, F9, go into the Roofed Passage and try to take the object. A crash is harmless
(memory only - reload). Then try the gate again.
- Crash, nothing to take, or a Stone & Metal Object in the inventory?
- Gate open or closed afterwards?

| Result | Gate holder |
|---|---|
| Nothing to take (no crash) | Client keeps +0x22D.3 on after the take-back / once the object is received |
| You get an object | Same, plus the client takes away the extra object picked up there |
| Crash | Find the object's model/pickup separately (code dump) before building |
