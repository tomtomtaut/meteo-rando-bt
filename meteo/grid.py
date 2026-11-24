"""Quadrillage de la Basse-Terre sur les mailles AROME (2,5 km) et scores par activité, heure par heure.

Chaque case correspond exactement à une maille du modèle : on n'invente pas de détail entre deux mailles.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone

import numpy as np

from . import scoring

from .heure import TZ  # noqa: E402
STEP = 0.025                 # pas de la grille AROME Antilles
LAT0, LON0 = 9.7, -75.3      # coin de la grille « CARAÏBES » (open data Météo-France)
HOURS = list(range(5, 20))

# Contours simplifiés des îles (précision ~1 km). Une petite île sans centre de maille dedans
# reçoit quand même la maille la plus proche de son centre.
BASSE_TERRE = [
    (16.355, -61.760), (16.345, -61.700), (16.320, -61.660), (16.275, -61.625), (16.250, -61.590),
    (16.200, -61.585), (16.140, -61.565), (16.090, -61.555), (16.035, -61.555), (15.990, -61.600),
    (15.965, -61.650), (15.945, -61.700), (15.975, -61.730), (16.010, -61.745), (16.060, -61.775),
    (16.120, -61.775), (16.180, -61.785), (16.230, -61.795), (16.290, -61.805), (16.330, -61.795),
]


GRANDE_TERRE = [
    (16.515, -61.465), (16.470, -61.415), (16.400, -61.385), (16.335, -61.340), (16.290, -61.250),
    (16.255, -61.180), (16.245, -61.235), (16.225, -61.330), (16.205, -61.450), (16.215, -61.510),
    (16.240, -61.540), (16.300, -61.530), (16.350, -61.510), (16.400, -61.535), (16.445, -61.535),
    (16.480, -61.500),
]
MARIE_GALANTE = [(16.010, -61.300), (15.995, -61.220), (15.940, -61.190), (15.880, -61.210),
                 (15.865, -61.290), (15.900, -61.330), (15.960, -61.330)]
DESIRADE = [(16.300, -61.100), (16.335, -61.020), (16.330, -60.995), (16.290, -61.080)]
TERRE_DE_HAUT = [(15.880, -61.600), (15.880, -61.570), (15.855, -61.570), (15.855, -61.600)]
TERRE_DE_BAS = [(15.870, -61.650), (15.870, -61.620), (15.840, -61.620), (15.840, -61.650)]
PETITE_TERRE = [(16.180, -61.130), (16.180, -61.100), (16.165, -61.100), (16.165, -61.130)]
ILES = {
    "Basse-Terre": BASSE_TERRE, "Grande-Terre": GRANDE_TERRE, "Marie-Galante": MARIE_GALANTE,
    "La Désirade": DESIRADE, "Les Saintes": TERRE_DE_HAUT, "Les Saintes (Terre-de-Bas)": TERRE_DE_BAS,
    "Petite-Terre": PETITE_TERRE,
}
SEA_STEP = 0.05               # cases en mer : 5,5 km, à l'échelle du modèle de vagues
SEA_BBOX = (15.75, 16.60, -61.95, -60.90)
SEA_MAX_DIST = 0.12           # ° : mer jusqu'à ~13 km des côtes


def _inside(lat: float, lon: float, poly=BASSE_TERRE) -> bool:
    inside = False
    for k in range(len(poly)):
        (y1, x1), (y2, x2) = poly[k], poly[k - 1]
        if (y1 > lat) != (y2 > lat):
            x = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if lon < x:
                inside = not inside
    return inside


def _land_cells(poly, ile: str) -> list[dict]:
    lats = [p[0] for p in poly]
    lons = [p[1] for p in poly]
    out = []
    j0, j1 = math.floor((min(lats) - LAT0) / STEP), math.ceil((max(lats) - LAT0) / STEP)
    i0, i1 = math.floor((min(lons) - LON0) / STEP), math.ceil((max(lons) - LON0) / STEP)
    for j in range(j0, j1 + 1):
        for i in range(i0, i1 + 1):
            lat, lon = round(LAT0 + j * STEP, 4), round(LON0 + i * STEP, 4)
            if _inside(lat, lon, poly):
                out.append({"lat": lat, "lon": lon, "kind": "terre", "ile": ile, "size": STEP})
    if not out:  # îlot plus petit qu'une maille
        cy, cx = sum(lats) / len(lats), sum(lons) / len(lons)
        lat = round(LAT0 + round((cy - LAT0) / STEP) * STEP, 4)
        lon = round(LON0 + round((cx - LON0) / STEP) * STEP, 4)
        out.append({"lat": lat, "lon": lon, "kind": "terre", "ile": ile, "size": STEP})
    return out


def on_land(lat: float, lon: float) -> bool:
    return any(_inside(lat, lon, p) for p in ILES.values())


def cells() -> list[dict]:
    """Mailles AROME sur toutes les îles, puis cases en mer (0,05°) jusqu'à ~13 km des côtes."""
    land = []
    for ile, poly in ILES.items():
        land += _land_cells(poly, ile.split(" (")[0])
    sea = []
    lat = SEA_BBOX[0]
    while lat <= SEA_BBOX[1] + 1e-9:
        lon = SEA_BBOX[2]
        while lon <= SEA_BBOX[3] + 1e-9:
            la, lo = round(lat, 3), round(lon, 3)
            if not on_land(la, lo):
                d = min(math.hypot(la - c["lat"], lo - c["lon"]) for c in land)
                if d <= SEA_MAX_DIST:
                    sea.append({"lat": la, "lon": lo, "kind": "mer", "ile": None, "size": SEA_STEP})
            lon += SEA_STEP
        lat += SEA_STEP
    return land + sea


def model_altitude(merged, i: int) -> float:
    """Altitude du relief du modèle (lissé) à partir de la pression de surface."""
    sp = merged.data.get("sp")
    if sp is None:
        return float("nan")
    v = sp[:, i]
    v = v[~np.isnan(v)]
    if not len(v):
        return float("nan")
    p = float(np.median(v))
    p = p / 100 if p > 2000 else p
    return 44330.8 * (1 - (p / 1013.25) ** 0.190263)


def _r(x, nd=1):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), nd)


LAYERS = ("rando", "riviere", "sommet", "mer", "surf", "kite")


def compute(merged, cell_idx: list[int], cell_alts: list[float], days: list[date],
            not_before: datetime | None = None, kinds: list[str] | None = None) -> dict:
    """Pour chaque jour et chaque heure : score 0-100 par activité et données brutes, par case.
    Cases à terre : randos, rivières, sommets. Cases en mer : mer calme, surf, kite."""
    from . import mer as mer_mod
    kinds = kinds or ["terre"] * len(cell_idx)
    spots = {
        "rando": [{"type": "rando", "_obj": [i], "_all": [i], "_obj_high": [], "_high": False} for i in cell_idx],
        "sommet": [{"type": "sommet", "_obj": [i], "_all": [i], "_obj_high": [i], "_high": True} for i in cell_idx],
        "mer": [{"type": "mer", "mer": "calme", "_obj": [i], "_all": [i]} for i in cell_idx],
        "surf": [{"type": "mer", "mer": "surf", "_obj": [i], "_all": [i]} for i in cell_idx],
        "kite": [{"type": "mer", "mer": "kite", "_obj": [i], "_all": [i]} for i in cell_idx],
    }
    cache: dict = {}

    def r90(ti, i):
        if (ti, i) not in cache:
            cache[(ti, i)] = scoring.rain_stats(merged, ti, [i], scoring.RIVER_PCTL)[0]
        return cache[(ti, i)]

    out = []
    for d in days:
        day = {"date": d.isoformat(), "hours": HOURS, "src": [],
               "score": {k: [] for k in LAYERS},
               "raw": {k: [] for k in ("pluie", "proba", "nuages_bas", "nuage_case", "hum_case", "etat",
                                       "rafales", "pluie24", "vagues", "houle", "periode", "dir_houle", "vent",
                                       "base_nuages", "haut_nuages")}}
        for h in HOURS:
            t = datetime(d.year, d.month, d.day, h, tzinfo=TZ).astimezone(timezone.utc)
            ti = merged.index.get(t)
            day["src"].append(merged.source[ti] if ti is not None else None)
            sc = {k: [] for k in day["score"]}
            raw = {k: [] for k in day["raw"]}
            for n, i in enumerate(cell_idx):
                if ti is None:
                    for k in sc:
                        sc[k].append(None)
                    for k in raw:
                        raw[k].append(None)
                    continue
                if kinds[n] == "mer":
                    e_m = None
                    for lay in ("mer", "surf", "kite"):
                        sc_m, e_m = scoring.hour_eval(spots[lay][n], merged, ti)
                        sc[lay].append(None if sc_m is None else round(sc_m))
                    for lay in ("rando", "riviere", "sommet"):
                        sc[lay].append(None)
                    for k in raw:
                        raw[k].append(None)
                    raw["pluie"][-1] = _r(e_m["rain"])
                    raw["proba"][-1] = None if e_m["prob"] is None else round(e_m["prob"] * 100)
                    raw["rafales"][-1] = _r(e_m["gust"], 0)
                    raw["vagues"][-1] = _r(e_m["hs"])
                    raw["houle"][-1] = _r(e_m["sw"])
                    raw["periode"][-1] = _r(e_m["per"], 0)
                    raw["dir_houle"][-1] = mer_mod.dir_name(e_m["dir"]) if e_m["dir"] == e_m["dir"] else None
                    raw["vent"][-1] = _r(e_m["ws"], 0)
                    continue
                for lay in ("mer", "surf", "kite"):
                    sc[lay].append(None)
                s_r, e_r = scoring.hour_eval(spots["rando"][n], merged, ti)
                s_s, _ = scoring.hour_eval(spots["sommet"][n], merged, ti)
                # rivière : pluie des 24 h précédentes et de l'heure, sur la case et ses voisines (90e percentile)
                p24 = sum(r90(merged.index[t - timedelta(hours=k)], i)
                          for k in range(0, 24) if (t - timedelta(hours=k)) in merged.index)
                if p24 >= scoring.RIVER_NOGO_24H or r90(scoring.rain_index(merged, ti), i) >= scoring.RIVER_NOGO_RATE:
                    s_v = 0.0
                else:
                    s_v = s_r - (35 if p24 >= scoring.RIVER_BAD_24H else 15 if p24 >= scoring.RIVER_MEH_24H else 0)
                    s_v -= 25 if e_r["storm"] else 0
                sc["rando"].append(round(s_r))
                sc["sommet"].append(round(s_s))
                sc["riviere"].append(round(max(0.0, s_v)))
                st = merged.summit_state.get((i, t))
                det = st[1] if st else {}
                lcc = merged.data["lcc"][ti, i] if "lcc" in merged.data else float("nan")
                raw["pluie"].append(_r(e_r["rain"]))
                raw["proba"].append(None if e_r["prob"] is None else round(e_r["prob"] * 100))
                raw["nuages_bas"].append(_r(lcc, 0))
                raw["nuage_case"].append(det.get("cc"))
                raw["hum_case"].append(det.get("rh"))
                raw["etat"].append(st[0] if st else None)
                raw["base_nuages"].append(det.get("base"))
                raw["haut_nuages"].append(det.get("haut"))
                raw["rafales"].append(_r(e_r["gust"], 0))
                raw["pluie24"].append(_r(p24))
                for k in ("vagues", "houle", "periode", "dir_houle"):
                    raw[k].append(None)
                ws = merged.data["ws10"][ti, i] if "ws10" in merged.data else float("nan")
                raw["vent"].append(_r(ws, 0))
            for k in sc:
                day["score"][k].append(sc[k])
            for k in raw:
                day["raw"][k].append(raw[k])
        out.append(day)
    return {"cells": [], "days": out}
