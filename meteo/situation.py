"""Lecture de la situation météo du jour, comme un prévisionniste des Petites Antilles.

On regarde la colonne d'air EN AMONT de l'île (point en mer à l'est, dans l'alizé non perturbé) :
- force de l'alizé vers 500-1 500 m : alizé fort = soulèvement mécanique sur le relief, pluie concentrée
  côté au vent et sur les crêtes, côte sous-le-vent abritée ; alizé faible = convection thermique,
  matins souvent dégagés puis averses l'après-midi sur le relief, nuits fraîches avec brise descendante ;
- sommet de la couche humide (là où l'humidité chute) : en dessous, les cumulus d'alizé ;
  s'il est sous l'altitude d'un sommet, ce sommet peut sortir des nuages ;
- humidité vers 3 000 m (700 hPa) : air sec en altitude (subsidence, poussières sahariennes, intrusion
  sèche) = averses limitées ; air humide = averses plus étendues, onde tropicale possible.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone

import numpy as np

TZ = timezone(timedelta(hours=-4))
WIND_WEAK, WIND_STRONG = 18, 36  # km/h vers 1 000 m
MOIST_TOP_RH = 75                # % : l'air au-dessus de ce seuil est compté dans la couche humide
DRY_ALOFT, MOIST_ALOFT = 35, 70  # % d'humidité à 700 hPa


def _column(prof: dict, i: int):
    z = prof["z"][:, i]
    order = np.argsort(z)
    pick = lambda k: prof[k][:, i][order] if k in prof else np.full(len(z), np.nan)  # noqa: E731
    return z[order], pick("rh"), pick("t"), pick("u"), pick("v"), np.array(prof["p"])[order]


def analyse_hour(prof: dict, i: int) -> dict:
    z, rh, t, u, v, p = _column(prof, i)
    ws = np.hypot(u, v) * 3.6
    low = (z >= 400) & (z <= 1600)
    wind = float(np.nanmean(ws[low])) if low.any() and not np.all(np.isnan(ws[low])) else float("nan")
    # sommet de la couche humide : premier niveau au-dessus de 500 m où l'humidité passe sous le seuil
    top = float("nan")
    for k in range(len(z) - 1):
        if z[k] >= 500 and rh[k] >= MOIST_TOP_RH and rh[k + 1] < MOIST_TOP_RH:
            frac = (rh[k] - MOIST_TOP_RH) / max(rh[k] - rh[k + 1], 1e-6)
            top = float(z[k] + frac * (z[k + 1] - z[k]))
            break
    # inversion : couche où la température baisse de moins de 2 °C/km ou monte, au-dessus de 500 m
    inv = float("nan")
    for k in range(len(z) - 1):
        if 500 <= z[k] <= 3500 and z[k + 1] > z[k]:
            lapse = (t[k + 1] - t[k]) / (z[k + 1] - z[k])
            if lapse > -0.002:
                inv = float(z[k])
                break
    rh700 = float(rh[np.argmin(np.abs(p - 700))]) if len(p) else float("nan")
    return {"wind": wind, "moist_top": top, "inversion": inv, "rh700": rh700}


def _mean(vals):
    vals = [x for x in vals if x is not None and not math.isnan(x)]
    return float(np.mean(vals)) if vals else float("nan")


DUST_HAZE = 50   # µg/m³ de poussières désertiques près du sol : brume de sable visible


def day_situation(d: date, profiles: dict, i_up: int | None, merged, i_up_ec: int | None,
                  summit_alt: float = 1467, dust: dict | None = None) -> dict:
    """Synthèse de 6h à 16h. AROME si les profils couvrent la journée, sinon ECMWF (vent, humidité)."""
    hours = [datetime(d.year, d.month, d.day, h, tzinfo=TZ).astimezone(timezone.utc) for h in range(6, 17)]
    rows = [analyse_hour(profiles[t], i_up) for t in hours if t in profiles and i_up is not None]
    src = "AROME"
    if len(rows) < 4:
        src = "ECMWF"
        rows = []
        for t in hours:
            ti = merged.index.get(t)
            if ti is None or i_up_ec is None:
                continue
            g = lambda k: float(merged.data[k][ti, i_up_ec]) if k in merged.data else float("nan")  # noqa: E731
            rows.append({"wind": g("ws925"), "moist_top": float("nan"), "inversion": float("nan"), "rh700": g("rh700")})
    if not rows:
        return {"texte": [], "source": None}
    wind = _mean([r["wind"] for r in rows])
    top = _mean([r["moist_top"] for r in rows])
    inv = _mean([r["inversion"] for r in rows])
    rh700 = _mean([r["rh700"] for r in rows])

    r100 = lambda x: f"{round(x, -2):.0f}"  # noqa: E731 — niveaux espacés de 250-500 m : pas de fausse précision
    txt = []
    if not math.isnan(wind):
        if wind >= WIND_STRONG:
            txt.append(f"Alizé fort (~{wind:.0f} km/h vers 1 000 m) : l'air est forcé à monter sur le relief. "
                       "Averses répétées côté au vent et sur les crêtes, même le matin ; la côte sous-le-vent "
                       "est à l'abri (effet d'ombre pluviométrique). Rafales sur les crêtes.")
        elif wind <= WIND_WEAK:
            txt.append(f"Alizé faible (~{wind:.0f} km/h vers 1 000 m) : peu de forçage par le relief. "
                       "Matinée souvent la plus dégagée, puis nuages et averses de chaleur sur le massif "
                       "l'après-midi. Le versant sous-le-vent n'est pas forcément épargné.")
        else:
            txt.append(f"Alizé modéré (~{wind:.0f} km/h vers 1 000 m) : régime classique. Nuages accrochés "
                       "côté au vent et sur les sommets, éclaircies plus nettes côté sous-le-vent.")
    if not math.isnan(top):
        if top < summit_alt - 100:
            txt.append(f"Couche humide (cumulus d'alizé) jusqu'à ~{r100(top)} m seulement : les plus hauts sommets "
                       "peuvent dépasser la couche, surtout tôt le matin.")
        else:
            txt.append(f"Couche humide jusqu'à ~{r100(top)} m : au-dessus de la Soufrière, qui a donc de bonnes "
                       "chances d'être prise dans le nuage.")
    elif not math.isnan(inv):
        txt.append(f"Inversion vers ~{r100(inv)} m.")
    dmax = max((dust.get(t, 0) or 0 for t in hours), default=0) if dust else 0
    if not math.isnan(rh700):
        if rh700 <= DRY_ALOFT:
            txt.append(f"Air sec en altitude ({rh700:.0f} % vers 3 000 m) : averses courtes et peu étendues.")
        elif rh700 >= MOIST_ALOFT:
            txt.append(f"Air humide en altitude ({rh700:.0f} % vers 3 000 m) : averses plus étendues et durables "
                       "possibles (onde tropicale ou perturbation).")
    if dmax >= DUST_HAZE:
        txt.append(f"Brume de sable (poussières sahariennes ~{dmax:.0f} µg/m³) : ciel laiteux, vue lointaine voilée "
                   "même avec un sommet dégagé ; l'air sec qui l'accompagne limite souvent les averses.")
    return {"texte": txt, "source": src, "wind": wind, "moist_top": top, "inversion": inv, "rh700": rh700,
            "dust": dmax}


def islands_and_sea(d: date, merged, wind: float, i_sea_e: int | None, i_sea_n: int | None) -> list[str]:
    """Lignes « îles plates » et « mer », de 8h à 16h."""
    from .mer import dir_name
    hours = [datetime(d.year, d.month, d.day, h, tzinfo=TZ).astimezone(timezone.utc) for h in range(8, 17)]

    def mean(k, i):
        if i is None or k not in merged.data:
            return float("nan")
        vals = [merged.data[k][merged.index[t], i] for t in hours if t in merged.index]
        vals = [v for v in vals if not math.isnan(v)]
        return float(np.mean(vals)) if vals else float("nan")

    txt = []
    if not math.isnan(wind):
        if wind <= WIND_WEAK:
            txt.append("Grande-Terre, Marie-Galante, Désirade : soleil le matin, averses de chaleur possibles "
                       "l'après-midi sur l'intérieur (Grands Fonds). Forte chaleur sur les sentiers littoraux "
                       "exposés : partir tôt.")
        else:
            txt.append("Grande-Terre et îles plates : averses brèves apportées par l'alizé, vite passées ; "
                       "vent plus frais et mer plus formée côté Atlantique.")
    hs, sw, per, dr = (mean(k, i_sea_e) for k in ("hs", "sw", "per", "dir"))
    if not math.isnan(hs):
        calm = "mer calme" if hs < 1 else ("mer peu agitée" if hs < 1.5 else ("mer agitée" if hs < 2.5 else "mer forte"))
        f1 = lambda x: f"{x:.1f}".replace(".", ",")  # noqa: E731
        txt.append(f"Mer au large (Atlantique) : creux ~{f1(hs)} m ({calm}), houle de {dir_name(dr)} "
                   f"~{f1(sw)} m / {per:.0f} s. Côte sous-le-vent (Bouillante, Saintes) et lagons plus abrités.")
    swn, dn = mean("sw", i_sea_n), mean("dir", i_sea_n)
    if not math.isnan(swn) and swn >= 1.0 and not math.isnan(dn) and (dn >= 300 or dn <= 40):
        txt.append(f"Houle de nord (~{swn:.1f} m) : vagues à Port-Louis et sur la côte nord, prudence à la baignade."
                   .replace(f"{swn:.1f}", f"{swn:.1f}".replace(".", ",")))
    return txt
