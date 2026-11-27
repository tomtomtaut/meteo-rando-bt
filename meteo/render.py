"""Petites fonctions partagées : dates en français, couverture des modèles, catégories, pépites (données)."""

from __future__ import annotations

from datetime import date, datetime, timezone

from .heure import TZ as TZL
from .sommets import sun_text

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
SOURCE_NAMES = {"AROME": "AROME 2,5 km", "ECMWF-ens": "ensemble ECMWF (probabilités, maille ~25 km)",
                "ECMWF": "ECMWF seul (maille ~9-25 km)", "—": "pas de donnée"}
CAT_NAMES = {"rando": "Randos", "riviere": "Rivières", "sommet": "Sommets",
             "mer": "Mer calme", "surf": "Surf", "kite": "Kite / wing"}


def coverage(merged, d: date) -> str:
    """Quel modèle couvre quelles heures de la journée (5h-20h)."""
    segs = []
    for h in range(5, 21):
        t = datetime(d.year, d.month, d.day, h, tzinfo=TZL).astimezone(timezone.utc)
        ti = merged.index.get(t)
        src = merged.source[ti] if ti is not None else "—"
        if segs and segs[-1][0] == src:
            segs[-1][2] = h
        else:
            segs.append([src, h, h])
    parts = [f"{SOURCE_NAMES.get(src, src)} de {a}h à {b + 1}h" for src, a, b in segs]
    return " · ".join(parts)


def fdate(d: date) -> str:
    return f"{JOURS[d.weekday()]} {d.day} {MOIS[d.month - 1]}"


def cat_of(spot: dict) -> str:
    if spot["type"] == "mer":
        return {"calme": "mer", "surf": "surf", "kite": "kite"}.get(spot.get("mer"), "mer")
    return "riviere" if spot["type"] == "riviere" else ("sommet" if spot.get("_high") else "rando")


def pepites_list(report: dict) -> list[dict]:
    """Pépites en données (pour la carte) : [{jour, texte, fiable}]."""
    out = []
    for d in report["days"]:
        day = d["title"].split(" · ")[1]
        for kind, key in (("Lever", "lever"), ("Coucher", "coucher")):
            names = [x for x in d.get("sommets", []) if x[key]["top"]]
            if names:
                out.append({"jour": day, "texte": sun_text(kind.lower(), names, key),
                            "fiable": any(x[key].get("src") == "AROME" for x in names),
                            "confiance": ((d.get("avis") or {}).get("confiance") or {}).get("niveau"),
                            "details": [{"nom": x["nom"], "alt": x["alt"], **(x[key].get("fenetre") or {})}
                                        for x in names]})
    return out
