"""Fusion AROME + ECMWF et calcul d'un score par activité, par jour et par créneau de départ.

Tous les seuils sont regroupés en haut du fichier pour être ajustés après quelques sorties.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

import numpy as np

TZ = timezone(timedelta(hours=-4))  # Guadeloupe, pas d'heure d'été

# --- Seuils (à calibrer) --------------------------------------------------------------------
RAIN_PENALTY = [(0.1, 0), (0.5, 15), (1.0, 30), (2.5, 50), (5.0, 70), (math.inf, 90)]  # mm/h → pénalité
CLOUD_FULL = 85          # % de nuages bas au-dessus duquel le sommet est « dans le nuage »
CLOUD_PARTIAL = 60
RH_FOG = 97              # % d'humidité à 2 m = brouillard
GUST_SUMMIT = [(50, 0), (65, 15), (math.inf, 35)]  # km/h
GUST_OTHER = [(70, 0), (math.inf, 20)]
CAPE_UNSTABLE = 1000     # J/kg
HOT = 31                 # °C, pour le littoral
RIVER_NOGO_24H = 25      # mm tombés en amont sur les 24 h avant le départ
RIVER_BAD_24H = 10
RIVER_MEH_24H = 4
RIVER_NOGO_RATE = 4      # mm/h en amont pendant la sortie
RIVER_NOGO_WINDOW = 6    # mm cumulés en amont pendant la sortie
FIRST_START, LAST_END = 6, 18  # heures locales
NIVEAU_BONUS = {"Hors sentiers": 8, "Intermédiaire": 4, "Touristique": 0}  # pour classer le « top du top »


def _lookup(table, x):
    for limit, val in table:
        if x < limit:
            return val
    return table[-1][1]


@dataclass
class Merged:
    times: list[datetime]                 # UTC, pas horaire
    data: dict[str, np.ndarray]           # var -> (T, P)
    source: list[str]                     # "AROME" | "ECMWF" par heure
    index: dict[datetime, int] = field(default_factory=dict)
    summit_state: dict = field(default_factory=dict)  # (i_point, t) -> (état, détails, source)

    def __post_init__(self):
        self.index = {t: i for i, t in enumerate(self.times)}


def merge(arome: dict | None, ecmwf: dict | None, n_points: int) -> Merged:
    """Base horaire ECMWF, remplacée par AROME là où AROME a des valeurs."""
    if ecmwf is None and arome is None:
        raise RuntimeError("Aucune source météo disponible")
    base = ecmwf or arome
    times = list(base["times"])
    if ecmwf and arome:
        known = set(times)
        extra = [t for t in arome["times"] if t not in known]
        times = sorted(times + extra)
    idx = {t: i for i, t in enumerate(times)}
    T = len(times)
    data, source = {}, ["ECMWF" if ecmwf else "—"] * T
    for var in ("precip", "lcc", "mcc", "rh", "rh850", "gust", "t2m", "cape"):
        arr = np.full((T, n_points), np.nan)
        if ecmwf and var in ecmwf:
            for i, t in enumerate(ecmwf["times"]):
                arr[idx[t]] = ecmwf[var][i]
        if arome and var in arome:
            for i, t in enumerate(arome["times"]):
                row = arome[var][i]
                ok = ~np.isnan(row)
                arr[idx[t]][ok] = row[ok]
        data[var] = arr
    if arome and "precip" in arome:
        for i, t in enumerate(arome["times"]):
            if not np.all(np.isnan(arome["precip"][i])):
                source[idx[t]] = "AROME"
    return Merged(times, data, source)


def _max(m: Merged, var: str, ti: int, cols: list[int]) -> float:
    if var not in m.data:
        return float("nan")
    v = m.data[var][ti, cols]
    return float(np.nanmax(v)) if not np.all(np.isnan(v)) else float("nan")


def _nz(x: float) -> float:
    return 0.0 if math.isnan(x) else x


def hour_eval(spot: dict, m: Merged, ti: int) -> tuple[float, dict]:
    obj = spot["_obj"]
    rain = _nz(_max(m, "precip", ti, obj))
    lcc, rh = _max(m, "lcc", ti, obj), _max(m, "rh", ti, obj)
    gust, cape, t2m = _max(m, "gust", ti, obj), _max(m, "cape", ti, obj), _max(m, "t2m", ti, obj)
    pen = _lookup(RAIN_PENALTY, rain)
    in_cloud = False
    if spot["_high"]:
        sts = [m.summit_state.get((i, m.times[ti])) for i in spot.get("_obj_high", [])]
        sts = [x[0] for x in sts if x and x[0]]
        if sts:  # état déduit du profil vertical à l'altitude réelle du sommet
            in_cloud = "nuage" in sts
            pen += 25 if in_cloud else (10 if "incertain" in sts else 0)
        else:    # repli : champs de surface
            in_cloud = _nz(lcc) >= CLOUD_FULL or _nz(rh) >= RH_FOG
            pen += 25 if in_cloud else (10 if _nz(lcc) >= CLOUD_PARTIAL else 0)
        pen += _lookup(GUST_SUMMIT, _nz(gust))
    else:
        pen += _lookup(GUST_OTHER, _nz(gust))
    if _nz(cape) >= CAPE_UNSTABLE:
        pen += 15
    if spot["type"] == "littoral" and _nz(t2m) >= HOT:
        pen += 10
    return max(0.0, 100.0 - pen), {"rain": rain, "in_cloud": in_cloud, "gust": gust, "cape": cape, "t2m": t2m}


def _river_rain(spot: dict, m: Merged, ti: int) -> float:
    return _nz(_max(m, "precip", ti, spot["_all"]))


def evaluate_day(spot: dict, m: Merged, day: date) -> dict:
    dur = max(2, min(9, math.ceil(spot["duree_h"])))
    best = None
    for start in range(FIRST_START, LAST_END - dur + 1):
        t0 = datetime(day.year, day.month, day.day, start, tzinfo=TZ).astimezone(timezone.utc)
        tis = [m.index.get(t0 + timedelta(hours=k)) for k in range(dur)]
        if any(t is None for t in tis):
            continue
        evals = [hour_eval(spot, m, ti) for ti in tis]
        scores = [e[0] for e in evals]
        score = 0.6 * float(np.mean(scores)) + 0.4 * min(scores)
        nogo, reasons = False, []

        rain_win = sum(e[1]["rain"] for e in evals)
        if spot["type"] == "riviere" or spot.get("riviere_partielle"):
            before = [m.index.get(t0 - timedelta(hours=k)) for k in range(1, 25)]
            p24 = sum(_river_rain(spot, m, ti) for ti in before if ti is not None)
            up_win = [_river_rain(spot, m, ti) for ti in tis]
            if spot["type"] == "riviere":
                if p24 >= RIVER_NOGO_24H:
                    nogo = True
                    reasons.append(f"Trop de pluie en amont : {p24:.0f} mm sur 24 h")
                elif max(up_win) >= RIVER_NOGO_RATE or sum(up_win) >= RIVER_NOGO_WINDOW:
                    nogo = True
                    reasons.append(f"Pluie en amont pendant la sortie ({sum(up_win):.0f} mm) : risque de montée des eaux")
                else:
                    if p24 >= RIVER_BAD_24H:
                        score -= 35
                    elif p24 >= RIVER_MEH_24H:
                        score -= 15
                    reasons.append(f"Amont : {p24:.0f} mm sur les 24 h avant")
                if any(_nz(e[1]["cape"]) >= CAPE_UNSTABLE for e in evals) and sum(up_win) >= 1:
                    score -= 25
            else:
                if p24 >= 30:
                    score -= 30
                    reasons.append(f"Rivières à traverser probablement grosses ({p24:.0f} mm en 24 h)")
                if max(up_win) >= RIVER_NOGO_RATE:
                    score -= 20

        if rain_win < 0.3:
            reasons.insert(0, "Sec")
        elif rain_win < 2:
            reasons.insert(0, f"Quelques gouttes ({rain_win:.1f} mm)".replace(".", ","))
        elif rain_win < 6:
            reasons.insert(0, f"Averses ({rain_win:.0f} mm)")
        else:
            reasons.insert(0, f"Pluie ({rain_win:.0f} mm)")
        n_cloud = sum(e[1]["in_cloud"] for e in evals)
        if spot["_high"]:
            reasons.append("Sommet dégagé" if n_cloud == 0 else f"Sommet dans le nuage {n_cloud} h sur {dur}")
        if any(_nz(e[1]["cape"]) >= CAPE_UNSTABLE for e in evals):
            reasons.append("Air instable : orages possibles")
        gmax = max(_nz(e[1]["gust"]) for e in evals)
        if gmax >= 50:
            reasons.append(f"Rafales jusqu'à {gmax:.0f} km/h")
        if spot["type"] == "littoral" and max(_nz(e[1]["t2m"]) for e in evals) >= HOT:
            reasons.append("Chaud : prévoir de l'eau")

        score = 0.0 if nogo else max(0.0, min(100.0, score))
        arome_share = sum(m.source[ti] == "AROME" for ti in tis) / dur
        cand = {
            "score": round(score),
            "nogo": nogo,
            "start": f"{start}h",
            "end": f"{start + dur}h",
            "reasons": reasons,
            "source": "AROME" if arome_share >= 0.9 else ("mixte" if arome_share > 0 else "ECMWF"),
            "hourly": [round(s) for s in scores],
        }
        if best is None or cand["score"] > best["score"]:
            best = cand
    if best is None:
        return {"score": None, "nogo": False, "reasons": ["Pas de données"], "source": "—"}
    best["label"] = label(best)
    return best


def label(r: dict) -> str:
    if r.get("nogo"):
        return "Non"
    s = r["score"]
    return "Top" if s >= 75 else "Bien" if s >= 55 else "Moyen" if s >= 35 else "À éviter"


def top3(results: list[tuple[dict, dict]]) -> list[tuple[dict, dict]]:
    """results = [(spot, eval)] d'un jour. Meilleurs scores, un seul par secteur."""
    ok = [(s, r) for s, r in results if r.get("score") is not None and not r["nogo"]]
    ok.sort(key=lambda sr: -(sr[1]["score"] + NIVEAU_BONUS.get(sr[0]["niveau"], 0)))
    picked, sectors = [], set()
    for s, r in ok:
        if s["secteur"] in sectors:
            continue
        picked.append((s, r))
        sectors.add(s["secteur"])
        if len(picked) == 3:
            break
    return picked
