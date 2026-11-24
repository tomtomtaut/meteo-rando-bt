"""Webcams autour de la Basse-Terre (et des Saintes, d'où l'on voit le sud du massif).

Avec une clé gratuite de l'API Windy Webcams (secret GitHub WINDY_WEBCAMS_KEY), on liste
automatiquement toutes les webcams de la zone. Sans clé, on garde celles de spots.json.
"""

from __future__ import annotations

import logging
import os

import requests

log = logging.getLogger(__name__)

API = "https://api.windy.com/webcams/api/v3/webcams"
CENTER = (16.10, -61.68)      # milieu de la Basse-Terre
RADIUS_KM = 40
BBOX = (15.80, 16.40, -61.85, -61.52)  # Basse-Terre + Saintes, sans la Grande-Terre


def player(wid: str) -> str:
    return f"https://webcams.windy.com/webcams/public/embed/player/{wid}/day"


def fetch(configured: list[dict]) -> list[dict]:
    """Webcams à afficher : celles de spots.json d'abord, puis celles trouvées par l'API."""
    cams = [{**c, "id": str(c["id"]), "player": player(c["id"]),
             "lien": f"https://www.windy.com/webcams/{c['id']}"} for c in configured]
    key = os.environ.get("WINDY_WEBCAMS_KEY")
    if not key:
        return cams
    try:
        r = requests.get(API, headers={"x-windy-api-key": key}, timeout=30, params={
            "nearby": f"{CENTER[0]},{CENTER[1]},{RADIUS_KM}", "limit": 50,
            "include": "location,player,urls"})
        r.raise_for_status()
        found = r.json().get("webcams", [])
    except (requests.RequestException, ValueError) as e:
        log.warning("API Windy Webcams indisponible : %s", e)
        return cams
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
