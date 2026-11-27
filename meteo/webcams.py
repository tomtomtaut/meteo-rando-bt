"""Webcams de la Guadeloupe, de ses îles et de la Dominique.

Avec une clé gratuite de l'API Windy Webcams (secret GitHub WINDY_WEBCAMS_KEY), on liste
automatiquement toutes les webcams de la zone. Sans clé, on garde celles de spots.json.
"""

from __future__ import annotations

import logging
import os

import requests

log = logging.getLogger(__name__)

API = "https://api.windy.com/webcams/api/v3/webcams"
SEARCHES = [((16.15, -61.40), 70),   # Guadeloupe et ses îles
            ((15.42, -61.35), 40)]   # Dominique
BBOX = (15.15, 16.60, -61.90, -60.90)  # Guadeloupe, ses îles et la Dominique


def player(wid: str) -> str:
    return f"https://webcams.windy.com/webcams/public/embed/player/{wid}/day"


def fetch(configured: list[dict]) -> list[dict]:
    """Webcams à afficher : celles de spots.json d'abord, puis celles trouvées par l'API."""
    cams = [{**c, "id": str(c["id"]), "player": player(c["id"]),
             "lien": f"https://www.windy.com/webcams/{c['id']}"} for c in configured]
    key = os.environ.get("WINDY_WEBCAMS_KEY")
    if not key:
        return cams
    found = []
    for (la, lo), rad in SEARCHES:
        try:
            r = requests.get(API, headers={"x-windy-api-key": key}, timeout=30, params={
                "nearby": f"{la},{lo},{rad}", "limit": 50, "include": "location,player,urls"})
            r.raise_for_status()
            found += r.json().get("webcams", [])
        except (requests.RequestException, ValueError) as e:
            log.warning("API Windy Webcams indisponible : %s", e)
    known = {c["id"] for c in cams}
    for w in found:
        wid = str(w.get("webcamId") or w.get("id"))
        loc = w.get("location") or {}
        lat, lon = loc.get("latitude"), loc.get("longitude")
        if wid in known or lat is None or not (BBOX[0] <= lat <= BBOX[1] and BBOX[2] <= lon <= BBOX[3]):
            continue
        if w.get("status") not in (None, "active"):
            continue
        cams.append({"id": wid, "titre": w.get("title", wid), "lat": lat, "lon": lon,
                     "player": (w.get("player") or {}).get("day") or player(wid),
                     "lien": ((w.get("urls") or {}).get("detail")) or f"https://www.windy.com/webcams/{wid}"})
        known.add(wid)
    log.info("Webcams : %d affichées (%d trouvées par l'API)", len(cams), len(found))
    return cams
