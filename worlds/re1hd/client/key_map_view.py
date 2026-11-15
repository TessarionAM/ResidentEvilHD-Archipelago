"""The Key Map tab (TessarionAM 2026-11-12, v0.9.2): draws the shapes from map_render.py with Kivy.

A plain map: grey rooms, one wall thickness, locked doors in their key's colour, red while you
can't open them, ordinary and unlocked doors dark blue, one-way doors dark green, Jill's room
slowly glowing, and the map key drawn beside the map. Hover a room or door for its name and
what opens it; hover a key in the panel to light up its doors. Kivy only (imported by the
client)."""
import time

from kivy.clock import Clock
from kivy.core.text import Label as CoreLabel
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, InstructionGroup, Line, Rectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.widget import Widget

from .. import map_position, map_render
from ..map_layout import FLOORS
from ..tracker import floor_of, map_state

_TEXTURES = {}


def _texture(text, size, bold):
    key = (text, size, bold)
    tex = _TEXTURES.get(key)
    if tex is None:
        if len(_TEXTURES) > 600:
            _TEXTURES.clear()
        lab = CoreLabel(text=text, font_size=size, bold=bold)
        lab.refresh()
        tex = _TEXTURES[key] = lab.texture
    return tex


def measure(text, size, bold=False):
    tex = _texture(text, size, bold)
    return float(tex.width), float(tex.height)


def draw(group, ops, ox, oy, height, pulses=None):
    """Add the shapes to a Kivy InstructionGroup. Shapes use y going down from the top of the
    widget; Kivy's y goes up from (ox, oy). "pulse" rects share one Color, added to pulses so the
    view can make it glow."""
    top = oy + height
    pulse_colour = None
    for op in ops:
        kind = op[0]
        if kind == "pulse":
            if pulse_colour is None:
                pulse_colour = Color(*op[1])
                if pulses is not None:
                    pulses.append((pulse_colour, op[1]))
            group.add(pulse_colour)
            _k, _c, x, y, w, h = op
            group.add(Rectangle(pos=(ox + x, top - y - h), size=(w, h)))
            continue
        group.add(Color(*op[1]))
        if kind == "rect":
            _k, _c, x, y, w, h = op
            group.add(Rectangle(pos=(ox + x, top - y - h), size=(w, h)))
        elif kind == "circle":
            _k, _c, x, y, r = op
            group.add(Ellipse(pos=(ox + x - r, top - y - r), size=(2 * r, 2 * r)))
        elif kind == "ring":
            _k, _c, x, y, r, lw = op
            group.add(Line(circle=(ox + x, top - y, r), width=max(1.0, lw / 2)))
        elif kind == "ring_rect":
            _k, _c, x, y, w, h, lw = op
            group.add(Line(rectangle=(ox + x, top - y - h, w, h), width=max(1.0, lw / 2)))
        elif kind == "line":
            _k, _c, lw, pts = op
            flat = []
            for i in range(0, len(pts), 2):
                flat += [ox + pts[i], top - pts[i + 1]]
            group.add(Line(points=flat, width=max(1.0, lw / 2), joint="round", cap="round"))
        elif kind in ("text", "ctext"):
            _k, _c, text, size, x, y, bold = op
            tex = _texture(text, size, bold)
            if kind == "text":
                pos = (ox + x, top - y - tex.height)
            else:
                pos = (ox + x - tex.width / 2, top - y - tex.height / 2)
            group.add(Rectangle(texture=tex, pos=(int(pos[0]), int(pos[1])), size=tex.size))


class _MapCanvas(Widget):
    def __init__(self, view, **kw):
        super().__init__(**kw)
        self.view = view
        self.base = InstructionGroup()
        self.over = InstructionGroup()
        self.canvas.add(self.base)
        self.canvas.after.add(self.over)
        self.bind(size=lambda *_: view.redraw(), pos=lambda *_: view.redraw())


class KeyMapView(BoxLayout):
    def __init__(self, on_shortcut=None, **kw):
        super().__init__(orientation="vertical", **kw)
        self.on_shortcut = on_shortcut      # name -> called when a shortcut button is pressed
        self.floor = 0
        self.user_picked = False
        self.state = ({}, [[] for _ in FLOORS], [])
        self.current_room = None
        self.here = []                 # drawn rooms Jill is in (map_position.locate)
        self.jill_floor = -1
        self._number = None            # game room number at the last update
        self._old_pos = None           # Jill's position in the room before (stale for a moment)
        self._last_pos = None
        self._number_since = 0.0
        self.highlight = None
        self.scene = None
        self._drawn = None
        self._mouse = None
        self._pulses = []
        self._pulse_ev = None
        self._t0 = time.monotonic()
        top = BoxLayout(size_hint_y=None, height=36)
        prev_b = Button(text="<", size_hint_x=None, width=44)
        next_b = Button(text=">", size_hint_x=None, width=44)
        self.title = Label(text="", markup=True)
        here_b = Button(text="Where's Jill", size_hint_x=None, width=120)
        prev_b.bind(on_release=lambda *_: self.pick((self.floor - 1) % len(FLOORS)))
        next_b.bind(on_release=lambda *_: self.pick((self.floor + 1) % len(FLOORS)))
        here_b.bind(on_release=lambda *_: self.follow())
        for w in (prev_b, self.title, next_b, here_b):
            top.add_widget(w)
        self.add_widget(top)
        # Shortcuts (TessarionAM, 2026-11-13): unlocked by visiting the room; key_map_shortcuts in the YAML
        # 2026-11-14: one per typewriter room (11), so two rows of buttons with short labels
        from .shortcuts import LABELS, ORDER
        self.shortcut_row = BoxLayout(size_hint_y=None, height=60)
        self.shortcut_buttons = {}
        self.shortcut_row.add_widget(Label(text="Shortcuts:", size_hint_x=None, width=90))
        grid = GridLayout(cols=(len(ORDER) + 1) // 2, spacing=2)
        self.shortcut_row.add_widget(grid)
        self.shortcut_labels = {n: LABELS.get(n, n) for n in ORDER}
        for name in ORDER:
            b = Button(text=self.shortcut_labels[name], disabled=True, font_size="12sp")
            b.bind(on_release=lambda _b, n=name: self.on_shortcut and self.on_shortcut(n))
            self.shortcut_buttons[name] = b
            grid.add_widget(b)
        self._shortcuts_shown = False
        self.canvas_w = _MapCanvas(self)
        self.add_widget(self.canvas_w)
        self.bind(parent=self._on_parent)
        self._on_parent(self, self.parent)

    # mouse tracking only while the tab is showing
    def _on_parent(self, _w, parent):
        Window.unbind(mouse_pos=self._on_mouse)
        if self._pulse_ev is not None:
            self._pulse_ev.cancel()
            self._pulse_ev = None
        if parent is not None:
            Window.bind(mouse_pos=self._on_mouse)
            self._pulse_ev = Clock.schedule_interval(self._pulse, 1 / 30)

    def _pulse(self, _dt):
        """Jill's room: 25% darker to 50% brighter and back, on a loop (map_render.pulse_colour)."""
        t = time.monotonic() - self._t0
        for colour, base in self._pulses:
            colour.rgba = map_render.pulse_colour(base, t)

    def set_shortcuts(self, on: bool, unlocked, armed=None):
        """Show the shortcut row only when the option is on; a button works once its room has been
        visited; the armed one says so."""
        if on and not self._shortcuts_shown:
            self.add_widget(self.shortcut_row, index=len(self.children) - 1)   # under the top bar
            self._shortcuts_shown = True
        elif not on and self._shortcuts_shown:
            self.remove_widget(self.shortcut_row)
            self._shortcuts_shown = False
        for name, b in self.shortcut_buttons.items():
            label = self.shortcut_labels[name]
            b.disabled = name not in unlocked
            b.text = f"> {label} <" if name == armed else label      # greyed out until visited

    def pick(self, i):
        self.floor, self.user_picked, self.highlight = i, True, None
        self.redraw()

    def follow(self):
        self.user_picked = False
        f = self.jill_floor if self.jill_floor >= 0 else (floor_of(self.current_room) if self.current_room else -1)
        if f >= 0:
            self.floor = f
        self.redraw()

    def update(self, received, active, checked, box_gate, current_room, unlocked=(), number=None, pos=None,
               discovered=None, bosses=None):
        """current_room: our name for the game's room; number + pos: the game's room number and
        Jill's x, y, z - they say which map room (and floor) she's really in (map_position)."""
        self.state = map_state(received, active, checked, box_gate, unlocked, discovered)
        self.bosses = dict(bosses) if bosses is not None else None      # Boss Rush skulls
        now = time.monotonic()
        if number != self._number:
            # v0.9.9 (TessarionAM): for a moment after a door the game still holds Jill's position from
            # the room she left, which put her in the wrong drawn room for a second
            self._number, self._old_pos, self._number_since = number, self._last_pos, now
        stale = pos is not None and pos == self._old_pos and now - self._number_since < 3.0
        self._last_pos = pos
        prev = self.here[0] if len(self.here) == 1 else None
        if number is None:
            where = None
        elif stale:
            # the new room from its number alone (her position isn't updated yet): on the floor
            # she was on if the room is drawn there (stairways), else the room's first floor
            rooms = map_position.drawn_rooms(number)
            if rooms:
                fi = self.jill_floor if self.jill_floor in rooms else min(rooms)
                where = map_position.Where(fi, rooms[fi])
            else:
                where = None
        else:
            where = map_position.locate(number, pos, prev)
        if where is None and number is not None and self.here and self.jill_floor >= 0:
            # a room the map doesn't draw (the Kitchen Elevator, 0x200): Jill stays shown where she
            # got in, instead of vanishing from the map (2026-11-15)
            where = map_position.Where(self.jill_floor, list(self.here))
        here = where.rooms if where else []
        jill_floor = where.floor if where else (floor_of(current_room) if current_room else -1)
        if jill_floor != self.jill_floor and jill_floor >= 0:
            # Jill changed floor (also on one room drawn on two floors, e.g. the East Wing
            # Stairway): the map follows her, even if you'd picked another floor by hand
            self.user_picked = False
            self.floor = jill_floor
        elif (current_room, here) != (self.current_room, self.here):
            if not self.user_picked and jill_floor >= 0:
                self.floor = jill_floor
        self.current_room, self.here = current_room, here
        self.jill_floor = jill_floor
        self.redraw()

    def redraw(self, force=False):
        c = self.canvas_w
        self.title.text = f"[b]{FLOORS[self.floor][0]}[/b]  ({self.floor + 1}/{len(FLOORS)})"
        here = self.here if self.floor == self.jill_floor else []
        bosses = getattr(self, "bosses", None)
        sig = (self.floor, repr(self.state), tuple(c.size), tuple(c.pos), self.current_room, tuple(here),
               self.highlight, repr(bosses))
        if sig == self._drawn and not force:
            return
        self._drawn = sig
        self.scene = map_render.build(self.floor, self.state, c.width, c.height, self.current_room,
                                      measure, self.highlight, here=here if self.here else None,
                                      bosses=bosses)
        c.base.clear()
        self._pulses = []
        draw(c.base, self.scene.ops, c.x, c.y, c.height, self._pulses)
        self._draw_overlay(again=False)

    def _on_mouse(self, _window, pos):
        if self.get_root_window() is None or self.scene is None:
            return
        c = self.canvas_w
        lx, ly = c.to_widget(*pos)
        if not c.collide_point(lx, ly):
            if self._mouse is not None or self.highlight is not None:
                self._mouse = None
                if self.highlight is not None:
                    self.highlight = None
                    self.redraw()
                self._draw_overlay()
            return
        self._mouse = (lx - c.x, c.top - ly)
        self._draw_overlay()

    def _draw_overlay(self, again=True):
        c = self.canvas_w
        c.over.clear()
        if self._mouse is None or self.scene is None:
            return
        ops, lid = map_render.overlay(self.scene, self._mouse[0], self._mouse[1], c.width, c.height, measure)
        if lid != self.highlight and again:
            self.highlight = lid
            self.redraw()            # redraws the overlay too
            return
        draw(c.over, ops, c.x, c.y, c.height, self._pulses)
