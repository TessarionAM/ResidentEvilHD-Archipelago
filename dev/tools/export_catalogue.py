"""
Export the list of every pickup and extra check such as maps (location name,
room, in-game item id, known flag bit if any) from the AP world into client/pickup_catalogue.json,
so tools that run WITHOUT Archipelago (the pickup mapper) know the mansion.

Must be run inside an Archipelago source checkout that contains worlds/re1hd
(it imports the world). tests/test_catalogue.py checks the JSON is current.
"""
import json
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "client" / "pickup_catalogue.json"


def build():
    # Same logic as the client's own catalogue (worlds/re1hd/client/game_bridge.py)
    from worlds.re1hd.client.game_bridge import pickup_catalogue
    return pickup_catalogue()


if __name__ == "__main__":
    data = build()
    OUT.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")
    print(f"wrote {len(data)} pickups to {OUT}")
