"""
Batch seed validation for the door lock randomiser (2026-11-12). Run from an Archipelago source
folder that has worlds/re1hd:  python <path>/Tools/door_lock_batch.py [seeds per setting]
Generates single-player seeds with Archipelago's real fill for every mode and several locked door
counts, and reports any seed that fails (option error, fill error or not beatable).
"""
import logging
import os
import sys
import time

sys.path.insert(0, os.getcwd())

logging.disable(logging.CRITICAL)
from worlds.re1hd.test.test_door_locks import generate   # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 100
SETTINGS = [("mansion_only", c) for c in ("fewer", "vanilla", "more", "many", 42)] + \
           [("regional", c) for c in ("fewer", "vanilla", "more", "many", 55, 65)] + \
           [("full", c) for c in (0, "fewer", "vanilla", "more", "many", 55, 65)]
total_bad = 0
for mode, count in SETTINGS:
    for goal in ("complete_game", "mansion_escape"):
        t = time.time()
        bad = []
        for seed in range(N):
            _mw, problem = generate({"door_lock_randomisation": mode, "locked_door_count": count, "goal": goal}, seed)
            if problem:
                bad.append((seed, problem[:160]))
        total_bad += len(bad)
        print(f"{mode:13s} {str(count):8s} {goal:15s} {N - len(bad)}/{N} ok  ({time.time() - t:.0f} s)", flush=True)
        for seed, problem in bad[:3]:
            print(f"      seed {seed}: {problem}", flush=True)
print("ALL OK" if not total_bad else f"{total_bad} FAILED SEEDS")
