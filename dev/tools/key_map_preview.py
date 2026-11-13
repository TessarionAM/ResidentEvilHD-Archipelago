"""Draw the client's Key Map to PNG files without Kivy (needs Pillow). Uses the same shapes as
the Key Map tab (worlds/re1hd/map_render.py), so it shows exactly what the tab draws.

    python Tools/key_map_preview.py OUT_DIR [WIDTH HEIGHT]

Writes one PNG per floor, with a sample game state (Sword + Armor Key found, the Sword Key doors
unlocked, Jill in the Tea Room, drawn at the brightest point of its glow) and a sample tooltip on the first floor.
"""
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # repository root
if "rw" not in sys.modules:                      # load the world folder without Archipelago
    pkg = types.ModuleType("rw")
    pkg.__path__ = [os.path.join(ROOT, "worlds", "re1hd")]
    sys.modules["rw"] = pkg

from PIL import Image, ImageDraw, ImageFont      # noqa: E402

from rw import map_render                        # noqa: E402
from rw.data import PICKUPS                      # noqa: E402
from rw.map_layout import FLOORS                 # noqa: E402
from rw.tracker import map_state                 # noqa: E402

SS = 2   # supersampling
_FONTS = {}


def font(size, bold):
    key = (size, bold)
    if key not in _FONTS:
        name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
        try:
            _FONTS[key] = ImageFont.truetype(name, size * SS)
        except OSError:
            _FONTS[key] = ImageFont.load_default()
    return _FONTS[key]


def measure(text, size, bold=False):
    l, t, r, b = font(size, bold).getbbox(text or " ")
    return (r - l) / SS, (size * 1.25)


def col(c):
    return tuple(int(v * 255) for v in c[:3]) + (int(c[3] * 255),)


def paint(ops, width, height, img=None):
    img = img or Image.new("RGBA", (int(width * SS), int(height * SS)), (0, 0, 0, 255))
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    def flush():
        nonlocal layer, d
        img.alpha_composite(layer)
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)

    for op in ops:
        kind, c = op[0], op[1]
        if c[3] < 1:
            flush()
        if kind in ("rect", "pulse"):
            _k, _c, x, y, w, h = op
            if kind == "pulse":                  # Jill's room, drawn at its brightest
                c = map_render.pulse_colour(c, map_render.PULSE_SECONDS / 4)
            d.rectangle([x * SS, y * SS, (x + w) * SS - 1, (y + h) * SS - 1], fill=col(c))
        elif kind == "ring_rect":
            _k, _c, x, y, w, h, lw = op
            d.rectangle([x * SS, y * SS, (x + w) * SS, (y + h) * SS], outline=col(c), width=int(lw * SS))
        elif kind == "circle":
            _k, _c, x, y, r = op
            d.ellipse([(x - r) * SS, (y - r) * SS, (x + r) * SS, (y + r) * SS], fill=col(c))
        elif kind == "ring":
            _k, _c, x, y, r, lw = op
            d.ellipse([(x - r) * SS, (y - r) * SS, (x + r) * SS, (y + r) * SS], outline=col(c), width=int(lw * SS))
        elif kind == "line":
            _k, _c, lw, pts = op
            d.line([v * SS for v in pts], fill=col(c), width=int(lw * SS), joint="curve")
        elif kind == "text":
            _k, _c, text, size, x, y, bold = op
            d.text((x * SS, y * SS), text, font=font(size, bold), fill=col(c))
        elif kind == "ctext":
            _k, _c, text, size, x, y, bold = op
            d.text((x * SS, y * SS), text, font=font(size, bold), fill=col(c), anchor="mm")
        if c[3] < 1:
            flush()
    flush()
    return img


def sample_state():
    """Sword + Armor Key found, and the Sword Key doors already unlocked."""
    from rw.tracker import unlock_flags
    active = {n for _r, n, _i, _q in PICKUPS}
    checked = {n for r, n, _i, _q in PICKUPS if r in ("Main Hall", "Dining Room")}
    first = map_state(["Book of Curses", "Armor Key"], active, checked, True)
    opened = set()
    for d in first[1][0]:
        if d["key"] == "Book of Curses":
            opened |= unlock_flags().get(frozenset((d["a"], d["b"])), set())
    return map_state(["Book of Curses", "Armor Key"], active, checked, True, opened)


def main(out, width=1100, height=640):
    os.makedirs(out, exist_ok=True)
    state = sample_state()
    for i, (title, *_r) in enumerate(FLOORS):
        sc = map_render.build(i, state, width, height, "Tea Room", measure)
        img = paint(sc.ops, width, height)
        if i == 0:
            d = sc.door_hits[len(sc.door_hits) // 2][1]
            px, py = sc.ox + d["x"] * sc.s, sc.oy + d["y"] * sc.s
            ops, _lid = map_render.overlay(sc, px, py, width, height, measure)
            img = paint(ops, width, height, img)
        img = img.resize((int(width), int(height)), Image.LANCZOS)
        img.save(os.path.join(out, f"{i:02d}_{title.replace(' ', '_')}.png"))
    print("wrote", len(FLOORS), "floors to", out)


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0] if a else "key_map_preview", *(int(v) for v in a[1:3]))
