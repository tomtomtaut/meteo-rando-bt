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

from .heure import TZ  # noqa: E402

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
    # Jour julien à midi UTC du jour d (nombre entier). Attention : l'arrondi « ceil(... + 0.0008) » de la
    # formule usuelle suppose une date à minuit ; appliqué à midi, il décale d'un jour (bug corrigé).
    jd_noon = (datetime(d.year, d.month, d.day, 12, tzinfo=timezone.utc).timestamp() / 86400) + 2440587.5
    n = round(jd_noon - 2451545.0)
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
    """Repli sans profil AROME (au-delà d'AROME, ECMWF ~9-25 km) : humidité vers 1 500 m et nuages bas.

    Seuils volontairement sévères : la maille ECMWF mélange mer et relief et ne voit pas le nuage
    accroché au sommet, elle est donc trop optimiste sur le « dégagé »."""
    if math.isnan(rh850) and math.isnan(lcc):
        return None
    r = 0 if math.isnan(rh850) else rh850
    c = 0 if math.isnan(lcc) else lcc
    if r >= 85 or c >= 70:
        return "nuage"
    if r < 65 and c < 30:
        return "degage"
    return "incertain"


# --- Couche nuageuse d'alizé, calculée sur l'air en amont (méthode validée dans la littérature) ----
# Base : niveau de condensation par soulèvement (LCL) de l'air de basse couche en mer, formule d'Espy
#   (125 m par °C d'écart température / point de rosée). C'est l'indicateur de la base des nuages sur
#   les reliefs au vent utilisé pour les montagnes de Porto Rico (Miller et al. 2018).
# Haut : sommet de la couche humide, plafonnée par l'inversion des alizés (AMS Glossary ; Hawaï).
# Un relief au vent entre la base et le haut est dans le nuage orographique.
MARGE_HAUT = 100   # m : marge autour du haut de la couche (choix de Tomas ; niveaux du modèle espacés de 250-500 m)
MARGE_BASE = 50    # m : condensation un peu au-dessus du LCL réel (sursaturation)


def dewpoint(t_c: float, rh: float) -> float:
    """Point de rosée (Magnus, coefficients d'Alduchov et Eskridge)."""
    a, b = 17.625, 243.04
    g = math.log(max(rh, 1) / 100) + a * t_c / (b + t_c)
    return b * g / (a - g)


def cloud_layer(prof: dict | None, merged, ti: int, i_up: int) -> tuple[float, float]:
    """(base, haut) de la couche nuageuse d'alizé en amont, en m. NaN si inconnu, inf si pas de haut net."""
    temps, rhs, alts = [], [], []
    if "t2m" in merged.data and "rh" in merged.data:
        t2, r2 = merged.data["t2m"][ti, i_up], merged.data["rh"][ti, i_up]
        if not (math.isnan(t2) or math.isnan(r2)):
            temps.append(t2), rhs.append(r2), alts.append(2)
    top = float("nan")
    if prof is not None:
        z, rh, t = prof["z"][:, i_up], prof["rh"][:, i_up], prof["t"][:, i_up]
        order = np.argsort(z)
        z, rh, t = z[order], rh[order], t[order]
        # « mean-layer LCL » : moyenne de l'air entre la surface et 500 m (Miller et al. 2018)
        for k in range(len(z)):
            if 0 < z[k] <= 500 and not (math.isnan(t[k]) or math.isnan(rh[k])):
                temps.append(t[k] - 273.15 if t[k] > 150 else t[k]), rhs.append(rh[k]), alts.append(z[k])
        sel = (z >= 500) & (z <= 3500) & ~np.isnan(rh)
        if sel.any():
            zz, rr = z[sel], rh[sel]
            below = rr >= 75
            if below.all():
                top = float("inf")
            elif below[0]:
                k = int(np.argmin(below))
                frac = (rr[k - 1] - 75) / max(rr[k - 1] - rr[k], 1e-6)
                top = float(zz[k - 1] + frac * (zz[k] - zz[k - 1]))
    if not temps:
        return float("nan"), top
    tm, rm, zm = float(np.mean(temps)), float(np.mean(rhs)), float(np.mean(alts))
    base = zm + 125 * (tm - dewpoint(tm, rm))
    return base, top


def state_from_layer(alt: float, base: float, top: float, model_state: str | None) -> str | None:
    if model_state == "nuage" or math.isnan(base) or math.isnan(top):
        return model_state
    if alt < base - MARGE_BASE:
        return model_state if model_state in ("incertain",) else "degage"   # sous la base des nuages
    if alt <= top - MARGE_HAUT:
        return "nuage"                                                       # dans le nuage orographique
    if alt < top + MARGE_HAUT:
        return "incertain"                                                   # à la limite du haut de la couche
    return "mer"                                                             # au-dessus de la couche


def compute_states(points_alt: dict[int, float], profiles: dict, merged, i_windward: int | None,
                   i_up: int | None = None) -> dict:
    """{(i_point, time_utc): (state, détails, source)} pour chaque heure de la base fusionnée."""
    out = {}
    i_up = i_windward if i_up is None else i_up
    for t in merged.times:
        prof = profiles.get(t)
        ti = merged.index[t]
        base, top = cloud_layer(prof, merged, ti, i_up) if i_up is not None else (float("nan"), float("nan"))
        for i, alt in points_alt.items():
            if prof is not None:
                st, det = state_from_profile(prof, i, alt, i_windward)
                if st is not None:
                    st = state_from_layer(alt, base, top, st)
                    det = {**det, "base": None if math.isnan(base) else round(base, -1),
                           "haut": None if math.isnan(top) else (9999 if math.isinf(top) else round(top, -1))}
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
    rise_src = (states.get((i, t_rise)) or (None, None, None))[2]
    set_src = (states.get((i, t_set)) or (None, None, None))[2]
    good = ("degage", "mer")
    lever = {"heure": _hm(rise), "etat": rise_state, "horizon": horizon_clear(merged, i_east, t_rise), "src": rise_src}
    coucher = {"heure": _hm(sset), "etat": set_state, "horizon": horizon_clear(merged, i_west, t_set), "src": set_src}
    def neighbour_ok(t):  # l'heure voisine (le soleil se lève/couche entre deux heures pleines) pas dans le nuage
        others = [states.get((i, t + timedelta(hours=k))) for k in (-1, 1)]
        return all(o is None or o[0] != "nuage" for o in others)

    lever["top"] = rise_state in good and lever["horizon"] is not False and neighbour_ok(t_rise)
    coucher["top"] = set_state in good and coucher["horizon"] is not False and neighbour_ok(t_set)
    lever["date"] = rise.astimezone(TZ).date().isoformat()
    coucher["date"] = sset.astimezone(TZ).date().isoformat()

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
    for kind, sun, i_h in (("lever", rise, i_east), ("coucher", sset, i_west)):
        (lever if kind == "lever" else coucher)["fenetre"] = window(sommet, i, states, merged, kind, sun, i_h)
    return {
        "nom": sommet["nom"], "alt": sommet["alt"], "hours": hours, "lever": lever, "coucher": coucher,
        "texte": ", ".join(texte), "source": "AROME" if src == {"AROME"} else ("mixte" if "AROME" in src else "ECMWF"),
    }


VUE = {"degage": "dégagé", "mer": "au-dessus des nuages"}


def sun_text(kind: str, sums: list[dict], key: str) -> str:
    """« coucher 17h38 au-dessus des nuages : La Soufrière · dégagé : Piton Baille-Argent ».

    « dégagé » = ciel clair autour du sommet ; « au-dessus des nuages » = sommet qui dépasse la couche
    nuageuse : mer de nuages en dessous, vue sur les autres îles mais pas forcément sur la côte."""
    groups: dict[str, list[str]] = {}
    for x in sums:
        groups.setdefault(VUE.get(x[key]["etat"], "dégagé"), []).append(x["nom"])
    return f"{kind} {sums[0][key]['heure']} " + " · ".join(f"{v} : {', '.join(n)}" for v, n in groups.items())


def montee_min(acces: dict | None) -> int | None:
    """Temps de montée (min) jusqu'au sommet.

    Depuis la fiche officielle (durée aller-retour, distance, D+) : on garde la durée officielle et on la partage
    entre montée et descente dans la proportion de la norme DIN 33466 des clubs alpins (300 m/h en montée,
    500 m/h en descente, 4 km/h à plat ; temps = le plus grand des deux + la moitié du plus petit)."""
    if not acces:
        return None
    if acces.get("montee_min"):
        return int(acces["montee_min"])
    f = acces.get("fiche")
    if not f:
        return None
    half_km, d = f["km"] / 2, f["dplus"]
    din = lambda v, h: max(v, h) + min(v, h) / 2  # noqa: E731
    up, down = din(d / 300, half_km / 4), din(d / 500, half_km / 4)
    return int(round(f["duree_h"] * 60 * up / (up + down) / 5) * 5)


def _dur(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    return f"{h}h{m:02d}" if h else f"{m} min"


def window(sommet: dict, i: int, states: dict, merged, kind: str, sun: datetime, i_h) -> dict:
    """Le créneau d'une pépite : heure de départ, et les conditions heure par heure jusqu'au lever / coucher."""
    from . import scoring
    acces = sommet.get("acces") or {}
    mm = montee_min(acces)
    sun_loc = sun.astimezone(TZ)
    dep = (sun - timedelta(minutes=mm)) if mm else None
    h0 = (dep.astimezone(TZ).hour if dep else max(FIRST_H, sun_loc.hour - 2))
    h1 = sun_loc.hour + 1
    lignes = []
    for h in range(h0, h1 + 1):
        t = datetime(sun_loc.year, sun_loc.month, sun_loc.day, h, tzinfo=TZ).astimezone(timezone.utc)
        st = states.get((i, t))
        ti = merged.index.get(t)
        if not st or ti is None:
            continue
        det = st[1] or {}
        parts = [f"{h}h : {STATES.get(st[0], (st[0] or '?',))[0].lower()}"]
        haut = det.get("haut")
        if haut is not None and not (isinstance(haut, float) and math.isnan(haut)):
            if haut >= 9000:
                parts.append("pas de plafond net à la couche")
            else:
                ecart = sommet["alt"] - haut
                parts.append(f"haut des nuages ~{haut:.0f} m, " + (f"sommet {ecart:.0f} m au-dessus" if ecart >= 0
                             else f"sommet {-ecart:.0f} m en dessous"))
        rain, _ = scoring.rain_stats(merged, scoring.rain_index(merged, ti), [i], scoring.RAIN_PCTL)
        parts.append(f"pluie {rain:.1f} mm".replace(".", ","))
        g = merged.data.get("gust")
        if g is not None and not math.isnan(g[ti, i]):
            parts.append(f"rafales {g[ti, i]:.0f} km/h")
        lignes.append(" · ".join(parts))
    hz = None
    t_sun = (sun + timedelta(minutes=30)).replace(minute=0, second=0, microsecond=0)
    ti = merged.index.get(t_sun)
    if ti is not None and i_h is not None and "lcc" in merged.data:
        lcc, mcc = merged.data["lcc"][ti, i_h], merged.data.get("mcc", merged.data["lcc"])[ti, i_h]
        if not math.isnan(lcc):
            ok = lcc < HORIZON_LOW and (math.isnan(mcc) or mcc < HORIZON_MID)
            hz = (f"Horizon {'est' if kind == 'lever' else 'ouest'} en mer : nuages bas {lcc:.0f} %, moyens "
                  f"{0 if math.isnan(mcc) else mcc:.0f} % → {'dégagé' if ok else 'bouché'} "
                  f"(seuils de l'outil {HORIZON_LOW} / {HORIZON_MID} %)")
    if mm:
        f = acces.get("fiche") or {}
        src = (f"fiche officielle : {_dur(int(f['duree_h'] * 60))} {f.get('type', '')} ; part de la montée selon "
               "la norme DIN 33466" if f else "temps renseigné à la main")
        creneau = (f"Départ du {acces.get('depart', 'parking')} vers {_hm(dep)}, montée ≈ {_dur(mm)} ({src}), "
                   f"au sommet pour le {kind} à {_hm(sun)}.")
    else:
        creneau = (f"Temps de montée non renseigné pour ce sommet (pas de fiche officielle exploitable) : "
                   f"conditions affichées à partir de {h0}h.")
    rappel = ("Descente de nuit : frontale indispensable. La charte de la randonnée en Guadeloupe conseille de ne "
              "pas partir après 15h." if kind == "coucher" else "Montée de nuit : frontale indispensable.")
    return {"depart": _hm(dep) if dep else None, "montee_min": mm, "creneau": creneau, "lignes": lignes,
            "horizon": hz, "rappel": rappel, "source": acces.get("source")}
