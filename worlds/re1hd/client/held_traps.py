"""
Fun traps: Archipelago's own "<player> sent you <trap>" line is held back until the prank is over
(TessarionAM, 2026-11-13: "I was sent the To Be Continued trap and it told me so I knew it was a fake").
The client releases each held line when the bridge reports that prank finished (fun_done).

If a prank finishes before its line arrives from the server, the line is printed as soon as it
comes (a credit). Lines never released (the client was closed mid-prank, a trap that can't run)
are printed after HOLD_LIMIT seconds so nothing is lost for good.
"""
import time
from typing import Callable, Dict, List, Optional, Tuple

HOLD_LIMIT = 600.0


class HeldTraps:
    def __init__(self, trap_of: Callable[[dict], Optional[str]], emit: Callable[[dict], None]):
        self.trap_of = trap_of          # args -> trap name if it's a fun trap sent to us, else None
        self.emit = emit                # prints a PrintJSON message the normal way
        self.held: Dict[str, List[Tuple[float, dict]]] = {}
        self.credits: Dict[str, int] = {}

    def hold(self, args: dict, now: Optional[float] = None) -> bool:
        """True = held (don't print it now)."""
        try:
            name = self.trap_of(args)
        except Exception:
            return False
        if not name:
            return False
        if self.credits.get(name, 0) > 0:
            self.credits[name] -= 1
            return False                 # that prank is already over
        self.held.setdefault(name, []).append((time.time() if now is None else now, args))
        return True

    def release(self, name: str) -> None:
        waiting = self.held.get(name)
        if waiting:
            self.emit(waiting.pop(0)[1])
        else:
            self.credits[name] = self.credits.get(name, 0) + 1

    def expire(self, now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        for name, waiting in self.held.items():
            while waiting and now - waiting[0][0] > HOLD_LIMIT:
                self.emit(waiting.pop(0)[1])
