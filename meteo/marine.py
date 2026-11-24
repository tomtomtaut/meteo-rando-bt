"""État de la mer (Open-Meteo Marine : modèles de vagues Météo-France MFWAM / ECMWF WAM).

hs = hauteur des vagues (mer du vent + houle), sw = hauteur de houle, per = période de houle (s),
dir = direction d'où vient la houle (°).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import numpy as np
import requests

log = logging.getLogger(__name__)

API = "https://marine-api.open-meteo.com/v1/marine"
VARS = {"hs": "wave_height", "sw": "swell_wave_height", "per": "swell_wave_period", "dir": "swell_wave_direction"}
CHUNK = 80


def fetch(points: list[tuple[float, float]]) -> dict | None:
    out_times, cols = None, {k: [] for k in VARS}
    for c0 in range(0, len(points), CHUNK):
        chunk = points[c0:c0 + CHUNK]
        try:
            r = requests.get(API, timeout=90, params={
                "latitude": ",".join(f"{la:.3f}" for la, _ in chunk),
                "longitude": ",".join(f"{lo:.3f}" for _, lo in chunk),
                "hourly": ",".join(VARS.values()), "timezone": "GMT", "past_days": 1, "forecast_days": 4})
            r.raise_for_status()
            data = r.json()
        except (requests.RequestException, ValueError) as e:
            log.warning("Open-Meteo Marine indisponible : %s", e)
            return None
        data = data if isinstance(data, list) else [data]
        if out_times is None:
            out_times = [datetime.fromisoformat(t).replace(tzinfo=timezone.utc) for t in data[0]["hourly"]["time"]]
        for d in data:
            for k, v in VARS.items():
                col = d["hourly"].get(v) or [None] * len(out_times)
                cols[k].append([np.nan if x is None else x for x in col])
    out = {"times": out_times}
    for k in VARS:
        out[k] = np.array(cols[k], dtype=float).T  # (T, P)
    log.info("Mer : %d points, %d heures", len(points), len(out_times))
    return out
