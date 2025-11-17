# =================
# algo_two_phase.py
# =================
# Two-Phase (NS vs EW) planning with short demo timings (5..12 s).

from dataclasses import dataclass

# ---------- Tunables (short demo ranges) ----------
GMIN_MS   = 5000
GBASE_MS  = 8000
GMAX_MS   = 12000
K_PER_CAR = 1000     # ms per car above average
AMBER_MS  = 2000
ALLRED_MS = 1000
DELTA_HYS = 2        # hysteresis threshold (cars)

@dataclass
class Cycle:
    order: str        # "NS" or "EW" (who starts)
    ns_green_ms: int
    ew_green_ms: int
    amber_ms:   int
    allred_ms:  int

def _clamp(v, a, b): 
    return max(a, min(b, v))

def plan_cycle(N: int, S: int, E: int, W: int, last_order: str = "NS") -> Cycle:
    """Compute a cycle given N,S,E,W counts. Hysteresis keeps last_order on near ties."""
    ns = max(0, int(N)) + max(0, int(S))
    ew = max(0, int(E)) + max(0, int(W))
    qavg = (ns + ew) / 2.0

    if abs(ns - ew) < DELTA_HYS:
        order = last_order
    else:
        order = "NS" if ns > ew else "EW"

    def g(q):
        return int(_clamp(GBASE_MS + K_PER_CAR * (q - qavg), GMIN_MS, GMAX_MS))

    ns_g = g(ns)
    ew_g = g(ew)
    return Cycle(order=order, ns_green_ms=ns_g, ew_green_ms=ew_g,
                 amber_ms=AMBER_MS, allred_ms=ALLRED_MS)
