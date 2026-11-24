"""L'avis du jour : les chiffres qui comptent, leur lecture, et la confiance qu'on peut avoir.

Confiance (pluie sur les activités de Basse-Terre, de 6h à 18h) :
- accord AROME / ECMWF : deux modèles différents qui disent la même chose ;
- accord entre le dernier run AROME et le précédent : une prévision qui ne bouge pas d'un run à l'autre ;
- dispersion de l'ensemble ECMWF (51 scénarios) : scénarios groupés = situation prévisible
  (guide de l'utilisateur ECMWF), scénarios partagés = incertitude réelle.
Les classes de pluie (1 / 5 / 15 mm sur la journée) et les seuils de confiance sont des règles de l'outil.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone

import numpy as np

from . import lecture, scoring
from .heure import TZ
from .sommets import sun_text

CLASSES = [(1, "sec"), (5, "quelques averses"), (15, "pluvieux"), (math.inf, "très pluvieux")]  # mm sur 6h-18h
ENS_WET = 5          # mm sur la journée : seuil « journée mouillée » pour compter les scénarios
SOUFRIERE = 1467


def _f1(x):
    return f"{x:.1f}".replace(".", ",")


def _cls(x: float) -> int:
    return next(i for i, (lim, _) in enumerate(CLASSES) if x < lim)


def _labels(d: date, h0: int, h1: int) -> list[datetime]:
    """Instants UTC des cumuls horaires qui couvrent h0 → h1 (heure locale) : étiquettes h0+1 … h1."""
    return [datetime(d.year, d.month, d.day, h, tzinfo=TZ).astimezone(timezone.utc) for h in range(h0 + 1, h1 + 1)]


def _total(src: dict | None, key: str, labels: list[datetime], cols: list[int]):
    """Cumul sur les étiquettes, moyenné sur les points. None si le modèle ne couvre pas toute la plage."""
    if not src or key not in src:
        return None
    idx = {t: i for i, t in enumerate(src["times"])}
    if any(t not in idx for t in labels):
        return None
    arr = src[key][[idx[t] for t in labels]][:, cols]          # (H, P) ou (H, P, M)
    if np.isnan(arr).all():
        return None
    tot = np.where(np.isnan(arr).all(axis=0), np.nan, np.nansum(arr, axis=0))   # (P,) ou (P, M)
    return np.nanmean(tot, axis=0)                                               # scalaire ou (M,)


def _agree(a: float, b: float) -> tuple[str, int]:
    gap = abs(_cls(a) - _cls(b))
    return ("d'accord" if gap == 0 else "proches" if gap == 1 else "en désaccord"), gap


def confidence(d: date, h0: int, cols: list[int], ar, ar_lag, ec, ens) -> dict:
    labels = _labels(d, h0, 18)
    lignes, niveau = [], 2   # 2 élevée, 1 moyenne, 0 faible
    a = _total(ar, "precip", labels, cols)
    e = _total(ec, "precip", labels, cols)
    if a is not None and e is not None:
        verdict, gap = _agree(a, e)
        niveau = min(niveau, 2 - gap)
        lignes.append({"t": f"AROME {_f1(a)} mm · ECMWF {_f1(e)} mm (moyenne des activités de Basse-Terre, "
                            f"{h0}h-18h) → modèles {verdict}", "aide": "confiance"})
    p = _total(ar_lag, "precip", labels, cols)
    if a is not None and p is not None:
        verdict, gap = _agree(a, p)
        niveau = min(niveau, 2 - gap)
        lignes.append({"t": f"Dernier run AROME {_f1(a)} mm · run précédent {_f1(p)} mm → "
                            + ("prévision stable" if gap == 0 else "prévision qui bouge un peu" if gap == 1
                               else "prévision qui change d'un run à l'autre"), "aide": "confiance"})
    m = _total(ens, "precip_ens", labels, cols)
    if m is not None and np.ndim(m) == 1 and np.sum(~np.isnan(m)) >= 10:
        m = m[~np.isnan(m)]
        q10, q50, q90 = np.percentile(m, [10, 50, 90])
        frac = float(np.mean(m >= ENS_WET))
        if frac <= 0.1 or frac >= 0.9:
            lect = "scénarios groupés : situation prévisible"
        elif 0.3 <= frac <= 0.7:
            lect, niveau = "scénarios partagés : vraie incertitude", min(niveau, 0)
        else:
            lect, niveau = "scénarios plutôt groupés", min(niveau, 1)
        lignes.append({"t": f"Ensemble ECMWF ({len(m)} scénarios, maille ~25 km) : {round(100 * frac)} % donnent "
                            f"≥ {ENS_WET} mm ; fourchette 10-90 % : {_f1(q10)} à {_f1(q90)} mm (médiane {_f1(q50)}) "
                            f"→ {lect}", "aide": "confiance"})
    if not lignes:
        return {"niveau": None, "texte": "non évaluée (pas assez de modèles sur ce créneau)", "lignes": []}
    if a is None:
        lignes.append({"t": "Au-delà d'AROME, aucun modèle ne voit les vallées : la confiance porte sur la tendance "
                            "de la journée, pas sur le détail par sentier.", "aide": "modeles"})
    noms = {2: "élevée", 1: "moyenne", 0: "faible"}
    return {"niveau": noms[niveau], "texte": noms[niveau], "lignes": lignes}


def _rain_bt(m: scoring.Merged, d: date, h0: int, spots: list[dict]):
    """Pluie retenue (70e percentile des scénarios) cumulée de h0 à 18h, par activité de Basse-Terre."""
    tots = []
    for s in spots:
        tot, hmax = 0.0, 0.0
        for h in range(h0, 18):
            t = datetime(d.year, d.month, d.day, h, tzinfo=TZ).astimezone(timezone.utc)
            ti = m.index.get(t)
            if ti is None:
                continue
            r, _ = scoring.rain_stats(m, scoring.rain_index(m, ti), s["_obj"], scoring.RAIN_PCTL)
            tot += r
            hmax = max(hmax, r)
        tots.append((tot, hmax, s["nom"]))
    return tots


def _mean_at(m: scoring.Merged, key: str, i: int | None, d: date, h0=8, h1=16) -> float:
    if i is None or key not in m.data:
        return float("nan")
    vals = []
    for h in range(h0, h1 + 1):
        ti = m.index.get(datetime(d.year, d.month, d.day, h, tzinfo=TZ).astimezone(timezone.utc))
        if ti is not None and not math.isnan(m.data[key][ti, i]):
            vals.append(m.data[key][ti, i])
    return float(np.mean(vals)) if vals else float("nan")


def day_avis(d: date, now: datetime, m: scoring.Merged, spots: list[dict], top, sit: dict, sommets_day: list,
             raw: dict, idx_h: dict) -> dict:
    h0 = 6   # journée entière, même les heures passées (demande de Tomas : voir les données quand même)
    bt = [s for s in spots if s.get("ile") == "Basse-Terre" and s["type"] != "mer"]
    cols = sorted({i for s in bt for i in s["_obj"]})
    ch = []

    w = sit.get("wind", float("nan"))
    if w is not None and not math.isnan(w):
        f, l = lecture.beaufort(w)
        lect = ("faible : peu de pluie de relief, nuages de chaleur en journée (seuil 5 m/s, DOMEX)" if w <= 18 else
                "fort : averses répétées côté au vent et sur les crêtes, abri côté sous-le-vent (seuil de l'outil)"
                if w >= 36 else "modéré : nuages accrochés côté au vent et sur les sommets, régime classique")
        ch.append({"label": "Alizé vers 1 000 m", "valeur": f"{w:.0f} km/h (force {f})", "lecture": lect, "aide": "alize"})

    base, lo, hi = sit.get("base"), sit.get("top_lo"), sit.get("top_hi")
    top_ = sit.get("moist_top")
    ok = lambda x: x is not None and not math.isnan(x)  # noqa: E731
    if ok(top_) or ok(base):
        r100 = lambda x: f"{round(x, -2):.0f}"  # noqa: E731
        if ok(top_) and math.isinf(top_):
            val, lect = "pas de plafond net", "air humide sur toute l'épaisseur : sommets au vent dans le nuage"
        else:
            haut = (f"{r100(lo)}-{r100(hi)} m" if ok(lo) and ok(hi) and hi - lo >= 300 else
                    f"~{r100(top_)} m" if ok(top_) else "non déterminé (pas de profil AROME ce jour)")
            val = (f"base ~{r100(base)} m · " if ok(base) else "") + f"haut {haut}"
            if not ok(top_):
                lect = "sans le haut de la couche, l’état des sommets reste une tendance"
            elif top_ < SOUFRIERE - 100:
                lect = f"la Soufrière ({SOUFRIERE} m) dépasse la couche : au-dessus des nuages possible"
            elif top_ <= SOUFRIERE + 100:
                lect = f"haut de la couche à hauteur de la Soufrière : sommet à la limite"
            else:
                lect = f"couche plus haute que la Soufrière : sommets au vent surtout dans le nuage"
        ch.append({"label": "Couche nuageuse d'alizé", "valeur": val, "lecture": lect, "aide": "couche"})

    if h0 < 18 and bt:
        tots = _rain_bt(m, d, h0, bt)
        if tots:
            vals = sorted(t for t, _, _ in tots)
            med = float(np.median(vals))
            wettest = max(tots)
            hmax = max(h for _, h, _ in tots)
            ch.append({"label": f"Pluie sur les activités de Basse-Terre ({h0}h-18h)",
                       "valeur": f"médiane {_f1(med)} mm · max {_f1(wettest[0])} mm ({wettest[2]})",
                       "lecture": f"intensité la plus forte {_f1(hmax)} mm/h → {lecture.pluie_h(hmax)} (AMS)",
                       "aide": "pluie"})
        cape = [m.data["cape"][ti, cols] for h in range(h0, 18)
                for ti in [m.index.get(datetime(d.year, d.month, d.day, h, tzinfo=TZ).astimezone(timezone.utc))]
                if ti is not None and "cape" in m.data]
        cmax = float(np.nanmax(cape)) if cape and not np.all(np.isnan(cape)) else float("nan")
        if ok(cmax) and cmax >= 1000:
            ch.append({"label": "Instabilité (CAPE max)", "valeur": f"{cmax:.0f} J/kg",
                       "lecture": f"{lecture.cape(cmax)} (SPC) : orages possibles si des averses se forment",
                       "aide": "cape"})

    i_e = idx_h.get("mer_est")
    hs, per, dr = (_mean_at(m, k, i_e, d) for k in ("hs", "per", "dir"))
    if ok(hs):
        f, l = lecture.douglas(hs)
        from .mer import dir_name
        val = f"creux {_f1(hs)} m" + (f" · houle {per:.0f} s de {dir_name(dr)}" if ok(per) else "")
        ch.append({"label": "Mer au large (Atlantique, 8h-16h)", "valeur": val,
                   "lecture": f"mer {l} (Douglas {f})" + (f" ; {lecture.periode(per)}" if ok(per) else "")
                   + " ; côte sous-le-vent et lagons plus abrités", "aide": "mer"})

    dust = sit.get("dust") or 0
    if dust >= 50:
        ch.append({"label": "Poussières sahariennes", "valeur": f"~{dust:.0f} µg/m³",
                   "lecture": "brume de sable : vue lointaine voilée même au-dessus des nuages (seuil de l'outil 50)",
                   "aide": "poussieres"})

    # À retenir : le meilleur de la journée et les sommets au lever / coucher
    retenir = [f"{s['nom']} {r['score']}/100" + (f", {r['start']}-{r['end']}" if r.get("start") else "")
               + (" (passé)" if r.get("passe") else "") for s, r in top]
    soleil = []
    for key, nom in (("lever", "lever"), ("coucher", "coucher")):
        clear = [x for x in sommets_day if x[key]["top"]]
        if clear:
            deps = [f"{x['nom']} : départ vers {x[key]['fenetre']['depart']}" for x in clear
                    if (x[key].get("fenetre") or {}).get("depart")]
            soleil.append(sun_text(nom, clear, key) + (" (" + ", ".join(deps) + ")" if deps else ""))
    # le tableau donne déjà la mer et les poussières : on ne les répète pas dans la lecture
    lect = [t for t in sit.get("texte", []) if not t.startswith(("Mer au large", "Brume de sable"))]
    return {"chiffres": ch, "lecture": lect, "source": sit.get("source"),
            "retenir": retenir, "soleil": soleil,
            "confiance": confidence(d, h0, cols, raw.get("ar"), raw.get("ar_lag"), raw.get("ec"), raw.get("ens"))}
