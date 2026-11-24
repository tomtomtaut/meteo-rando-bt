"""Quadrillage de la Basse-Terre sur les mailles AROME (2,5 km) et scores par activité, heure par heure.

Chaque case correspond exactement à une maille du modèle : on n'invente pas de détail entre deux mailles.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone

import numpy as np

from . import scoring

TZ = timezone(timedelta(hours=-4))
STEP = 0.025                 # pas de la grille AROME Antilles
LAT0, LON0 = 9.7, -75.3      # coin de la grille « CARAÏBES » (open data Météo-France)
HOURS = list(range(5, 20))

# Contour simplifié de la Basse-Terre (sens horaire depuis la pointe nord), précision ~1 km
BASSE_TERRE = [
    (16.355, -61.760), (16.345, -61.700), (16.320, -61.660), (16.275, -61.625), (16.250, -61.590),
    (16.200, -61.585), (16.140, -61.565), (16.090, -61.555), (16.035, -61.555), (15.990, -61.600),
    (15.965, -61.650), (15.945, -61.700), (15.975, -61.730), (16.010, -61.745), (16.060, -61.775),
    (16.120, -61.775), (16.180, -61.785), (16.230, -61.795), (16.290, -61.805), (16.330, -61.795),
]


def _inside(lat: float, lon: float, poly=BASSE_TERRE) -> bool:
    inside = False
    for k in range(len(poly)):
        (y1, x1), (y2, x2) = poly[k], poly[k - 1]
        if (y1 > lat) != (y2 > lat):
            x = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if lon < x:
                inside = not inside
    return inside


def cells() -> list[dict]:
    """Centres des mailles AROME dont le centre est dans le contour de la Basse-Terre."""
    lats = [p[0] for p in BASSE_TERRE]
    lons = [p[1] for p in BASSE_TERRE]
    out = []
    j0, j1 = math.floor((min(lats) - LAT0) / STEP), math.ceil((max(lats) - LAT0) / STEP)
    i0, i1 = math.floor((min(lons) - LON0) / STEP), math.ceil((max(lons) - LON0) / STEP)
    for j in range(j0, j1 + 1):
        for i in range(i0, i1 + 1):
            lat, lon = round(LAT0 + j * STEP, 4), round(LON0 + i * STEP, 4)
            if _inside(lat, lon):
                out.append({"lat": lat, "lon": lon})
    return out


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


def compute(merged, cell_idx: list[int], cell_alts: list[float], days: list[date],
            not_before: datetime | None = None) -> dict:
    """Pour chaque jour et chaque heure : score 0-100 par activité et données brutes, par case."""
    spots = {
        "rando": [{"type": "rando", "_obj": [i], "_all": [i], "_obj_high": [], "_high": False} for i in cell_idx],
        "sommet": [{"type": "sommet", "_obj": [i], "_all": [i], "_obj_high": [i], "_high": True} for i in cell_idx],
    }
    cache: dict = {}

    def r90(ti, i):
        if (ti, i) not in cache:
            cache[(ti, i)] = scoring.rain_stats(merged, ti, [i], scoring.RIVER_PCTL)[0]
        return cache[(ti, i)]

    out = []
    for d in days:
        day = {"date": d.isoformat(), "hours": HOURS, "src": [],
               "score": {"rando": [], "riviere": [], "sommet": []},
               "raw": {k: [] for k in ("pluie", "proba", "nuages_bas", "nuage_case", "hum_case", "etat",
                                       "rafales", "pluie24")}}
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
                s_r, e_r = scoring.hour_eval(spots["rando"][n], merged, ti)
                s_s, _ = scoring.hour_eval(spots["sommet"][n], merged, ti)
                # rivière : pluie des 24 h précédentes et de l'heure, sur la case et ses voisines (90e percentile)
                p24 = sum(r90(merged.index[t - timedelta(hours=k)], i)
                          for k in range(1, 25) if (t - timedelta(hours=k)) in merged.index)
                if p24 >= scoring.RIVER_NOGO_24H or r90(ti, i) >= scoring.RIVER_NOGO_RATE:
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
                raw["rafales"].append(_r(e_r["gust"], 0))
                raw["pluie24"].append(_r(p24))
            for k in sc:
                day["score"][k].append(sc[k])
            for k in raw:
                day["raw"][k].append(raw[k])
        out.append(day)
    return {"cells": [], "days": out}
