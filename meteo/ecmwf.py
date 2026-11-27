"""Complément ECMWF via Open-Meteo : jour 3, heures hors du run AROME, et pluie des jours passés."""

from __future__ import annotations

import logging
import time
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
# Open-Meteo gratuit : 600 « appels » par minute. Un appel = un lieu, pondéré par
# max(1, variables/10) × max(1, jours/14). Au-delà : refus 429 Too Many Requests.
# On garde une marge et on attend que la minute se libère avant le paquet suivant.
BUDGET_MINUTE = 540
WINDOW_S = 61
_sent: list[tuple[float, float]] = []   # (instant, poids) des requêtes de la dernière minute
_sleep = time.sleep                      # remplaçable dans les tests
_clock = time.monotonic


MAX_REFUSALS = 3
_refusals = [0]


class TooMany(Exception):
    """Refus 429 d'Open-Meteo."""


def _weight(n_points: int, n_vars: int, n_days: int) -> float:
    return n_points * max(1.0, n_vars / 10) * max(1.0, n_days / 14)


def _throttle(w: float) -> None:
    """Attend, si besoin, que le poids envoyé sur la dernière minute laisse la place à w."""
    while True:
        now = _clock()
        _sent[:] = [(t, x) for t, x in _sent if now - t < WINDOW_S]
        used = sum(x for _, x in _sent)
        if not _sent or used + w <= BUDGET_MINUTE:
            _sent.append((now, w))
            return
        wait = WINDOW_S - (now - _sent[0][0]) + 0.5
        log.info("Open-Meteo : %.0f appels sur la dernière minute, pause de %.0f s", used, wait)
        _sleep(max(wait, 1.0))


def fetch(points: list[tuple[float, float]], alts: list[float], order: list[int] | None = None) -> dict | None:
    """Comme _fetch, par paquets de 100 points (limite de longueur d'URL), au rythme permis par Open-Meteo.

    order : ordre de priorité des points (les plus importants d'abord). Un paquet en échec
    laisse ses colonnes vides (NaN) sans faire perdre les autres. None si tout échoue."""
    order = list(order) if order is not None else list(range(len(points)))
    chunks = [order[i:i + CHUNK] for i in range(0, len(order), CHUNK)]
    parts = []
    _refusals[0] = 0
    for ch in chunks:
        if _refusals[0] >= MAX_REFUSALS:   # Open-Meteo refuse encore après plusieurs minutes : on arrête
            parts.append(None)
            continue
        part = _fetch([points[i] for i in ch])
        if part is not None:
            # Variables en altitude parfois absentes du modèle à 9 km : on les prend à 25 km
            missing = [k for k in ("rh850", "rh700", "ws925") if k not in part]
            if missing:
                extra = _fetch([points[i] for i in ch], models=("ecmwf_ifs025",), only=missing)
                if extra is not None:
                    _align_into(part, extra, missing)
        parts.append(part)
    ok = [(ch, p) for ch, p in zip(chunks, parts) if p is not None]
    if not ok:
        return None
    times = ok[0][1]["times"]
    models = []
    for _, p in ok:
        if p["model"] not in models:
            models.append(p["model"])
    out = {"times": times, "model": "+".join(models)}
    failed = sum(len(ch) for ch, p in zip(chunks, parts) if p is None)
    if failed:
        log.warning("Open-Meteo : %d points sur %d sans ECMWF (paquets refusés)", failed, len(points))
    out["n_missing"] = failed
    for k in VARS:
        if not any(k in p for _, p in ok):
            continue
        full = np.full((len(times), len(points)), np.nan)
        for ch, p in ok:
            if k not in p:
                continue
            if p["times"] == times:
                full[:, ch] = p[k]
            else:
                idx = {t: i for i, t in enumerate(p["times"])}
                for i, t in enumerate(times):
                    if t in idx:
                        full[i, ch] = p[k][idx[t]]
        out[k] = full
    return out


def _align_into(part: dict, extra: dict, keys: list[str]) -> None:
    idx = {t: i for i, t in enumerate(extra["times"])}
    for k in keys:
        if k not in extra:
            continue
        full = np.full((len(part["times"]), extra[k].shape[1]), np.nan)
        for i, t in enumerate(part["times"]):
            if t in idx:
                full[i] = extra[k][idx[t]]
        part[k] = full


PAST_DAYS, FORECAST_DAYS = 2, 7   # 7 jours : pour repérer une fenêtre Everesting assez tôt


def _get(params: dict, n_points: int, n_vars: int) -> dict | list:
    """Une requête, avec une seconde chance après une minute en cas de refus 429."""
    w = _weight(n_points, n_vars, PAST_DAYS + FORECAST_DAYS)
    for attempt in (1, 2):
        _throttle(w)
        r = requests.get(API, params=params, timeout=60)
        if r.status_code == 429:
            if attempt == 1:
                log.warning("Open-Meteo : refus 429, nouvel essai dans %d s", WINDOW_S)
                _sent[:] = [(_clock(), BUDGET_MINUTE)]   # la minute est pleine côté serveur
                continue
            _refusals[0] += 1
            raise TooMany("429 Too Many Requests (après une minute d'attente)")
        r.raise_for_status()
        return r.json()
    raise TooMany("429")


def _fetch(points: list[tuple[float, float]], models=MODELS, only=None) -> dict | None:
    """Renvoie {"times": [...UTC], "model": str, var: array(T, P)}."""
    wanted = {k: v for k, v in VARS.items() if only is None or k in only}
    params = {
        "latitude": ",".join(f"{la:.4f}" for la, _ in points),
        "longitude": ",".join(f"{lo:.4f}" for _, lo in points),
        "hourly": ",".join(wanted.values()),
        "timezone": "GMT",
        "past_days": PAST_DAYS,
        "forecast_days": FORECAST_DAYS,
        "wind_speed_unit": "kmh",
    }
    for model in models:
        try:
            data = _get({**params, "models": model}, len(points), len(wanted))
        except TooMany as e:
            # Refus de débit : les autres modèles seraient refusés aussi, inutile d'insister
            log.warning("Open-Meteo %s refusé : %s", model, e)
            return None
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
            log.info("Open-Meteo : modèle %s, %d heures, %d points", model, len(times), len(points))
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
