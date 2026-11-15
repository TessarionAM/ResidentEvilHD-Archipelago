# 01 - Death and reload memory (read-only)

**Why.** v0.9.15-0.9.17 showed that the game frees and rebuilds its Game object (and every door
record) on a death or load. On 2026-11-14 01:23 the Graveyard gate to the Large Gallery locked itself
again after a load, although it had been unlocked at 23:04 and 00:32. The seed gives both sides
Lock Pick with unlock flag 39, so either flag 39 was cleared or the door record changed.

**Tool.** `launchers/run_hd_death_memory_test.bat`. It logs every change of the 256 door-unlock flags
all the time (with the room), so it can run during a normal seed with the client open.

**Steps**
1. Load a save where the Graveyard gate is unlocked. Go to the Graveyard, press **Page Down**
   (lists each door: lock type, unlock flag, SET or not).
2. Press **Home** (snapshot A). Die. Load the same save. Press **End** (snapshot B + comparison).
   Go back to the Graveyard and press **Page Down** again.
3. **Home**, load a different (older) save, **End**, **Page Down**.
4. Play on normally with it open. If the gate ever locks itself again, press **Page Down** there
   and send the log straight away.

**Send.** `hd_death_memory_test_output.txt` and `hd_death_memory_test_events.jsonl`, plus the
client log of the same time.

**Decides.**
- Flag 39 turned OFF (an `UNLOCK flag 39 -> OFF` line): the game or our client cleared it - the
  room and time say which.
- Flag 39 stayed ON but the door shows another flag or lock type: the lock randomiser wrote the
  wrong record - fix in `_lock_tick`.
- What changes between A and B on a death (Game object, flags address, story bytes) - the list
  of things the client must re-find after a death.
