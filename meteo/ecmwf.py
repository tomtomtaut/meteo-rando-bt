"""Complément ECMWF via Open-Meteo : jour 3, heures hors du run AROME, et pluie des jours passés."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import numpy as np
import requests

log = logging.getLogger(__name__)

API = "https://api.open-meteo.com/v1/forecast"
MODELS = ("ecmwf_ifs", "ecmwf_ifs025", "best_match")
VARS = {
    "precip": "precipitation",
    "lcc": "cloud_cover_low",
    "mcc": "cloud_cover_mid",
    "rh850": "relative_humidity_850hPa",
    "rh": "relative_humidity_2m",
    "gust": "wind_gusts_10m",
    "t2m": "temperature_2m",
    "cape": "cape",
}


def fetch(points: list[tuple[float, float]], alts: list[float]) -> dict | None:
    """Renvoie {"times": [...UTC], "model": str, var: array(T, P)}."""
    params = {
        "latitude": ",".join(f"{la:.4f}" for la, _ in points),
        "longitude": ",".join(f"{lo:.4f}" for _, lo in points),
        "elevation": ",".join(f"{a:.0f}" for a in alts),
        "hourly": ",".join(VARS.values()),
        "timezone": "GMT",
        "past_days": 2,
        "forecast_days": 5,
        "wind_speed_unit": "kmh",
    }
    for model in MODELS:
        try:
            r = requests.get(API, params={**params, "models": model}, timeout=60)
            r.raise_for_status()
            data = r.json()
        except (requests.RequestException, ValueError) as e:
            log.warning("Open-Meteo %s indisponible : %s", model, e)
            continue
        data = data if isinstance(data, list) else [data]
        times = [datetime.fromisoformat(t).replace(tzinfo=timezone.utc) for t in data[0]["hourly"]["time"]]
        out = {"times": times, "model": model}
        for k, v in VARS.items():
            cols = [d["hourly"].get(v) for d in data]
            if any(c is None for c in cols):
                continue
            arr = np.array([[np.nan if x is None else x for x in c] for c in cols], dtype=float).T
            if np.all(np.isnan(arr)):
                continue
            out[k] = arr
        if "precip" in out:
            log.info("Open-Meteo : modèle %s, %d heures", model, len(times))
            return out
    return None
