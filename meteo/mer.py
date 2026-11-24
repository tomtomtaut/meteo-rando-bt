"""Scores des activités en mer, heure par heure.

- « calme » (kayak, snorkeling, plongée, traversée en bateau) : petite mer et peu de vent ;
- « surf » : houle assez grande et longue, venant du bon côté pour le spot ;
- « kite » (kitesurf, wingfoil) : alizé établi, ni trop faible ni trop fort.
Seuils de départ, à ajuster avec vos sorties.
"""

from __future__ import annotations

import math

WAVE_CALM = [(0.6, 0), (1.0, 20), (1.5, 45), (math.inf, 75)]          # m → pénalité
WIND_CALM = [(15, 0), (25, 15), (35, 35), (math.inf, 60)]             # km/h
SWELL_SURF = [(0.5, 70), (0.8, 45), (1.2, 20), (2.5, 0), (3.5, 10), (math.inf, 40)]
PERIOD_SURF = [(7, 20), (9, 5), (math.inf, 0)]                        # s
WIND_KITE = [(18, 70), (22, 40), (30, 10), (45, 0), (55, 15), (math.inf, 50)]
DIRS = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]


def _lk(table, x):
    for lim, v in table:
        if x < lim:
            return v
    return table[-1][1]


def _get(m, k, ti, cols):
    if k not in m.data:
        return float("nan")
    vals = [m.data[k][ti, c] for c in cols]
    vals = [v for v in vals if not math.isnan(v)]
    return max(vals) if vals else float("nan")


def dir_name(deg: float) -> str:
    return "?" if deg is None or math.isnan(deg) else DIRS[int(((deg % 360) + 22.5) // 45) % 8]


def _in_range(deg: float, rng) -> bool:
    a, b = rng
    return (a <= deg <= b) if a <= b else (deg >= a or deg <= b)


def hour_eval(spot: dict, m, ti: int, rain: float, prob, storm: bool, gust: float) -> tuple[float, dict]:
    from .scoring import RAIN_PENALTY, _lookup  # import local : évite une boucle d'import
    cols = spot["_obj"]
    hs, sw, per, d = (_get(m, k, ti, cols) for k in ("hs", "sw", "per", "dir"))
    ws = _get(m, "ws10", ti, cols)
    kind = spot.get("mer", "calme")
    pens = {"p": round(_lookup(RAIN_PENALTY, rain) * 0.5), "o": 25 if storm else 0}
    nodata = all(math.isnan(x) for x in (hs, ws))
    if kind == "calme":
        pens["m"] = _lk(WAVE_CALM, 0 if math.isnan(hs) else hs)
        pens["v"] = _lk(WIND_CALM, 0 if math.isnan(ws) else ws)
    elif kind == "surf":
        pens["h"] = _lk(SWELL_SURF, 0 if math.isnan(sw) else sw)
        pens["t"] = _lk(PERIOD_SURF, 0 if math.isnan(per) else per)
        if spot.get("houle") and not math.isnan(d) and not _in_range(d, spot["houle"]):
            pens["d"] = 40
        if not math.isnan(ws) and ws > 35:
            pens["v"] = 20
        nodata = math.isnan(sw)
    elif kind == "kite":
        pens["v"] = _lk(WIND_KITE, 0 if math.isnan(ws) else ws)
        if not math.isnan(gust) and not math.isnan(ws) and gust - ws > 20:
            pens["k"] = 15
        nodata = math.isnan(ws)
    pens = {k: v for k, v in pens.items() if v}
    score = None if nodata else max(0.0, 100.0 - sum(pens.values()))
    return score, {"hs": hs, "sw": sw, "per": per, "dir": d, "ws": ws, "pens": pens}


def reasons(spot: dict, evals: list[dict]) -> list[str]:
    def mean(k):
        v = [e[k] for e in evals if not math.isnan(e[k])]
        return sum(v) / len(v) if v else float("nan")
    hs, sw, per, d, ws = mean("hs"), mean("sw"), mean("per"), mean("dir"), mean("ws")
    out = []
    if not math.isnan(hs):
        out.append(f"mer {hs:.1f} m".replace(".", ","))
    if spot.get("mer") == "surf" and not math.isnan(sw):
        out.append(f"houle {sw:.1f} m / {per:.0f} s de {dir_name(d)}".replace(".", ","))
        if spot.get("houle") and not math.isnan(d) and not _in_range(d, spot["houle"]):
            out.append("houle pas orientée pour ce spot")
    if not math.isnan(ws):
        kn = ws / 1.852
        out.append(f"vent {ws:.0f} km/h ({kn:.0f} nœuds)")
    return out
