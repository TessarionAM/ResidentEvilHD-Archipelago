"""
The research tools' "client" package.

The tools use the same memory-access code as the Archipelago client, so there is one copy of it:
worlds/re1hd/client. That package normally loads inside Archipelago; here it is loaded on its own
(without running worlds/re1hd/__init__.py, which needs Archipelago) and each module is made
available as client.<name>, e.g. `from client.pc_process import ProcessConnection`.

Only hd_items.py (BhdTool's item id table) and the research data files (*.json) live here.
"""
import importlib
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # the repository root
WORLD = ROOT / "worlds" / "re1hd"

for _name, _path in (("worlds", ROOT / "worlds"), ("worlds.re1hd", WORLD),
                     ("worlds.re1hd.client", WORLD / "client")):
    if _name not in sys.modules:
        _module = types.ModuleType(_name)
        _module.__path__ = [str(_path)]
        sys.modules[_name] = _module

SHARED = ("autosave", "door_data", "door_skip", "gamepad", "hd_delivery", "hd_pickups", "hd_versions",
          "pc_process", "pickup_mapper", "window_mode", "wrong_door")

for _name in SHARED:
    _module = importlib.import_module(f"worlds.re1hd.client.{_name}")
    sys.modules[f"{__name__}.{_name}"] = _module
    globals()[_name] = _module
