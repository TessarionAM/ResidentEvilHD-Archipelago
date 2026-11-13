# Changelog

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
