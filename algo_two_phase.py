"""Two-phase (NS vs EW) cycle planner for the Smart Road demo.

The planner receives raw counts for the four approaches, applies a small
hysteresis to avoid flip-flopping near ties, and clamps the calculated green
windows to short classroom-friendly ranges.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Cycle", "plan_cycle"]


@dataclass(frozen=True)
class Cycle:
    """Container for a full signal cycle."""

    order: str  # Either "NS" or "EW" – whichever direction starts the cycle
    ns_green_ms: int
    ew_green_ms: int
    amber_ms: int
    allred_ms: int


# Tunable parameters (demo-friendly defaults)
GMIN_MS = 5_000
GBASE_MS = 8_000
GMAX_MS = 12_000
K_PER_CAR = 1_000  # ms per car deviation from avg
AMBER_MS = 2_000
ALLRED_MS = 1_000
DELTA_HYS = 2  # cars


def _clamp(value: float, lo: int, hi: int) -> int:
    return int(max(lo, min(hi, value)))


def plan_cycle(N: int, S: int, E: int, W: int, last_order: str = "NS") -> Cycle:
    """Return the next :class:`Cycle` given directional counts.

    Args:
        N,S,E,W: Car counts gathered since the previous cycle.
        last_order: Direction that led the previous cycle. Used to apply
            hysteresis so the intersection does not flicker near ties.
    """

    counts = {
        "N": max(0, int(N)),
        "S": max(0, int(S)),
        "E": max(0, int(E)),
        "W": max(0, int(W)),
    }
    ns = counts["N"] + counts["S"]
    ew = counts["E"] + counts["W"]
    avg = (ns + ew) / 2.0

    if abs(ns - ew) < DELTA_HYS:
        order = last_order
    else:
        order = "NS" if ns >= ew else "EW"

    def _g(q: int) -> int:
        return _clamp(GBASE_MS + K_PER_CAR * (q - avg), GMIN_MS, GMAX_MS)

    return Cycle(
        order=order,
        ns_green_ms=_g(ns),
        ew_green_ms=_g(ew),
        amber_ms=AMBER_MS,
        allred_ms=ALLRED_MS,
    )
