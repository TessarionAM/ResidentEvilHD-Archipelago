# 02 - Autoload after a death (read-only, one optional write)

**Why.** After a death the player has to go title -> Load -> slot by hand. The code dump shows
the Load menu object at `[[0x00CF30D8]+0x10C]` (vtable `0x00C38320`); state 7 at `+0x25C` loads
slot `[+0x260]`. If setting those two values loads the save, the client can do it.

**Tool.** `launchers/run_hd_load_menu_watch.bat` (client closed).

**Steps**
1. Press Enter at the slot question (8 = the autosave slot), or type the slot of a spare save.
2. Die. Watch the screens to the title. Open Load, move between a few slots, back out, open Load
   again, load a save. Use a typewriter and back out. Press **Home** whenever the screen changes.
3. Send the log. Claude reads which state means "choosing a slot".
4. Only after Claude says so: open Load, don't press anything, press **F10**. Does it load the slot?

**Send.** `hd_load_menu_watch_output.txt`.

**Decides.** Whether autoload can be "one write" when the Load menu is open (then only the title
screen -> Load step is left to find), or needs key presses sent to the game window instead.
