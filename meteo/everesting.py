"""Everesting à la Soufrière : quel jour il fera le moins mauvais pour 20 à 24 h d'allers-retours.

Parcours : Bains Jaunes → Pas du Roy → Savane à Mulets (ancien parking) → Chemin des Dames → sommet, et retour.
Fiche officielle : 510 m de dénivelé positif par aller-retour, donc 18 allers-retours pour 8 848 m.

Pour chaque fenêtre de 24 h (départ à chaque heure), sur les trois points du parcours :
- orage possible (CAPE ≥ 2 000 J/kg avec averse) : fenêtre écartée, le sommet est exposé ;
- pluie cumulée (70e percentile des scénarios) et heures de pluie modérée ou forte (≥ 2,5 mm/h, échelle AMS) ;
- rafales maximales au sommet, température minimale et vent au sommet ;
- heures du sommet dans le nuage (confort, pas sécurité) ;
- part des 51 scénarios ECMWF qui restent sous 5 mm sur la fenêtre (confiance).
L'étoile s'allume si une fenêtre passe tous les seuils ci-dessous (règles de l'outil, à caler après une tentative).
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import numpy as np

from . import scoring
from .heure import TZ

DPLUS_AR = 510             # m par aller-retour (fiche officielle La Soufrière, Parc national)
OBJECTIF = 8848
DUREE_H = 24
SEUILS = {"pluie": 5.0, "heures_moderees": 0, "rafales": 50, "scenarios": 70}  # mm, h, km/h, %
POINTS = [
    {"nom": "Bains Jaunes", "lat": 16.0272, "lon": -61.6614, "alt": 950},
    {"nom": "Savane à Mulets", "lat": 16.0383, "lon": -61.6627, "alt": 1142},
]
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def _fday(dt: datetime) -> str:
    loc = dt.astimezone(TZ)
    return f"{JOURS[loc.weekday()]} {loc.day} à {loc.hour}h"


def _window(m: scoring.Merged, t0: datetime, cols: list[int], i_top: int, ens: dict | None) -> dict | None:
    tis = [m.index.get(t0 + timedelta(hours=k)) for k in range(DUREE_H)]
    if any(t is None for t in tis):
        return None
    spot = {"type": "sommet", "_obj": cols, "_all": cols, "_obj_high": [i_top], "_high": True}
    evals = [scoring.hour_eval(spot, m, ti)[1] for ti in tis]
    rains = [e["rain"] for e in evals]
    g = m.data.get("gust")
    t2 = m.data.get("t2m")
    ws = m.data.get("ws10")
    col = lambda arr: [float(arr[ti, i_top]) for ti in tis if arr is not None and not math.isnan(arr[ti, i_top])]  # noqa: E731
    gusts, temps, winds = col(g), col(t2), col(ws)
    nuage = sum(1 for ti in tis if (m.summit_state.get((i_top, m.times[ti])) or (None,))[0] == "nuage")
    arome = sum(m.source[ti] == "AROME" for ti in tis) / DUREE_H
    frac = None
    if ens is not None:
        idx = {t: i for i, t in enumerate(ens["times"])}
        # cumul de la fenêtre : étiquettes t0+1 … t0+24 (pluie de l'heure écoulée)
        lab = [idx.get(t0 + timedelta(hours=k)) for k in range(1, DUREE_H + 1)]
        if all(x is not None for x in lab):
            arr = ens["precip_ens"][lab][:, cols]                     # (H, P, M)
            ok = ~np.isnan(arr).all(axis=(0, 1))
            if ok.sum() >= 10:
                tot = np.nanmean(np.nansum(arr[:, :, ok], axis=0), axis=0)   # (M,)
                frac = round(100 * float(np.mean(tot <= SEUILS["pluie"])))
    w = {
        "depart": t0.astimezone(TZ).isoformat(), "depart_txt": _fday(t0),
        "fin_txt": _fday(t0 + timedelta(hours=DUREE_H)),
        "pluie": round(sum(rains), 1),
        "heures_moderees": sum(r >= 2.5 for r in rains),
        "pluie_max_h": round(max(rains), 1),
        "orage": any(e["storm"] for e in evals),
        "rafales": round(max(gusts)) if gusts else None,
        "tmin": round(min(temps)) if temps else None,
        "vent_max": round(max(winds)) if winds else None,
        "nuage_h": nuage,
        "scenarios": frac,
        "source": "AROME" if arome >= 0.9 else ("AROME + ECMWF" if arome > 0 else "ECMWF"),
    }
    w["etoile"] = (not w["orage"] and w["pluie"] <= SEUILS["pluie"]
                   and w["heures_moderees"] <= SEUILS["heures_moderees"]
                   and (w["rafales"] is None or w["rafales"] < SEUILS["rafales"])
                   and (frac is None or frac >= SEUILS["scenarios"]))
    return w


def _rank(w: dict):
    """Le moins mauvais : pas d'orage, puis le moins de pluie, puis le moins d'heures modérées, puis les rafales."""
    return (w["orage"], w["pluie"], w["heures_moderees"], w["rafales"] or 0)


def compute(m: scoring.Merged, now: datetime, cols: list[int], i_top: int, ens: dict | None) -> dict:
    start = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    wins = []
    for k in range(0, 24 * 6):
        w = _window(m, start + timedelta(hours=k), cols, i_top, ens)
        if w:
            wins.append(w)
    if not wins:
        return {"fenetres": [], "jours": [], "etoile": None, "meilleure": None}
    days: dict[str, dict] = {}
    for w in wins:
        d = w["depart"][:10]
        if d not in days or _rank(w) < _rank(days[d]):
            days[d] = w
    jours = [days[d] for d in sorted(days)]
    stars = [w for w in wins if w["etoile"]]
    best = min(wins, key=_rank)
    return {
        "jours": jours,
        "etoile": min(stars, key=_rank) if stars else None,
        "meilleure": best,
        "seuils": SEUILS,
        "allers_retours": math.ceil(OBJECTIF / DPLUS_AR),
        "dplus_ar": DPLUS_AR,
    }
