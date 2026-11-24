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
    "rh700": "relative_humidity_700hPa",
    "ws925": "wind_speed_925hPa",
    "ws10": "wind_speed_10m",
    "rh": "relative_humidity_2m",
    "gust": "wind_gusts_10m",
    "t2m": "temperature_2m",
    "cape": "cape",
}


CHUNK = 100


def fetch(points: list[tuple[float, float]], alts: list[float]) -> dict | None:
    """Comme _fetch, par paquets de 100 points (limite de longueur d'URL)."""
    parts = [_fetch(points[i:i + CHUNK]) for i in range(0, len(points), CHUNK)]
    if not parts or any(p is None for p in parts):
        return None
    out = {"times": parts[0]["times"], "model": parts[0]["model"]}
    for k in VARS:
        if all(k in p for p in parts):
            out[k] = np.concatenate([p[k] for p in parts], axis=1)
    # Variables en altitude parfois absentes du modèle à 9 km : on les prend à 25 km
    missing = [k for k in ("rh850", "rh700", "ws925") if k not in out]
    if missing:
        extra = [_fetch(points[i:i + CHUNK], models=("ecmwf_ifs025",), only=missing)
                 for i in range(0, len(points), CHUNK)]
        if all(e is not None for e in extra):
            idx = {t: i for i, t in enumerate(extra[0]["times"])}
            for k in missing:
                if all(k in e for e in extra):
                    arr = np.concatenate([e[k] for e in extra], axis=1)
                    full = np.full((len(out["times"]), arr.shape[1]), np.nan)
                    for i, t in enumerate(out["times"]):
                        if t in idx:
                            full[i] = arr[idx[t]]
                    out[k] = full
    return out


def _fetch(points: list[tuple[float, float]], models=MODELS, only=None) -> dict | None:
    """Renvoie {"times": [...UTC], "model": str, var: array(T, P)}."""
    wanted = {k: v for k, v in VARS.items() if only is None or k in only}
    params = {
        "latitude": ",".join(f"{la:.4f}" for la, _ in points),
        "longitude": ",".join(f"{lo:.4f}" for _, lo in points),
        "hourly": ",".join(wanted.values()),
        "timezone": "GMT",
        "past_days": 2,
        "forecast_days": 7,   # 7 jours : pour repérer une fenêtre Everesting assez tôt
        "wind_speed_unit": "kmh",
    }
    for model in models:
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
        for k, v in wanted.items():
            cols = [d["hourly"].get(v) for d in data]
            if any(c is None for c in cols):
                continue
            arr = np.array([[np.nan if x is None else x for x in c] for c in cols], dtype=float).T
            if np.all(np.isnan(arr)):
                continue
            out[k] = arr
        if "precip" in out or only:
            log.info("Open-Meteo : modèle %s, %d heures", model, len(times))
            return out
    return None


ENS_API = "https://ensemble-api.open-meteo.com/v1/ensemble"
ENS_MODELS = ("ecmwf_ifs025", "ecmwf_ifs04")


def fetch_ensemble(points: list[tuple[float, float]]) -> dict | None:
    """Ensemble ECMWF (51 scénarios) : pluie, pour des probabilités au-delà d'AROME.

    Renvoie {"times": [...], "model": str, "precip_ens": array(T, P, M)} ou None."""
    params = {
        "latitude": ",".join(f"{la:.4f}" for la, _ in points),
        "longitude": ",".join(f"{lo:.4f}" for _, lo in points),
        "hourly": "precipitation",
        "timezone": "GMT",
        "past_days": 1,
        "forecast_days": 7,
    }
    for model in ENS_MODELS:
        try:
            r = requests.get(ENS_API, params={**params, "models": model}, timeout=90)
            r.raise_for_status()
            data = r.json()
        except (requests.RequestException, ValueError) as e:
            log.warning("Ensemble Open-Meteo %s indisponible : %s", model, e)
            continue
        data = data if isinstance(data, list) else [data]
        hourly0 = data[0].get("hourly", {})
        members = sorted(k for k in hourly0 if k.startswith("precipitation"))
        if len(members) < 5:
            log.warning("Ensemble %s : membres introuvables (%s)", model, list(hourly0)[:5])
            continue
        times = [datetime.fromisoformat(t).replace(tzinfo=timezone.utc) for t in hourly0["time"]]
        arr = np.full((len(times), len(data), len(members)), np.nan)
        for p, d in enumerate(data):
            for m, k in enumerate(members):
                col = d["hourly"].get(k)
                if col:
                    arr[:, p, m] = [np.nan if x is None else x for x in col]
        # Modèle tri-horaire : Open-Meteo peut renvoyer des cumuls sur 3 h aux heures 0,3,6…
        # et rien entre. On répartit alors chaque cumul sur les 3 heures.
        filled = ~np.isnan(arr).all(axis=(1, 2))
        if filled.mean() < 0.6:
            out = np.full_like(arr, np.nan)
            for i in np.where(filled)[0]:
                for k in range(3):
                    if 0 <= i - k < len(times):
                        out[i - k] = arr[i] / 3
            arr = out
        log.info("Ensemble %s : %d scénarios", model, len(members))
        return {"times": times, "model": model, "precip_ens": arr, "n_members": len(members)}
    return None


AQ_API = "https://air-quality-api.open-meteo.com/v1/air-quality"


def fetch_dust(lat: float, lon: float) -> dict | None:
    """Poussières désertiques (modèle CAMS de Copernicus) : {time_utc: µg/m³}."""
    try:
        r = requests.get(AQ_API, params={"latitude": lat, "longitude": lon, "hourly": "dust",
                                         "timezone": "GMT", "forecast_days": 4}, timeout=60)
        r.raise_for_status()
        h = r.json()["hourly"]
        return {datetime.fromisoformat(t).replace(tzinfo=timezone.utc): v
                for t, v in zip(h["time"], h["dust"]) if v is not None}
    except (requests.RequestException, ValueError, KeyError) as e:
        log.warning("Poussières (CAMS) indisponibles : %s", e)
        return None
