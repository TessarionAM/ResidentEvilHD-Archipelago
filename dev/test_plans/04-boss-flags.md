# 04 - Boss flags for the Boss Rush goal (read-only)

**Boss Rush set (TessarionAM, 2026-11-14):** Crypt Crimson Head, Plant 42, Library Yawn, Black Tiger,
Neptune, Lisa Trevor (Altar), Lab Tyrant. The Signal Rockets are locked behind all seven.

**Why.** The full mapping run (2026-11-10) gave one sample per boss. Two samples = confirmed.
Candidates (flags-relative):

| Boss | Kill-table bit | Story bits |
|---|---|---|
| Crypt Crimson Head | +0x270.6 | +0x222.3, +0x222.4 |
| Plant 42 | +0x270.3 | +0x223.6, +0x23C.0 |
| Yawn (Library) | +0x2A5.0 | +0x232.3 |
| Black Tiger | +0x2AD.0 | +0x236.1 |
| Neptune (Water Tank, 2026-11-10 15:29 - TessarionAM's best guess) | +0x2AC.0 | +0x234.0-3 |
| Lisa (Altar) | +0x272.0 | +0x23D.0, +0x23D.2, +0x200.4, +0x200.5 |
| Tyrant (Lab) | +0x2AE.1 | - |

**Tool.** `launchers/run_hd_boss_watch.bat` - can run during a normal seed. Best with `boss_rush: true`
(v0.9.23): the client's own Boss Rush notices then show which kills it saw, side by side with the watch.

**Steps.** Play normally. Press **End** after each boss and type what happened. Most useful:
- Plant 42 with the V-Jolt (Jill skips the fight): does its kill bit still turn on?
- Black Tiger skipped (webs burned), then killed later.
- Neptune in the Aqua Ring water tank (electrocuted), and what the 15:29 "Water Tank" event was.
- Lisa at the Altar with Barry alive / with Barry's Magnum kept.
- The Heliport Tyrant (if the Rocket Launcher drops).

**Send.** `hd_boss_watch_output.txt`.

**Decides.** The bits the client reads for each boss; which bosses can count for Boss Rush.
