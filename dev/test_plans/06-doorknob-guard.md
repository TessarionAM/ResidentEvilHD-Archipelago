# 06 - Doorknob guard (client v0.9.19+, run with 0.9.25)

**Why.** The door between the East Wing Stairway (room 207) and the 'C' Corridor (room 204) has a
handle that breaks in the vanilla game; after that the door only opens from the 'C' Corridor. With
randomised items or locks that can cut the corridor off.

**What the client does.** The door scan says the stairway side of that door record is lock type 21
("opens from this side"), unlock flag 16. Every time the room loads, the client puts that side
back to 21 if it finds anything else, and logs what it saw:
- `Doorknob door (stairway side): lock type N, flag 16.` - every time the record is seen
- `Doorknob: the stairway side was type N - set back to 21 ...` - when it had to fix it
- With the lock randomiser on, the seed's own lock is written instead (`_lock_tick`), so the guard
  stays quiet - say which kind of seed you used.

**Unknown (what this test answers).** Whether the break lives in that door record at all. If the
game keeps "handle broken" in a separate flag (like the Stone & Metal gate), the record looks fine
and the door still breaks. The event recorder catches that flag.

## Steps
1. Start the game and the client as normal (v0.9.25), load a save near the East Wing Stairway.
2. Start `launchers/run_hd_event_recorder.bat` too (read-only).
3. Go from the East Wing Stairway through the door into the 'C' Corridor, and back. Repeat at least
   **4 times**. Whenever the handle breaks (message or scene), press **End** in the game straight
   away - that marks the moment in the recorder.
4. Then try the door from the stairway side again: does it open?
5. Die (or load a save), and use the door from the stairway side once more.

## Send
- What you saw each time (did it break? which use? what did the game say?).
- The newest `RE1HDClient_....txt` from the `logs` folder in your Archipelago folder.
- `hd_event_recorder_output.txt` and `hd_event_recorder_events.jsonl` from the `dev` folder.

## What it decides
| Result | Next |
|---|---|
| Never breaks; log shows "set back to 21" | The guard works - done |
| Never breaks; log never needed a fix | The record wasn't the break, or the break needs more uses - read the recorder |
| It breaks anyway | Find the "handle broken" bit in the recorder log at the End mark; the client then keeps that bit off (like the gate holder) |

## Result (2026-11-15, TessarionAM; lock randomiser off)
- Two uses, then "The doorknob is broken. You can't pass through." The door is East Wing Stairway
  (207) <-> **Dark Corridor (10a)**, not the 'C' Corridor door the old guard watched (its record
  stayed type 21 / flag 16 the whole time).
- Event recorder, the same pattern twice (13:01:47-13:01:56 and 13:02:49-13:02:57):
  1st trip 207 -> 10a: +0x248 bit 3 on (and unlock flag 14 on); 2nd trip: +0x248 bit 4 on;
  back into 207: **+0x23A bit 0 on** (broken) and flag 14 off. Door records never changed.
- v0.9.26: when +0x23A bit 0 turns on, the client clears it and both counters - the knob is new again.

## Re-test (v0.9.26)
Same steps (4+ trips). Expected: it never says the knob is broken; the client log shows
"Doorknob: ... put back as new" after every second trip.

## Re-test 1 (v0.9.26, 13:14) - still broke
Log: "put back as new" fired at 13:14:08.6, 1.1 s after Jill entered the stairway - the room had
already loaded the door as broken. v0.9.27 un-counts the 2nd trip (+0x248 bit 4) while she is
still in the Dark Corridor instead.

## Re-test 2 (v0.9.27)
**Close the RE1HD client and the Archipelago Launcher first, then open them again** (the launcher
loads the apworld only when it starts). Then 4+ trips. Expected: never broken; the log shows
"Doorknob: second trip un-counted" on every second trip.
