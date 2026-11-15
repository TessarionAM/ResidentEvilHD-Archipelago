# Changelog

## 0.9.33

- Random start beyond the Stone & Metal gate (Mining Area, Cabin, Residence Storeroom): instead of
  locking the Garden Shed door, the client puts the object in the gate for you from the start, so
  the gate is open both ways. The drawn object is a copy: if you pick it up it's taken away again,
  so there are never more than the game's two. The logic knows the gate is open.
- Boss Rush skulls disappear from the Key Map once the boss is dead.
- The Garbage Compactor Room shortcut now arrives at the Winding Underground Passage door (a spot
  checked in play) instead of Barry's lift.
- README, setup guide and credits brought up to date (random start room, Boss Rush, autoload,
  instant shortcuts; BhdTool's room jump method).

## 0.9.32

From TessarionAM's finished play-test seed:
- Broken Flamethrower: Barry's cave lift only goes down (the game won't take Jill back up), so the
  Broken Flamethrower is now always placed below it, before Lisa's door (Garbage Compactor Room,
  Winding Underground Passage or Underground Storage Room) and handed straight to Jill (there's no
  item box down there). The logic knows the lift is one-way. The "carry the flamethrower" warning
  is gone.
- Greenhouse Green Herbs 1-5 need the Herbicide (the plant must die first). Still junk checks.
- The Cerberus' Collar check (Dog Whistle) is junk, and leaves the tracker once you've received a
  Collar (the whistle stops working then).
- Shortcuts are instant: the same room jump as the random start room (fade to black, then the
  room). Pressing the button again cancels. The old "next door you go through" way stays as the
  fallback if the jump can't be set up.
- On-screen messages: the item's name is coloured like in the Archipelago client (progression
  plum, useful slate blue, trap salmon, other cyan); the rest of the line keeps its colour.
- Boss Rush: the Tracker tab lists the bosses defeated and left, and the Key Map draws a skull in
  each boss room (dim once the boss is dead; hover for the name). Neptune's kill bit is confirmed.
- The Fish Tank Room's second arrival spot from the corridor is known (no more position warning).

## 0.9.31

- Courtyard lifts (TessarionAM's play-test): they are now set for the room Jill is GOING to (the
  game's door/ride target, which changes before the room loads), so riding the pool lift down from
  the Water Pool no longer leaves the Battery lift at the top of the Falls Area.
- Courtyard lifts: a lift is only moved once it works in the game - the pool lift after the Square
  Crank drained the pool, the Battery lift once the Battery is in it. Moving the pool lift down
  before that let Jill ride up from the Falls Area without the crank, which the logic didn't allow.
- Random start in the Mining Area, Cabin or Residence Storeroom (beyond the Stone & Metal gate): the
  Garden Shed's door to the Roofed Passage stays locked until the Stone & Metal Object has been
  received, and the logic knows it. Walking through it first could leave Jill on the Mansion side
  with no way back (the gate is the only way back to the Courtyard, Residence and Caves).

## 0.9.30

- New option `random_start_room` (EXPERIMENTAL): `off` (default), `mansion_save_rooms` (Dining
  Room, East Wing Storeroom) or `save_rooms` (also the Mining Area, Cabin and Residence Storeroom).
  A new game starts in the Main Hall; about ten seconds in, the client moves Jill to the start room
  with the game's own room change (BhdTool's room jump method, our own code). It only happens once
  per new game. The world picks the room and checks the whole seed from there (simulated fill and
  softlock check, with the lock and door randomisers too); a room that doesn't work is skipped.
  Barry's Lock Pick check gives junk with this option (the intro replays when you first walk back
  into the Main Hall); the real Lock Pick is placed elsewhere.
- The client autosaves in the start room as soon as Jill arrives (with autosave on).
- Death Link "kill" now also arms autoload after death.
- Kitchen Elevator: named in the client, and the Key Map keeps Jill where she got in.
- "Auto sort waiting" is logged once per reason instead of every half second.
- Play-test logging: kill-table bits with the room (for the Boss Rush flags), Jill's real arrival
  spot when it doesn't match our door data, and Jill's state around a death (Death Link research).

## 0.9.29

- The client now always says whether autoload after death is on or off when it connects, and
  why (YAML, /autoload, or autosave off). 0.9.28 said nothing when it was off, so a test ran with
  it off and nobody could tell.
- New command `/autoload on|off` (no word = show the setting). It works on any seed with autosave
  on, without generating again, and is remembered for that seed. `/status` shows it too.

## 0.9.28

- New option `autoload_after_death` (EXPERIMENTAL, needs `autosave`): after Jill dies, the client
  loads your autosave slot by itself once the title screen's menu is up. It does what picking
  "Load Game" does, then picks the slot. Only after the client has autosaved at least once in
  this seed, so it never loads an empty slot or a save from another seed. If anything goes wrong
  it stops and tells you to load yourself.

## 0.9.27

- Doorknob, take two: 0.9.26 mended the knob only after it broke, but by then the East Wing Stairway
  had already loaded the broken door (TessarionAM's re-test). Now the client un-counts the second
  trip while Jill is still in the Dark Corridor, so the knob never breaks. A save where it's
  already broken is mended too (it works again the next time you enter the stairway).
- No more T-pose when the client connects to a save: the "put the weapon away" fix ran once per
  client run even with nothing to fix. It now only runs for a weapon Jill holds that isn't in her
  inventory, or straight after the random start took the Handgun away.

## 0.9.26

- The East Wing Stairway doorknob can't stay broken any more (TessarionAM's test 06). The door that
  breaks is the one between the East Wing Stairway and the Dark Corridor: after two trips the game
  says "The doorknob is broken. You can't pass through." The client now puts the knob back as new
  the moment it breaks. The old guard watched the wrong door (the 'C' Corridor one) and is gone.

## 0.9.25

- The Roofed Passage gate to the Garden Shed now stays open for good (TessarionAM's idea, test 07):
  - as soon as the Stone & Metal Object has been received from the multiworld, the client opens
    the gate - no need to put the object in;
  - if you put it in yourself, you can still take it back for the Altar, and the gate stays open
    afterwards. Before this, taking it back shut the Courtyard, Residence and Caves off for the
    rest of the game, while the logic still counted on them;
  - an object picked up from a gate the client opened is a free copy and is taken away again.
- Logic: the way from the Roofed Passage into the Garden Shed needs the Stone & Metal Object.

## 0.9.24

- Logic: the Stone & Metal gate only blocks the way from the Roofed Passage into the Garden Shed.
  From the Garden Shed the door to the Roofed Passage opens without the object (TessarionAM's
  test 07, 2026-11-14). The logic used to need the gate opened in both directions.
- The coupled door randomiser finds a working layout more often again (about 1 in 5 tries).

## 0.9.23

- New option `boss_rush` (EXPERIMENTAL, off by default). The Signal Rockets are locked behind seven
  bosses: the Crypt Crimson Head, Plant 42, Yawn (Library), Black Tiger, Neptune, Lisa Trevor
  (Altar) and the Lab Tyrant.
  - The client reads each boss's bit in the game's kill table. When all seven are on it sends the
    new "Boss Rush - All Bosses Defeated" check, which holds this world's Signal Rockets. They go
    straight into Jill's inventory (there's no item box on the way out of the Laboratory).
  - The Heliport's own Signal Rockets pickup holds something else instead.
  - A notice for each boss; a warning in the Main Laboratory if any of the other six are still
    alive (the Laboratory self-destructs after the Tyrant). `/bosses` lists them.
  - The boss bits come from one recorded run each: test plan 04 confirms them.
- The Courtyard lifts now follow Jill (TessarionAM, 2026-11-14: a lift left on the other floor
  nearly soft-locked a run). When she enters the Garden Shed, Main Garden or Water Pool both lifts
  are put at the top; when she enters the Falls Area, Zigzag Path or Mining Area both go to the
  bottom. The client writes this once per room entry, never during a ride. The lift positions
  (+0x249 bits 1 and 2) were read from the recorded run; test plan 08 checks them in the game.

## 0.9.22

- Logic: the Courtyard's one-sided puzzles are now modelled the way they work in the game
  (TessarionAM, 2026-11-14):
  - The Stone & Metal Object only goes into the Roofed Passage gate from the Mansion side. From
    the Garden Shed side the gate counts as open only once it has been opened from the Mansion.
  - The Square Crank only drains the pool in the Water Pool. The way back up from the Falls Area
    is the drained pool or the Battery lift (the Battery goes in at the Falls Area end), so the
    logic never expects you to carry the crank to get back to the Mansion.
  - The cave ladder behind the waterfall needs the crank (to refill the pool) and the powered lift.
- Door randomiser: these three doors (the gate, the pool lift, the Battery lift) now stay where
  they are. Their rules belong to the rooms, not to where the doors lead. Before this, a layout
  could make the Roofed Passage reachable only through the gate from the wrong side, which was
  impossible in the game.
- Test tools: the flag poke helper has the Stone & Metal gate candidates (test plan 07); the boss
  watch names Neptune.

## 0.9.21

- New check: the Shotgun Shells in the Lab B3 Cell (flag +0x2FB bit 4, seen in the logs of
  2026-11-13 and 2026-11-14). It is added at the end of the location list, so no existing
  location ID changes.
- The East Wing doorknob guard stands down when the door lock randomiser has given that door its
  own lock, so the two never fight over the same door.
- A failing step of the Fun Trap screen effect is now logged as a warning instead of hidden.
- Development tools for the next tests (in `dev/`, with step-by-step plans in `dev/test_plans/`):
  a death and reload memory test, a load menu watch (autoload), a room jump test (random start
  room) and a boss watch (Boss Rush goal).

## 0.9.20

- The client log now lists the locked door sides of each room Jill enters, with each door's
  unlock flag and whether it is set ("Locks in 0x10b: ->0x117 type 22 flag 39 open"). This is to
  find out why a door that was already open (the Graveyard gate to the Large Gallery) can be
  locked again later.

## 0.9.19

- Key Map shortcuts now go to every typewriter room (the game's 11 save rooms: Mansion Drug Room,
  Dining Room, East Wing Storeroom, Cabin, Residence Storeroom, Room 003, Mining Area, Garbage
  Compactor Room, Altar Stairway Passage, Lab Item Box Room, Lounge Room). The Main Hall, Garden
  Shed and Lab Entrance shortcuts are gone. Each still unlocks once the room has been visited.
- The East Wing Stairway doorknob (which breaks after two uses in the game) is kept unbroken: the
  stairway side of that door is held at its "opens from this side" lock. This is a first version;
  the client logs what it finds on that door so it can be confirmed.

## 0.9.18

- Fixed: the Danger Flash Trap never showed. On 64-bit Python a Windows bitmap handle was passed
  as a 32-bit number and the drawing call failed ("int too long to convert"). Every Windows call
  it makes now declares its types. A failure is now logged as a warning, not hidden.

## 0.9.17

- Fixed: after Jill died (or a save was loaded), Key Map shortcuts, the Wrong Door Trap and the
  door randomiser stopped working for the rest of the session. A death or load frees the game
  object that holds the room's doors; the client kept the old address and never found the new
  one. It now looks for the new one straight away.
- `/unstick` confirmed in game: it cleared the stuck menu state (flags 0x10a0 -> 0xa0).

## 0.9.16

- New `/unstick` command: if the game behaves as though a menu is still open (the camera
  doesn't follow Jill, you can't interact or open the inventory, and the client says "Close
  the menu first"), it resets the menu state and logs the values it found.
- Fixed: an autosave could be made while a pickup prompt was on screen; loading it left the
  game stuck in that menu. Autosaves now start only in a frame where Jill can move.
- Fixed: a save from an earlier seed was accepted as this seed's when it had no seed tag but
  did have a delivery record, and its old pickups were sent as checks. A save without this
  seed's tag that has pickups done is now always treated as another seed's (`/adopt` overrides).

## 0.9.15

Door randomiser fixes. It is now marked **experimental** (option, YAML, README): it still needs
more play-testing, so keep a spare save.

- Fixed: after loading a save, doors stopped being randomised (and a Wrong Door Trap or shortcut
  never fired). The client kept using door data it had found before the load. It now checks
  every room that the game's door list belongs to the room Jill is in, and that the door
  animation table entries are still where it found them; if not, it looks for them again
  (a few seconds) and carries on.
- Fixed: the ceiling trap could lock Jill in the Living Room. The Marble Room's exit had been
  shuffled to lead into the Living Room, and the trap only locks the door by where it normally
  leads. Both Marble Room doors now stay where they are. Needs a new seed.
- Fixed: cancelling a Key Map shortcut put back the door animation table but left the door
  itself leading to the shortcut's room (a combination that can crash the game).

## 0.9.14

Faster generation with the door randomiser. No gameplay changes.

- Some door lock layouts can never be built, or never pass the logic check, for the door
  randomiser (about a third of regional lock layouts). Generation used to try 400 door layouts
  on each one before rolling new locks, which could take over a minute. It now gives up on a
  lock layout after 25 failed builds or 60 failed logic checks, and tries up to 12 lock layouts
  (was 6). Measured over 180 test seeds: every seed generates, typically in 1-2 seconds.

## 0.9.13

Optimisation, clean-up and release preparation. No gameplay changes.

- Client: about half the memory reads per update (50 to 25) and half the processing time. Jill's
  object is looked up once per update, the room flag positions are computed once, the item box
  is only read when an Insecticide Spray leaves the inventory, and room flags are read once and
  reused.
- Client: the item box research log is off by default (`/boxdebug on` enables it).
- Removed unused code: an old pickup table, two unused delivery and pickup helpers, an unused
  layout function and an unused module lookup.
- Option descriptions rewritten; the example YAML is now a complete, documented template that
  is tested against the implemented options.
- The research tools moved to `dev/` and now share the client's code instead of a copy.

## 0.9.12

- The door randomiser works in the game: the client redirects each door, ladder and lift as
  you enter a room. The Key Map shows where a door leads once you have used it.

## 0.9.10 - 0.9.11

- Fun traps are announced only once the prank is over. The Fake Item trap names the fake item.
- Key Map: follows Jill between floors; shows the new room immediately after a door; door
  tooltips list every requirement.
- Logic: the Secret Passage drop is one-way; the passage where Lisa roams needs the Broken
  Flamethrower; the Gallery Insecticide Spray location is sent when a spray is used; the
  Courtyard Study door needs only the insignia.
- New: Key Map shortcuts to the Main Hall, the Garden Shed and the Laboratory Entrance.
- Options that are not implemented are hidden.

## 0.9.9

- Door randomiser generator and logic (coupled and decoupled).

## 0.9.6 - 0.9.8

- Random starting inventory: Jill no longer holds an invisible Handgun at the start.

## 0.9.0 - 0.9.5

- Door lock randomiser (Mansion only, regional, full) with a configurable locked door count.
- Key Map redesign: door colours by key, Jill's room from her actual position, hover details.
- Game resolution setting.

## 0.8.x

- Fun traps, including the Wrong Door trap. Ending detection for the helicopter goal. Logic
  audit against Evil Resource for Jill on Normal.

## 0.5 - 0.7

- The whole game as one world: every detectable pickup, maps, files and first room visits as
  locations. Item box delivery, the item box anywhere, automatic sorting, autosave, door skip,
  traps, special items, Death Link, the Tracker and the Key Map.
