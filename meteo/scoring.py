"""Fusion AROME + ECMWF et calcul d'un score par activité, par jour et par créneau de départ.

Tous les seuils sont regroupés en haut du fichier pour être ajustés après quelques sorties.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

import numpy as np

from .heure import TZ  # noqa: E402

# --- Seuils (à calibrer) --------------------------------------------------------------------
RAIN_PENALTY = [(0.1, 0), (0.5, 15), (1.0, 30), (2.5, 50), (5.0, 70), (math.inf, 90)]  # mm/h → pénalité
CLOUD_FULL = 85          # % de nuages bas au-dessus duquel le sommet est « dans le nuage »
CLOUD_PARTIAL = 60
RH_FOG = 97              # % d'humidité à 2 m = brouillard
GUST_SUMMIT = [(50, 0), (65, 15), (math.inf, 35)]  # km/h
GUST_OTHER = [(70, 0), (math.inf, 20)]
CAPE_UNSTABLE = 2000     # J/kg. Sous les tropiques 1 000-1 500 est courant sans orage : on ne signale
                         # l'instabilité que si elle est forte ET qu'une averse est prévue autour.
RAIN_WET = 0.5           # mm/h : seuil d'« averse » pour les probabilités
RAIN_PCTL = 70           # percentile des scénarios (voisinage x runs) retenu pour la pluie au point
RIVER_PCTL = 90          # plus prudent pour les crues : 90e percentile en amont
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


def merge(arome: dict | None, ecmwf: dict | None, n_points: int,
          arome_lag: dict | None = None, ens: dict | None = None) -> Merged:
    """Base horaire ECMWF, remplacée par AROME là où AROME a des valeurs.

    Pluie en scénarios (« precip_ens », (T, P, M)) :
    - heures AROME : les 9 mailles autour du point, pour le dernier run ET le run précédent
      (méthode de voisinage + ensemble décalé : une averse prévue à 2 km près compte) ;
    - heures ECMWF : les 51 scénarios de l'ensemble ECMWF si disponibles, sinon la valeur unique."""
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
    for var in ("precip", "lcc", "mcc", "rh", "rh850", "rh700", "ws925", "ws10", "gust", "t2m", "cape", "sp"):
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

    m_ar = 9 * (2 if arome_lag else 1)
    m_ens = ens["precip_ens"].shape[2] if ens else 1
    pe = np.full((T, n_points, max(m_ar, m_ens)), np.nan)
    if ecmwf and "precip" in ecmwf:
        for i, t in enumerate(ecmwf["times"]):
            pe[idx[t], :, 0] = ecmwf["precip"][i]
    if ens:
        for i, t in enumerate(ens["times"]):
            if t in idx and source[idx[t]] != "AROME" and not np.all(np.isnan(ens["precip_ens"][i])):
                pe[idx[t], :, :m_ens] = ens["precip_ens"][i]
                source[idx[t]] = "ECMWF-ens"
    if arome and "precip_nb" in arome:
        lag = {t: i for i, t in enumerate(arome_lag["times"])} if arome_lag and "precip_nb" in arome_lag else {}
        for i, t in enumerate(arome["times"]):
            if source[idx[t]] != "AROME":
                continue
            row = np.full((n_points, pe.shape[2]), np.nan)
            row[:, :9] = arome["precip_nb"][i]
            if t in lag:
                row[:, 9:18] = arome_lag["precip_nb"][lag[t]]
            pe[idx[t]] = row
    data["precip_ens"] = pe
    return Merged(times, data, source)


def _max(m: Merged, var: str, ti: int, cols: list[int]) -> float:
    if var not in m.data:
        return float("nan")
    v = m.data[var][ti, cols]
    return float(np.nanmax(v)) if not np.all(np.isnan(v)) else float("nan")


def _nz(x: float) -> float:
    return 0.0 if math.isnan(x) else x


def rain_stats(m: Merged, ti: int, cols: list[int], pctl: float) -> tuple[float, float | None]:
    """(pluie retenue en mm/h, probabilité d'averse) : max sur les points, à partir des scénarios."""
    ens = m.data.get("precip_ens")
    if ens is None:
        return _nz(_max(m, "precip", ti, cols)), None
    rains, probs = [], []
    for c in cols:
        v = ens[ti, c]
        v = v[~np.isnan(v)]
        if len(v) >= 2:
            rains.append(float(np.percentile(v, pctl)))
            probs.append(float(np.mean(v >= RAIN_WET)))
        elif len(v) == 1:
            rains.append(float(v[0]))
    if not rains:
        return _nz(_max(m, "precip", ti, cols)), None
    return max(rains), (max(probs) if probs else None)


def rain_index(m: Merged, ti: int) -> int:
    """La pluie « de h à h+1 » est le cumul étiqueté h+1 (cumul sur l'heure écoulée, AROME comme Open-Meteo)."""
    return ti + 1 if ti + 1 < len(m.times) else ti


PEN_LABELS = {
    "p": "pluie", "o": "orage possible", "n": "nuage sur le parcours", "r": "rafales", "c": "chaleur",
    "v": "vent", "m": "état de la mer", "h": "taille de la houle", "t": "période de la houle",
    "d": "orientation de la houle", "k": "rafales irrégulières", "a": "pluie en amont (24 h)",
}


def hour_eval(spot: dict, m: Merged, ti: int) -> tuple[float | None, dict]:
    """Conditions pour l'heure qui commence à m.times[ti].

    Renvoie (score, infos) ; infos["pens"] détaille chaque pénalité (clé courte -> points retirés)."""
    obj = spot["_obj"]
    rain, prob = rain_stats(m, rain_index(m, ti), obj, RAIN_PCTL)
    gust, cape = _max(m, "gust", ti, obj), _max(m, "cape", ti, obj)
    storm = _nz(cape) >= CAPE_UNSTABLE and (rain >= RAIN_WET or (prob or 0) >= 0.3)
    if spot["type"] == "mer":
        from . import mer
        score, sea = mer.hour_eval(spot, m, ti, rain, prob, storm, gust)
        return score, {"rain": rain, "prob": prob, "in_cloud": False, "gust": gust, "storm": storm,
                       "cape": cape, "t2m": float("nan"), **sea}
    lcc, rh = _max(m, "lcc", ti, obj), _max(m, "rh", ti, obj)
    t2m = _max(m, "t2m", ti, obj)
    pens = {}
    if (p := _lookup(RAIN_PENALTY, rain)):
        pens["p"] = p
    in_cloud = False
    if spot["_high"]:
        sts = [m.summit_state.get((i, m.times[ti])) for i in spot.get("_obj_high", [])]
        sts = [x[0] for x in sts if x and x[0]]
        if sts:  # état déduit de la couche nuageuse et du profil vertical, à l'altitude réelle
            in_cloud = "nuage" in sts
            n = 25 if in_cloud else (10 if "incertain" in sts else 0)
        else:    # repli : champs de surface
            in_cloud = _nz(lcc) >= CLOUD_FULL or _nz(rh) >= RH_FOG
            n = 25 if in_cloud else (10 if _nz(lcc) >= CLOUD_PARTIAL else 0)
        if n:
            pens["n"] = n
        if (g := _lookup(GUST_SUMMIT, _nz(gust))):
            pens["r"] = g
    elif (g := _lookup(GUST_OTHER, _nz(gust))):
        pens["r"] = g
    if storm:
        pens["o"] = 15
    if spot["type"] == "littoral" or spot.get("expose"):
        c = 20 if _nz(t2m) >= HOT + 1 else (10 if _nz(t2m) >= HOT - 1 else 0)
        if c:
            pens["c"] = c
    score = max(0.0, 100.0 - sum(pens.values()))
    ws = _max(m, "ws10", ti, obj)
    return score, {"rain": rain, "prob": prob, "in_cloud": in_cloud, "gust": gust, "storm": storm,
                   "cape": cape, "t2m": t2m, "lcc": lcc, "ws": ws, "pens": pens}


def _river_rain(spot: dict, m: Merged, ti: int) -> float:
    return rain_stats(m, ti, spot["_all"], RIVER_PCTL)[0]


def evaluate_day(spot: dict, m: Merged, day: date, not_before: datetime | None = None) -> dict:
    dur = max(2, min(9, math.ceil(spot["duree_h"])))
    best = None
    for start in range(FIRST_START, LAST_END - dur + 1):
        t0 = datetime(day.year, day.month, day.day, start, tzinfo=TZ).astimezone(timezone.utc)
        if not_before is not None and t0 < not_before:
            continue
        tis = [m.index.get(t0 + timedelta(hours=k)) for k in range(dur)]
        if any(t is None for t in tis):
            continue
        evals = [hour_eval(spot, m, ti) for ti in tis]
        if any(e[0] is None for e in evals):
            continue
        scores = [e[0] for e in evals]
        mean_s, min_s = float(np.mean(scores)), min(scores)
        score = 0.6 * mean_s + 0.4 * min_s
        base_score = score
        nogo, reasons, ajust = False, [], []
        p24 = up_sum = up_win = None

        rain_win = sum(e[1]["rain"] for e in evals)
        if spot["type"] == "riviere" or spot.get("riviere_partielle"):
            before = [m.index.get(t0 - timedelta(hours=k)) for k in range(0, 24)]  # cumuls de t0-24h à t0
            p24 = sum(_river_rain(spot, m, ti) for ti in before if ti is not None)
            up_win = [_river_rain(spot, m, rain_index(m, ti)) for ti in tis]
            up_sum = sum(up_win)
            if spot["type"] == "riviere":
                if p24 >= RIVER_NOGO_24H:
                    nogo = True
                    reasons.append(f"Trop de pluie en amont : {p24:.0f} mm sur 24 h")
                    ajust.append((f"pluie en amont ≥ {RIVER_NOGO_24H} mm sur 24 h : sortie déconseillée", None))
                elif max(up_win) >= RIVER_NOGO_RATE or sum(up_win) >= RIVER_NOGO_WINDOW:
                    nogo = True
                    reasons.append(f"Pluie en amont pendant la sortie ({sum(up_win):.0f} mm) : risque de montée des eaux")
                    ajust.append(("pluie en amont pendant la sortie : risque de montée des eaux", None))
                else:
                    if p24 >= RIVER_BAD_24H:
                        score -= 35
                        ajust.append((f"amont {p24:.1f} mm sur 24 h (≥ {RIVER_BAD_24H})".replace(".", ","), -35))
                    elif p24 >= RIVER_MEH_24H:
                        score -= 15
                        ajust.append((f"amont {p24:.1f} mm sur 24 h (≥ {RIVER_MEH_24H})".replace(".", ","), -15))
                    reasons.append(f"Amont : {p24:.0f} mm sur les 24 h avant")
                if any(e[1]["storm"] for e in evals):
                    score -= 25
                    ajust.append(("orage possible en rivière", -25))
            else:
                if p24 >= 30:
                    score -= 30
                    ajust.append((f"rivières à traverser : {p24:.0f} mm en amont sur 24 h", -30))
                    reasons.append(f"Rivières à traverser probablement grosses ({p24:.0f} mm en 24 h)")
                if max(up_win) >= RIVER_NOGO_RATE:
                    score -= 20
                    ajust.append(("averse forte en amont pendant la sortie", -20))

        span = f"de {start}h à {start + dur}h"
        if rain_win < 0.3:
            reasons.insert(0, "Sec")
        elif rain_win < 2:
            reasons.insert(0, f"{rain_win:.1f} mm en tout {span} (petites averses)".replace(".", ","))
        elif rain_win < 6:
            reasons.insert(0, f"{rain_win:.0f} mm en tout {span} (averses)")
        else:
            reasons.insert(0, f"{rain_win:.0f} mm en tout {span} (pluie)")
        if spot.get("_high"):
            reasons += cloud_reasons(spot, m, tis, dur)
        probs = [e[1]["prob"] for e in evals if e[1]["prob"] is not None]
        if probs and max(probs) >= 0.15 and rain_win < 6:
            reasons.append(f"risque d'averse ~{round(max(probs) * 10) * 10} %")
        if any(e[1]["storm"] for e in evals):
            reasons.append("Air très instable : orage possible")
        gmax = max(_nz(e[1]["gust"]) for e in evals)
        if gmax >= 50:
            reasons.append(f"Rafales jusqu'à {gmax:.0f} km/h")
        if (spot["type"] == "littoral" or spot.get("expose")) and max(_nz(e[1]["t2m"]) for e in evals) >= HOT - 1:
            reasons.append(f"Chaud ({max(_nz(e[1]['t2m']) for e in evals):.0f} °C) : partir tôt, beaucoup d'eau")
        if spot["type"] == "mer":
            from . import mer
            reasons += mer.reasons(spot, [e[1] for e in evals])

        score = 0.0 if nogo else max(0.0, min(100.0, score))
        k_worst = int(np.argmin(scores))
        pens_mean = {}
        for e in evals:
            for k, v in (e[1].get("pens") or {}).items():
                pens_mean[k] = pens_mean.get(k, 0) + v / dur
        def brut(k, e, ti):
            """Données de l'heure, adaptées au type d'activité (arrondies)."""
            r_ = lambda x, n=0: None if x is None or (isinstance(x, float) and math.isnan(x)) else round(x, n)  # noqa: E731
            out = {"pluie": r_(e["rain"], 1), "proba": None if e.get("prob") is None else round(100 * e["prob"]),
                   "rafales": r_(e.get("gust")), "vent": r_(e.get("ws")), "src": m.source[ti]}
            if spot["type"] == "mer":
                out.update({"creux": r_(e.get("hs"), 1), "houle": r_(e.get("sw"), 1), "periode": r_(e.get("per")),
                            "dir": r_(e.get("dir"))})
            else:
                out.update({"t2m": r_(e.get("t2m")), "nuages_bas": r_(e.get("lcc")), "cape": r_(e.get("cape")),
                            "orage": bool(e.get("storm"))})
                if spot.get("_high"):
                    names = spot.get("_names", {})
                    out["points_hauts"] = [{"nom": names.get(i, "sommet"),
                                            "etat": (m.summit_state.get((i, m.times[ti])) or (None,))[0]}
                                           for i in spot.get("_obj_high", [])]
                if up_win is not None:
                    out["amont"] = r_(up_win[k], 1)
            return out

        detail = {
            "heures": [{"h": start + k, "score": round(sc), "pens": e[1].get("pens", {}), "brut": brut(k, e[1], ti)}
                       for k, (sc, e, ti) in enumerate(zip(scores, evals, tis))],
            "moyenne": round(mean_s), "pire_h": start + k_worst, "pire": round(min_s),
            "pens_moy": {PEN_LABELS[k]: round(v, 1) for k, v in sorted(pens_mean.items(), key=lambda x: -x[1])},
            "pens_pire": {PEN_LABELS[k]: v for k, v in (evals[k_worst][1].get("pens") or {}).items()},
            "creneau": round(base_score),
            "ajustements": [{"raison": r, "points": v} for r, v in ajust],
            "final": round(score),
        }
        e1 = [e[1] for e in evals]
        mx = lambda k: max((_nz(x.get(k, float("nan"))) for x in e1), default=0.0)  # noqa: E731
        mean = lambda k: float(np.nanmean([x.get(k, float("nan")) for x in e1])) if any(  # noqa: E731
            not math.isnan(x.get(k, float("nan"))) for x in e1) else float("nan")
        probs_all = [x["prob"] for x in e1 if x.get("prob") is not None]
        mesures = {
            "pluie_creneau": round(rain_win, 1), "pluie_max_h": round(mx("rain"), 1),
            "proba_max": None if not probs_all else round(max(probs_all) * 100),
            "rafales_max": round(mx("gust")), "vent_moy": None if math.isnan(mean("ws")) else round(mean("ws")),
            "temp_max": None if math.isnan(mean("t2m")) else round(mx("t2m")),
            "cape_max": round(mx("cape")),
            "pluie_amont_24h": None if p24 is None else round(p24, 1),
            "pluie_amont_sortie": None if up_sum is None else round(up_sum, 1),
        }
        if spot["type"] == "mer":
            for k, nk in (("hs", "vagues"), ("sw", "houle"), ("per", "periode"), ("dir", "dir_houle")):
                v = mean(k)
                mesures[nk] = None if math.isnan(v) else round(v, 1)
        arome_share = sum(m.source[ti] == "AROME" for ti in tis) / dur
        ens_share = sum(m.source[ti] == "ECMWF-ens" for ti in tis) / dur
        cand = {
            "score": round(score),
            "nogo": nogo,
            "start": f"{start}h",
            "end": f"{start + dur}h",
            "reasons": reasons,
            "source": "AROME" if arome_share >= 0.9 else ("mixte" if arome_share > 0 else
                                                          ("ECMWF-ens" if ens_share >= 0.5 else "ECMWF")),
            "hourly": [round(s) for s in scores],
            "detail": detail,
            "mesures": mesures,
        }
        if best is None or cand["score"] > best["score"]:
            best = cand
    if best is None:
        return {"score": None, "nogo": False, "reasons": ["Pas de données"], "source": "—"}
    best["label"] = label(best)
    return best


def cloud_reasons(spot: dict, m: Merged, tis: list[int], dur: int) -> list[str]:
    """Nuage point par point (sommet, col…), avec le nom du point."""
    names = spot.get("_names", {})
    out = []
    for i in spot.get("_obj_high", []):
        sts = [(m.summit_state.get((i, m.times[ti])) or (None,))[0] for ti in tis]
        known = [x for x in sts if x]
        if not known:
            continue
        n_in = sum(x == "nuage" for x in known)
        n_clear = sum(x in ("degage", "mer") for x in known)
        nom = names.get(i, "sommet")
        if n_in:
            out.append(f"{nom} dans le nuage {n_in} h sur {dur}")
        elif n_clear == len(known):
            n_mer = sum(x == "mer" for x in known)
            out.append(f"{nom} au-dessus des nuages" if n_mer == len(known) else
                       f"{nom} dégagé" if n_mer == 0 else f"{nom} dégagé ou au-dessus des nuages")
        else:
            out.append(f"{nom} : nuages partiels ({len(known) - n_clear} h incertaines)")
    return out


def label(r: dict) -> str:
    if r.get("nogo"):
        return "Non"
    s = r["score"]
    return "Top" if s >= 75 else "Bien" if s >= 55 else "Moyen" if s >= 35 else "À éviter"


def _cat(spot: dict) -> str:
    if spot["type"] == "mer":
        return spot.get("mer", "calme")
    return "riviere" if spot["type"] == "riviere" else ("sommet" if spot.get("_high") else "rando")


def top3(results: list[tuple[dict, dict]]) -> list[tuple[dict, dict]]:
    """results = [(spot, eval)] d'un jour. Meilleurs scores, varié : un seul par secteur et par type d'activité."""
    ok = [(s, r) for s, r in results if r.get("score") is not None and not r["nogo"]]
    ok.sort(key=lambda sr: -(sr[1]["score"] + NIVEAU_BONUS.get(sr[0]["niveau"], 0)))
    picked, sectors, cats = [], set(), set()
    for s, r in ok:
        if s["secteur"] in sectors or _cat(s) in cats:
            continue
        picked.append((s, r))
        sectors.add(s["secteur"])
        cats.add(_cat(s))
        if len(picked) == 3:
            break
    return picked


def add_series(m: Merged, series: dict, keys) -> None:
    """Ajoute des séries horaires (T', P) d'une autre source, alignées sur l'axe de temps de m."""
    idx = {t: i for i, t in enumerate(series["times"])}
    for k in keys:
        if k not in series:
            continue
        arr = np.full((len(m.times), series[k].shape[1]), np.nan)
        for i, t in enumerate(m.times):
            if t in idx:
                arr[i] = series[k][idx[t]]
        m.data[k] = arr
