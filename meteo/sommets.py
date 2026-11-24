"""État des sommets heure par heure (dans le nuage, dégagé, au-dessus d'une mer de nuages),
heures de lever et de coucher du soleil, et fenêtres pour les voir.

Principe : on lit le profil vertical AROME (humidité et fraction nuageuse niveau par niveau)
au-dessus du sommet, et on l'interpole à l'altitude RÉELLE du sommet. Le relief du modèle est
lissé (sommet trop bas) : lire « au sol du modèle » sous-estime l'altitude, d'où ce détour.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone

import numpy as np

TZ = timezone(timedelta(hours=-4))

# --- Seuils (à calibrer avec la webcam et les sorties) -------------------------------------
CLOUD_IN = 50      # % de fraction nuageuse à l'altitude du sommet → dans le nuage
RH_IN = 95         # % d'humidité à l'altitude du sommet → dans le nuage (brouillard)
CLOUD_CLEAR = 20
RH_CLEAR = 88
SEA_OF_CLOUDS = 50  # % de nuages sous le sommet (côté au vent) pour parler de mer de nuages
HORIZON_LOW = 50    # % de nuages bas sur la mer, au-delà l'horizon est bouché
HORIZON_MID = 60
FIRST_H, LAST_H = 5, 19

STATES = {
    "degage": ("Dégagé", "#2e9d5b"),
    "mer": ("Au-dessus des nuages", "#2b7bd6"),
    "incertain": ("Incertain", "#c9b458"),
    "nuage": ("Dans le nuage", "#8a8a85"),
    None: ("Pas de donnée", "#dcdcd6"),
}


# --- Soleil --------------------------------------------------------------------------------

def sun_times(d: date, lat: float, lon: float, alt: float = 0.0) -> tuple[datetime, datetime]:
    """Lever et coucher (UTC), équation du lever de soleil, avec correction d'altitude
    (depuis un sommet, l'horizon est plus bas : le soleil apparaît quelques minutes plus tôt)."""
    jd_noon = (datetime(d.year, d.month, d.day, 12, tzinfo=timezone.utc).timestamp() / 86400) + 2440587.5
    n = math.ceil(jd_noon - 2451545.0 + 0.0008)
    j_star = n - lon / 360
    m = math.radians((357.5291 + 0.98560028 * j_star) % 360)
    c = 1.9148 * math.sin(m) + 0.02 * math.sin(2 * m) + 0.0003 * math.sin(3 * m)
    lam = math.radians((math.degrees(m) + c + 180 + 102.9372) % 360)
    j_transit = 2451545.0 + j_star + 0.0053 * math.sin(m) - 0.0069 * math.sin(2 * lam)
    decl = math.asin(math.sin(lam) * math.sin(math.radians(23.4397)))
    h0 = math.radians(-0.833 - 2.076 * math.sqrt(max(alt, 0)) / 60)
    phi = math.radians(lat)
    cos_w = (math.sin(h0) - math.sin(phi) * math.sin(decl)) / (math.cos(phi) * math.cos(decl))
    w = math.degrees(math.acos(max(-1, min(1, cos_w))))

    def to_dt(j):
        return datetime.fromtimestamp((j - 2440587.5) * 86400, tz=timezone.utc)

    return to_dt(j_transit - w / 360), to_dt(j_transit + w / 360)


# --- État du sommet ------------------------------------------------------------------------

def _interp(z_col, v_col, alt):
    ok = ~(np.isnan(z_col) | np.isnan(v_col))
    if ok.sum() < 2:
        return float("nan")
    zs, vs = z_col[ok], v_col[ok]
    order = np.argsort(zs)
    return float(np.interp(alt, zs[order], vs[order]))


def state_from_profile(prof: dict, i: int, alt: float, i_windward: int | None) -> tuple[str, dict]:
    z = prof["z"][:, i]
    cc = _interp(z, prof["cc"][:, i], alt) if not np.all(np.isnan(prof["cc"])) else float("nan")
    rh = _interp(z, prof["rh"][:, i], alt) if not np.all(np.isnan(prof["rh"])) else float("nan")
    below = float("nan")
    if i_windward is not None and not np.all(np.isnan(prof["cc"])):
        zw, cw = prof["z"][:, i_windward], prof["cc"][:, i_windward]
        sel = (zw >= 300) & (zw <= alt - 150) & ~np.isnan(cw)
        below = float(np.max(cw[sel])) if sel.any() else float("nan")
    cc0 = 0.0 if math.isnan(cc) else cc
    rh0 = 0.0 if math.isnan(rh) else rh
    if math.isnan(cc) and math.isnan(rh):
        st = None
    elif cc0 >= CLOUD_IN or rh0 >= RH_IN:
        st = "nuage"
    elif cc0 < CLOUD_CLEAR and rh0 < RH_CLEAR:
        st = "mer" if (not math.isnan(below) and below >= SEA_OF_CLOUDS) else "degage"
    else:
        st = "incertain"
    return st, {"cc": None if math.isnan(cc) else round(cc), "rh": None if math.isnan(rh) else round(rh),
                "dessous": None if math.isnan(below) else round(below)}


def state_from_surface(rh850: float, lcc: float) -> str | None:
    """Repli sans profil AROME (jour 3, ECMWF) : humidité vers 1 500 m et nuages bas."""
    if math.isnan(rh850) and math.isnan(lcc):
        return None
    r = 0 if math.isnan(rh850) else rh850
    c = 0 if math.isnan(lcc) else lcc
    if r >= 92 or c >= 85:
        return "nuage"
    if r < 75 and c < 50:
        return "degage"
    return "incertain"


def compute_states(points_alt: dict[int, float], profiles: dict, merged, i_windward: int | None) -> dict:
    """{(i_point, time_utc): (state, détails, source)} pour chaque heure de la base fusionnée."""
    out = {}
    for t in merged.times:
        prof = profiles.get(t)
        ti = merged.index[t]
        for i, alt in points_alt.items():
            if prof is not None:
                st, det = state_from_profile(prof, i, alt, i_windward)
                if st is not None:
                    out[(i, t)] = (st, det, "AROME")
                    continue
            rh850 = float(merged.data["rh850"][ti, i]) if "rh850" in merged.data else float("nan")
            lcc = float(merged.data["lcc"][ti, i]) if "lcc" in merged.data else float("nan")
            st = state_from_surface(rh850, lcc)
            out[(i, t)] = (st, {}, "ECMWF")
    return out


def horizon_clear(merged, i_point: int, t: datetime) -> bool | None:
    ti = merged.index.get(t)
    if ti is None or i_point is None:
        return None
    lcc = float(merged.data["lcc"][ti, i_point]) if "lcc" in merged.data else float("nan")
    mcc = float(merged.data["mcc"][ti, i_point]) if "mcc" in merged.data else float("nan")
    if math.isnan(lcc) and math.isnan(mcc):
        return None
    return (0 if math.isnan(lcc) else lcc) < HORIZON_LOW and (0 if math.isnan(mcc) else mcc) < HORIZON_MID


def _hm(dt: datetime) -> str:
    loc = dt.astimezone(TZ)
    return f"{loc.hour}h{loc:%M}"


def day_summary(sommet: dict, i: int, states: dict, merged, d: date, i_east, i_west) -> dict:
    rise, sset = sun_times(d, sommet["lat"], sommet["lon"], sommet["alt"])
    hours = []
    for h in range(FIRST_H, LAST_H + 1):
        t = datetime(d.year, d.month, d.day, h, tzinfo=TZ).astimezone(timezone.utc)
        st = states.get((i, t))
        hours.append({"h": h, "state": st[0] if st else None, "src": st[2] if st else None,
                      "det": st[1] if st else {}})

    def at(dt):
        t = (dt + timedelta(minutes=30)).replace(minute=0, second=0, microsecond=0)
        st = states.get((i, t))
        return (st[0] if st else None), t

    rise_state, t_rise = at(rise)
    set_state, t_set = at(sset)
    good = ("degage", "mer")
    lever = {"heure": _hm(rise), "etat": rise_state, "horizon": horizon_clear(merged, i_east, t_rise)}
    coucher = {"heure": _hm(sset), "etat": set_state, "horizon": horizon_clear(merged, i_west, t_set)}
    lever["top"] = rise_state in good and lever["horizon"] is not False
    coucher["top"] = set_state in good and coucher["horizon"] is not False

    clear = [x["h"] for x in hours if x["state"] in good]
    texte = []
    if not clear:
        texte.append("Sommet dans le nuage ou incertain toute la journée")
    else:
        # plus longue plage continue de ciel dégagé
        best, cur = [], []
        for x in hours:
            if x["state"] in good:
                cur.append(x["h"])
                best = cur if len(cur) > len(best) else best
            else:
                cur = []
        texte.append(f"Dégagé de {best[0]}h à {best[-1] + 1}h" if len(best) > 1 else f"Dégagé vers {best[0]}h")
        nxt = next((x["h"] for x in hours if x["h"] > best[-1] and x["state"] == "nuage"), None)
        if nxt and best[0] <= 9:
            texte.append(f"se couvre vers {nxt}h")
    if any(x["state"] == "mer" for x in hours):
        h_mer = next(x["h"] for x in hours if x["state"] == "mer")
        texte.append(f"mer de nuages possible vers {h_mer}h")
    src = {x["src"] for x in hours if x["src"]}
    return {
        "nom": sommet["nom"], "alt": sommet["alt"], "hours": hours, "lever": lever, "coucher": coucher,
        "texte": ", ".join(texte), "source": "AROME" if src == {"AROME"} else ("mixte" if "AROME" in src else "ECMWF"),
    }
