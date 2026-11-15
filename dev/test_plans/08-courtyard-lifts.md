# 08 - Courtyard lifts follow Jill (client v0.9.23)

**Why.** TessarionAM (2026-11-14): a lift left on the other floor nearly soft-locked a run. The
recorded run shows the lift positions: +0x249 bit 1 = the pool lift is at the bottom (Water Pool ->
Falls Area), bit 2 = the Battery lift is at the top (Falls Area -> Main Garden). The client now puts
both lifts on Jill's floor when she enters a Courtyard room (Garden Shed / Main Garden / Water Pool =
top; Falls Area / Zigzag Path / Mining Area = bottom), once per entry.

**Steps** (normal play, client open)
1. Ride a lift down, walk away (e.g. into the Residence), come back to the top another way if you
   can, or load a save at the top where the lift was left at the bottom. Is the lift waiting for you?
2. Ride each lift both ways a few times. Any ride that stops, glitches or leaves Jill stuck?
3. Load a save that starts in the Main Garden or Falls Area with a lift on the other floor. If the
   lift isn't there, leave the room and come back.

**Send.** The client log lines "Courtyard lifts: ..." and what you saw.

**Decides.** Whether writing the bit is enough (the lift appears on the next room load), or the
client also has to set it earlier.
