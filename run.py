"""Rapport du soir : quelles activités de Basse-Terre faire dans les 3 prochains jours,
et quand voir les sommets dégagés (lever, journée, coucher).

Usage : python run.py --out site [--history history]
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from meteo import apprendre, arome, avis, ecmwf, grid, lecture, marine, render, render_map, scoring, situation, sommets, webcams

log = logging.getLogger("rapport")
ROOT = Path(__file__).parent


def clean(x):
    """JSON valide pour un navigateur : NaN et infinis deviennent null."""
    if isinstance(x, float):
        return None if (x != x or x in (float("inf"), float("-inf"))) else x
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    if isinstance(x, np.generic):
        return clean(x.item())
    return x


class Points:
    """Liste dédupliquée des points où on lit la météo."""

    def __init__(self):
        self.coords, self.alts, self._idx = [], [], {}

    def add(self, p: dict) -> int:
        key = (round(p["lat"], 4), round(p["lon"], 4))
        if key not in self._idx:
            self._idx[key] = len(self.coords)
            self.coords.append(key)
            self.alts.append(p.get("alt", 0))
        return self._idx[key]


def load_config():
    cfg = json.loads((ROOT / "spots.json").read_text(encoding="utf-8"))
    pts = Points()
    for spot in cfg["spots"]:
        spot["_obj"], spot["_all"], spot["_obj_high"] = [], [], []
        spot["_high"] = spot["type"] == "sommet" or (
            spot["type"] == "itinerance" and max(p["alt"] for p in spot["points"]) >= 900)
        for p in spot["points"]:
            i = pts.add(p)
            spot["_all"].append(i)
            if p["role"] == "objectif":
                spot["_obj"].append(i)
                if spot["_high"] and p["alt"] >= 700:
                    spot["_obj_high"].append(i)
                    spot.setdefault("_names", {})[i] = f"{p['nom']} ({p['alt']} m)"
    for s in cfg.get("sommets", []):
        s["_i"] = pts.add(s)
    hz = cfg.get("horizons", {})
    idx_h = {k: pts.add(v) for k, v in hz.items() if isinstance(v, dict)}
    return cfg, pts, idx_h


def high_points(cfg, pts) -> dict[int, float]:
    """Points d'altitude (≥ 700 m) dont on calcule l'état : sommets + objectifs des sorties en altitude."""
    out = {s["_i"]: s["alt"] for s in cfg.get("sommets", [])}
    for spot in cfg["spots"]:
        for p in spot["points"]:
            i = pts.add(p)
            if i in spot["_obj_high"]:
                out[i] = p["alt"]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="site")
    ap.add_argument("--history", default=None, help="dossier où archiver les scores du jour")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    now = datetime.now(timezone.utc)
    cfg, pts, idx_h = load_config()
    n_spots = len(pts.coords)
    grid_cells = grid.cells()
    grid_idx = [pts.add({**c, "alt": 0}) for c in grid_cells]
    n = len(pts.coords)
    log.info("%d points d'activités + %d mailles de grille", n_spots, len(grid_cells))
    warnings, debug = [], {"points": [{"lat": la, "lon": lo, "alt": a} for (la, lo), a in zip(pts.coords, pts.alts)]}

    ec = ecmwf.fetch(pts.coords, pts.alts)
    if ec is None:
        warnings.append("ECMWF (Open-Meteo) indisponible : les heures au-delà d'AROME ne sont pas calculées.")
    ens = ecmwf.fetch_ensemble(pts.coords[:n_spots])  # ensemble sur les activités seulement (volume)
    if ens is not None:
        full = np.full(ens["precip_ens"].shape[:1] + (n,) + ens["precip_ens"].shape[2:], np.nan)
        full[:, :n_spots] = ens["precip_ens"]
        ens["precip_ens"] = full
    else:
        warnings.append("Ensemble ECMWF indisponible : au-delà d'AROME, pluie en un seul scénario (pas de probabilité).")
    som0 = cfg.get("sommets", [{}])[0]
    dust = ecmwf.fetch_dust(som0.get("lat", 16.04), som0.get("lon", -61.66))
    debug.update({"ensemble": ens and {"model": ens["model"], "membres": ens["n_members"]},
                  "poussieres": dust is not None})

    ar, ar_lag, profiles, run_txt = None, None, {}, "AROME indisponible"
    try:
        found = arome.find_run(now)
        if found:
            run, hmax = found
            results, inventory, grid_info = arome.download(run, hmax, pts.coords)
            ar = arome.to_series(run, hmax, results, inventory, n)
            end_local = (run + timedelta(hours=hmax)).astimezone(scoring.TZ)
            run_txt = (f"AROME Antilles run {run:%d/%m %Hh} UTC (jusqu'à {render.fdate(end_local.date())} "
                       f"{end_local.hour}h)")
            debug.update({"run": run.isoformat(), "hmax": hmax, "keys": ar["keys"], "precip_mode": ar.get("precip_mode"),
                          "inventory": inventory, "grid": grid_info, "files_read": len(results)})
            missing = [k for k in ("precip", "lcc", "rh", "gust") if k not in ar]
            if missing:
                warnings.append(f"Champs AROME non trouvés : {', '.join(missing)} (remplacés par ECMWF).")

            # Run précédent (pluie seulement) : « ensemble décalé », 2 scénarios AROME au lieu d'un
            try:
                prev = arome.find_run(now, before=run, paquets=("SP1",))
                if prev:
                    run2, hmax2 = prev
                    res2, inv2, _ = arome.download(run2, hmax2, pts.coords, paquets=("SP1",))
                    ar_lag = arome.to_series(run2, hmax2, res2, inv2, n)
                    debug["run_precedent"] = run2.isoformat()
                    run_txt += f" + run précédent {run2:%d/%m %Hh} UTC pour la pluie"
            except Exception as e:  # noqa: BLE001
                log.exception("Run précédent en échec")
                warnings.append(f"Run AROME précédent non lu ({e.__class__.__name__}) : probabilités sur un seul run.")

            # Profils verticaux, seulement aux heures de jour (lever → coucher)
            hours = [h for h in range(0, hmax + 1)
                     if sommets.FIRST_H - 1 <= (run + timedelta(hours=h)).astimezone(scoring.TZ).hour <= sommets.LAST_H]
            try:
                res_p, inv_p, _ = arome.download(run, hmax, pts.coords, paquets=arome.PAQUETS_PROFIL, hours=hours)
                pr = arome.to_profiles(run, res_p, inv_p, hours, n)
                profiles = pr["profiles"]
                debug.update({"inventory_profil": inv_p, "profil_niveaux": pr["used"], "profil_heures": len(profiles)})
                if not profiles:
                    warnings.append("Profils verticaux AROME non lus : état des sommets estimé depuis la surface.")
            except Exception as e:  # noqa: BLE001
                log.exception("Profils AROME en échec")
                warnings.append(f"Profils verticaux AROME en échec ({e.__class__.__name__}).")
        else:
            warnings.append("Aucun run AROME récent publié : prévision ECMWF seule, moins précise sur le relief.")
    except Exception as e:  # noqa: BLE001 — le rapport doit sortir même sans AROME
        log.exception("AROME en échec")
        warnings.append(f"AROME en échec ({e.__class__.__name__}) : prévision ECMWF seule.")

    debug["runs_publies"] = arome.AVAILABILITY
    sources = run_txt + (f" · au-delà : {ec['model']}" if ec else "") + (
        f" et ensemble {ens['model']} ({ens['n_members']} scénarios)" if ens else "") + " (Open-Meteo)"
    merged = scoring.merge(ar, ec, n, arome_lag=ar_lag, ens=ens)

    # Mer : vagues aux points en mer (activités, cases, références au large)
    sea_idx = sorted({i for s in cfg["spots"] if s["type"] == "mer" for i in s["_obj"]}
                     | {i for c, i in zip(grid_cells, grid_idx) if c["kind"] == "mer"}
                     | {idx_h[k] for k in ("mer_est", "mer_nord") if k in idx_h})
    sea = marine.fetch([pts.coords[i] for i in sea_idx]) if sea_idx else None
    if sea:
        full = {"times": sea["times"]}
        for k in ("hs", "sw", "per", "dir"):
            arr = np.full((len(sea["times"]), n), np.nan)
            arr[:, sea_idx] = sea[k]
            full[k] = arr
        scoring.add_series(merged, full, ("hs", "sw", "per", "dir"))
        sources += " · vagues : Open-Meteo Marine"
    else:
        warnings.append("Modèle de vagues indisponible : activités en mer non notées.")
    debug["mer_points"] = len(sea_idx)
    # état « dans le nuage » : sommets + objectifs en altitude à leur altitude réelle,
    # mailles de la grille à l'altitude de leur relief (lissé) dans le modèle
    grid_alts = [grid.model_altitude(merged, i) for i in grid_idx]
    pts_alt = high_points(cfg, pts)
    for i, a in zip(grid_idx, grid_alts):
        pts_alt.setdefault(i, (0 if np.isnan(a) else a) + 20)
    merged.summit_state = sommets.compute_states(pts_alt, profiles, merged, idx_h.get("au_vent"), idx_h.get("est"))

    local = now.astimezone(scoring.TZ)
    today = local.date()
    # Avant 15h, le rapport couvre aujourd'hui (heures restantes), demain, après-demain ;
    # le rapport du soir couvre les 3 jours suivants.
    first = 0 if local.hour < 15 else 1
    names = {0: "Aujourd'hui", 1: "Demain", 2: "Après-demain", 3: "Dans 3 jours"}
    days = []
    for k in range(first, first + 3):
        d = today + timedelta(days=k)
        # Aujourd'hui : on calcule aussi les heures déjà passées (affichées, marquées « passé »)
        all_ = [(s, scoring.evaluate_day(s, merged, d)) for s in cfg["spots"]]
        if k == 0:
            for _, r_ in all_:
                if r_.get("end") and int(r_["end"].rstrip("h")) <= local.hour:
                    r_["passe"] = True
        for s_, r_ in all_:
            r_["lecture"] = lecture.lines(s_, r_)
        days.append({
            "date": d.isoformat(),
            "title": f"{names[k]} · {render.fdate(d)}",
            "short": render.fdate(d).split(" ")[0][:3] + f". {d.day}",
            "all": all_,
            "top": scoring.top3(all_),
            "couverture": render.coverage(merged, d),
            "situation": situation.day_situation(d, profiles, idx_h.get("est"), merged, idx_h.get("est"),
                                                 dust=dust),
            "sommets": [sommets.day_summary(s, s["_i"], merged.summit_state, merged, d,
                                            idx_h.get("est"), idx_h.get("ouest")) for s in cfg.get("sommets", [])],
        })
    nb_today = now if first == 0 else None
    grid_data = grid.compute(merged, grid_idx, grid_alts, [date.fromisoformat(d["date"]) for d in days], nb_today,
                             kinds=[c["kind"] for c in grid_cells])
    grid_data["cells"] = [{"lat": c["lat"], "lon": c["lon"], "kind": c["kind"], "ile": c["ile"], "size": c["size"],
                           "alt": None if (np.isnan(a) or c["kind"] == "mer") else round(a)}
                          for c, a in zip(grid_cells, grid_alts)]
    grid_data["step"] = grid.STEP
    grid_data["echelles"] = lecture.scales()
    grid_data["pen_labels"] = scoring.PEN_LABELS
    # Contrôles de cohérence des dates et heures (heure de Guadeloupe) : visibles dans debug.json
    controles = []
    for d in days:
        for x in d["sommets"]:
            for k in ("lever", "coucher"):
                if x[k].get("date") != d["date"]:
                    controles.append(f"{x['nom']} {k} daté du {x[k].get('date')} au lieu du {d['date']}")
            hh = {h["h"]: h["state"] for h in x["hours"]}
            for k in ("lever", "coucher"):
                hr, mn = (int(v) for v in x[k]["heure"].split("h"))
                near = hr + (1 if mn >= 30 else 0)
                if near in hh and hh[near] != x[k]["etat"]:
                    controles.append(f"{x['nom']} {k} {x[k]['heure']} : état {x[k]['etat']} ≠ barre à {near}h ({hh[near]})")
    debug["controles"] = controles or ["OK : levers, couchers et barres horaires cohérents, dates en heure de Guadeloupe"]
    if controles:
        warnings.append(f"{len(controles)} incohérence(s) d'heures détectée(s) : voir debug.json.")
    for d in days:
        dd = date.fromisoformat(d["date"])
        d["situation"]["texte"] = d["situation"].get("texte", []) + situation.islands_and_sea(
            dd, merged, d["situation"].get("wind", float("nan")), idx_h.get("mer_est"), idx_h.get("mer_nord"))
        d["avis"] = avis.day_avis(dd, now, merged, cfg["spots"], d["top"], d["situation"], d["sommets"],
                                  {"ar": ar, "ar_lag": ar_lag, "ec": ec, "ens": ens}, idx_h)
    report = {
        "generated": f"{render.fdate(local.date())} à {local.hour}h{local:%M}",
        "sources": sources, "warnings": warnings, "days": days, "spots": cfg["spots"],
        "exclus": cfg.get("exclus", []), "webcams": webcams.fetch(cfg.get("webcams", [])),
    }

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "liste.html").write_text(render.page(report), encoding="utf-8")
    (out / "index.html").write_text(render_map.page(), encoding="utf-8")
    (out / "apprendre.html").write_text(apprendre.page(), encoding="utf-8")
    (out / "grid.json").write_text(json.dumps(clean(grid_data), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    def geo(spot):
        p = next(p for p in spot["points"] if p["role"] == "objectif")
        cat = render.cat_of(spot)
        return {"id": spot["id"], "nom": spot["nom"], "cat": cat, "type": spot["type"], "ile": spot.get("ile", ""),
                "lat": p["lat"],
                "lon": p["lon"], "secteur": spot["secteur"], "niveau": spot["niveau"],
                "acces": spot.get("acces", ""), "conseil": spot.get("conseil", "")}

    compact = {
        "generated_utc": now.isoformat(), "generated": report["generated"], "sources": sources, "warnings": warnings,
        "spots": [geo(s) for s in cfg["spots"]],
        "webcams": report["webcams"],
        "pepites": render.pepites_list(report),
        "days": [{
            "date": d["date"], "title": d["title"], "couverture": d["couverture"],
            "top": [s["id"] for s, _ in d["top"]],
            "scores": {s["id"]: {k: r.get(k) for k in ("score", "label", "start", "end", "source", "reasons", "passe",
                                                         "detail", "mesures", "lecture")}
                       for s, r in d["all"]},
            "situation": d["situation"], "avis": d["avis"],
            "sommets": {x["nom"]: {"etats": {h["h"]: h["state"] for h in x["hours"]},
                                   "details": {h["h"]: h["det"] for h in x["hours"]},
                                   "lever": x["lever"], "coucher": x["coucher"], "texte": x["texte"]}
                        for x in d["sommets"]},
        } for d in days],
    }
    (out / "data.json").write_text(json.dumps(clean(compact), ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (out / "debug.json").write_text(json.dumps(clean(debug), ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    if args.history:
        h = Path(args.history)
        h.mkdir(parents=True, exist_ok=True)
        (h / f"{local:%Y-%m-%d_%Hh}.json").write_text(json.dumps(clean(compact), ensure_ascii=False, default=str), encoding="utf-8")
    for d in days:
        log.info("%s : %s", d["title"], ", ".join(f"{s['nom']} ({r['score']})" for s, r in d["top"]) or "rien")
        sf = d["sommets"][0] if d["sommets"] else None
        if sf:
            log.info("  %s : lever %s, %s", sf["nom"], sf["lever"]["etat"], sf["texte"])


if __name__ == "__main__":
    main()
