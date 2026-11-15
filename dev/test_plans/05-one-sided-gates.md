# 05 - One-sided gates (Residence / Courtyard start) - ANSWERED 2026-11-14

**Answer (TessarionAM, 2026-11-14):** both only work from one side. The gate takes the Stone & Metal
Object from the Roofed Passage side only; the Square Crank only works in the Water Pool, and the
Battery lift in the Falls Area gets you back up without it. The logic was changed in 0.9.22; the
gate follow-up is plan 07.


**Why.** The logic treats these as two-way, but whether Jill can open them from the far side is
unknown. A random start in the Residence or Courtyard depends on them.

| Gate | Normally opened from | Question |
|---|---|---|
| Roofed Passage <-> Garden Shed (Stone & Metal Object) | the Mansion side | Can Jill open it from the Courtyard side, and with what? |
| Main Garden <-> Falls Area pool (Square Crank) | the Courtyard side | Can the pool be drained / crossed from the far side? |

**How.** With a save in the Courtyard before using these (or `run_hd_door_teleport.bat` with room `11b`, the Garden Shed,
then F10), walk up to each from the far side and check it: message shown, item
asked for, opens or not.

**Send.** What each one says or does (a screenshot of any message helps).

**Decides.** Whether the Residence -> Mansion way back needs the Mansion-side item, and so which
rooms are allowed as random starts.
