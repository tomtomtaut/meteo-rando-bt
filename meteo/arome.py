"""Téléchargement d'AROME Outre-Mer Antilles (open data Météo-France) et extraction aux points.

Les fichiers sont publiés en GRIB2 horaires sur le stockage public de Météo-France :
  {BASE}/{run}/arome-om/ANTIL/0025/{paquet}/arome-om-ANTIL__0025__{paquet}__{HHH}H__{run}.grib2

On ne garde de chaque champ que les valeurs aux points qui nous intéressent :
le fichier entier (toute la Caraïbe) est jeté aussitôt lu.
"""

from __future__ import annotations

import logging
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import eccodes
import numpy as np
import requests

log = logging.getLogger(__name__)

BASE = "https://meteofrance-pnt.s3.rbx.io.cloud.ovh.net/pnt"
PAQUETS = ("SP1", "SP2")          # surface, toutes les échéances
PAQUETS_PROFIL = ("IP1", "IP2")   # niveaux de pression (T, HU, Z / fraction nuageuse), heures utiles seulement
TIMEOUT = 60


def url(run: datetime, paquet: str, h: int) -> str:
    r = f"{run:%Y-%m-%dT%H}:00:00Z"
    return f"{BASE}/{r}/arome-om/ANTIL/0025/{paquet}/arome-om-ANTIL__0025__{paquet}__{h:03d}H__{r}.grib2"


def _exists(u: str) -> bool:
    try:
        return requests.head(u, timeout=20).status_code == 200
    except requests.RequestException:
        return False


AVAILABILITY: dict[str, bool] = {}  # run -> publié ? (pour régler l'heure du rapport)


def find_run(now: datetime | None = None, before: datetime | None = None,
             paquets=PAQUETS) -> tuple[datetime, int] | None:
    """Run le plus récent (antérieur à `before` si donné) dont les paquets sont publiés jusqu'à au moins +36h.

    Renvoie (run, échéance max disponible)."""
    now = now or datetime.now(timezone.utc)
    latest = now.replace(minute=0, second=0, microsecond=0)
    latest -= timedelta(hours=latest.hour % 3)
    for k in range(12):
        run = latest - timedelta(hours=3 * k)
        if before is not None and run >= before:
            continue
        ok = all(_exists(url(run, p, 36)) for p in paquets)
        AVAILABILITY[run.isoformat()] = ok
        if not ok:
            continue
        for hmax in (48, 45, 42, 39, 36):
            if all(_exists(url(run, p, hmax)) for p in paquets):
                log.info("Run AROME retenu : %s (jusqu'à +%dh)", run.isoformat(), hmax)
                return run, hmax
    return None


NB = 1  # rayon du voisinage en mailles : 3x3 = ±2,5 km (méthode de voisinage, cf. README)
CENTER = (2 * NB + 1) ** 2 // 2


class _Extractor:
    """Lit un GRIB2 et renvoie, pour chaque champ, les valeurs aux points demandés
    et dans les mailles voisines (tableau (P, 9) : la maille du point est au centre)."""

    def __init__(self, points: list[tuple[float, float]]):
        self.points = points
        self._idx_cache: dict[tuple, tuple[np.ndarray, list]] = {}

    def _indices(self, gid) -> tuple[np.ndarray, list]:
        key = tuple(
            eccodes.codes_get(gid, k)
            for k in ("gridType", "Ni", "Nj", "latitudeOfFirstGridPointInDegrees", "longitudeOfFirstGridPointInDegrees")
        )
        if key not in self._idx_cache:
            ni, nj = eccodes.codes_get(gid, "Ni"), eccodes.codes_get(gid, "Nj")
            idx, info = [], []
            for lat, lon in self.points:
                n = eccodes.codes_grib_find_nearest(gid, lat, lon)[0]
                c = int(n.index)
                j, i = divmod(c, ni)
                row = []
                for dj in range(-NB, NB + 1):
                    for di in range(-NB, NB + 1):
                        jj, ii = j + dj, i + di
                        row.append(jj * ni + ii if 0 <= jj < nj and 0 <= ii < ni else c)
                idx.append(row)
                info.append({"lat": float(n.lat), "lon": float(n.lon), "dist_km": round(float(n.distance), 2)})
            self._idx_cache[key] = (np.array(idx), info)
        return self._idx_cache[key]

    def read(self, path: str) -> tuple[dict, dict]:
        fields, meta = {}, {}
        with open(path, "rb") as f:
            while True:
                gid = eccodes.codes_grib_new_from_file(f)
                if gid is None:
                    break
                try:
                    short = eccodes.codes_get(gid, "shortName")
                    tlev = eccodes.codes_get(gid, "typeOfLevel")
                    lev = eccodes.codes_get(gid, "level")
                    key = f"{short}|{tlev}|{lev}"
                    idx, info = self._indices(gid)
                    vals = eccodes.codes_get_values(gid)[idx].astype(float)
                    missing = eccodes.codes_get(gid, "missingValue")
                    vals[vals == missing] = np.nan
                    fields[key] = vals
                    meta[key] = {
                        "name": eccodes.codes_get(gid, "name"),
                        "units": eccodes.codes_get(gid, "units"),
                        "stepType": eccodes.codes_get(gid, "stepType"),
                        "stepRange": str(eccodes.codes_get(gid, "stepRange")),
                    }
                    meta["_grid"] = info
                finally:
                    eccodes.codes_release(gid)
        return fields, meta


def _fetch_one(u: str, tmpdir: str) -> str | None:
    """Télécharge un fichier (3 essais). Le décodage se fait ensuite dans le fil principal."""
    path = os.path.join(tmpdir, os.path.basename(u).replace(":", "-"))
    for attempt in range(3):
        try:
            with requests.get(u, stream=True, timeout=TIMEOUT) as r:
                r.raise_for_status()
                with open(path, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
            return path
        except requests.RequestException as e:
            log.warning("Échec %s (essai %d) : %s", u, attempt + 1, e)
    return None


def download(run: datetime, hmax: int, points: list[tuple[float, float]], workers: int = 8,
             paquets=PAQUETS, hours=None):
    """Renvoie ({(paquet, h): fields}, inventaire des champs, infos grille)."""
    ex = _Extractor(points)
    hours = list(range(0, hmax + 1)) if hours is None else hours
    jobs = [(p, h) for p in paquets for h in hours]
    results, inventory, grid = {}, {}, None
    with tempfile.TemporaryDirectory() as tmp, ThreadPoolExecutor(workers) as pool:
        futs = {job: pool.submit(_fetch_one, url(run, *job), tmp) for job in jobs}
        for job, fut in futs.items():
            path = fut.result()
            if path is None:
                continue
            try:
                fields, meta = ex.read(path)
            except Exception as e:  # noqa: BLE001 — un fichier illisible ne doit pas tout bloquer
                log.warning("Lecture impossible %s : %s", path, e)
                continue
            finally:
                if os.path.exists(path):
                    os.remove(path)
            grid = meta.pop("_grid", grid)
            results[job] = fields
            for k, m in meta.items():
                inv = inventory.setdefault(k, {**m, "paquet": job[0], "steps": []})
                inv["steps"].append(m["stepRange"])
    for inv in inventory.values():
        inv["steps"] = inv["steps"][:4] + (["…"] if len(inv["steps"]) > 4 else [])
    log.info("AROME : %d/%d fichiers lus, %d champs", len(results), len(jobs), len(inventory))
    return results, inventory, grid


# --- Conversion en séries horaires par point -------------------------------------------------

def _pick(inventory: dict, tests) -> str | None:
    for test in tests:
        for k, m in inventory.items():
            short, tlev, lev = k.split("|")
            if test(short, tlev, int(lev), m["name"].lower()):
                return k
    return None


def _pct(a):
    a = np.asarray(a, dtype=float)
    return a * 100 if np.nanmax(a) <= 1.01 else a


def to_series(run: datetime, hmax: int, results: dict, inventory: dict, n_points: int) -> dict:
    """Renvoie {"times": [...], var: array(T, P)} avec var parmi
    precip (mm/h), lcc (%), rh (%), gust (km/h), t2m (°C), cape (J/kg)."""
    keys = {
        "precip": _pick(inventory, [
            lambda s, t, l, n: s == "tp",
            lambda s, t, l, n: s in ("tirf", "rprate", "prate"),
            lambda s, t, l, n: "precipitation" in n and "snow" not in n and "rate" not in n,
        ]),
        "lcc": _pick(inventory, [lambda s, t, l, n: s == "lcc", lambda s, t, l, n: "low cloud" in n]),
        "mcc": _pick(inventory, [lambda s, t, l, n: s == "mcc", lambda s, t, l, n: "medium cloud" in n or "middle cloud" in n]),
        "sp": _pick(inventory, [lambda s, t, l, n: s == "sp", lambda s, t, l, n: n == "surface pressure"]),
        "rh": _pick(inventory, [
            lambda s, t, l, n: s in ("2r", "r2"),
            lambda s, t, l, n: s == "r" and t == "heightAboveGround" and l == 2,
        ]),
        "t2m": _pick(inventory, [lambda s, t, l, n: s in ("2t", "t2m"), lambda s, t, l, n: s == "t" and t == "heightAboveGround" and l == 2]),
        "cape": _pick(inventory, [lambda s, t, l, n: "cape" in s.lower(), lambda s, t, l, n: "convective available" in n]),
        "gust": _pick(inventory, [lambda s, t, l, n: s in ("fg10", "i10fg", "10fg", "gust", "max_i10fg"),
                                  lambda s, t, l, n: "wind gust" in n and "eastward" not in n and "northward" not in n]),
        "efg": _pick(inventory, [lambda s, t, l, n: s in ("efg10", "10efg", "max_10efg")]),
        "nfg": _pick(inventory, [lambda s, t, l, n: s in ("nfg10", "10nfg", "max_10nfg")]),
    }
    log.info("Champs AROME utilisés : %s", keys)

    hours = list(range(0, hmax + 1))
    times = [run + timedelta(hours=h) for h in hours]
    nan = np.full((n_points, (2 * NB + 1) ** 2), np.nan)

    def grab_nb(key):
        if key is None:
            return None
        pkg = inventory[key]["paquet"]
        return np.array([results.get((pkg, h), {}).get(key, nan) for h in hours])  # (T, P, 9)

    def grab(key):
        v = grab_nb(key)
        return None if v is None else v[:, :, CENTER]

    out = {"times": times, "keys": keys}

    # Précipitations : cumul depuis le début du run, ou cumul horaire, selon le stepRange.
    pr = grab_nb(keys["precip"])
    if pr is not None:
        steps = [s for s in inventory[keys["precip"]]["steps"] if s != "…"]
        cumulative = any(s.startswith("0-") and s != "0-1" for s in steps)
        if cumulative:
            hourly = np.concatenate([np.full((1,) + pr.shape[1:], np.nan), np.diff(pr, axis=0)])
        else:
            hourly = pr
        hourly = np.clip(hourly, 0, None)
        out["precip_nb"] = hourly            # (T, P, 9) : la pluie dans le voisinage de chaque point
        out["precip"] = hourly[:, :, CENTER]
        out["precip_mode"] = "cumul depuis le run" if cumulative else "horaire"

    if (v := grab(keys["lcc"])) is not None:
        out["lcc"] = _pct(v)
    if (v := grab(keys["sp"])) is not None:
        out["sp"] = v
    if (v := grab(keys["mcc"])) is not None:
        out["mcc"] = _pct(v)
    if (v := grab(keys["rh"])) is not None:
        out["rh"] = _pct(v)
    if (v := grab(keys["t2m"])) is not None:
        out["t2m"] = v - 273.15 if np.nanmean(v) > 150 else v
    if (v := grab(keys["cape"])) is not None:
        out["cape"] = v
    if keys["gust"]:
        out["gust"] = grab(keys["gust"]) * 3.6
    elif keys["efg"] and keys["nfg"]:
        out["gust"] = np.hypot(grab(keys["efg"]), grab(keys["nfg"])) * 3.6
    return out


# --- Profils verticaux (niveaux de pression) --------------------------------------------------

def _std_height(p_hpa: float) -> float:
    """Altitude standard (m) d'un niveau de pression, si le géopotentiel manque."""
    return 44330.8 * (1 - (p_hpa / 1013.25) ** 0.190263)


def to_profiles(run: datetime, results: dict, inventory: dict, hours: list[int], n_points: int) -> dict:
    """Renvoie {time: {"z","rh","cc","t": array(L, P)}} trié par altitude croissante, + clés utilisées."""
    iso = {k: m for k, m in inventory.items() if k.split("|")[1] == "isobaricInhPa"}

    def family(tests):
        for test in tests:
            fam = {int(k.split("|")[2]): k for k, m in iso.items()
                   if test(k.split("|")[0], m["name"].lower())}
            if fam:
                return fam
        return {}

    fams = {
        "t": family([lambda s, n: s == "t"]),
        "rh": family([lambda s, n: s == "r", lambda s, n: "relative humidity" in n]),
        "z": family([lambda s, n: s in ("z", "gh"), lambda s, n: "geopotential" in n]),
        "cc": family([lambda s, n: s in ("cc", "ccl", "tcc"),
                      lambda s, n: "cloud" in n and ("fraction" in n or "cover" in n)]),
        "u": family([lambda s, n: s == "u"]),
        "v": family([lambda s, n: s == "v"]),
    }
    used = {v: sorted(f.keys()) for v, f in fams.items()}
    levels = sorted(set(fams["rh"]) | set(fams["cc"]), reverse=True)  # 1000 hPa d'abord = bas
    if not levels:
        return {"profiles": {}, "used": used}
    nan = np.full(n_points, np.nan)
    profiles = {}
    for h in hours:
        def stack(var):
            fam = fams[var]
            rows = []
            for lev in levels:
                key = fam.get(lev)
                val = results.get((inventory[key]["paquet"], h), {}).get(key) if key else None
                rows.append(nan if val is None else val[:, CENTER])
            return np.array(rows, dtype=float)
        rh, cc, t, z = stack("rh"), stack("cc"), stack("t"), stack("z")
        u, v = stack("u"), stack("v")
        if np.all(np.isnan(rh)) and np.all(np.isnan(cc)):
            continue
        if fams["z"]:
            zname = next(iter(fams["z"].values())).split("|")[0]
            if zname == "z" or np.nanmax(z) > 50000:
                z = z / 9.80665
        std = np.array([_std_height(p) for p in levels])[:, None] * np.ones((1, n_points))
        z = np.where(np.isnan(z), std, z)
        if not np.all(np.isnan(cc)):
            cc = cc * 100 if np.nanmax(cc) <= 1.01 else cc
        if not np.all(np.isnan(rh)):
            rh = rh * 100 if np.nanmax(rh) <= 1.01 else rh
        profiles[run + timedelta(hours=h)] = {"z": z, "rh": rh, "cc": cc, "t": t, "u": u, "v": v, "p": levels}
    return {"profiles": profiles, "used": used}
