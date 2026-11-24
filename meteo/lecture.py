"""Lecture des chiffres : chaque valeur avec ce qu'elle veut dire sur le terrain.

Échelles reconnues (mêmes seuils que ceux affichés dans la page « Apprendre à lire ») :
- pluie : intensités de l'American Meteorological Society (faible < 2,5 mm/h, modérée 2,5-7,6, forte > 7,6,
  violente > 50) ;
- vent : échelle de Beaufort (Organisation météorologique mondiale) ;
- mer : échelle de Douglas (état de la mer, OMM) ;
- instabilité : descripteurs CAPE du Storm Prediction Center (NOAA).
Les règles propres à l'outil (seuils de pénalité) sont signalées comme telles.
"""

from __future__ import annotations

import math

PLUIE = [(0.1, "sec"), (2.5, "pluie faible"), (7.6, "pluie modérée"), (50, "forte pluie"), (math.inf, "pluie violente")]
BEAUFORT = [(1, 0, "calme"), (6, 1, "très légère brise"), (12, 2, "légère brise"), (20, 3, "petite brise"),
            (29, 4, "jolie brise"), (39, 5, "bonne brise"), (50, 6, "vent frais"), (62, 7, "grand frais"),
            (75, 8, "coup de vent"), (89, 9, "fort coup de vent"), (103, 10, "tempête"),
            (118, 11, "violente tempête"), (math.inf, 12, "ouragan")]
DOUGLAS = [(0.05, 0, "calme"), (0.1, 1, "ridée"), (0.5, 2, "belle"), (1.25, 3, "peu agitée"), (2.5, 4, "agitée"),
           (4, 5, "forte"), (6, 6, "très forte"), (9, 7, "grosse"), (14, 8, "très grosse"), (math.inf, 9, "énorme")]
CAPE = [(1000, "instabilité marginale"), (2500, "instabilité modérée"), (4000, "très instable"),
        (math.inf, "extrêmement instable")]


def _f1(x):
    return f"{x:.1f}".replace(".", ",")


def pluie_h(mm):
    lab = next(l for lim, l in PLUIE if mm < lim)
    return lab


def beaufort(kmh):
    return next((f, l) for lim, f, l in BEAUFORT if kmh < lim)


def douglas(m):
    return next((f, l) for lim, f, l in DOUGLAS if m < lim)


def cape(j):
    return next(l for lim, l in CAPE if j < lim)


def lines(spot: dict, r: dict) -> list[str]:
    """Chiffres clés du créneau, chacun avec sa lecture."""
    m = r.get("mesures") or {}
    out = []
    if m.get("pluie_creneau") is not None:
        pm = m.get("pluie_max_h") or 0
        txt = f"Pluie : {_f1(m['pluie_creneau'])} mm sur le créneau, au plus {_f1(pm)} mm/h → {pluie_h(pm)} (AMS)"
        if m.get("proba_max"):
            txt += f" ; risque d'averse {m['proba_max']} % (part des scénarios ≥ 0,5 mm/h, non calibrée)"
        out.append(txt)
    if m.get("pluie_amont_24h") is not None:
        a = m["pluie_amont_24h"]
        lect = ("eau basse et claire probable" if a < 4 else "rivière un peu grossie, eau possiblement trouble"
                if a < 10 else "rivière grosse : prudence, gués difficiles" if a < 25 else
                "crue possible : ne pas s'engager")
        out.append(f"Pluie en amont sur 24 h : {_f1(a)} mm → {lect} (seuils de l'outil : 4 / 10 / 25 mm)")
    if m.get("rafales_max"):
        g = m["rafales_max"]
        f, l = beaufort(g)
        crete = " ; gênant sur les crêtes (seuil de l'outil 50 km/h)" if spot.get("_high") and g >= 50 else ""
        out.append(f"Rafales max : {g} km/h → force {f} Beaufort, {l}{crete}")
    if m.get("vent_moy") is not None and spot["type"] == "mer":
        w = m["vent_moy"]
        f, l = beaufort(w)
        kn = round(w / 1.852)
        usage = {"kite": "navigable en kite/wing" if 22 <= w <= 45 else ("trop faible pour le kite, possible en wing foil "
                 "léger" if w < 22 else "très fort : réservé aux confirmés"),
                 "calme": "agréable en kayak" if w < 15 else ("kayak fatigant face au vent" if w < 25 else "kayak déconseillé au large"),
                 "surf": "vent faible, vagues propres" if w < 15 else "vent qui hache les vagues" if w > 30 else "vent modéré"}
        out.append(f"Vent moyen : {w} km/h ({kn} nœuds) → force {f} Beaufort, {l} ; {usage.get(spot.get('mer'), '')}")
    if m.get("vagues") is not None:
        f, l = douglas(m["vagues"])
        out.append(f"Mer : creux {_f1(m['vagues'])} m → mer {l} (Douglas {f})")
    if m.get("houle") is not None and spot.get("mer") == "surf":
        per = m.get("periode") or 0
        qual = ("houle courte, vagues molles et désordonnées" if per < 8 else
                "houle moyenne" if per < 11 else "houle longue et puissante")
        out.append(f"Houle : {_f1(m['houle'])} m, période {per:.0f} s → {qual} (repère surf usuel)")
    if m.get("cape_max", 0) >= 300:
        out.append(f"Instabilité (CAPE) : {m['cape_max']} J/kg → {cape(m['cape_max'])} (SPC) ; "
                   "un orage n'est signalé que si une averse est aussi prévue")
    if m.get("temp_max") is not None and (spot["type"] == "littoral" or spot.get("expose")):
        t = m["temp_max"]
        out.append(f"Température max : {t} °C → " + ("chaleur marquée, partir tôt" if t >= 30 else "supportable"))
    return out


def scales() -> dict:
    """Les échelles, pour la carte (JavaScript) : mêmes seuils qu'ici."""
    inf = 1e9
    return {
        "pluie": [[lim if lim != math.inf else inf, l] for lim, l in PLUIE],
        "beaufort": [[lim if lim != math.inf else inf, f, l] for lim, f, l in BEAUFORT],
        "douglas": [[lim if lim != math.inf else inf, f, l] for lim, f, l in DOUGLAS],
        "cape": [[lim if lim != math.inf else inf, l] for lim, l in CAPE],
    }
