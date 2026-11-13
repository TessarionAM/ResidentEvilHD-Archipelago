"""
Archipelago client for Resident Evil HD Remaster (Steam).

Start it from the Archipelago Launcher ("Resident Evil HD Remaster Client"),
connect to the server, and play. It:
  * sends a check whenever you pick up a detected pickup, a map, or enter a room for
    the first time (and takes the vanilla item back out of your inventory);
  * puts every item you receive into the item box (ammo stacks); the Lock Pick goes to its
    hidden slot, the Book of Curses and starting items straight to Jill; traps hit Jill;
  * remembers what it delivered (and keeps a record in box slot 256 so loading an older
    save re-sends exactly what that save is missing) - nothing is lost or doubled;
  * Death Link and door skip, if switched on.

Commands (type in the client):
  /status            what the client knows right now
  /delivered         list received items and which were delivered
  /redeliver N       deliver again from item N (normally automatic after a reload)
  /learned           pickups the client learned while you played (become checks after an update)
  /overlay on|off    on-screen messages
  /doorskip on|off   skip door animations
  /borderless on|off borderless fullscreen (game in Windowed mode; messages stay visible)
  /sortbox [on|off]  sort the item box now (keys first, stacks merged); on|off = automatically
  /box               what's arrived in the item box since you last stood by one
  /keys              key items you've received and whether they're in the game yet
  /tracker on|off    show/hide the Tracker and Key Map tabs
  /inlogic (/stuck)  checks you can reach right now with the items you have
  /autosave          save to the autosave slot now (in a save room; option autosave)
  /escaped           backup: tell the server you finished (normally automatic)
"""

import asyncio
import time
from pathlib import Path

import Utils
from CommonClient import ClientCommandProcessor, CommonContext, get_base_parser, gui_enabled, logger, server_loop
from NetUtils import ClientStatus

from ..game_data import DELIVERY_QUANTITY, GOAL_ROOM_NUMBER, ROOM_NUMBERS
ROOM_NAME_OF = {nb: name for name, nb in ROOM_NUMBERS.items()}
from ..items import item_table
from ..locations import all_location_ids
from .game_bridge import EFFECT_ITEMS, FUN_TRAPS, WRONG_DOOR, EndingWatcher, GameBridge, Incoming, StateFile
from .held_traps import HeldTraps
from .hd_delivery import Journal
from .overlay import Overlay, message_for

GAME = "Resident Evil HD Remaster"
ITEM_ID_TO_GAME_ID = {data.code: data.game_id for data in item_table.values()}
LOCATION_NAME_TO_ID = dict(all_location_ids)


def item_quantity(name: str):
    """How many of this item one delivery gives (e.g. Shotgun Shells -> 6), for messages."""
    data = item_table.get(name)
    return DELIVERY_QUANTITY.get(data.game_id) if data and data.game_id is not None else None


class RE1HDCommandProcessor(ClientCommandProcessor):
    def _cmd_status(self):
        """Show the game connection and delivery status."""
        ctx: RE1HDContext = self.ctx
        b = ctx.bridge
        logger.info(f"Game connected: {bool(b and b.conn)}")
        logger.info(f"Items received from server: {len(ctx.items_received)}")
        if b:
            logger.info(f"Items delivered into the game: {b.state.delivered}")
            if b.state.undeliverable:
                logger.info(f"Items that couldn't be delivered: {b.state.undeliverable}")
        logger.info(f"Checks sent: {len(ctx.checked_locations)} of {len(ctx.server_locations)}")
        if b:
            logger.info(f"Door skip: {'on' if b.door_skip else 'off'}   Borderless: {'on' if b.borderless else 'off'}   "
                        f"Autosave: {'slot ' + str(b.autosave_slot + 1) if b.autosave_slot is not None else 'off'}"
                        f"   Game-thread routine: {'ready' if b.autosaver else 'not installed'}")

    def _cmd_delivered(self):
        """List received items and whether they've been delivered."""
        ctx: RE1HDContext = self.ctx
        done = ctx.bridge.state.delivered if ctx.bridge else 0
        for i, item in enumerate(ctx.incoming()):
            logger.info(f"{i:>3}: {'delivered' if i < done else 'waiting  '}  {item.label}")

    def _cmd_redeliver(self, index: str = ""):
        """After loading an OLDER save, deliver received items again starting from number N (see /delivered)."""
        ctx: RE1HDContext = self.ctx
        if not ctx.bridge or not index.isdigit():
            logger.info("Usage: /redeliver N   (N from /delivered)")
            return
        ctx.bridge.redeliver_from(int(index))
        logger.info(f"Will deliver again from item {int(index)}.")

    def _cmd_learned(self):
        """Show pickups the client has learned while you played (they become checks after an update)."""
        ctx: RE1HDContext = self.ctx
        if not ctx.bridge or not ctx.bridge.mapper:
            logger.info("Connect first.")
            return
        data = ctx.bridge.mapper.data
        for name, m in sorted(data["mappings"].items()):
            logger.info(f"  {name}: +{m['offset']:#x} bit {m['bit']} ({m['how']})")
        logger.info(f"{len(data['mappings'])} learned, {len(data['observations'])} waiting for elimination. "
                    f"Report learned_pickups.json (see the README) so they can become checks.")

    def _cmd_overlay(self, setting: str = ""):
        """Turn the on-screen messages over the game on or off: /overlay on | off"""
        ctx = self.ctx
        if setting.lower() not in ("on", "off"):
            logger.info(f"On-screen messages are {'on' if ctx.overlay.enabled else 'off'}. Use /overlay on or /overlay off.")
            return
        ctx.overlay.enabled = setting.lower() == "on"
        if ctx.overlay.enabled:
            ctx.overlay.start()
            ctx.overlay.show("On-screen messages on.")
        logger.info(f"On-screen messages {setting.lower()}.")

    def _cmd_doorskip(self, setting: str = ""):
        """Skip the door-opening animations: /doorskip on | off (no BhdTool needed)"""
        ctx = self.ctx
        if setting.lower() not in ("on", "off") or ctx.bridge is None:
            logger.info("Use /doorskip on or /doorskip off (after connecting).")
            return
        ctx.bridge.door_skip = setting.lower() == "on"
        logger.info(ctx.bridge.set_door_skip(ctx.bridge.door_skip))

    def _cmd_sortbox(self, setting: str = ""):
        """Sort the item box now (keys first, stacks merged). /sortbox auto on|off = also on entering a box room."""
        b = self.ctx.bridge
        if b is None:
            logger.info("Connect first.")
            return
        if setting.lower() in ("on", "off"):
            b.box_auto_sort = setting.lower() == "on"
            logger.info(f"Automatic item box sort {setting.lower()}.")
            return
        logger.info(b.sort_box("by command"))

    def _cmd_shortcut(self, *words: str):
        """Key Map shortcut: /shortcut main hall | garden shed | lab entrance. The next door Jill
        goes through takes her there (once she has visited it). The same again cancels it."""
        b = self.ctx.bridge
        if b is None:
            logger.info("Connect first.")
            return
        from .shortcuts import SHORTCUTS
        wanted = " ".join(words).strip().lower()
        name = next((n for n in SHORTCUTS if n.lower() == wanted), None)
        if name is None:
            logger.info("Use /shortcut " + " | ".join(n.lower() for n in SHORTCUTS))
            return
        logger.info(b.request_shortcut(name))

    def _cmd_itembox(self, setting: str = "", key: str = ""):
        """Open the item box wherever Jill is. /itembox key F1-F12|off = the hotkey (default F7).
        /itembox mode off|save_rooms|anywhere = change where it works, for this session."""
        b = self.ctx.bridge
        if b is None:
            logger.info("Connect first.")
            return
        if setting.lower() == "mode":
            modes = {"off": 0, "save_rooms": 1, "anywhere": 2}
            if key.lower() not in modes:
                logger.info("Use /itembox mode off | save_rooms | anywhere (for this session).")
                return
            b.box_anywhere = modes[key.lower()]
            logger.info(f"Item box anywhere: {key.lower()} (until the client restarts).")
            return
        if setting.lower() == "key":
            from .window_mode import VK_CODES
            key = key.upper()
            if key == "OFF":
                b.box_hotkey = None
                logger.info("Item box hotkey off.")
            elif key in VK_CODES:
                b.box_hotkey = key
                logger.info(f"Item box hotkey: {key} (while the game window is in front).")
            else:
                logger.info("Use /itembox key F1..F12, or /itembox key off.")
            return
        logger.info(b.open_item_box())

    def _cmd_adopt(self):
        """The loaded save IS this seed's (the client thinks it isn't): mark it as this seed's."""
        if self.ctx.bridge is None:
            logger.info("Connect first.")
            return
        self.ctx.bridge.adopt_save = True
        logger.info("OK - the loaded save will be treated as this seed's. Its pickups count as checks.")

    def _cmd_boxdebug(self, setting: str = ""):
        """Item box research log in the client log: /boxdebug on|off (off by default)."""
        if self.ctx.bridge is None:
            logger.info("Connect first.")
            return
        self.ctx.bridge.box_debug = setting.lower() != "off"
        logger.info(f"Box debug log {'on' if self.ctx.bridge.box_debug else 'off'}.")

    def _cmd_testtrap(self, *name: str):
        """Try a trap on yourself right now (nothing is sent anywhere): /testtrap Window Shake Trap.
        Without a name it lists them."""
        from .game_bridge import EFFECT_ITEMS
        wanted = " ".join(name).strip().lower()
        match = [n for n in sorted(EFFECT_ITEMS) if n.lower() == wanted or n.lower().startswith(wanted)] if wanted else []
        if len(match) != 1:
            logger.info("Use /testtrap <name>, one of: " + ", ".join(sorted(EFFECT_ITEMS)))
            return
        b = self.ctx.bridge
        if b is None:
            logger.info("Connect first.")
            return
        ok = b._apply_trap(Incoming(-1, None, f"{match[0]} from Test", trap=match[0]))
        logger.info(f"{match[0]}: {'done' if ok else 'not possible right now (is Jill in the game?)'}")

    def _cmd_tracker(self, setting: str = ""):
        """Show or hide the Tracker and Key Map tabs: /tracker on | off"""
        ctx = self.ctx
        if setting.lower() not in ("on", "off"):
            logger.info(f"Tracker tabs are {'on' if ctx.tracker_enabled else 'off'}. Use /tracker on or /tracker off.")
            return
        ctx.tracker_enabled = setting.lower() == "on"
        if getattr(ctx, "ui", None) is not None and hasattr(ctx.ui, "show_trackers"):
            ctx.ui.show_trackers(ctx.tracker_enabled)
        logger.info(f"Tracker tabs {setting.lower()}.")

    def _cmd_box(self):
        """What has arrived in the item box since you last stood in an item box room."""
        b = self.ctx.bridge
        if b is None:
            logger.info("Connect first.")
            return
        from .game_bridge import box_summary
        logger.info("Nothing new in the item box." if not b.state.box_unseen
                    else "New in the item box: " + box_summary(b.state.box_unseen, limit=50))

    def _cmd_keys(self):
        """Every key / progression item you've received, and whether it's in the game yet."""
        ctx: RE1HDContext = self.ctx
        done = ctx.bridge.state.delivered if ctx.bridge else 0
        rows = [(i, ctx.item_names.lookup_in_game(n.item)) for i, n in enumerate(ctx.items_received)
                if n.flags & 0b001]
        if not rows:
            logger.info("No key items received yet.")
            return
        for i, name in rows:
            logger.info(f"  {name:32s} {'in the game' if i < done else 'waiting to be delivered'}")

    def _cmd_inlogic(self):
        """List the checks you can reach right now with the items you have (the seed's logic)."""
        ctx: RE1HDContext = self.ctx
        if ctx.slot is None:
            logger.info("Connect to the server first.")
            return
        from ..logic_tracker import in_logic
        names = {v: k for k, v in LOCATION_NAME_TO_ID.items()}
        checked = {names[i] for i in ctx.checked_locations if i in names}
        active = checked | {names[i] for i in ctx.missing_locations if i in names}
        received = [ctx.item_names.lookup_in_game(n.item) for n in ctx.items_received]
        box_gate = ctx.bridge is None or ctx.bridge.destination == 0
        found = in_logic(received, active, checked, box_gate)
        if not found:
            logger.info("Nothing in logic right now that you haven't checked. If you're stuck, "
                        "report it with your client log (see the README) - the seed or the logic may be wrong.")
            return
        logger.info(f"{len(found)} check(s) in logic that you haven't done yet:")
        for n in found:
            logger.info(f"   {n}")

    def _cmd_stuck(self):
        """Same as /inlogic: what you can reach right now."""
        self._cmd_inlogic()

    def _cmd_borderless(self, setting: str = ""):
        """Borderless fullscreen (keeps the on-screen messages visible): /borderless on | off"""
        ctx = self.ctx
        if setting.lower() not in ("on", "off") or ctx.bridge is None:
            logger.info("Use /borderless on or /borderless off (after connecting). "
                        "Set the game to Windowed mode first.")
            return
        logger.info(ctx.bridge.set_borderless(setting.lower() == "on"))

    def _cmd_autosave(self):
        """Save to your autosave slot now (you must be in a save room)."""
        ctx = self.ctx
        if ctx.bridge is None:
            logger.info("Connect first.")
            return
        logger.info(ctx.bridge.autosave_now())

    def _cmd_escaped(self):
        """Tell the server you finished your goal (backup if it isn't detected automatically)."""
        ctx: RE1HDContext = self.ctx
        if ctx.slot is None:
            logger.info("Connect to the server first.")
            return
        Utils.async_start(ctx.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}]))
        ctx.finished_game = True
        logger.info("Goal sent - well done!")


class RE1HDContext(CommonContext):
    game = GAME
    items_handling = 0b111          # receive items from others, our own, and starting items
    command_processor = RE1HDCommandProcessor

    def __init__(self, server_address, password):
        super().__init__(server_address, password)
        self.bridge: GameBridge | None = None
        self.overlay = Overlay()
        self.goal = 1                       # slot_data "goal": 1 = complete_game, 0 = mansion_escape
        self.ending = EndingWatcher()
        self.tracker_enabled = True             # /tracker on|off
        self.held_traps = HeldTraps(self._fun_trap_of, self._print_json_now)

    def _fun_trap_of(self, args: dict):
        """The fun trap's name if this PrintJSON announces one sent to us, else None."""
        if self.slot is None or args.get("type") not in ("ItemSend", "ItemCheat"):
            return None
        if args.get("receiving") != self.slot:
            return None
        net = args.get("item")
        item_id = net.get("item") if isinstance(net, dict) else (net[0] if net else None)
        if item_id is None:
            return None
        name = self.item_names.lookup_in_slot(item_id, self.slot)
        return name if name in FUN_TRAPS or name == WRONG_DOOR else None

    def on_deathlink(self, data: dict):
        super().on_deathlink(data)
        if self.bridge is not None:
            self.bridge.deaths_to_apply += 1

    def on_print_json(self, args: dict):
        if self.held_traps.hold(args):
            return                       # a fun trap for us: announced once the prank is over
        self._print_json_now(args)

    def _print_json_now(self, args: dict):
        super().on_print_json(args)
        try:
            if self.slot is None:
                return
            msg = message_for(args, self.slot,
                              lambda item, slot: self.item_names.lookup_in_slot(item, slot),
                              lambda slot: self.player_names.get(slot, f"player {slot}"),
                              item_quantity)
            if msg:
                self.overlay.show(msg[1], msg[0])
        except Exception:
            logger.debug("Overlay message failed", exc_info=True)

    async def server_auth(self, password_requested: bool = False):
        if password_requested and not self.password:
            await super().server_auth(password_requested)
        await self.get_username()
        await self.send_connect()

    def on_package(self, cmd: str, args: dict):
        if cmd == "RoomInfo":
            # CommonContext (0.6.7) never stores the seed name itself. Without it every seed
            # shared one delivery record ("state_None_1.json"), so a new seed thought its items
            # were already delivered (seed test 2, 2026-11-11).
            self.seed_name = args.get("seed_name")
        if cmd == "Connected":
            self.overlay.start()
            self.overlay.show(f"Connected to Archipelago as {self.player_names.get(self.slot, 'you')}.")
            folder = Path(Utils.user_path("re1hd_client"))
            folder.mkdir(parents=True, exist_ok=True)
            if not self.seed_name:
                logger.error("The server didn't send a seed name - not delivering items, to be safe. "
                             "Please reconnect.")
                return
            stem = f"{self.seed_name}_{self.slot}"
            self.bridge = GameBridge(StateFile(folder / f"state_{stem}.json"),
                                     Journal(folder / f"journal_{stem}.jsonl"),
                                     learned_file=folder / "learned_pickups.json")
            import zlib
            self.bridge.seed_tag = (zlib.crc32(stem.encode()) & 0x7FFFFFFF) | 1   # never 0
            logger.info(f"New pickups learned while you play are saved in {folder / 'learned_pickups.json'}")
            logger.info(f"Delivery record: {folder / ('state_' + stem + '.json')}")
            self.goal = args.get("slot_data", {}).get("goal", 0)   # worlds before 0.5.0 only had mansion_escape
            logger.info("Goal: " + ("complete the game (helicopter ending)" if self.goal == 1
                                    else "escape the mansion (reach the Garden Shed)"))
            self.bridge.destination = args.get("slot_data", {}).get("received_item_destination", 0)
            sd = args.get("slot_data", {})
            self.bridge.random_start = bool(sd.get("random_starting_inventory", 0))
            self.bridge.room_entries_on = bool(sd.get("first_room_entries", 0))
            # door lock randomiser (0.9.0): the client writes the locks, the tracker / Key Map show them
            self.bridge.set_door_locks(sd.get("door_locks") or {}, sd.get("key_uses") or {})
            from .. import door_locks as _door_locks
            _door_locks.apply_to_tracker(sd.get("door_locks") or {}, sd.get("door_shuffle") or {})
            self.bridge.set_door_shuffle(sd.get("door_shuffle") or {})   # door randomiser (0.9.12)
            self.bridge.trap_damage_percent = int(sd.get("damage_trap_amount", 25))
            self.bridge.trap_can_kill = bool(sd.get("damage_trap_can_kill", 0))
            self.bridge.death_link_kill = sd.get("death_link_effect", 1) == 1
            self.bridge.door_skip = bool(sd.get("door_skip", 0))
            self.bridge.box_auto_sort = bool(sd.get("item_box_auto_sort", 0))
            self.bridge.shortcuts_on = bool(sd.get("key_map_shortcuts", 0))   # seeds before 0.9.9: off
            self.bridge.box_anywhere = box_anywhere_mode(sd)
            res = int(sd.get("game_resolution", 0))
            if res:
                from .game_config import set_resolution
                logger.info(set_resolution(res))
            from ..options import ItemBoxButton
            self.bridge.box_button = ItemBoxButton.name_lookup.get(sd.get("item_box_button", 0), "off")
            if sd.get("borderless_fullscreen"):
                logger.info(self.bridge.set_borderless(True))
            self.bridge.start_box = [tuple(x) for x in sd.get("start_box", [])]
            if sd.get("autosave"):
                self.bridge.autosave_slot = int(sd.get("autosave_slot", 8)) - 1
                logger.info(f"Autosave is on: walking into a save room saves to slot {sd.get('autosave_slot', 8)}.")
            if sd.get("death_link"):
                Utils.async_start(self.update_death_link(True))
                logger.info("Death Link is on.")
            logger.info("Items you receive go to: " + ("Jill's inventory (the item box if it's full)"
                                                        if self.bridge.destination == 1 else "the item box"))

    def incoming(self):
        out = []
        for i, net in enumerate(self.items_received):
            name = self.item_names.lookup_in_game(net.item)
            sender = self.player_names.get(net.player, f"player {net.player}")
            # location -2 = starting inventory (Archipelago's convention): handed straight to Jill
            out.append(Incoming(i, ITEM_ID_TO_GAME_ID.get(net.item), f"{name} from {sender}",
                                starting=net.location == -2,
                                trap=name if name in EFFECT_ITEMS else None))
        return out

    # ------------------------------------------------------------------ tracker tabs
    def tracker_inputs(self):
        names = {v: k for k, v in LOCATION_NAME_TO_ID.items()}
        checked = {names[i] for i in self.checked_locations if i in names}
        active = checked | {names[i] for i in self.missing_locations if i in names}
        received = [self.item_names.lookup_in_game(n.item) for n in self.items_received]
        box_gate = self.bridge is None or self.bridge.destination == 0
        return received, active, checked, box_gate

    def make_gui(self):
        ui = super().make_gui()
        ctx = self

        class RE1HDManager(ui):
            base_title = "Resident Evil HD Remaster Client"

            def build(self):
                container = super().build()
                self.tracker_tabs, self.tracker_labels, self.key_map = [], [], None
                try:                 # never let the tracker stop the client from starting
                    if ctx.tracker_enabled:
                        self.show_trackers(True)
                    from kivy.clock import Clock
                    Clock.schedule_interval(lambda dt: self.refresh_trackers(), 2.0)
                except Exception:
                    logger.exception("The tracker tabs couldn't be built (the client still works; /inlogic too):")
                return container

            def show_trackers(self, on: bool):
                from kivy.uix.label import Label
                from kivy.uix.scrollview import ScrollView
                if on and not self.tracker_tabs:
                    label = Label(text="Connect to see the tracker.", markup=True, size_hint_y=None,
                                  halign="left", valign="top", padding=(12, 12))
                    label.bind(width=lambda l, w: setattr(l, "text_size", (w, None)),
                               texture_size=lambda l, ts: setattr(l, "height", ts[1]))
                    scroll = ScrollView()
                    scroll.add_widget(label)
                    self.tracker_tabs.append(self.add_client_tab("Tracker", scroll))
                    self.tracker_labels = [label]
                    try:
                        from .key_map_view import KeyMapView
                        self.key_map = KeyMapView(on_shortcut=self.use_shortcut)
                        self.tracker_tabs.append(self.add_client_tab("Key Map", self.key_map))
                    except Exception:
                        logger.exception("The Key Map tab couldn't be built (the Tracker tab still works):")
                        self.key_map = None
                    self.refresh_trackers()
                elif not on and self.tracker_tabs:
                    for tab in self.tracker_tabs:
                        self.remove_client_tab(tab)
                    self.tracker_tabs, self.tracker_labels, self.key_map = [], [], None

            def use_shortcut(self, name: str):
                if ctx.bridge is None:
                    logger.info("Connect and load your save first.")
                    return
                message = ctx.bridge.request_shortcut(name)
                logger.info(message)
                ctx.overlay.show(message, "info")
                self.refresh_trackers()

            def refresh_trackers(self):
                if not self.tracker_tabs or ctx.slot is None:
                    return
                try:
                    from ..tracker import tracker_text
                    received, active, checked, box_gate = ctx.tracker_inputs()
                    self.tracker_labels[0].text = tracker_text(received, active, checked, box_gate)
                    if getattr(self, "key_map", None) is not None:
                        number = ctx.bridge.current_room if ctx.bridge is not None else None
                        unlocked = ctx.bridge.unlocked_flags if ctx.bridge is not None else frozenset()
                        pos = ctx.bridge.jill_pos if ctx.bridge is not None else None
                        found = ctx.bridge.door_shuffler.s.get("discovered", {}) if ctx.bridge is not None else {}
                        self.key_map.update(received, active, checked, box_gate, ROOM_NAME_OF.get(number),
                                            unlocked, number, pos, found)
                        b = ctx.bridge
                        self.key_map.set_shortcuts(bool(b and b.shortcuts_on),
                                                   b.shortcuts_unlocked if b else frozenset(),
                                                   b.shortcut.target_name if b else None)
                except Exception:
                    logger.debug("Tracker refresh failed", exc_info=True)

        return RE1HDManager


# how long each PC-side prank lasts: Archipelago's "sent you <trap>" line waits until then
PRANK_SECONDS = {"To Be Continued Trap": 6.5, "Danger Flash Trap": 5.5, "Window Shake Trap": 1.5}


def run_fun_trap(ctx, name: str, sender: str):
    """Fun traps that happen on the PC (see fun_effects.py / overlay.py)."""
    from . import fun_effects
    pid = getattr(getattr(ctx.bridge, "conn", None), "pid", 0)
    done = lambda delay=0.0: ctx.bridge.fun_done.append((time.time() + delay, name))
    if name == "Fake Crash Trap":
        def after():
            ctx.bridge.notices.append((f"Gotcha! That crash was a Fun Trap from {sender}.", "info"))
            done()                                 # announced once the error box is closed
        if not fun_effects.fake_crash(pid, after):
            after()
        return
    if name == "To Be Continued Trap":
        ctx.overlay.show_screen([(3.5, "To Be Continued...", ""),
                                 (2.0, "To Be Continued...", f"...just kidding. (from {sender})")])
    elif name == "Danger Flash Trap":
        from .vignette import danger_flash
        if not danger_flash():                     # glow fading in from the edges; else red frame
            ctx.overlay.show_flash("danger")
    elif name == "Window Shake Trap":
        if not fun_effects.shake(pid):
            logger.info("Window Shake Trap: the game window wasn't found (exclusive fullscreen?).")
        ctx.bridge.notices.append((f"Earthquake! (Window Shake Trap from {sender})", "info"))
    done(PRANK_SECONDS.get(name, 0.0))


def version_tuple(text) -> tuple:
    try:
        return tuple(int(p) for p in str(text).split(".")[:3])
    except ValueError:
        return (0, 0, 0)


def box_anywhere_mode(slot_data: dict) -> int:
    """item_box_anywhere: 0 off, 1 save rooms, 2 anywhere. Seeds made before world 0.7.5 had an
    on/off switch, stored as 1 = ON (anywhere). Read as the new choice, that 1 meant "save rooms
    only" (seed test 5, 2026-11-12: TessarionAM's whole seed suddenly had the box in save rooms only)."""
    value = int(slot_data.get("item_box_anywhere", 0))
    if version_tuple(slot_data.get("world_version", "0")) < (0, 7, 5):
        return 2 if value else 0
    return value


async def game_loop(ctx: RE1HDContext):
    """Every 0.1 s: talk to the game, send new checks."""
    while not ctx.exit_event.is_set():
        try:
            if ctx.bridge is not None:
                on = ctx.bridge.tick(ctx.incoming())
                if ctx.bridge.jill_died:
                    ctx.bridge.jill_died = False
                    if "DeathLink" in ctx.tags:
                        await ctx.send_death(f"{ctx.player_names.get(ctx.slot, 'Jill')} died in the mansion.")
                while ctx.bridge.notices:
                    note = ctx.bridge.notices.pop(0)
                    text, kind = note if isinstance(note, tuple) else (note, "info")
                    ctx.overlay.show(text, kind)
                while ctx.bridge.fun_requests:
                    run_fun_trap(ctx, *ctx.bridge.fun_requests.pop(0))
                now = time.time()
                due = [d for d in ctx.bridge.fun_done if d[0] <= now]
                ctx.bridge.fun_done = [d for d in ctx.bridge.fun_done if d[0] > now]
                for _t, trap in due:
                    ctx.held_traps.release(trap)
                ctx.held_traps.expire(now)
                if not ctx.finished_game and ctx.slot is not None:
                    if ctx.goal == 1:
                        # read the inventory LIVE: after the ending the client stops its normal tick
                        # (Jill isn't in the game), so last_inv still held the Heliport inventory and
                        # the ending was never seen (seed test 5, 2026-11-12 07:43)
                        empty = ctx.bridge.inventory_empty_now()
                        done = ctx.ending.update(ctx.bridge.current_room, empty, time.time())
                        message = "You escaped on the helicopter - game complete! Goal complete."
                    else:
                        done = ctx.bridge.current_room == GOAL_ROOM_NUMBER
                        message = "You reached the Garden Shed - you escaped the mansion! Goal complete."
                    if done:
                        await ctx.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])
                        ctx.finished_game = True
                        logger.info(message)
                        ctx.overlay.show(message.split(" - ")[0] + "!", "info")
                if on is not None:
                    ids = {LOCATION_NAME_TO_ID[n] for n in on} & ctx.missing_locations
                    new = ids - ctx.locations_checked
                    if new:
                        ctx.locations_checked |= new
                        await ctx.send_msgs([{"cmd": "LocationChecks", "locations": list(new)}])
        except Exception:
            logger.exception("Problem in the game loop (the client keeps running):")
        await asyncio.sleep(0.1)


def launch(*args):
    async def main(parsed):
        ctx = RE1HDContext(parsed.connect, parsed.password)
        ctx.server_task = asyncio.create_task(server_loop(ctx), name="server loop")
        if gui_enabled:
            ctx.run_gui()
        ctx.run_cli()
        loop_task = asyncio.create_task(game_loop(ctx), name="RE1HD game loop")
        await ctx.exit_event.wait()
        ctx.server_address = None
        loop_task.cancel()
        await ctx.shutdown()

    parser = get_base_parser(description="Resident Evil HD Remaster client.")
    parsed, _ = parser.parse_known_args(args)
    Utils.init_logging("RE1HDClient", exception_logger="Client")
    asyncio.run(main(parsed))
